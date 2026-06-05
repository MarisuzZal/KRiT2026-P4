"""
Konfiguracja platformy pomiarowej KRiT2026-P4.

Numery portów (D_P) zgodne z polaczenia_struktura.md. Skala histogramu
i pula adresów strumieni baseline są konfigurowalne.
"""

# --- Połączenie z gRPC server (bf_switchd) --------------------------------
# Analizator (Tofino #1, Wedge 100BF-65X) — bf_switchd pod tym adresem.
# Override przez env: BF_SWITCHD_HOST, BF_SWITCHD_PORT.
import os as _os
ANALYZER_HOST = _os.environ.get("BF_SWITCHD_HOST", "10.133.5.4")
ANALYZER_PORT = int(_os.environ.get("BF_SWITCHD_PORT", "50052"))
GRPC_ADDR     = f"{ANALYZER_HOST}:{ANALYZER_PORT}"
DEVICE_ID = 0
PROGRAM   = "measurement"

# --- Mapowanie portów (D_P) -----------------------------------------------
# Serwer
PORT_S0 = 284   # NIC #1 B1, prefiks 10.3.0.0/16
PORT_S1 = 280   # NIC #1 B0, prefiks 10.2.0.0/16
PORT_S2 = 184   # NIC #2 A1, prefiks 10.1.0.0/16
PORT_S3 = 188   # NIC #2 A0, prefiks 10.0.0.0/16

# Uplinki do DUT (Wedge 100BF-32X)
PORT_UPLINK_A = 60    # para A: 10.3 <-> 10.1
PORT_UPLINK_B = 132   # para B: 10.2 <-> 10.0

# Baseline (tryb domyślny — recyrkulacja per pipe)
BASELINE_MODE = "RECIRC"   # albo "DAC"

# Tofino-1 4-pipe: każdy pipe ma swój port recyrkulacyjny D_P = pipe<<7 | 68
# Pakiet z portu w pipe X MUSI iść na recirc D_P pipe X (cross-pipe do recirc
# innego pipe nie działa w SDE 9.13.4 na Wedge 100BF-65X).
PIPE_RECIRC = {
    0: 68,
    1: 196,
    2: 324,
    3: 452,
}

def pipe_of(port: int) -> int:
    """D_P → pipe (Tofino-1 numerowanie: 7 bitów port w pipe, wyższe = pipe)."""
    return port >> 7

def recirc_for(port: int) -> int:
    """Zwraca recirc D_P dla pipe w którym żyje dany port."""
    return PIPE_RECIRC[pipe_of(port)]

if BASELINE_MODE == "RECIRC":
    # Per-pipe: zarówno OUT jak IN to recirc-of-source-pipe.
    # Tablica routingu dostanie 4 wpisy fan-in (po jednym per port serwera),
    # każdy z innym egress_port = recirc_for(port_src).
    PORT_BASE_OUT = None  # nieużywane — patrz recirc_for() w routing.py
    PORT_BASE_IN  = None
elif BASELINE_MODE == "DAC":
    PORT_BASE_OUT = 308
    PORT_BASE_IN  = 148
else:
    raise ValueError(f"Nieznany tryb baseline: {BASELINE_MODE}")

# --- Pula adresów dla strumieni baseline ---------------------------------
# Każdy port serwera ma własną podsieć /24 wewnątrz 10.250.0.0/16
# żeby pakiet baseline wracał do portu, z którego wyszedł
BASELINE_SUBNET = "10.250.0.0/16"
BASELINE_SUBNETS_PER_PORT = {
    PORT_S0: ("10.250.0.0", 24),
    PORT_S1: ("10.250.1.0", 24),
    PORT_S2: ("10.250.2.0", 24),
    PORT_S3: ("10.250.3.0", 24),
}

