#!/usr/bin/env python3
"""
Kontroler dla null_switch.p4 — przezroczyste przekierowanie portowe.

Programuje pojedynczą tablicę `forward` mapującą:
    PORT_FROM_ANALYZER_A -> PORT_FROM_ANALYZER_B   (i odwrotnie)
"""
import bfrt_grpc.client as gc
from common import connect, PORT_FROM_ANALYZER_A, PORT_FROM_ANALYZER_B

PROGRAM = "null_switch"


def program_forward(bfrt, target):
    tbl = bfrt.table_get("pipe.SwitchIngress.forward")
    entries = [
        (PORT_FROM_ANALYZER_A, PORT_FROM_ANALYZER_B),
        (PORT_FROM_ANALYZER_B, PORT_FROM_ANALYZER_A),
    ]
    for ig_port, eg_port in entries:
        key = tbl.make_key([gc.KeyTuple("ig_intr_md.ingress_port", ig_port)])
        data = tbl.make_data([gc.DataTuple("port", eg_port)],
                             action_name="SwitchIngress.set_egress")
        tbl.entry_add(target, [key], [data])
    print(f"[OK] forward: {len(entries)} wpisów")


if __name__ == "__main__":
    bfrt, target = connect(PROGRAM)
    program_forward(bfrt, target)
    print("[OK] NullSwitch gotowy.")
