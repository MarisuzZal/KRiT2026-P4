#!/usr/bin/env python3
"""
Post-hoc analiza histogramu z hist_*.csv (z poprzednich runs).

Liczy:
  - średnią ważoną (mean)
  - odchylenie standardowe (std)
  - min, max
  - percentyle 50, 90, 95, 99, 99.9
  - liczbę pakietów

Uruchomienie:
    python3 analyzer/controller/analyze_hist.py path/to/hist_final.csv
"""
import csv
import sys
from pathlib import Path


def analyze(path: Path):
    bins = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            bins.append({
                "lo":  int(row["bin_lo_ns"]),
                "hi":  int(row["bin_hi_ns"]),
                "mid": (int(row["bin_lo_ns"]) + int(row["bin_hi_ns"])) / 2,
                "dut": int(row["count_dut"]),
                "base": int(row["count_base"]),
            })

    for which in ("dut", "base"):
        counts = [b[which] for b in bins]
        # Pomiń pierwszy bin (artefakty 0-bin_width)
        counts_clean = counts.copy()
        counts_clean[0] = 0

        total = sum(counts_clean)
        if total == 0:
            print(f"\n--- {which.upper()} ---  brak pakietów (pomijając bin 0)")
            continue

        midpoints = [b["mid"] for b in bins]

        # Mean
        mean = sum(m * c for m, c in zip(midpoints, counts_clean)) / total

        # Std
        var = sum(c * (m - mean) ** 2 for m, c in zip(midpoints, counts_clean)) / total
        std = var ** 0.5

        # Min, max
        first = next((i for i, c in enumerate(counts_clean) if c > 0), None)
        last  = next((i for i, c in enumerate(reversed(counts_clean)) if c > 0), None)
        min_v = bins[first]["mid"]
        max_v = bins[len(bins) - 1 - last]["mid"]

        # Percentyle
        percentiles = [50, 90, 95, 99, 99.9]
        cum = 0
        pct_results = {}
        for i, c in enumerate(counts_clean):
            cum += c
            frac = cum / total * 100
            for p in list(percentiles):
                if frac >= p:
                    pct_results[p] = bins[i]["mid"]
                    percentiles.remove(p)
        for p in percentiles:
            pct_results[p] = bins[-1]["mid"]

        # Wyjście
        print(f"\n--- {which.upper()} ({path.name}) ---")
        print(f"  Total packets:     {total:>15,}")
        print(f"  Mean:              {mean:>12.2f} ns")
        print(f"  Std dev:           {std:>12.2f} ns")
        print(f"  Min:               {min_v:>12.1f} ns")
        print(f"  Max:               {max_v:>12.1f} ns")
        print(f"  Jitter (max-min):  {max_v - min_v:>12.1f} ns")
        for p in [50, 90, 95, 99, 99.9]:
            print(f"  p{p}:                {pct_results[p]:>12.1f} ns")

        # Anomalia (bin 0)
        if counts[0] > 0:
            pct_anomaly = counts[0] / sum(counts) * 100
            print(f"  Artefakt 0-{bins[0]['hi']} ns: {counts[0]:>15,} pakietów ({pct_anomaly:.3f}%)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python3 analyze_hist.py path/to/hist_final.csv [hist_*.csv ...]")
        sys.exit(1)
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"[WARN] brak pliku: {p}")
            continue
        analyze(p)
