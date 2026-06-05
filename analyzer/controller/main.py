#!/usr/bin/env python3
"""
Kontroler pomiarowy KRiT2026-P4.

Cykl:
  1) Połączenie z bf_switchd przez gRPC
  2) Wyczyszczenie + zaprogramowanie tabel (port_routing, histogram_bin_map)
  3) Polling rejestrów co POLL_INTERVAL_SEC, korekta baseline, log do CSV
  4) Co 60 s: zapis histogramu PNG (snapshot)

Wymaga:
  - Intel P4 Studio SDE 9.13.2 (bfrt_grpc.client)
  - matplotlib (opcjonalnie, do PNG)
"""
import argparse
import csv
import signal
import sys
import time
from pathlib import Path

import sde_paths  # noqa: F401
import bfrt_grpc.client as gc

import config
from config import (
    DEVICE_ID, PROGRAM, POLL_INTERVAL_SEC, CSV_OUTPUT_PATH,
    BASELINE_MODE,
)
from ports  import configure_all_ports
from routing import program_routing, program_routing_per_pipe, program_histogram, clear_all
from stats import read_all_stats, compute_corrected_metrics, reset_registers
from histogram import save_histogram_csv, save_histogram_png


_running = True


def _handle_sigint(signum, frame):
    global _running
    _running = False
    print("\n[*] Otrzymano SIGINT — kończę polling...")


def connect():
    """Łączy się z bf_switchd, zwraca (bfrt, target)."""
    interface = gc.ClientInterface(config.GRPC_ADDR, client_id=0, device_id=DEVICE_ID)
    target = gc.Target(device_id=DEVICE_ID, pipe_id=0xffff)
    interface.bind_pipeline_config(PROGRAM)
    bfrt = interface.bfrt_info_get(PROGRAM)
    print(f"[OK] połączono z {config.GRPC_ADDR}, program={PROGRAM}, baseline={BASELINE_MODE}")
    return bfrt, target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--grpc-host", default=None,
                        help="Host bf_switchd (override BF_SWITCHD_HOST i config.py)")
    parser.add_argument("--grpc-port", type=int, default=None,
                        help="Port bf_switchd (default 50052)")
    parser.add_argument("--no-program", action="store_true",
                        help="Tylko polling, bez programowania tabel")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="Czas pomiaru w sekundach (0 = nieskończony, do Ctrl+C)")
    parser.add_argument("--snapshot-interval", type=float, default=60.0,
                        help="Co ile sekund zapisać snapshot histogramu PNG")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_sigint)

    # CLI override gRPC endpoint
    if args.grpc_host or args.grpc_port:
        host = args.grpc_host or config.ANALYZER_HOST
        port = args.grpc_port or config.ANALYZER_PORT
        config.GRPC_ADDR = f"{host}:{port}"
        print(f"[*] gRPC endpoint override: {config.GRPC_ADDR}")

    bfrt, target = connect()

    if not args.no_program:
        configure_all_ports(bfrt, target)
        clear_all(bfrt, target)
        reset_registers(bfrt, target)
        program_routing(bfrt, target)
        program_histogram(bfrt, target)
        print("[*] Tabele zaprogramowane. Czekam 2 s na ustabilizowanie...")
        time.sleep(2.0)

    # CSV log
    csv_path = Path(CSV_OUTPUT_PATH)
    csv_file = open(csv_path, "w", newline="")
    # Metadata header (importujemy z histogram.py — wspólne)
    from histogram import _metadata_header_csv
    csv_file.write(_metadata_header_csv() + "\n")
    csv_file.flush()
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        "timestamp", "dut_count", "base_count",
        "dut_min", "dut_max", "dut_avg", "jitter",
        "base_min", "base_max", "base_avg", "base_std", "base_total_hist",
        "corrected_avg", "corrected_min", "corrected_max",
    ])
    print(f"[*] Logowanie do {csv_path}")

    start_time = time.time()
    last_snapshot = start_time
    snapshot_idx = 0

    print(f"[*] Start pollingu (interval={POLL_INTERVAL_SEC}s)")
    print(f"{'timestamp':>10} {'count_DUT':>10} {'avg_real':>10} "
          f"{'min':>8} {'max':>8} {'jitter':>8} {'base_avg':>10} "
          f"{'base_std':>10} {'base_n':>12} {'snap_DUT':>10} {'snap_BASE':>10}")

    while _running:
        time.sleep(POLL_INTERVAL_SEC)
        now = time.time()
        elapsed = now - start_time

        stats = read_all_stats(bfrt, target)
        metrics = compute_corrected_metrics(stats)
        if metrics is None:
            continue

        csv_writer.writerow([
            f"{elapsed:.3f}",
            stats["dut"]["count"], stats["base"]["count"],
            stats["dut"]["min"], stats["dut"]["max"],
            stats["dut"]["sum"] / max(1, stats["dut"]["count"]),
            metrics["jitter"],
            stats["base"]["min"], stats["base"]["max"],
            metrics.get("baseline_avg", 0),
            metrics.get("baseline_std", 0),
            metrics.get("baseline_total_hist", 0),
            metrics["avg"], metrics["min"], metrics["max"],
        ])
        csv_file.flush()

        print(f"{elapsed:10.1f} {stats['dut']['count']:>10} "
              f"{metrics['avg']:>10.1f} {metrics['min']:>8.1f} "
              f"{metrics['max']:>8.1f} {metrics['jitter']:>8.1f} "
              f"{metrics.get('baseline_avg', 0):>10.1f} "
              f"{metrics.get('baseline_std', 0):>10.2f} "
              f"{metrics.get('baseline_total_hist', 0):>12} "
              f"{stats['dut'].get('snap_delta', 0):>10} "
              f"{stats['base'].get('snap_delta', 0):>10}")

        # Snapshot PNG co N sekund
        if now - last_snapshot >= args.snapshot_interval:
            snap_csv = Path(f"hist_{snapshot_idx:04d}.csv")
            snap_png = Path(f"hist_{snapshot_idx:04d}.png")
            save_histogram_csv(stats["dut"]["hist"], stats["base"]["hist"], snap_csv)
            save_histogram_png(stats["dut"]["hist"], stats["base"]["hist"], snap_png,
                               title=f"Δ histogram (t={elapsed:.0f}s, baseline={BASELINE_MODE})")
            snapshot_idx += 1
            last_snapshot = now

        if args.duration > 0 and elapsed >= args.duration:
            print(f"[*] Osiągnięto duration={args.duration}s — kończę.")
            break

    csv_file.close()

    # Końcowy snapshot
    stats = read_all_stats(bfrt, target)
    save_histogram_csv(stats["dut"]["hist"], stats["base"]["hist"],
                       Path("hist_final.csv"))
    save_histogram_png(stats["dut"]["hist"], stats["base"]["hist"],
                       Path("hist_final.png"),
                       title=f"Δ histogram (final, baseline={BASELINE_MODE})")
    print(f"[OK] Pomiar zakończony. Logi: {csv_path}, hist_final.{{csv,png}}")


if __name__ == "__main__":
    main()
