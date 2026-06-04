"""
Programowanie tabel BF-RT:
  - port_routing (fan-in DUT + fan-in baseline + fan-out + read_from_baseline)
  - histogram_bin_map (range-match na Δ -> bin_index)

Wymaga `bfrt_grpc.client` z BF-RT API (część Intel P4 Studio SDE 9.13.2).
"""
import ipaddress
import sde_paths  # noqa: F401
import bfrt_grpc.client as gc

from config import (
    DUT_PAIRS, FANOUT_FROM_UPLINK, BASELINE_SUBNETS_PER_PORT,
    PORT_BASE_OUT, PORT_BASE_IN,
    HISTOGRAM_BIN_WIDTH_NS, HISTOGRAM_OFFSET_NS,
    FLOW_ID_DUT_START, FLOW_ID_BASELINE_START,
)


def _ip_to_int(s: str) -> int:
    return int(ipaddress.IPv4Address(s))


def program_routing(bfrt, target):
    """Wpisuje 16 fan-in DUT + 4 fan-in baseline + 4 fan-out DUT + 4 fan-out baseline."""
    tbl = bfrt.table_get("pipe.SwitchIngress.port_routing")
    flow_id_dut = FLOW_ID_DUT_START

    # --- Fan-in DUT (16 wpisów: 4 porty x 4 prefiksy) -----------------------
    # Ale faktycznie sensowne są tylko 4 — port serwera ma 1 partnera cross-card
    # Pozostałe 12 to drop (default_action).
    for port_src, dst, plen, uplink, _ in DUT_PAIRS:
        key = tbl.make_key([
            gc.KeyTuple("ig_intr_md.ingress_port", port_src),
            gc.KeyTuple("hdr.ipv4.dst_addr", _ip_to_int(dst), prefix_len=plen),
        ])
        data = tbl.make_data([
            gc.DataTuple("egress_port", uplink),
            gc.DataTuple("flow_id", flow_id_dut),
        ], action_name="SwitchIngress.stamp_to_dut")
        tbl.entry_add(target, [key], [data])
        flow_id_dut += 1

    # --- Fan-in baseline (4 wpisy: 4 porty serwera -> port baseline) -------
    flow_id_base = FLOW_ID_BASELINE_START
    for port_src, (subnet_ip, plen) in BASELINE_SUBNETS_PER_PORT.items():
        key = tbl.make_key([
            gc.KeyTuple("ig_intr_md.ingress_port", port_src),
            gc.KeyTuple("hdr.ipv4.dst_addr", _ip_to_int(subnet_ip), prefix_len=plen),
        ])
        data = tbl.make_data([
            gc.DataTuple("egress_port", PORT_BASE_OUT),
            gc.DataTuple("flow_id", flow_id_base),
        ], action_name="SwitchIngress.stamp_to_baseline")
        tbl.entry_add(target, [key], [data])
        flow_id_base += 1

    # --- Fan-out DUT (4 wpisy) ---------------------------------------------
    for uplink, dst, plen, port_dst in FANOUT_FROM_UPLINK:
        key = tbl.make_key([
            gc.KeyTuple("ig_intr_md.ingress_port", uplink),
            gc.KeyTuple("hdr.ipv4.dst_addr", _ip_to_int(dst), prefix_len=plen),
        ])
        data = tbl.make_data([
            gc.DataTuple("egress_port", port_dst),
        ], action_name="SwitchIngress.read_from_dut")
        tbl.entry_add(target, [key], [data])

    # --- Fan-out baseline (4 wpisy) ----------------------------------------
    # Klucz: (PORT_BASE_IN, 10.250.X.0/24) -> port serwera, z którego wyszło
    for port_dst, (subnet_ip, plen) in BASELINE_SUBNETS_PER_PORT.items():
        key = tbl.make_key([
            gc.KeyTuple("ig_intr_md.ingress_port", PORT_BASE_IN),
            gc.KeyTuple("hdr.ipv4.dst_addr", _ip_to_int(subnet_ip), prefix_len=plen),
        ])
        data = tbl.make_data([
            gc.DataTuple("egress_port", port_dst),
        ], action_name="SwitchIngress.read_from_baseline")
        tbl.entry_add(target, [key], [data])

    print(f"[OK] port_routing: {4 + 4 + 4 + 4} wpisów (4 fan-in DUT + 4 fan-in base + 4 fan-out DUT + 4 fan-out base)")


def program_histogram(bfrt, target):
    """Wpisuje 128 wpisów range-match dla histogram_bin_map."""
    tbl = bfrt.table_get("pipe.SwitchIngress.histogram_bin_map")
    for i in range(128):
        low  = HISTOGRAM_OFFSET_NS + i * HISTOGRAM_BIN_WIDTH_NS
        high = HISTOGRAM_OFFSET_NS + (i + 1) * HISTOGRAM_BIN_WIDTH_NS - 1
        key = tbl.make_key([
            gc.KeyTuple("ig_md.delta_lo", low=low, high=high),
        ])
        data = tbl.make_data([
            gc.DataTuple("b", i),
        ], action_name="SwitchIngress.set_bin")
        tbl.entry_add(target, [key], [data])
    span_start = HISTOGRAM_OFFSET_NS
    span_end   = HISTOGRAM_OFFSET_NS + 128 * HISTOGRAM_BIN_WIDTH_NS
    print(f"[OK] histogram_bin_map: 128 binów, zakres [{span_start}..{span_end}) ns, "
          f"szerokość binu {HISTOGRAM_BIN_WIDTH_NS} ns")


def clear_all(bfrt, target):
    """Usuwa wszystkie wpisy (przed reprogramowaniem)."""
    for tname in ["pipe.SwitchIngress.port_routing",
                  "pipe.SwitchIngress.histogram_bin_map"]:
        try:
            tbl = bfrt.table_get(tname)
            tbl.entry_del(target)
            print(f"[OK] wyczyszczono {tname}")
        except Exception as e:
            print(f"[WARN] nie udało się wyczyścić {tname}: {e}")


def program_routing_per_pipe(bfrt, num_pipes: int = 4):
    """Wersja explicit per-pipe — jeśli pipe_id=0xffff nie programuje
    wszystkich pipes na danym targecie SDE. Programuje TĘ SAMĄ tablicę
    osobno w każdym z `num_pipes` pipes Tofino-1."""
    for pipe_id in range(num_pipes):
        target = gc.Target(device_id=0, pipe_id=pipe_id)
        print(f"[*] Programowanie pipe {pipe_id}...")
        try:
            program_routing(bfrt, target)
        except Exception as e:
            # Wpis może już istnieć z poprzedniego pipe — to OK, kontynuuj
            print(f"    pipe {pipe_id}: {e}")
