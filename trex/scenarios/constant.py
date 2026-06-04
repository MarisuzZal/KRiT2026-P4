"""
Scenariusz: stałe natężenie.

Uruchomienie:
    trex-console
    > start -f trex/scenarios/constant.py -m 50% -d 60

`-m 50%`  — natężenie strumienia (procent line-rate)
`-d 60`   — czas trwania w sekundach
"""
from trex_stl_lib.api import (
    STLProfile, STLStream, STLPktBuilder, STLTXCont, STLFlowLatencyStats,
)
from scapy.layers.inet import IP, UDP, Ether

PAYLOAD = b"\x00" * 1000   # ~1064 B na drucie z preamble


def _packet(src_ip, dst_ip):
    return (Ether() / IP(src=src_ip, dst=dst_ip) /
            UDP(sport=12345, dport=4791) / PAYLOAD)


class STLS1:
    """Profil per port — direction wskazuje numer portu TRex (0..3)."""

    def get_streams(self, direction=0, **kwargs):
        # Cztery pary cross-card; konkretne adresy zgodne z polaczenia_struktura.md
        src_dst = {
            0: ("10.3.1.10", "10.1.1.10"),
            1: ("10.2.1.10", "10.0.1.10"),
            2: ("10.1.1.10", "10.3.1.10"),
            3: ("10.0.1.10", "10.2.1.10"),
        }
        src, dst = src_dst.get(direction, ("10.0.0.1", "10.0.0.2"))
        return [STLStream(
            packet=STLPktBuilder(pkt=_packet(src, dst)),
            mode=STLTXCont(percentage=100.0),     # rate kontrolowany przez `-m`
            flow_stats=STLFlowLatencyStats(pg_id=100 + direction),
        )]


def register():
    return STLS1()
