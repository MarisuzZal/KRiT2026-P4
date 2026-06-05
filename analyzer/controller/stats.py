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


def _read_register(bfrt, target, reg_name: str, num_entries: int, aggregator=sum):
    """Czyta rejestr jako listę wartości (kolejność = index).

    Per-pipe register w hardware to lista 4 wartości (jedna per pipe).
    Aggregator decyduje jak agregować:
      - sum:  dla count i sum (globalna suma per pipe)
      - max:  dla reg_max (faktyczne maksimum)
      - min:  dla reg_min (faktyczne minimum)
    """
    tbl = bfrt.table_get(f"pipe.SwitchIngress.{reg_name}")
    values = []
    for idx in range(num_entries):
        key = tbl.make_key([gc.KeyTuple("$REGISTER_INDEX", idx)])
        resp = tbl.entry_get(target, [key], {"from_hw": True})
        for data, _ in resp:
            d = data.to_dict()
            field = next(k for k in d.keys() if not k.startswith("$"))
            v = d[field]
            if isinstance(v, list):
                v = aggregator(v)
            values.append(v)
    return values


def read_all_stats(bfrt, target):
    """Zwraca słownik ze wszystkimi metrykami DUT i baseline.
    Per-pipe aggregation:
      - min/max: faktyczne min/max ze wszystkich pipes
      - sum/count/hist: globalna suma per pipe
    """
    min_v   = _read_register(bfrt, target, "reg_min",     2, aggregator=min)
    max_v   = _read_register(bfrt, target, "reg_max",     2, aggregator=max)
    sum_v   = _read_register(bfrt, target, "reg_sum_lo",  2, aggregator=sum)
    count_v = _read_register(bfrt, target, "reg_count",   2, aggregator=sum)
    hist_d  = _read_register(bfrt, target, "reg_hist_dut",  128, aggregator=sum)
    hist_b  = _read_register(bfrt, target, "reg_hist_base", 128, aggregator=sum)
    # DIAGNOSTYKA Bug B: snapshot ig_md.delta dla ostatniego pakietu w każdym pipe.
    # Agregacja: max — jeśli ANY pipe widzi delta>=1000, snap_delta będzie 1000+.
    snap_d  = _read_register(bfrt, target, "reg_snap_delta", 2, aggregator=max)
    return {
        "dut": {
            "min":   min_v[0],
            "max":   max_v[0],
            "sum":   sum_v[0],
            "count": count_v[0],
            "hist":  hist_d,
            "snap_delta": snap_d[0],
        },
        "base": {
            "min":   min_v[1],
            "max":   max_v[1],
            "sum":   sum_v[1],
            "count": count_v[1],
            "hist":  hist_b,
            "snap_delta": snap_d[1],
        },
    }


def compute_corrected_metrics(stats):
    """Wylicza skorygowane metryki.

    Średnia liczona z HISTOGRAMU (Σ midpoint × count / Σ count),
    nie z reg_sum_lo / reg_count, bo reg_sum_lo jest 32-bit i
    overflow'uje po ~6.6M pakietów × 646 ns. Histogram odporny
    bo każdy bin ma własny 32-bit licznik.

    Min/max z reg_min/reg_max (te są stabilne — single-pkt update).
    Jitter z reg_max - reg_min."""
    from histogram import histogram_to_stats

    dut, base = stats["dut"], stats["base"]
    dut_hstats  = histogram_to_stats(dut["hist"],  drop_first_bin=True)
    base_hstats = histogram_to_stats(base["hist"], drop_first_bin=True)

    if dut["count"] == 0 and base["count"] == 0:
        return None

    avg_dut  = dut_hstats["mean"]
    avg_base = base_hstats["mean"]

    return {
        "avg":          (avg_dut - avg_base) if dut["count"] > 0 else 0.0,
        "min":          (dut["min"] - avg_base) if dut["count"] > 0 else 0.0,
        "max":          (dut["max"] - avg_base) if dut["count"] > 0 else 0.0,
        "jitter":       (dut["max"] - dut["min"]) if dut["count"] > 0 else 0.0,
        "baseline_avg": avg_base,
        "baseline_std": base_hstats["std"],
        "baseline_min": base["min"] if base["count"] > 0 else 0,
        "baseline_max": base["max"] if base["count"] > 0 else 0,
        "baseline_total_hist": base_hstats["total"],
        "corrected":    dut["count"] > 0 and base["count"] > 0,
        "count":        dut["count"],
        "base_count":   base["count"],
    }


def reset_registers(bfrt, target):
    """Zeruje rejestry SALU przed nowym pomiarem.

    Tofino zachowuje stan rejestrów między uruchomieniami kontrolera —
    bez resetu nowy run "widzi" dane z poprzednich pomiarów. To wpływa
    głównie na hist_dut/hist_base oraz reg_count.

    Używa autodyskrycji data field name (per kompilacja).
    """
    register_specs = [
        ("reg_min",        2,   0xFFFFFFFF),
        ("reg_max",        2,   0),
        ("reg_sum_lo",     2,   0),
        ("reg_count",      2,   0),
        ("reg_hist_dut",   128, 0),
        ("reg_hist_base",  128, 0),
        ("reg_snap_delta", 2,   0),
    ]
    for reg, n, default in register_specs:
        try:
            tbl = bfrt.table_get(f"pipe.SwitchIngress.{reg}")
        except Exception as e:
            print(f"[WARN] reset {reg}: tabela nie istnieje ({e})")
            continue
        # Autodyskrycja nazwy pola data (BfRt nazewnictwo zmienne)
        data_field = None
        try:
            field_names = tbl.info.data_field_name_list_get()
            data_field = next((f for f in field_names if not f.startswith("$")), None)
        except Exception:
            pass
        if data_field is None:
            print(f"[WARN] reset {reg}: brak pola data — pomijam")
            continue
        # Zeruj wszystkie indeksy
        n_done = 0
        for idx in range(n):
            key = tbl.make_key([gc.KeyTuple("$REGISTER_INDEX", idx)])
            data = tbl.make_data([gc.DataTuple(data_field, default)])
            try:
                tbl.entry_mod(target, [key], [data])
                n_done += 1
            except Exception as e:
                # Niektóre rejestry mogą wymagać entry_add
                try:
                    tbl.entry_add(target, [key], [data])
                    n_done += 1
                except Exception:
                    pass
        print(f"[OK] reset {reg}: {n_done}/{n} indeksów zerowane (default={default})")
