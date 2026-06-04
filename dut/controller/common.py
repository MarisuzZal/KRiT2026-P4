"""
Wspólny boilerplate kontrolerów BF-RT dla programów na Tofino #2 (DUT).

Założenia:
  * bf_switchd uruchomione z odpowiednim programem (null_switch, l2l3_switch
    albo l2l3_recirc2), gRPC dostępne na localhost:50052.
  * dev_port numery na Tofino #2 muszą być sprawdzone poleceniem `pm show`
    w bfshell po podłączeniu kabli DAC -- numery poniżej są placeholderem
    do dostosowania.
"""
import os
import sys
_SDE = os.environ.get("SDE_INSTALL", "/home/student/sde/bf-sde-9.13.4/install")
_PY = f"python{sys.version_info.major}.{sys.version_info.minor}"
for _p in [f"{_SDE}/lib/{_PY}/site-packages",
           f"/usr/local/lib/{_PY}/dist-packages"]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)

import bfrt_grpc.client as gc

GRPC_ADDR = "localhost:50052"
DEVICE_ID = 0

# --- Mapowanie portów DUT (Wedge 100BF-32X) --------------------------------
# 32X ma 32 porty front-panel; D_P sprawdzić `bfshell> pm show`.
# Tu placeholder: 2 porty od Tofino #1 (uplink_A i uplink_B).
PORT_FROM_ANALYZER_A = 4    # TBD: sprawdzić po podłączeniu
PORT_FROM_ANALYZER_B = 8    # TBD


def connect(program_name: str):
    """Połącz z bf_switchd, zwróć (bfrt, target) dla konkretnego programu."""
    interface = gc.ClientInterface(GRPC_ADDR, client_id=0, device_id=DEVICE_ID)
    target = gc.Target(device_id=DEVICE_ID, pipe_id=0xffff)
    interface.bind_pipeline_config(program_name)
    bfrt = interface.bfrt_info_get(program_name)
    print(f"[OK] połączono z {GRPC_ADDR}, program={program_name}")
    return bfrt, target


def ip_to_int(ip: str) -> int:
    parts = ip.split(".")
    return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])


def mac_to_int(mac: str) -> int:
    return int(mac.replace(":", "").replace("-", ""), 16)
