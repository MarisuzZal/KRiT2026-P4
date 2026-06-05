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
    STLProfile, STLStream, STLPktBuilder, STLTXCont,
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


def _make_stream(pkt, percentage: float = 100.0):
    """Strumień ciągły. Latency mierzona po stronie analizatora (SALU)."""
    return STLStream(
        packet=STLPktBuilder(pkt=pkt),
        mode=STLTXCont(percentage=percentage),
    )


class STLS1(object):

    def get_streams(self, direction=0, port_id=0, **kwargs):
        # UWAGA: TRex 'direction' to NIE numer portu — to relacja w parze
        # (0 = parzyste porty: 0,2; 1 = nieparzyste: 1,3).
        # Używamy 'port_id' (faktyczny numer portu TRex 0..3) który TRex
        # przekazuje przez kwargs przy wywołaniu get_streams() per port.
        streams = []

        # DUT streams — cross-card, dst w prefiksie portu-partnera
        # Mapa: port → (src_ip, dst_ip)
        # Topologia par (z polaczenia_struktura.md):
        #   Para A: port 0 (10.3) ↔ port 2 (10.1)
        #   Para B: port 1 (10.2) ↔ port 3 (10.0)
        DUT_ENDPOINTS = {
            0: ("10.3.1.10", "10.1.1.10"),   # 10.3 → 10.1 (do portu 2)
            1: ("10.2.1.10", "10.0.1.10"),   # 10.2 → 10.0 (do portu 3)
            2: ("10.1.1.10", "10.3.1.10"),   # 10.1 → 10.3 (do portu 0)
            3: ("10.0.1.10", "10.2.1.10"),   # 10.0 → 10.2 (do portu 1)
        }
        if port_id in DUT_ENDPOINTS:
            src_ip, dst_ip = DUT_ENDPOINTS[port_id]
            streams.append(_make_stream(
                _make_packet(src_ip, dst_ip, 12345, ROCE_UDP_PORT),
                percentage=45.0,
            ))

        # Baseline streams — kierowane przez analizator do portu recirc.
        # Każdy port wysyła do własnej podsieci 10.250.X.0/24 — pakiet wraca
        # tym samym portem (via recirc pipe) po pomiarze Δ_baseline.
        BASELINE_ENDPOINTS = {
            0: ("10.3.1.20", "10.250.0.10"),
            1: ("10.2.1.20", "10.250.1.10"),
            2: ("10.1.1.20", "10.250.2.10"),
            3: ("10.0.1.20", "10.250.3.10"),
        }
        if port_id in BASELINE_ENDPOINTS:
            src_ip, dst_ip = BASELINE_ENDPOINTS[port_id]
            streams.append(_make_stream(
                _make_packet(src_ip, dst_ip, 23456, ROCE_UDP_PORT),
                percentage=5.0,
            ))

        return streams


def register():
    return STLS1()
