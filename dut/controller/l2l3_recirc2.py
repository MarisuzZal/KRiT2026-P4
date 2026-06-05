#!/usr/bin/env python3
"""
Kontroler dla l2l3_recirc2.p4 — przełącznik L2/L3 z dwukrotną recyrkulacją.

Programowanie tabel identyczne jak w l2l3_switch (mac_lookup, ipv4_lookup);
sama logika recyrkulacji jest zaszyta w kodzie P4. Kontroler musi jedynie
wprowadzić wpisy trasowania.

Uwaga: D_P portu recyrkulacyjnego musi się zgadzać z #define RECIRC_PORT
w l2l3_recirc2.p4 (domyślnie 9w68 dla pipe 0).
"""
from l2l3_switch import program_mac_lookup, program_ipv4_lookup
from common import connect
from ports import configure_all_ports

PROGRAM = "l2l3_recirc2"

if __name__ == "__main__":
    bfrt, target = connect(PROGRAM)
    configure_all_ports(bfrt, target)
    program_mac_lookup(bfrt, target)
    program_ipv4_lookup(bfrt, target)
    print("[OK] L2/L3 Switch z 2x recyrkulacją gotowy.")
    print("[INFO] Każdy pakiet zostanie dwukrotnie zawrócony przez port recyrkulacyjny przed wysłaniem.")
