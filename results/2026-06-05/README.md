# Runy pomiarowe — 5 czerwca 2026

3 × 15-minutowy pomiar Δ_DUT_corrected dla różnych programów DUT.
Testbed: TRex v3.08 + Tofino #1 (FanInOut measurement) + Tofino #2 (DUT).

## Wyniki

| Program DUT | Δ_DUT_corrected | σ_baseline | git_commit |
|:---|---:|---:|:---|
| null_switch  | 991.7 ns | 0.79 ns | 9988a36 |
| l2l3_switch  | 1014.0 ns (+22 ns) | 0.79 ns | 5c7a646 |
| l2l3_recirc2 | ~195 μs (200×) | 0.61 ns | 5c7a646 |

Histogram dla l2l3_recirc2 cały w bin 0 — modulo 65,536 overflow w slice
[15:0] klucza histogram_bin_map. Realne wartości z reg_min/max + snap_delta
w polling (193-202 μs).

Szczegóły w docs/findings.md §14.
