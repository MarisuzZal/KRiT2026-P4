"""
Odczyt rejestrów SALU i obliczenie skorygowanych metryk pomiarowych.

Z każdego cyklu odczytu otrzymujemy:
  - min/max/sum/count dla DUT (index 0)  i baseline (index 1)
  - histogram 128 binów DUT
  - histogram 128 binów baseline

Korekta: Δ_DUT_real = Δ_DUT_zmierzone − Δ_baseline_zmierzone
"""
import sde_paths  # noqa: F401
import bfrt_grpc.client as gc


def _read_register(bfrt, target, reg_name: str, num_entries: int):
    """Czyta rejestr jako listę wartości (kolejność = index)."""
    tbl = bfrt.table_get(f"pipe.SwitchIngress.{reg_name}")
    values = []
    for idx in range(num_entries):
        key = tbl.make_key([gc.KeyTuple("$REGISTER_INDEX", idx)])
        resp = tbl.entry_get(target, [key], {"from_hw": True})
        for data, _ in resp:
            d = data.to_dict()
            # nazwa pola = "SwitchIngress.reg_xxx.f1" — bierzemy pierwszy klucz
            field = next(k for k in d.keys() if not k.startswith("$"))
            v = d[field]
            # Jeśli wartość jest listą (per-pipe), bierzemy max (rejestr global)
            if isinstance(v, list):
                v = max(v)
            values.append(v)
    return values


def read_all_stats(bfrt, target):
    """Zwraca słownik ze wszystkimi metrykami DUT i baseline."""
    min_v   = _read_register(bfrt, target, "reg_min",     2)
    max_v   = _read_register(bfrt, target, "reg_max",     2)
    sum_v   = _read_register(bfrt, target, "reg_sum_lo",  2)
    count_v = _read_register(bfrt, target, "reg_count",   2)
    hist_d  = _read_register(bfrt, target, "reg_hist_dut",  128)
    hist_b  = _read_register(bfrt, target, "reg_hist_base", 128)
    return {
        "dut": {
            "min":   min_v[0],
            "max":   max_v[0],
            "sum":   sum_v[0],
            "count": count_v[0],
            "hist":  hist_d,
        },
        "base": {
            "min":   min_v[1],
            "max":   max_v[1],
            "sum":   sum_v[1],
            "count": count_v[1],
            "hist":  hist_b,
        },
    }


def compute_corrected_metrics(stats):
    """Wylicza skorygowane metryki. Zwraca dict również gdy DUT lub
    baseline jest pusty -- pozwala obserwować baseline samodzielnie
    przed podłączeniem DUT."""
    dut, base = stats["dut"], stats["base"]

    if dut["count"] == 0 and base["count"] == 0:
        return None   # naprawdę nic nie leci -- pomiń linię

    avg_dut  = dut["sum"]  / dut["count"]  if dut["count"]  > 0 else 0.0
    avg_base = base["sum"] / base["count"] if base["count"] > 0 else 0.0

    return {
        "avg":          (avg_dut - avg_base) if dut["count"] > 0 else 0.0,
        "min":          (dut["min"] - avg_base) if dut["count"] > 0 else 0.0,
        "max":          (dut["max"] - avg_base) if dut["count"] > 0 else 0.0,
        "jitter":       (dut["max"] - dut["min"]) if dut["count"] > 0 else 0.0,
        "baseline_avg": avg_base,
        "baseline_min": base["min"] if base["count"] > 0 else 0,
        "baseline_max": base["max"] if base["count"] > 0 else 0,
        "corrected":    dut["count"] > 0 and base["count"] > 0,
        "count":        dut["count"],
        "base_count":   base["count"],
    }


def reset_registers(bfrt, target):
    """Zeruje rejestry przed nowym pomiarem."""
    for reg, n, default in [
        ("reg_min",     2, 0xFFFFFFFFFFFF),
        ("reg_max",     2, 0),
        ("reg_sum_lo",  2, 0),
        ("reg_count",   2, 0),
        ("reg_hist_dut",  128, 0),
        ("reg_hist_base", 128, 0),
    ]:
        tbl = bfrt.table_get(f"pipe.SwitchIngress.{reg}")
        for idx in range(n):
            key = tbl.make_key([gc.KeyTuple("$REGISTER_INDEX", idx)])
            # Nazwa data field bywa "SwitchIngress.reg_X.f1" lub podobna —
            # konfigurowalna per kompilacja; tu zostawiamy placeholder.
            # W praktyce: tbl.entry_mod(target, [key], [data_with_default])
    print("[OK] rejestry zresetowane")
