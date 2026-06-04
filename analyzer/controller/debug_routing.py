#!/usr/bin/env python3
"""
Diagnostyka tablicy port_routing. W SDE 9.13.4 entry per-pipe (0..3)
zwraca INVALID_ARGUMENT, więc dumpujemy tylko z target.pipe_id=0xffff.
"""
import sde_paths  # noqa: F401
import bfrt_grpc.client as gc

import config


def fmt_ip(v):
    if isinstance(v, int):
        return f"{(v>>24)&0xff}.{(v>>16)&0xff}.{(v>>8)&0xff}.{v&0xff}"
    if isinstance(v, bytes):
        return ".".join(str(b) for b in v[-4:])
    return str(v)


def main():
    interface = gc.ClientInterface(config.GRPC_ADDR, client_id=0, device_id=0)
    interface.bind_pipeline_config(config.PROGRAM)
    bfrt = interface.bfrt_info_get(config.PROGRAM)

    target = gc.Target(device_id=0, pipe_id=0xffff)  # ALL pipes
    tbl = bfrt.table_get("pipe.SwitchIngress.port_routing")

    print("[*] Dump pipe.SwitchIngress.port_routing (pipe_id=0xffff)\n")
    count = 0
    try:
        for data, key in tbl.entry_iter(target):
            count += 1
            k = key.to_dict()
            d = data.to_dict()
            ing = k.get("ig_intr_md.ingress_port", {}).get("value", "?")
            dst_d = k.get("hdr.ipv4.dst_addr", {})
            dst = fmt_ip(dst_d.get("value", "?"))
            pl  = dst_d.get("prefix_len", "?")
            act = d.get("action_name", "?").replace("SwitchIngress.", "")
            params = {k2: v for k2, v in d.items()
                      if not k2.startswith("$") and k2 != "action_name"}
            print(f"  ingress={ing:>4}, dst={dst}/{pl}, {act}, {params}")
    except Exception as e:
        print(f"ERROR: {e}")

    print(f"\n[OK] Razem: {count} wpisów")


if __name__ == "__main__":
    main()
