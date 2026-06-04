"""
Konfiguracja portów Tofino przez BF-RT.

Programowane porty (D_P) zgodne z polaczenia_struktura.md:
  Serwer (RS-FEC 100G):
    PORT_S0..PORT_S3  — 184, 188, 280, 284
  Uplinki do DUT (RS-FEC 100G):
    PORT_UPLINK_A     — 60
    PORT_UPLINK_B     — 132
  Recyrkulacja:
    PORT_BASE_OUT/IN  — 68 (FEC NONE; SDE automatycznie ustawia loopback)

W trybie DAC (BASELINE_MODE='DAC'): PORT_BASE_OUT/IN to fizyczne porty
DAC pętli, więc otrzymują RS-FEC zamiast FEC NONE.
"""
import sde_paths  # noqa: F401
import bfrt_grpc.client as gc

from config import (
    PORT_S0, PORT_S1, PORT_S2, PORT_S3,
    PORT_UPLINK_A, PORT_UPLINK_B,
    PORT_BASE_OUT, PORT_BASE_IN,
)


# Standard 100G na DAC QSFP28 — Reed-Solomon FEC (CL91, 802.3bj/bm)
CFG_100G_RS = {
    "$SPEED": "BF_SPEED_100G",
    "$FEC":   "BF_FEC_TYP_REED_SOLOMON",
    "$PORT_ENABLE": True,
}

# Port recyrkulacyjny — wewnętrzny, bez FEC (sygnał nie przechodzi przez SerDes/PHY)
CFG_RECIRC = {
    "$SPEED": "BF_SPEED_100G",
    "$FEC":   "BF_FEC_TYP_NONE",
    "$PORT_ENABLE": True,
}


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
    """Dodaj lub zmodyfikuj konfigurację pojedynczego portu."""
    tbl = bfrt.table_get("$PORT")
    key = tbl.make_key([gc.KeyTuple("$DEV_PORT", dev_port)])
    data = tbl.make_data(_data_tuples(config))

    try:
        tbl.entry_add(target, [key], [data])
        action = "add"
    except gc.BfruntimeRpcException:
        # Port już istnieje — modyfikuj
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
    """Konfiguruje wszystkie porty wymagane przez measurement.p4."""
    rs_ports = [
        (PORT_S0, "serwer TRex0 NIC#1"),
        (PORT_S1, "serwer TRex1 NIC#1"),
        (PORT_S2, "serwer TRex2 NIC#2"),
        (PORT_S3, "serwer TRex3 NIC#2"),
        (PORT_UPLINK_A, "Uplink_A → DUT"),
        (PORT_UPLINK_B, "Uplink_B → DUT"),
    ]
    for dp, label in rs_ports:
        configure_port(bfrt, target, dp, CFG_100G_RS, label)

    # Baseline: recirc (jeden port, FEC NONE) lub DAC (dwa porty, RS-FEC)
    if PORT_BASE_OUT == PORT_BASE_IN:
        configure_port(bfrt, target, PORT_BASE_OUT, CFG_RECIRC, "recirc baseline")
    else:
        configure_port(bfrt, target, PORT_BASE_OUT, CFG_100G_RS, "DAC baseline OUT")
        configure_port(bfrt, target, PORT_BASE_IN,  CFG_100G_RS, "DAC baseline IN")
