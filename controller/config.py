"""
Konfiguracja platformy pomiarowej KRiT2026-P4.

Numery portów (D_P) zgodne z polaczenia_struktura.md. Skala histogramu
i pula adresów strumieni baseline są konfigurowalne.
"""

# --- Połączenie z gRPC server (bf_switchd) --------------------------------
GRPC_ADDR = "localhost:50052"
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

# Baseline (tryb domyślny — recyrkulacja, działa bez podpiętego DAC)
BASELINE_MODE = "RECIRC"   # albo "DAC"

if BASELINE_MODE == "RECIRC":
    PORT_BASE_OUT = 68    # port recyrkulacyjny pipe 0
    PORT_BASE_IN  = 68
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

# --- Pary cross-card dla ruchu testowego (zgodnie z polaczenia_struktura.md) -
DUT_PAIRS = [
    # (port_src, dst_subnet, prefix_len, uplink, dst_port_after_fanout)
    (PORT_S0, "10.1.0.0",  16, PORT_UPLINK_A, PORT_S2),  # 10.3 (S0) -> 10.1 (S2)
    (PORT_S2, "10.3.0.0",  16, PORT_UPLINK_A, PORT_S0),  # 10.1 (S2) -> 10.3 (S0)
    (PORT_S1, "10.0.0.0",  16, PORT_UPLINK_B, PORT_S3),  # 10.2 (S1) -> 10.0 (S3)
    (PORT_S3, "10.2.0.0",  16, PORT_UPLINK_B, PORT_S1),  # 10.0 (S3) -> 10.2 (S1)
]

# Mapa fan-out z uplinku
FANOUT_FROM_UPLINK = [
    (PORT_UPLINK_A, "10.1.0.0", 16, PORT_S2),
    (PORT_UPLINK_A, "10.3.0.0", 16, PORT_S0),
    (PORT_UPLINK_B, "10.0.0.0", 16, PORT_S3),
    (PORT_UPLINK_B, "10.2.0.0", 16, PORT_S1),
]

# --- Skala histogramu — KONFIGURACJA ---------------------------------------
# Po wstępnych pomiarach min/max ustawiamy zakres tak, żeby 128 binów
# pokryło spodziewany zakres opóźnień Δ z marginesem
HISTOGRAM_BIN_WIDTH_NS = 10   # szerokość pojedynczego binu
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
