"""
Eksport histogramu do PNG i percentyle (post-processing).
"""
import csv
from pathlib import Path

# UWAGA: ustawiamy non-interactive backend PRZED importem pyplot.
# Inaczej matplotlib próbuje załadować TkAgg który wymaga GUI loop —
# crash 'main thread is not in main loop' przy długim pomiarze
# (z wielokrotnym savefig w trakcie pollingu).
import matplotlib
matplotlib.use("Agg")

import subprocess
import datetime
import os

from config import HISTOGRAM_BIN_WIDTH_NS, HISTOGRAM_OFFSET_NS


def _git_commit():
    """Zwraca skrócony hash git commit (lub 'unknown' jeśli nie git/brak)."""
    try:
        # Repo jest w katalogu nadrzędnym względem analyzer/controller/
        repo_dir = Path(__file__).resolve().parents[2]
        out = subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=2,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def _git_dirty():
    """Zwraca '-dirty' jeśli są niezacommitowane zmiany, inaczej ''."""
    try:
        repo_dir = Path(__file__).resolve().parents[2]
        out = subprocess.check_output(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            stderr=subprocess.DEVNULL, timeout=2,
        )
        return "-dirty" if out.strip() else ""
    except Exception:
        return ""


def _build_metadata():
    """Zwraca dict metadata do zapisu w plikach pomiarowych."""
    # Lazy import baseline_mode (config może mieć cykliczny import)
    try:
        from config import BASELINE_MODE
    except Exception:
        BASELINE_MODE = "?"
    return {
        "git_commit": _git_commit() + _git_dirty(),
        "timestamp":  datetime.datetime.now().isoformat(timespec="seconds"),
        "bin_width_ns": HISTOGRAM_BIN_WIDTH_NS,
        "bin_offset_ns": HISTOGRAM_OFFSET_NS,
        "baseline_mode": BASELINE_MODE,
        "host": os.uname().nodename,
    }


def _metadata_header_csv():
    """Zwraca jednolinijkowy nagłówek metadata jako komentarz CSV."""
    md = _build_metadata()
    return "# " + "; ".join(f"{k}={v}" for k, v in md.items())


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




def _bin_midpoints(n_bins=128):
    """Lista środków binów w nanosekundach."""
    return [HISTOGRAM_OFFSET_NS + (i + 0.5) * HISTOGRAM_BIN_WIDTH_NS
            for i in range(n_bins)]


def histogram_to_mean(hist):
    """Średnia ważona z histogramu.

    Σ (bin_midpoint × count[bin]) / Σ count[bin]

    Bardziej odporne na overflow niż reg_sum_lo / reg_count (każdy bin
    ma własny 32-bit licznik, mało prawdopodobne że pojedynczy bin
    przekroczy 2³²)."""
    total = sum(hist)
    if total == 0:
        return 0.0
    midpoints = _bin_midpoints(len(hist))
    weighted_sum = sum(m * c for m, c in zip(midpoints, hist))
    return weighted_sum / total


def histogram_to_stats(hist, drop_first_bin=True):
    """Zwraca słownik z mean, std, min, max, total.

    Args:
        hist: lista N int (liczba pakietów w binie)
        drop_first_bin: jeśli True, pomija bin [0..bin_width)
                        który zazwyczaj zbiera artefakty (pakiety bez
                        ekstraktowanego tx_ts).

    Returns:
        dict: mean, std, min, max, total (wszystko w ns, total liczba)
    """
    if drop_first_bin and len(hist) > 0:
        hist = list(hist)
        hist[0] = 0   # zeruj artefakt 0..bin_width

    total = sum(hist)
    if total == 0:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "total": 0}

    midpoints = _bin_midpoints(len(hist))

    # Średnia ważona
    mean = sum(m * c for m, c in zip(midpoints, hist)) / total

    # Wariancja i odchylenie standardowe
    variance = sum(c * (m - mean) ** 2 for m, c in zip(midpoints, hist)) / total
    std = variance ** 0.5

    # Min i max — pierwszy/ostatni bin z count > 0
    first_nonempty = next((i for i, c in enumerate(hist) if c > 0), None)
    last_nonempty  = next((i for i, c in enumerate(reversed(hist)) if c > 0), None)
    if first_nonempty is None:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "total": 0}

    last_idx = len(hist) - 1 - last_nonempty
    return {
        "mean":  mean,
        "std":   std,
        "min":   midpoints[first_nonempty],
        "max":   midpoints[last_idx],
        "total": total,
    }


def save_histogram_csv(hist_dut, hist_base, path: Path):
    """Zapisuje histogram jako CSV.

    Format:
      # git_commit=...; timestamp=...; bin_width_ns=...; ...   ← metadata
      bin_lo_ns,bin_hi_ns,count_dut,count_base                ← header
      0,20,12345,678                                          ← dane
      ...

    Czytelnik pandas: pd.read_csv(path, comment='#')
    """
    with open(path, "w", newline="") as f:
        # Komentarz metadata jako pierwsza linia (Pandas/csv ignoruje z comment='#')
        f.write(_metadata_header_csv() + "\n")
        writer = csv.writer(f)
        writer.writerow(["bin_lo_ns", "bin_hi_ns", "count_dut", "count_base"])
        for i in range(128):
            lo = HISTOGRAM_OFFSET_NS + i * HISTOGRAM_BIN_WIDTH_NS
            hi = HISTOGRAM_OFFSET_NS + (i + 1) * HISTOGRAM_BIN_WIDTH_NS
            writer.writerow([lo, hi, hist_dut[i], hist_base[i]])
    print(f"[OK] histogram zapisany do {path}")


def save_histogram_png(hist_dut, hist_base, path: Path,
                       title="Δ histogram (DUT vs baseline)"):
    """Zapisuje histogram jako PNG (matplotlib Agg backend, headless safe)."""
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
    # Footer z metadata
    md = _build_metadata()
    footer = f"git: {md['git_commit']}  |  {md['timestamp']}  |  bin_width={md['bin_width_ns']} ns  |  baseline={md['baseline_mode']}  |  host={md['host']}"
    fig.text(0.5, 0.01, footer, ha='center', fontsize=7, color='gray')
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"[OK] histogram zapisany do {path}")
