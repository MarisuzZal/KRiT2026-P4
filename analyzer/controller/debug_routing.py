#!/usr/bin/env python3
"""
Diagnostyka tablicy port_routing per-pipe.

Pokaże ile wpisów jest w każdym z 4 pipes Tofino-1. Jeśli wpisy są
tylko w niektórych pipes, mamy zidentyfikowany problem.

Uruchomienie:
    SDE_INSTALL=... python3 analyzer/controller/debug_routing.py
"""
import sde_paths  # noqa: F401
import bfrt_grpc.client as gc

import config

NUM_PIPES = 4   # Tofino-1 4-pipe


def main():
    interface = gc.ClientInterface(config.GRPC_ADDR, client_id=0, device_id=0)
    interface.bind_pipeline_config(config.PROGRAM)
    bfrt = interface.bfrt_info_get(config.PROGRAM)

    print(f"[*] Dump pipe.SwitchIngress.port_routing per pipe\n")

    for pipe_id in range(NUM_PIPES):
        target = gc.Target(device_id=0, pipe_id=pipe_id)
        tbl = bfrt.table_get("pipe.SwitchIngress.port_routing")

        count = 0
        try:
            resp = tbl.entry_get(target, [], {"from_hw": True})
            for data, key in resp:
                count += 1
                k = key.to_dict()
                d = data.to_dict()
                ing = k.get("ig_intr_md.ingress_port", {}).get("value", "?")
                dst = k.get("hdr.ipv4.dst_addr", {})
                dst_val = dst.get("value", "?")
                dst_pl  = dst.get("prefix_len", "?")
                # IP int -> dotted
                if isinstance(dst_val, int):
                    dst_val = f"{(dst_val>>24)&0xff}.{(dst_val>>16)&0xff}.{(dst_val>>8)&0xff}.{dst_val&0xff}"
                print(f"  pipe {pipe_id}: ingress={ing:>4}, dst={dst_val}/{dst_pl}, action={d.get('action_name','?')}")
        except Exception as e:
            print(f"  pipe {pipe_id}: ERROR {e}")
            continue

        print(f"[OK] pipe {pipe_id}: {count} wpisów\n")


if __name__ == "__main__":
    main()
