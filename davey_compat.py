from __future__ import annotations

import datetime
import dave

_active_sessions = {}

def get_active_session():
    for s in _active_sessions.values():
        if s.ready:
            return s
    return None

DAVE_PROTOCOL_VERSION: int = dave.get_max_supported_protocol_version()

class ProposalsOperationType:
    append = 0
    revoke = 1

class CommitWelcome:
    __slots__ = ("commit", "welcome")

    def __init__(self, data: bytes) -> None:
        self.commit = data
        self.welcome = None

class _EncryptionStats:
    __slots__ = ("attempts", "successes", "failures")

    def __init__(self, s) -> None:
        self.attempts = getattr(s, "encrypt_attempts", 0)
        self.successes = getattr(s, "encrypt_success_count", 0)
        self.failures = getattr(s, "encrypt_failure_count", 0)

class SessionStatus:
    inactive = 0
    pending = 1
    active = 3

class DaveSession:

    _SSRC: int = 0
    _ZERO = datetime.timedelta(0)

    def __init__(self, protocol_version: int, user_id: int, channel_id: int) -> None:
        self._protocol_version = protocol_version
        self._user_id = user_id
        self._channel_id = channel_id
        self._voice_state = None

        self._session = dave.Session(mls_failure_callback=self._on_mls_failure)

        self._encryptor = dave.Encryptor()
        self._encryptor.assign_ssrc_to_codec(self._SSRC, dave.Codec.opus)
        self._encryptor.set_passthrough_mode(True)

        self._decryptor = dave.Decryptor()
        try:
            self._decryptor.transition_to_passthrough_mode(True, self._ZERO)
        except Exception as e:
            print(f"[DAVE] decryptor passthrough init failed: {e}", flush=True)

        self._installed_ratchets: set[int] = set()

        self._ready = False
        self._epoch = None
        self.status = SessionStatus.inactive
        self.voice_privacy_code: str | None = None

        self._do_init()

    def _on_mls_failure(self, reason, detail) -> None:
        print(f"[DAVE] MLS failure: {reason} – {detail}", flush=True)

    def _do_init(self) -> None:
        self._session.init(
            self._protocol_version,
            self._channel_id,
            str(self._user_id),
        )
        self.status = SessionStatus.pending

    def _get_recognized_users(self) -> set:
        users = {str(self._user_id)}
        if self._voice_state is not None:
            try:
                channel = self._voice_state.voice_client.channel
                for member in channel.members:
                    users.add(str(member.id))
            except Exception as exc:
                print(f"[DAVE] Could not read channel members: {exc}", flush=True)
        return users

    def _refresh_key(self) -> None:
        own_ratchet = self._session.get_key_ratchet(str(self._user_id))
        if own_ratchet is None:
            print("[DAVE] WARNING: own ratchet is None", flush=True)
            return

        self._encryptor.set_key_ratchet(own_ratchet)
        self._encryptor.set_passthrough_mode(False)

        self._installed_ratchets.clear()

        try:
            self._decryptor.transition_to_passthrough_mode(False, self._ZERO)
        except Exception as e:
            print(f"[DAVE] decryptor passthrough off failed: {e}", flush=True)

        self._ready = True
        self.status = SessionStatus.active
        _active_sessions[self._channel_id] = self
        print(f"[DAVE] Session ready (channel {self._channel_id})", flush=True)

    def _ensure_user_ratchet(self, user_id: int) -> bool:
        if user_id in self._installed_ratchets:
            return True
        if user_id == 0:
            print(f"[DAVE] _ensure: user_id is 0, skip", flush=True)
            return False

        try:
            ratchet = self._session.get_key_ratchet(str(user_id))
            print(f"[DAVE] get_key_ratchet({user_id}) -> {ratchet!r} "
                f"(type: {type(ratchet).__name__})", flush=True)
            
            if ratchet is None:
                try:
                    auth = self._session.get_last_epoch_authenticator()
                    print(f"[DAVE] last_epoch_auth: {auth}", flush=True)
                except Exception as e:
                    print(f"[DAVE] cannot get auth: {e}", flush=True)
                return False
            
            self._decryptor.transition_to_key_ratchet(ratchet, self._ZERO)
            self._installed_ratchets.add(user_id)
            print(f"[DAVE] ✅ ratchet installed for user {user_id}", flush=True)
            return True
        except Exception as e:
            print(f"[DAVE] _ensure exception for {user_id}: {type(e).__name__}: {e}", 
                flush=True)
            import traceback
            traceback.print_exc()
            return False

    def reinit(self, protocol_version: int, user_id: int, channel_id: int) -> None:
        _active_sessions.pop(self._channel_id, None)
        self._protocol_version = protocol_version
        self._user_id = user_id
        self._channel_id = channel_id
        self._session.reset()
        self._ready = False
        self._epoch = None
        self.status = SessionStatus.inactive
        self._encryptor.set_key_ratchet(None)
        self._encryptor.set_passthrough_mode(True)
        self._installed_ratchets.clear()
        try:
            self._decryptor.transition_to_passthrough_mode(True, self._ZERO)
        except Exception:
            pass
        self._do_init()

    def reset(self) -> None:
        self._session.reset()
        self._ready = False
        self._epoch = None
        self.status = SessionStatus.inactive
        self._encryptor.set_key_ratchet(None)
        self._encryptor.set_passthrough_mode(True)
        self._installed_ratchets.clear()
        try:
            self._decryptor.transition_to_passthrough_mode(True, self._ZERO)
        except Exception:
            pass
        _active_sessions.pop(self._channel_id, None)

    def get_serialized_key_package(self) -> bytes:
        return self._session.get_marshalled_key_package()

    def set_external_sender(self, data: bytes) -> None:
        self._session.set_external_sender(data)

    def set_passthrough_mode(self, passthrough: bool, transition_expiry=None) -> None:
        self._encryptor.set_passthrough_mode(passthrough)
        try:
            self._decryptor.transition_to_passthrough_mode(passthrough, self._ZERO)
        except Exception:
            pass

    def process_proposals(self, optype, proposals: bytes):
        optype_byte = bytes([0 if optype == ProposalsOperationType.append else 1])
        full_data = optype_byte + proposals
        recognized = self._get_recognized_users()
        try:
            result = self._session.process_proposals(full_data, recognized)
        except Exception as exc:
            print(f"[DAVE] process_proposals FAILED: {exc}", flush=True)
            return None
        if result is not None:
            return CommitWelcome(result)
        return None

    def process_commit(self, commit: bytes) -> None:
        result = self._session.process_commit(commit)
        if isinstance(result, dave.RejectType):
            raise RuntimeError(f"DAVE commit rejected: {result.name}")
        if isinstance(result, dict) and result:
            self._epoch = max(result.keys())
        self._refresh_key()

    def process_welcome(self, welcome: bytes) -> None:
        recognized = self._get_recognized_users()
        try:
            result = self._session.process_welcome(welcome, recognized)
        except Exception as exc:
            print(f"[DAVE] process_welcome FAILED: {exc}", flush=True)
            raise
        if result is None:
            raise RuntimeError("DAVE welcome rejected by libdave")
        if isinstance(result, dict) and result:
            self._epoch = max(result.keys())
        self._refresh_key()

    def encrypt_opus(self, data: bytes) -> bytes:
        result = self._encryptor.encrypt(dave.MediaType.audio, self._SSRC, data)
        return result if result is not None else data

    def decrypt(self, user_id: int, media_type, packet: bytes) -> bytes | None:
        try:
            if not hasattr(self, "_decrypt_call_count"):
                self._decrypt_call_count = 0
            self._decrypt_call_count += 1
            if self._decrypt_call_count <= 3:
                print(f"[DAVE.decrypt] call#{self._decrypt_call_count}: "
                    f"user_id={user_id}, packet_size={len(packet)}", flush=True)

            self._ensure_user_ratchet(user_id)

            mtype = media_type if media_type is not None else dave.MediaType.audio
            result = self._decryptor.decrypt(mtype, packet)
            return bytes(result) if result is not None else None
        except Exception:
            return None

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def epoch(self):
        return self._epoch


    def get_user_ids(self) -> list:
        return []

    def get_encryption_stats(self):
        try:
            return _EncryptionStats(self._encryptor.get_stats(dave.MediaType.audio))
        except Exception:
            return type("_S", (), {"attempts": 0, "successes": 0, "failures": 0})()

    def __repr__(self) -> str:
        return (f"<DaveSession(libdave) epoch={self._epoch} ready={self._ready} "
                f"status={self.status}>")


def patch_reinit(voice_state_module) -> None:
    original = voice_state_module.VoiceConnectionState.reinit_dave_session

    async def _patched(self_state):
        await original(self_state)
        ds = self_state.dave_session
        if ds is not None and isinstance(ds, DaveSession):
            ds._voice_state = self_state

    voice_state_module.VoiceConnectionState.reinit_dave_session = _patched