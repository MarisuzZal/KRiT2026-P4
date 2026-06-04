"""
Scenariusz: liniowy ramp natężenia.

To skrypt sterujący (nie STLProfile). Łączy się z TRex serverem przez API
i w pętli zmienia mnożnik (mult) na portach, realizując rampę.

Uruchomienie:
    python3 trex/scenarios/ramp.py --from 10 --to 95 --duration 30

Argumenty:
    --from N     start natężenia (%)
    --to N       koniec natężenia (%)
    --duration N czas trwania rampy w sekundach
    --steps N    liczba kroków rampy (default 30 -- 1 krok/sek dla 30 s)
"""
import argparse
import time
from trex_stl_lib.api import STLClient
from constant import STLS1   # użyj tego samego profilu pakietów

PORTS = [0, 1, 2, 3]


def run_ramp(rate_from: float, rate_to: float, duration: float, steps: int):
    c = STLClient()
    c.connect()
    try:
        c.reset(ports=PORTS)
        streams = STLS1().get_streams(direction=0)
        c.add_streams(streams, ports=PORTS)

        c.start(ports=PORTS, mult=f"{rate_from}%", force=True)

        step_dt = duration / steps
        for i in range(steps + 1):
            frac = i / steps
            rate = rate_from + (rate_to - rate_from) * frac
            c.update(ports=PORTS, mult=f"{rate:.2f}%")
            print(f"[t={i*step_dt:5.1f}s] rate = {rate:5.2f}%")
            time.sleep(step_dt)

        c.stop(ports=PORTS)
    finally:
        c.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="rate_from", type=float, default=10.0)
    parser.add_argument("--to",   dest="rate_to",   type=float, default=95.0)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--steps",    type=int,   default=30)
    args = parser.parse_args()
    run_ramp(args.rate_from, args.rate_to, args.duration, args.steps)
