"""
Scenariusz: skokowa zmiana natężenia między poziomami (schodki).

Uruchomienie:
    python3 trex/scenarios/step.py --levels 10,50,95 --dwell 60

Każdy poziom utrzymywany jest przez `dwell` sekund, po czym następuje
skokowa zmiana do kolejnego.

Domyślnie: trzy poziomy 10%, 50%, 95% po 60 s każdy.
"""
import argparse
import time
from trex_stl_lib.api import STLClient
from constant import STLS1

PORTS = [0, 1, 2, 3]


def run_steps(levels, dwell: float):
    c = STLClient()
    c.connect()
    try:
        c.reset(ports=PORTS)
        c.add_streams(STLS1().get_streams(direction=0), ports=PORTS)
        c.start(ports=PORTS, mult=f"{levels[0]}%", force=True)
        for i, lvl in enumerate(levels):
            print(f"[poziom {i+1}/{len(levels)}] rate = {lvl}%, dwell {dwell}s")
            c.update(ports=PORTS, mult=f"{lvl}%")
            time.sleep(dwell)
        c.stop(ports=PORTS)
    finally:
        c.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--levels", default="10,50,95",
                        help="lista poziomów w procentach, np. 10,50,95")
    parser.add_argument("--dwell", type=float, default=60.0,
                        help="czas trwania każdego poziomu w sekundach")
    args = parser.parse_args()
    levels = [float(x) for x in args.levels.split(",")]
    run_steps(levels, args.dwell)
