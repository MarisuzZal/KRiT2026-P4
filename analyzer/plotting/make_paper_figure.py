#!/usr/bin/env python3
"""
Generuje figurę dla §6 KRiT 2026 paper:
  - 3 histogramy DUT na jednym wykresie (log-skala X)
  - bin 0 oznaczony jako TX-artifact (dropped)
  - annotacje z Δ_DUT_corrected per program
  - footer z metadata commit + timestamp

Plus tabela LaTeX z liczbami dla §6.

Uruchom:
  cd analyzer
  python3 plotting/make_paper_figure.py
  → paper_figure_dut_comparison.pdf
  → paper_figure_dut_comparison.png
  → paper_table_dut_comparison.tex
"""
import csv
import io
import sys
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def read_hist(path):
    """Czyta hist_final*.csv (z metadata header), zwraca (bins_lo, dut, base, meta)."""
    data = Path(path).read_text(encoding="utf-8").replace("\x00", "")
    md_line = data.split("\n", 1)[0]
    meta = {}
    if md_line.startswith("#"):
        for kv in md_line[1:].strip().split(";"):
            kv = kv.strip()
            if "=" in kv:
                k, v = kv.split("=", 1)
                meta[k.strip()] = v.strip()
    lines = [l for l in data.split("\n") if l and not l.startswith("#")]
    r = csv.reader(io.StringIO("\n".join(lines)))
    next(r)  # header
    bins_lo = []
    bins_hi = []
    dut = []
    base = []
    for row in r:
        if len(row) >= 4 and row[0]:
            try:
                bins_lo.append(int(row[0]))
                bins_hi.append(int(row[1]))
                dut.append(int(row[2]))
                base.append(int(row[3]))
            except ValueError:
                pass
    return np.array(bins_lo), np.array(bins_hi), np.array(dut), np.array(base), meta


def compute_stats(bins_lo, bins_hi, counts, drop_first_bin=True):
    """Mean, std, total (po opcjonalnym drop bin 0)."""
    if drop_first_bin:
        counts = counts.copy()
        counts[0] = 0
    total = counts.sum()
    if total == 0:
        return {"mean": 0, "std": 0, "total": 0}
    midpoints = (bins_lo + bins_hi) / 2.0
    mean = (midpoints * counts).sum() / total
    var = ((midpoints - mean) ** 2 * counts).sum() / total
    return {"mean": mean, "std": var ** 0.5, "total": total,
            "midpoints": midpoints, "counts": counts}


