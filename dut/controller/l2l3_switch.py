#!/usr/bin/env python3
"""
Kontroler dla l2l3_switch.p4 — klasyczny przełącznik L2/L3.

Programuje:
  * mac_lookup       — przykładowe dst MAC -> port
  * ipv4_lookup      — przykładowe podsieci -> (port, next-hop MAC)
"""
import sde_paths  # noqa: F401  # MUSI być przed bfrt_grpc
import bfrt_grpc.client as gc
from common import (connect, entry_add_or_mod, ip_to_int, mac_to_int,
                    PORT_FROM_ANALYZER_A, PORT_FROM_ANALYZER_B,
                    T2_PORT_A0, T2_PORT_A1, T2_PORT_B0, T2_PORT_B1)
from ports import configure_all_ports

PROGRAM = "l2l3_switch"


def program_mac_lookup(bfrt, target):
    """L2: mapowanie dst MAC -> port wyjściowy."""
    tbl = bfrt.table_get("pipe.SwitchIngress.mac_lookup")
    entries = [
        ("00:11:22:33:44:01", PORT_FROM_ANALYZER_B),   # ruch z A -> kierowany do B
        ("00:11:22:33:44:02", PORT_FROM_ANALYZER_A),
    ]
    for mac_str, port in entries:
        key = tbl.make_key([
            gc.KeyTuple("hdr.ethernet.dst_addr", mac_to_int(mac_str))
        ])
        data = tbl.make_data([gc.DataTuple("port", port)],
                             action_name="SwitchIngress.set_egress_l2")
        entry_add_or_mod(tbl, target, key, data)
    print(f"[OK] mac_lookup: {len(entries)} wpisów")


def program_ipv4_lookup(bfrt, target):
    """L3: LPM po dst IP -> (port, next-hop MAC)."""
    tbl = bfrt.table_get("pipe.SwitchIngress.ipv4_lookup")
    # Topology Plan A — 4 wpisy, każdy kieruje pakiet do partnera w parze:
    #   Para A:  10.3↔10.1 przez T2_PORT_A0(=0) ↔ T2_PORT_A1(=24)
    #   Para B:  10.2↔10.0 przez T2_PORT_B0(=16) ↔ T2_PORT_B1(=8)
    entries = [
        # (prefix, plen, egress_port, next_hop_mac)
        ("10.3.0.0", 16, T2_PORT_A0, "00:11:22:33:44:01"),  # do TRex 0 (port 0)
        ("10.1.0.0", 16, T2_PORT_A1, "00:11:22:33:44:02"),  # do TRex 2 (port 24)
        ("10.2.0.0", 16, T2_PORT_B0, "00:11:22:33:44:01"),  # do TRex 1 (port 16)
        ("10.0.0.0", 16, T2_PORT_B1, "00:11:22:33:44:02"),  # do TRex 3 (port 8)
    ]
    for prefix, plen, port, nh_mac in entries:
        key = tbl.make_key([
            gc.KeyTuple("hdr.ipv4.dst_addr",
                        ip_to_int(prefix), prefix_len=plen)
        ])
        data = tbl.make_data([
            gc.DataTuple("port", port),
            gc.DataTuple("new_dst_mac", mac_to_int(nh_mac)),
        ], action_name="SwitchIngress.set_egress_l3")
        entry_add_or_mod(tbl, target, key, data)
    print(f"[OK] ipv4_lookup: {len(entries)} wpisów")


if __name__ == "__main__":
    bfrt, target = connect(PROGRAM)
    configure_all_ports(bfrt, target)
    program_mac_lookup(bfrt, target)
    program_ipv4_lookup(bfrt, target)
    print("[OK] L2/L3 Switch gotowy.")
