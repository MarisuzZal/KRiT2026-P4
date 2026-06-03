"""
Eksport histogramu do PNG i percentyle (post-processing).
"""
import csv
from pathlib import Path

from config import HISTOGRAM_BIN_WIDTH_NS, HISTOGRAM_OFFSET_NS


def histogram_to_percentiles(hist, percentiles=(50, 90, 95, 99, 99.9)):
    """Wylicza percentyle Δ z histogramu binowego."""
    total = sum(hist)
    if total == 0:
        return {p: None for p in percentiles}

    cumulative = 0
    result = {}
    remaining = sorted(percentiles)
    for bin_idx, count in enumerate(hist):
        cumulative += count
        frac = cumulative / total * 100
        while remaining and frac >= remaining[0]:
            p = remaining.pop(0)
            # Środek binu jako reprezentant
            result[p] = HISTOGRAM_OFFSET_NS + (bin_idx + 0.5) * HISTOGRAM_BIN_WIDTH_NS
    for p in remaining:
        result[p] = HISTOGRAM_OFFSET_NS + 127.5 * HISTOGRAM_BIN_WIDTH_NS
    return result


def save_histogram_csv(hist_dut, hist_base, path: Path):
    """Zapisuje histogram jako CSV (bin_lo, bin_hi, count_dut, count_base)."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["bin_lo_ns", "bin_hi_ns", "count_dut", "count_base"])
        for i in range(128):
            lo = HISTOGRAM_OFFSET_NS + i * HISTOGRAM_BIN_WIDTH_NS
            hi = HISTOGRAM_OFFSET_NS + (i + 1) * HISTOGRAM_BIN_WIDTH_NS
            writer.writerow([lo, hi, hist_dut[i], hist_base[i]])
    print(f"[OK] histogram zapisany do {path}")


def save_histogram_png(hist_dut, hist_base, path: Path,
                       title="Δ histogram (DUT vs baseline)"):
    """Zapisuje histogram jako PNG (wymaga matplotlib)."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib nie jest zainstalowany — pomijam PNG")
        return

    bins_lo = [HISTOGRAM_OFFSET_NS + i * HISTOGRAM_BIN_WIDTH_NS for i in range(128)]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(bins_lo, hist_dut,  width=HISTOGRAM_BIN_WIDTH_NS,
           alpha=0.6, label="DUT (10.0/1/2/3)", color="steelblue")
    ax.bar(bins_lo, hist_base, width=HISTOGRAM_BIN_WIDTH_NS,
           alpha=0.6, label="baseline (10.250.X.X)", color="orange")
    ax.set_xlabel("Δ [ns]")
    ax.set_ylabel("liczba pakietów")
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"[OK] histogram zapisany do {path}")