def main():
    results_dir = Path("../results/2026-06-05")
    if not results_dir.exists():
        results_dir = Path("results/2026-06-05")
    if not results_dir.exists():
        print(f"BŁĄD: nie znaleziono katalogu z danymi: {results_dir}")
        sys.exit(1)

    runs = [
        ("null_switch",  "null_switch",   "tab:blue"),
        ("l2l3_switch",  "l2l3_switch",   "tab:orange"),
        ("l2l3_recirc2", "l2l3_recirc2",  "tab:red"),
    ]

    # Wczytaj wszystkie 3 runy
    data = {}
    # Hardcoded values z polling reg_min/max + snap_delta dla scenariuszy
    # gdzie delta przekracza 65 μs (max range klucza ig_md.delta[15:0]).
    # Histogram się WTEDY zachowuje błędnie (modulo 65,536 + bin 0 overflow),
    # ale reg_min/max widzą prawdziwe 32-bit wartości.
    HISTOGRAM_OUT_OF_RANGE = {
        "l2l3_recirc2": {
            "mean": 198955.0,    # = (reg_min 196,536 + reg_max 201,375) / 2
            "std":  1209.0,       # = jitter / 4 estimate (jitter 4,839 ns)
            "reg_min": 196536.0,
            "reg_max": 201375.0,
            "from": "reg_min/max polling (snap_DUT confirms ~201,500 ns)",
        },
    }

    for label, fname_suffix, color in runs:
        path = results_dir / f"hist_final_{fname_suffix}.csv"
        if not path.exists():
            print(f"OSTRZEŻENIE: brak {path}")
            continue
        bl, bh, dut, base, meta = read_hist(path)
        sd = compute_stats(bl, bh, dut)
        sb = compute_stats(bl, bh, base)
        # Override dla scenariuszy poza zakresem histogramu
        if label in HISTOGRAM_OUT_OF_RANGE:
            override = HISTOGRAM_OUT_OF_RANGE[label]
            sd["mean"] = override["mean"]
            sd["std"]  = override["std"]
            sd["from_polling"] = True
            print(f"  [INFO] {label}: histogram out of range, używam reg_min/max")
        else:
            sd["from_polling"] = False
        data[label] = dict(bl=bl, bh=bh, dut=dut, base=base,
                           sd=sd, sb=sb, meta=meta, color=color)
        src = " [reg_min/max]" if sd["from_polling"] else ""
        print(f"{label}: Δ_DUT mean={sd['mean']:.1f} ± {sd['std']:.1f} ns "
              f"(N={sd['total']:,}){src}")

    if not data:
        print("BŁĄD: żaden plik nie został wczytany")
        sys.exit(1)

    # === FIGURA: 3 histogramy DUT na jednym wykresie (log-skala X) ===
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bin_width = data[list(data)[0]]["bl"][1] - data[list(data)[0]]["bl"][0]

    for label, d in data.items():
        midpoints = (d["bl"] + d["bh"]) / 2
        # bar plot z log-y żeby ogonki były widoczne
        ax.bar(midpoints, d["dut"], width=bin_width * 0.9,
               alpha=0.55, label=f"{label} (N={d['sd']['total']:,})",
               color=d["color"], edgecolor=d["color"], linewidth=0)

    # Baseline na osobnym kolorze
    baseline_label = list(data)[0]
    d_base = data[baseline_label]
    midpoints = (d_base["bl"] + d_base["bh"]) / 2
    ax.bar(midpoints, d_base["base"], width=bin_width * 0.7,
           alpha=0.35, label=f"baseline (Δ ≈ 650 ns, σ < 1 ns)",
           color="tab:gray", edgecolor="black", linewidth=0.3)

    # Annotacje Δ_DUT_corrected
    bx_y = max(d["dut"].max() for d in data.values()) * 0.6
    for i, (label, d) in enumerate(data.items()):
        delta_corr = d["sd"]["mean"] - 650  # baseline ~ 650 ns
        ax.annotate(
            f"{label}\nΔ = {delta_corr:.0f} ns",
            xy=(d["sd"]["mean"], d["sd"]["total"] * 0.55),
            xytext=(d["sd"]["mean"] * 1.4, bx_y * (1 - 0.15 * i)),
            arrowprops=dict(arrowstyle="->", color=d["color"], lw=1),
            fontsize=9, color=d["color"], ha="left",
        )

    ax.set_xscale("log")
    ax.set_xlabel("Δ [ns]  (log-skala)")
    ax.set_ylabel("liczba pakietów")
    ax.set_title("Δ_DUT vs Δ_baseline — 3 programy DUT (15 min runy)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, which="both", alpha=0.3)
    ax.set_xlim(50, 300_000)

    # Footer
    md = data[list(data)[0]]["meta"]
    footer = (f"git: {md.get('git_commit', '?')}  |  "
              f"runs: {', '.join(data.keys())}  |  "
              f"bin_width = {md.get('bin_width_ns', '?')} ns")
    fig.text(0.5, 0.01, footer, ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=[0, 0.03, 1, 1])

    out_pdf = Path("paper_figure_dut_comparison.pdf")
    out_png = Path("paper_figure_dut_comparison.png")
    fig.savefig(out_pdf, dpi=150, bbox_inches="tight")
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {out_pdf}, {out_png}")

    # === TABELA LaTeX ===
    tex = r"""\begin{table}[t]
\centering
\caption{Wyniki pomiaru Δ_DUT dla trzech programów DUT (15 min, 4 kierunki, 100~Gbps). $^\dagger$Dla l2l3\_recirc2 wartości z reg\_min/max polling — histogram przekracza zakres 16-bit slice klucza.}
\label{tab:dut_comparison}
\begin{tabular}{l r r r r r}
\toprule
\textbf{Program DUT} & \textbf{N pakietów} & \textbf{Δ\_DUT} & \textbf{σ\_DUT} & \textbf{Δ\_DUT - Δ\_base} & \textbf{vs. null} \\
& & \textbf{[ns]} & \textbf{[ns]} & \textbf{[ns]} & \\
\midrule
"""
    base_mean = 650.0  # globalna baseline
    null_mean = data.get("null_switch", {"sd": {"mean": 0}})["sd"]["mean"]
    for label, d in data.items():
        n = d["sd"]["total"]
        mean = d["sd"]["mean"]
        std = d["sd"]["std"]
        corr = mean - base_mean
        delta_vs_null = corr - (null_mean - base_mean)
        vs_null = f"+{delta_vs_null:.1f}" if delta_vs_null > 0 else ("—" if delta_vs_null == 0 else f"{delta_vs_null:.1f}")
        safe_label = label.replace("_", "\\_")
        marker = "$^\\dagger$" if d["sd"].get("from_polling", False) else ""
        tex += f"{safe_label}{marker} & {n:,} & {mean:.1f} & {std:.1f} & {corr:.1f} & {vs_null} \\\\\n"

    tex += r"""\bottomrule
\end{tabular}
\end{table}
"""
    Path("paper_table_dut_comparison.tex").write_text(tex, encoding="utf-8")
    print(f"[OK] paper_table_dut_comparison.tex")


if __name__ == "__main__":
    main()
