#!/usr/bin/env python3
"""
Diagnostyka tablicy port_routing.

Sprawdza ile wpisów jest na każdym z 4 pipes Tofino-1. Używa entry_iter
zamiast entry_get([]) — to ostatnie nie zawsze działa z pustą listą kluczy.
"""
import sde_paths  # noqa: F401
import bfrt_grpc.client as gc

import config

NUM_PIPES = 4


def fmt_ip(v):
    if isinstance(v, int):
        return f"{(v>>24)&0xff}.{(v>>16)&0xff}.{(v>>8)&0xff}.{v&0xff}"
    if isinstance(v, bytes):
        return ".".join(str(b) for b in v[-4:])
    return str(v)


def dump_pipe(bfrt, pipe_id):
    target = gc.Target(device_id=0, pipe_id=pipe_id)
    tbl = bfrt.table_get("pipe.SwitchIngress.port_routing")

    count = 0
    print(f"\n--- pipe {pipe_id} ---")
    try:
        # Próba 1: entry_iter (zwraca wszystko)
        for data, key in tbl.entry_iter(target):
            count += 1
            k = key.to_dict()
            d = data.to_dict()
            ing = k.get("ig_intr_md.ingress_port", {}).get("value", "?")
            dst_d = k.get("hdr.ipv4.dst_addr", {})
            dst = fmt_ip(dst_d.get("value", "?"))
            pl  = dst_d.get("prefix_len", "?")
            act = d.get("action_name", "?")
            params = {k2:v for k2,v in d.items() if not k2.startswith("$") and k2 != "action_name"}
            print(f"  ingress={ing:>4}, dst={dst}/{pl}, action={act}, {params}")
    except AttributeError:
        # entry_iter może nie istnieć w starszych BF-RT
        print(f"  (entry_iter unavailable, fallback to entry_get with target.pipe_id=0xffff)")
        target_all = gc.Target(device_id=0, pipe_id=0xffff)
        for data, key in tbl.entry_get(target_all):
            count += 1
    except Exception as e:
        print(f"  ERROR: {e}")
        return -1

    print(f"  total: {count}")
    return count


def main():
    interface = gc.ClientInterface(config.GRPC_ADDR, client_id=0, device_id=0)
    interface.bind_pipeline_config(config.PROGRAM)
    bfrt = interface.bfrt_info_get(config.PROGRAM)

    print(f"[*] Dump pipe.SwitchIngress.port_routing per pipe")
    totals = {}
    for p in range(NUM_PIPES):
        totals[p] = dump_pipe(bfrt, p)

    print(f"\n--- podsumowanie ---")
    for p, n in totals.items():
        flag = "✓" if n > 0 else ("✗" if n == 0 else "?")
        print(f"  pipe {p}: {n} wpisów  {flag}")


if __name__ == "__main__":
    main()
