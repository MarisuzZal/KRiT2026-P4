#!/usr/bin/env python3
"""
Diagnostyka tablic measurement.p4.

Dumpuje:
  - pipe.SwitchIngress.port_routing       (16 wpisów: fan-in/out DUT + baseline)
  - pipe.SwitchIngress.histogram_bin_map  (128 wpisów range-match)

Próbuje DEV_PIPE_ALL (0xffff) jako pierwszy, potem per-pipe (0..3) jako
fallback diagnostyczny. Per-pipe pokaże czy bf-p4c wstawił wpisy tylko
do niektórych pipes (= bug).
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


def dump_port_routing(bfrt, target, label):
    tbl = bfrt.table_get("pipe.SwitchIngress.port_routing")
    n = 0
    try:
        resp = tbl.entry_get(target, flags={"from_hw": True})
        for data, key in resp:
            n += 1
            k = key.to_dict()
            d = data.to_dict()
            ing = k.get("ig_intr_md.ingress_port", {}).get("value", "?")
            dst_d = k.get("hdr.ipv4.dst_addr", {})
            dst = fmt_ip(dst_d.get("value", "?"))
            pl  = dst_d.get("prefix_len", "?")
            act = d.get("action_name", "?").replace("SwitchIngress.", "")
            params = {k2: v for k2, v in d.items()
                      if not k2.startswith("$") and k2 not in ("action_name", "is_default_entry")}
            print(f"  [{label}] ingress={ing:>4}, dst={dst}/{pl}, {act}, {params}")
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
    return n


def dump_histogram_bin_map(bfrt, target, label):
    tbl = bfrt.table_get("pipe.SwitchIngress.histogram_bin_map")
    n = 0
    bins = []
    try:
        resp = tbl.entry_get(target, flags={"from_hw": True})
        for data, key in resp:
            n += 1
            k = key.to_dict()
            d = data.to_dict()
            delta_d = k.get("ig_md.delta", k.get("ig_md.delta_lo", {}))
            low = delta_d.get("low", "?")
            high = delta_d.get("high", "?")
            b = d.get("b", "?")
            bins.append((low, high, b))
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
        return 0
    print(f"  [{label}] histogram_bin_map: {n} wpisów")
    if n > 0:
        print(f"    pierwszy: low={bins[0][0]} high={bins[0][1]} bin={bins[0][2]}")
        print(f"    ostatni:  low={bins[-1][0]} high={bins[-1][1]} bin={bins[-1][2]}")
    return n


def main():
    interface = gc.ClientInterface(config.GRPC_ADDR, client_id=0, device_id=0)
    interface.bind_pipeline_config(config.PROGRAM)
    bfrt = interface.bfrt_info_get(config.PROGRAM)

    print("=" * 78)
    print("DUMP: pipe.SwitchIngress.port_routing")
    print("=" * 78)

    target_all = gc.Target(device_id=0, pipe_id=0xffff)
    n_all = dump_port_routing(bfrt, target_all, "ALL")
    print(f"\n  → razem (pipe_id=ALL): {n_all} wpisów")

    print("\n  --- diagnostyka per-pipe ---")
    for pid in range(4):
        target_p = gc.Target(device_id=0, pipe_id=pid)
        n = dump_port_routing(bfrt, target_p, f"pipe{pid}")
        print(f"  → pipe {pid}: {n} wpisów")

    print("\n" + "=" * 78)
    print("DUMP: pipe.SwitchIngress.histogram_bin_map")
    print("=" * 78)
    dump_histogram_bin_map(bfrt, target_all, "ALL")
    for pid in range(4):
        target_p = gc.Target(device_id=0, pipe_id=pid)
        dump_histogram_bin_map(bfrt, target_p, f"pipe{pid}")


if __name__ == "__main__":
    main()
