#!/usr/bin/env python3
"""
Kontroler dla null_switch.p4 — przezroczyste przekierowanie portowe.

Programuje pojedynczą tablicę `forward` mapującą:
    PORT_FROM_ANALYZER_A -> PORT_FROM_ANALYZER_B   (i odwrotnie)
"""
import sde_paths  # noqa: F401  # MUSI być przed bfrt_grpc
import bfrt_grpc.client as gc
from common import connect, T2_PORT_A0, T2_PORT_A1, T2_PORT_B0, T2_PORT_B1

PROGRAM = "null_switch"


def program_forward(bfrt, target):
    """Programuje tablicę forward dla NullSwitch.

    4 wpisy realizujące cross-card hairpin per para:
      Para A: T2 D_P 0  ↔ T2 D_P 24
      Para B: T2 D_P 48 ↔ T2 D_P 8

    Wszystkie wpisy są same-pipe T2 (cztery porty w pipe 0).
    """
    tbl = bfrt.table_get("pipe.SwitchIngress.forward")
    entries = [
        # Para A: TRex 0 ↔ TRex 2
        (T2_PORT_A0, T2_PORT_A1),   # 0 → 24
        (T2_PORT_A1, T2_PORT_A0),   # 24 → 0
        # Para B: TRex 1 ↔ TRex 3
        (T2_PORT_B0, T2_PORT_B1),   # 48 → 8
        (T2_PORT_B1, T2_PORT_B0),   # 8 → 48
    ]
    for ig_port, eg_port in entries:
        key = tbl.make_key([gc.KeyTuple("ig_intr_md.ingress_port", ig_port)])
        data = tbl.make_data([gc.DataTuple("port", eg_port)],
                             action_name="SwitchIngress.set_egress")
        tbl.entry_add(target, [key], [data])
    print(f"[OK] forward: {len(entries)} wpisów (2× para A + 2× para B)")


if __name__ == "__main__":
    bfrt, target = connect(PROGRAM)
    program_forward(bfrt, target)
    print("[OK] NullSwitch gotowy — pakiety od TRex 0/2 routowane same-pipe T2.")
