from discord.ext.voice_recv import opus as vr_opus
import dave as _dave
import davey_compat


_diag = {"total": 0, "ds_found": 0, "ds_ready": 0,
        "decrypt_ok": 0, "decrypt_none": 0, "data_changed": 0}


def apply_dave_patch():
    original_decode = vr_opus.PacketDecoder._decode_packet

    def patched_decode(self, packet):
        _diag["total"] += 1

        ds = davey_compat.get_active_session()
        if ds is not None:
            _diag["ds_found"] += 1
            if ds.ready:
                _diag["ds_ready"] += 1

                pkt_user_id = getattr(packet, "user_id", None)
                pkt_ssrc = getattr(packet, "ssrc", None)
                
                if _diag["ds_ready"] <= 3:
                    print(f"[patch] pkt#{_diag['ds_ready']}: "
                        f"user_id={pkt_user_id}, ssrc={pkt_ssrc}, "
                        f"size={len(packet.decrypted_data) if packet.decrypted_data else 0}",
                        flush=True)

                if not pkt_user_id and pkt_ssrc:
                    try:
                        sink = self.router.sink
                        vc = sink.voice_client
                        pkt_user_id = vc._get_id_from_ssrc(pkt_ssrc)
                        if _diag["ds_ready"] <= 3:
                            print(f"[patch] resolved ssrc {pkt_ssrc} -> user_id {pkt_user_id}", 
                                flush=True)
                    except Exception as e:
                        if _diag["ds_ready"] <= 3:
                            print(f"[patch] ssrc->user resolution failed: {e}", flush=True)

                original_data = packet.decrypted_data
                try:
                    decrypted = ds.decrypt(
                        pkt_user_id or 0,
                        _dave.MediaType.audio,
                        original_data,
                    )
                    if decrypted is None:
                        _diag["decrypt_none"] += 1
                    else:
                        _diag["decrypt_ok"] += 1
                        if decrypted != original_data:
                            _diag["data_changed"] += 1
                        packet.decrypted_data = decrypted
                except Exception as e:
                    print(f"[patch] decrypt EXCEPTION: {e}", flush=True)

        if _diag["total"] % 50 == 0:
            print(f"[patch stats] {_diag}", flush=True)

        return original_decode(self, packet)

    vr_opus.PacketDecoder._decode_packet = patched_decode
    print("✅ voice_recv DAVE patch applied (using global registry)")