"""
Konfiguracja portów Tofino #2 (DUT) przez BF-RT.

T2 to Wedge100BF-32X. Mapping kabli T1↔T2 (z polaczenia_struktura.md
+ uzupełnienie Mariusza 2026-06-05):

  T1 D_P 288 (pipe 2) ↔ T2 D_P 0   (pipe 0)  ← para A TX
  T1 D_P 132 (pipe 1) ↔ T2 D_P 24  (pipe 0)  ← para A RX
  T1 D_P 292 (pipe 2) ↔ T2 D_P 48  (pipe 0)  ← para B TX
  T1 D_P 128 (pipe 1) ↔ T2 D_P 8   (pipe 0)  ← para B RX

  T1 D_P 60  (pipe 0) ↔ T2 D_P 152 (pipe 1)  ← legacy uplink_A
  T1 D_P 56  (pipe 0) ↔ T2 D_P 128 (pipe 3)  ← spare
  T1 D_P 408 (pipe 3) ↔ T2 D_P 136 (pipe 3)  ← spare
  T1 D_P 412 (pipe 3) ↔ T2 D_P 144 (pipe 3)  ← spare

W trybie Plan A (per-pipe DUT via T2 NullSwitch) konfigurujemy 4 porty
aktywne (0, 8, 24, 48) jako 100G RS-FEC. Pozostałe (legacy/spare)
zostają opcjonalnie skonfigurowane przez ENABLE_LEGACY_LINKS i
ENABLE_SPARE_LINKS.
"""
import sde_paths  # noqa: F401  # MUSI być przed bfrt_grpc
import bfrt_grpc.client as gc

from common import (
    T2_PORT_A0, T2_PORT_A1, T2_PORT_B0, T2_PORT_B1,
)

# Standard 100G na DAC QSFP28 — Reed-Solomon FEC (CL91, 802.3bj/bm)
CFG_100G_RS = {
    "$SPEED": "BF_SPEED_100G",
    "$FEC":   "BF_FEC_TYP_REED_SOLOMON",
    "$PORT_ENABLE": True,
}

# Czy konfigurować dodatkowo legacy uplinki RTSS i spare kable
ENABLE_LEGACY_LINKS = True   # T2 D_P 152
ENABLE_SPARE_LINKS  = False  # T2 D_P 128, 136, 144 — póki co wyłączone


def _data_tuples(config: dict):
    out = []
    for k, v in config.items():
        if isinstance(v, bool):
            out.append(gc.DataTuple(k, bool_val=v))
        elif isinstance(v, int):
            out.append(gc.DataTuple(k, v))
        else:  # string (enum)
            out.append(gc.DataTuple(k, str_val=v))
    return out


def configure_port(bfrt, target, dev_port: int, config: dict, label: str = ""):
    """Dodaj lub zmodyfikuj konfigurację pojedynczego portu T2."""
    tbl = bfrt.table_get("$PORT")
    key = tbl.make_key([gc.KeyTuple("$DEV_PORT", dev_port)])
    data = tbl.make_data(_data_tuples(config))

    try:
        tbl.entry_add(target, [key], [data])
        action = "add"
    except gc.BfruntimeRpcException:
        try:
            tbl.entry_mod(target, [key], [data])
            action = "mod"
        except Exception as e:
            print(f"[WARN] port {dev_port}: {e}")
            return

    fec = config.get("$FEC", "?").replace("BF_FEC_TYP_", "")
    extra = f" ({label})" if label else ""
    print(f"[OK] port {dev_port:>4} {action}, 100G, FEC={fec}{extra}")


def configure_all_ports(bfrt, target):
    """Konfiguruje porty T2 wymagane przez NullSwitch (Plan A)."""
    # 4 porty aktywne (Plan A)
    active = [
        (T2_PORT_A0, "od T1 D_P 288 — TRex 0 (para A TX)"),
        (T2_PORT_A1, "od T1 D_P 132 — TRex 2 (para A RX)"),
        (T2_PORT_B0, "od T1 D_P 292 — TRex 1 (para B TX)"),
        (T2_PORT_B1, "od T1 D_P 128 — TRex 3 (para B RX)"),
    ]
    for dp, label in active:
        configure_port(bfrt, target, dp, CFG_100G_RS, label)

    if ENABLE_LEGACY_LINKS:
        configure_port(bfrt, target, 152, CFG_100G_RS, "legacy uplink_A (T1 D_P 60)")

    if ENABLE_SPARE_LINKS:
        for dp, label in [
            (128, "spare ↔ T1 D_P 56"),
            (136, "spare ↔ T1 D_P 408"),
            (144, "spare ↔ T1 D_P 412"),
        ]:
            configure_port(bfrt, target, dp, CFG_100G_RS, label)
