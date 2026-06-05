"""
Wspólny boilerplate kontrolerów BF-RT dla programów na Tofino #2 (DUT).

Założenia:
  * bf_switchd uruchomione z odpowiednim programem (null_switch, l2l3_switch
    albo l2l3_recirc2), gRPC dostępne na localhost:50052.
  * dev_port numery na Tofino #2 muszą być sprawdzone poleceniem `pm show`
    w bfshell po podłączeniu kabli DAC -- numery poniżej są placeholderem
    do dostosowania.
"""
import sde_paths  # noqa: F401  # MUSI być przed bfrt_grpc
import os
import bfrt_grpc.client as gc

# Override przez env: BF_SWITCHD_HOST, BF_SWITCHD_PORT
DUT_HOST  = os.environ.get("BF_SWITCHD_HOST", "10.133.5.3")
DUT_PORT  = int(os.environ.get("BF_SWITCHD_PORT", "50052"))
GRPC_ADDR = f"{DUT_HOST}:{DUT_PORT}"
DEVICE_ID = 0

# --- Mapowanie portów DUT (Wedge 100BF-32X) --------------------------------
# Mapping ustalony 2026-06-05 (z polaczenia_struktura.md + pm show na T2):
#
# Z T1 do T2 (4 nowe + 2 stare uplinki RTSS):
#   T1 D_P 288 (pipe 2)  ↔  T2 D_P 0   (pipe 0)   — para A TX (od TRex 0)
#   T1 D_P 132 (pipe 1)  ↔  T2 D_P 24  (pipe 0)   — para A RX / stary uplink_B
#   T1 D_P 292 (pipe 2)  ↔  T2 D_P 48  (pipe 0)   — para B TX (od TRex 1)
#   T1 D_P 128 (pipe 1)  ↔  T2 D_P 8   (pipe 0)   — para B RX
#   T1 D_P 60  (pipe 0)  ↔  T2 D_P 152 (pipe 1)   — stary uplink_A (zachowany)
#   T1 D_P 56  (pipe 0)  ↔  T2 D_P 128 (pipe 3)   — wolne
#   T1 D_P 408 (pipe 3)  ↔  T2 D_P 136 (pipe 3)   — wolne
#   T1 D_P 412 (pipe 3)  ↔  T2 D_P 144 (pipe 3)   — wolne
#
# Cztery porty NullSwitch (wszystkie w pipe 0 T2 → same-pipe forward):
T2_PORT_A0 = 0      # od TRex 0 (via T1 D_P 288)
T2_PORT_A1 = 24     # do TRex 2 (via T1 D_P 132)
T2_PORT_B0 = 48     # od TRex 1 (via T1 D_P 292)
T2_PORT_B1 = 8      # do TRex 3 (via T1 D_P 128)

# Aliasy dla wstecznej kompatybilności (stare nazwy w null_switch.py)
PORT_FROM_ANALYZER_A = T2_PORT_A0      # para A: 0
PORT_FROM_ANALYZER_B = T2_PORT_A1      # para A: 24


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


def entry_add_or_mod(tbl, target, key, data, label: str = ""):
    """Idempotentne dodawanie wpisu — przy ALREADY_EXISTS robi entry_mod.

    bf_switchd zachowuje stan między uruchomieniami kontrolera, więc
    powtórne entry_add zwraca ALREADY_EXISTS. Ten helper robi mod.
    """
    try:
        tbl.entry_add(target, [key], [data])
        action = "add"
    except gc.BfruntimeRpcException:
        try:
            tbl.entry_mod(target, [key], [data])
            action = "mod"
        except Exception as e:
            print(f"[WARN] {label}: {e}")
            return None
    return action