# --- Per-pipe DUT uplinks --------------------------------------------------
# Mapping ustalony 2026-06-05 po analizie kabli T1↔T2:
#   Para A: TRex0↔TRex2 via T1 D_P 288 (pipe 2) ↔ T2 D_P 0 (pipe 0)
#                  oraz T1 D_P 132 (pipe 1) ↔ T2 D_P 24 (pipe 0)
#   Para B: TRex1↔TRex3 via T1 D_P 292 (pipe 2) ↔ T2 D_P 16 (pipe 0)
#                  oraz T1 D_P 128 (pipe 1) ↔ T2 D_P 8 (pipe 0)
#
# T2 NullSwitch forward:
#   T2 D_P 0  → T2 D_P 24 (i odwrotnie)  -- para A
#   T2 D_P 16 → T2 D_P 8  (i odwrotnie)  -- para B
#
# Wszystkie segmenty T1 są SAME-PIPE → eliminuje cross-pipe routing T1.
# T2 forward to też same-pipe (wszystkie cztery porty w pipe 0 T2).
PORT_UPLINK_TX_A = 288   # pipe 2 T1 — para A TX
PORT_UPLINK_TX_B = 292   # pipe 2 T1 — para B TX
PORT_UPLINK_RX_A = 132   # pipe 1 T1 — para A RX (powrót via T2)
PORT_UPLINK_RX_B = 128   # pipe 1 T1 — para B RX (powrót via T2)

# DUT pairs: każda określa pełną ścieżkę source→dest
DUT_PAIRS = [
    # (port_src, dst_subnet, plen, uplink_TX, port_dst_after_fanout, uplink_RX)
    # Para A: 10.3↔10.1 (cross-card, ale same-pipe T1)
    (PORT_S0, "10.1.0.0", 16, PORT_UPLINK_TX_A, PORT_S2, PORT_UPLINK_RX_A),
    (PORT_S2, "10.3.0.0", 16, PORT_UPLINK_RX_A, PORT_S0, PORT_UPLINK_TX_A),
    # Para B: 10.2↔10.0
    (PORT_S1, "10.0.0.0", 16, PORT_UPLINK_TX_B, PORT_S3, PORT_UPLINK_RX_B),
    (PORT_S3, "10.2.0.0", 16, PORT_UPLINK_RX_B, PORT_S1, PORT_UPLINK_TX_B),
]

# Fan-out: gdy pakiet wraca z DUT (przez T2), wchodzi na uplink_RX
FANOUT_FROM_UPLINK = [
    # Para A return: T1 D_P 132 (pipe 1) odbiera z T2
    (PORT_UPLINK_RX_A, "10.1.0.0", 16, PORT_S2),    # od TRex 0 → do TRex 2
    (PORT_UPLINK_TX_A, "10.3.0.0", 16, PORT_S0),    # od TRex 2 → do TRex 0 (pakiet TRex2 wrócił via uplink 288 pipe 2)
    # Para B return
    (PORT_UPLINK_RX_B, "10.0.0.0", 16, PORT_S3),    # od TRex 1 → do TRex 3
    (PORT_UPLINK_TX_B, "10.2.0.0", 16, PORT_S1),    # od TRex 3 → do TRex 1
]

# Legacy uplinki (z RTSS): zachowane dla wstecznej kompatybilności
# T1 60 ↔ T2 152 (stary uplink_A)
# T1 132 ↔ T2 24 (stary uplink_B) — także para A RX powyżej
PORT_UPLINK_A = 60    # legacy
PORT_UPLINK_B = 132   # legacy (= PORT_UPLINK_RX_A)

# --- Skala histogramu — KONFIGURACJA ---------------------------------------
# Po wstępnych pomiarach min/max ustawiamy zakres tak, żeby 128 binów
# pokryło spodziewany zakres opóźnień Δ z marginesem
HISTOGRAM_BIN_WIDTH_NS = 20    # 20 ns × 128 binów = 0..2560 ns (max range klucza 16-bit = 65 μs)   # szerokość pojedynczego binu
HISTOGRAM_OFFSET_NS    = 0    # początek pierwszego binu
# -> zakres histogramu: [0..1280) ns, rozdzielczość 10 ns
# Dla precyzyjniejszych pomiarów: BIN_WIDTH_NS=1, OFFSET_NS=300

# --- Polling ----------------------------------------------------------------
POLL_INTERVAL_SEC = 1.0
CSV_OUTPUT_PATH   = "measurement_log.csv"

# --- flow_id assignment ---------------------------------------------------
# flow_id_lsb (8-bit, bo SALU index 8-bit) per (port_src, prefix)
# Pierwsze 100 ID — ruch DUT, 100+ — ruch baseline
FLOW_ID_DUT_START      = 0
FLOW_ID_BASELINE_START = 100
