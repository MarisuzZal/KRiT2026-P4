"""
TRex stateless profile dla testbedu KRiT2026-P4.

Generuje równolegle:
  - 4 strumienie DUT  (każda para portów cross-card, RoCEv2-style payload)
  - 4 strumienie baseline (po jednym z każdego portu serwera, dst w 10.250.X.X)

Uruchomienie:
  trex-console
  > start -f trex/profile_fanio.py -m 50 -d 60

Mapowanie portów TRex (z polaczenia_struktura.md):
  port 0 = NIC#1 B1 (D_P 284), podsieć 10.3.0.0/16
  port 1 = NIC#1 B0 (D_P 280), podsieć 10.2.0.0/16
  port 2 = NIC#2 A1 (D_P 184), podsieć 10.1.0.0/16
  port 3 = NIC#2 A0 (D_P 188), podsieć 10.0.0.0/16
"""
from trex_stl_lib.api import (
    STLProfile, STLStream, STLPktBuilder, STLTXCont, STLFlowLatencyStats,
)
from scapy.layers.inet import IP, UDP, Ether


# RoCEv2 = UDP/4791 + BTH; tu uproszczenie do UDP/4791 + payload 1000 B
ROCE_UDP_PORT = 4791
PAYLOAD_SIZE  = 1000


def _make_packet(src_ip: str, dst_ip: str, src_port: int, dst_port: int):
    """Pakiet bazowy: Ether/IP/UDP + losowy payload o stałym rozmiarze."""
    pkt = (
        Ether(src="00:00:00:00:00:01", dst="00:00:00:00:00:02") /
        IP(src=src_ip, dst=dst_ip) /
        UDP(sport=src_port, dport=dst_port) /
        (b"\x00" * PAYLOAD_SIZE)
    )
    return pkt


def _make_stream(pkt, pg_id: int, percentage: float = 100.0):
    """Strumień ciągły z latency monitor (pg_id)."""
    return STLStream(
        packet=STLPktBuilder(pkt=pkt),
        mode=STLTXCont(percentage=percentage),
        flow_stats=STLFlowLatencyStats(pg_id=pg_id),
    )


class STLS1(object):

    def get_streams(self, direction=0, **kwargs):
        # Strumienie DUT — cross-card, dst w prefiksie partnera
        # Per-direction TRex tworzy strumienie tylko dla swojego portu wejściowego
        streams = []

        # DUT streams (pg_id 100..103)
        if direction == 0:
            # port 0 (10.3) -> 10.1
            streams.append(_make_stream(
                _make_packet("10.3.1.10", "10.1.1.10", 12345, ROCE_UDP_PORT),
                pg_id=100, percentage=45.0,
            ))
        elif direction == 1:
            # port 1 (10.2) -> 10.0
            streams.append(_make_stream(
                _make_packet("10.2.1.10", "10.0.1.10", 12345, ROCE_UDP_PORT),
                pg_id=101, percentage=45.0,
            ))
        elif direction == 2:
            # port 2 (10.1) -> 10.3
            streams.append(_make_stream(
                _make_packet("10.1.1.10", "10.3.1.10", 12345, ROCE_UDP_PORT),
                pg_id=102, percentage=45.0,
            ))
        elif direction == 3:
            # port 3 (10.0) -> 10.2
            streams.append(_make_stream(
                _make_packet("10.0.1.10", "10.2.1.10", 12345, ROCE_UDP_PORT),
                pg_id=103, percentage=45.0,
            ))

        # Baseline streams (pg_id 200..203)
        # 5% rate per port — wystarczy do statystycznie sensownego pomiaru baseline
        baseline_subnets = {
            0: "10.250.0.10",
            1: "10.250.1.10",
            2: "10.250.2.10",
            3: "10.250.3.10",
        }
        src_subnets = {
            0: "10.3.1.20",
            1: "10.2.1.20",
            2: "10.1.1.20",
            3: "10.0.1.20",
        }
        if direction in baseline_subnets:
            streams.append(_make_stream(
                _make_packet(src_subnets[direction], baseline_subnets[direction],
                             23456, ROCE_UDP_PORT),
                pg_id=200 + direction, percentage=5.0,
            ))

        return streams


def register():
    return STLS1()
