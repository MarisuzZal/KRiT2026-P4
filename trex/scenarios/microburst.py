"""
Scenariusz: microburst -- krótkie rafy maksymalnego natężenia
przerywane okresami ciszy. Pozwala badać reakcję DUT na nagłe
wzrosty natężenia, w tym przepełnienie kolejek TM.

Uruchomienie:
    trex-console
    > start -f trex/scenarios/microburst.py -d 60

Profil emituje 10 raf po 100k pakietów, z 50 ms ciszy między nimi.
"""
from trex_stl_lib.api import (
    STLProfile, STLStream, STLPktBuilder,
    STLTXMultiBurst, STLFlowLatencyStats,
)
from scapy.layers.inet import IP, UDP, Ether

PAYLOAD = b"\x00" * 1000


def _packet(src_ip, dst_ip):
    return (Ether() / IP(src=src_ip, dst=dst_ip) /
            UDP(sport=12345, dport=4791) / PAYLOAD)


PKTS_PER_BURST = 100_000           # ilość pakietów w pojedynczej rafie
BURST_COUNT    = 10                # liczba raf
IBG_USEC       = 50_000            # 50 ms ciszy między rafami


class STLS1:
    def get_streams(self, direction=0, **kwargs):
        src_dst = {
            0: ("10.3.1.10", "10.1.1.10"),
            1: ("10.2.1.10", "10.0.1.10"),
            2: ("10.1.1.10", "10.3.1.10"),
            3: ("10.0.1.10", "10.2.1.10"),
        }
        src, dst = src_dst.get(direction, ("10.0.0.1", "10.0.0.2"))
        return [STLStream(
            packet=STLPktBuilder(pkt=_packet(src, dst)),
            mode=STLTXMultiBurst(
                pkts_per_burst=PKTS_PER_BURST,
                count=BURST_COUNT,
                ibg=IBG_USEC,
                percentage=100.0,    # podczas rafy: 100% line-rate
            ),
            flow_stats=STLFlowLatencyStats(pg_id=200 + direction),
        )]


def register():
    return STLS1()
