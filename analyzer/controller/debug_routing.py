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
            # Klucz może mieć różne nazwy: ig_md.delta_lo, ig_md.delta,
            # ig_md.delta[15:0]. Bierzemy pierwszy klucz typu Range
            # (nie $MATCH_PRIORITY, ma low/high).
            low = high = "?"
            for k_name, k_val in k.items():
                if k_name == "$MATCH_PRIORITY":
                    continue
                if isinstance(k_val, dict) and "low" in k_val:
                    low = k_val.get("low", "?")
                    high = k_val.get("high", "?")
                    break
            prio = k.get("$MATCH_PRIORITY", {}).get("value", "?")
            b = d.get("b", "?")
            bins.append((low, high, b, prio))
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
        return 0
    print(f"  [{label}] histogram_bin_map: {n} wpisów")
    if n > 0:
        # Sortuj po bin
        srt = sorted(bins, key=lambda x: x[2] if isinstance(x[2], int) else 999)
        print(f"    pierwszy: bin={srt[0][2]:>3} low={srt[0][0]:>5} high={srt[0][1]:>5} priority={srt[0][3]}")
        # Bin 64 (delta baseline ~640-649) — działa
        # Bin 100 (delta DUT ~1000-1009) — nie działa, kluczowy do diagnozy
        for low, high, b, prio in srt:
            if b in (64, 100):
                tag = "← baseline (DZIAŁA)" if b == 64 else "← DUT (NIE DZIAŁA)"
                print(f"    BIN {b}:  bin={b:>3} low={low:>5} high={high:>5} priority={prio}   {tag}")
        print(f"    ostatni:  bin={srt[-1][2]:>3} low={srt[-1][0]:>5} high={srt[-1][1]:>5} priority={srt[-1][3]}")
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
