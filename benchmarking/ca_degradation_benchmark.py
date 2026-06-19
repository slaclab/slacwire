"""Benchmark CA connection degradation over sequential wire scans.

Measures EPICS CA latency after each scan to quantify how accumulated
PV connections degrade performance. Cycles through different wires so
each scan adds ~85-95 distinct PV connections to the cache.

Usage:
    python benchmarking/ca_degradation_benchmark.py \
        --wires WS28144 WS28444 WS28744 \
        --canary-pv "BPMS:IN20:221:TMIT" \
        --iterations 9 \
        --beampath CU_HXR
"""

import argparse
import csv
import logging
import os
import platform
import time
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any

import epics
import epics.ca
import numpy as np
from epics.pv import _PVcache_

from slacwire.suite import WireScanSuite

logger = logging.getLogger(__name__)

DEFAULT_WIRES = ["WS28144", "WS28444", "WS28744"]
DEFAULT_CANARY_PV = "BPMS:IN20:221:TMIT"
DEFAULT_ITERATIONS = 9
LATENCY_SAMPLES = 20

CSV_COLUMNS = [
    "iteration",
    "wire_scanned",
    "timestamp",
    "connect_time_ms",
    "caget_mean_ms",
    "caget_p50_ms",
    "caget_p95_ms",
    "caget_p99_ms",
    "pv_cache_total",
    "channel_cache_total",
    "open_fd_count",
    "scan_success",
    "scan_error",
    "cache_cleared",
]


@dataclass
class IterationMetrics:
    iteration: int
    wire_scanned: str
    timestamp: str
    connect_time_ms: float
    caget_mean_ms: float
    caget_p50_ms: float
    caget_p95_ms: float
    caget_p99_ms: float
    pv_cache_total: int
    channel_cache_total: int
    open_fd_count: int
    scan_success: bool
    scan_error: str | None
    cache_cleared: bool

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _evict_from_cache(pvname: str) -> None:
    """Remove a PV from the global cache so next connect is truly fresh."""
    stale = [pvid for pvid in list(_PVcache_) if pvid[0] == pvname]
    for pvid in stale:
        pv_obj = _PVcache_.pop(pvid, None)
        if pv_obj is not None:
            pv_obj.disconnect()


def measure_fresh_connect(pvname: str, timeout: float = 5.0) -> float:
    """Time a fresh PV connection from scratch (ms).

    Evicts the PV from cache before and after so it doesn't accumulate.
    Returns float('inf') if connection fails.
    """
    _evict_from_cache(pvname)

    t0 = time.perf_counter()
    pv = epics.PV(pvname, connection_timeout=timeout)
    connected = pv.wait_for_connection(timeout=timeout)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if not connected:
        elapsed_ms = float("inf")

    pv.disconnect()
    _evict_from_cache(pvname)
    return elapsed_ms


def measure_caget_latency(
    pvname: str, n_samples: int = LATENCY_SAMPLES
) -> dict[str, float]:
    """Measure round-trip caget latency on a PV (ms).

    Uses use_monitor=False to force a CA network round-trip each time.
    Returns dict with mean, p50, p95, p99, n_failed.
    """
    _evict_from_cache(pvname)
    pv = epics.PV(pvname)
    pv.wait_for_connection(timeout=5.0)

    latencies = []
    for _ in range(n_samples):
        t0 = time.perf_counter()
        val = pv.get(use_monitor=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if val is not None:
            latencies.append(elapsed_ms)

    pv.disconnect()
    _evict_from_cache(pvname)

    arr = np.array(latencies) if latencies else np.array([float("inf")])
    return {
        "mean": float(np.mean(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "n_failed": n_samples - len(latencies),
    }


def count_open_fds() -> int:
    """Count open file descriptors for the current process."""
    if platform.system() == "Darwin":
        try:
            return len(os.listdir("/dev/fd"))
        except OSError:
            return -1
    else:
        try:
            return len(os.listdir(f"/proc/{os.getpid()}/fd"))
        except OSError:
            return -1


def clear_ca_cache_all() -> None:
    """Aggressively clear all CA cache entries.

    Mirrors slac_timing.buffer._clear_ca_cache but clears everything
    rather than filtering by suffix.
    """
    ctx = epics.ca.current_context()
    if ctx is None:
        return

    for pvid in list(_PVcache_):
        pv_obj = _PVcache_.pop(pvid, None)
        if pv_obj is not None:
            pv_obj.disconnect()

    context_cache = epics.ca._cache.get(ctx)
    if context_cache is None:
        return
    for name in list(context_cache):
        entry = context_cache.get(name)
        if entry is not None and getattr(entry, "chid", None) is not None:
            epics.ca.clear_channel(entry.chid)
        context_cache.pop(name, None)


def run_benchmark(
    wires: list[str],
    canary_pv: str,
    iterations: int,
    scan_mode: str,
    beampath: str,
    clear_cache: bool,
    latency_samples: int,
) -> list[IterationMetrics]:
    """Run the degradation benchmark.

    Cycles through wires, running collect_single() on each, measuring
    canary PV latency after every scan.
    """
    suite = WireScanSuite(
        wires=wires,
        beampath=beampath,
        save=False,
        show=False,
        save_plots=False,
    )

    print(
        f"CA Degradation Benchmark\n"
        f"  Wires: {wires} | Canary: {canary_pv} | Iterations: {iterations}\n"
        f"  Mode: {scan_mode} | Beampath: {beampath} | Clear cache: {clear_cache}\n"
        f"{'━' * 70}"
    )

    # Baseline measurement
    baseline_latency = measure_caget_latency(canary_pv, latency_samples)
    baseline_connect = measure_fresh_connect(canary_pv)
    baseline_cache = suite.cache_info()
    print(
        f"[baseline] cache={baseline_cache['pv_cache_total']}/"
        f"{baseline_cache['channel_cache_total']}  "
        f"connect={baseline_connect:.1f}ms  "
        f"caget_p50={baseline_latency['p50']:.2f}ms  "
        f"fds={count_open_fds()}"
    )

    results: list[IterationMetrics] = []

    for i in range(iterations):
        wire = wires[i % len(wires)]

        scan_success = True
        scan_error = None
        try:
            suite.collect_single(wire, scan_mode=scan_mode)
        except Exception as e:
            scan_success = False
            scan_error = str(e)
            logger.warning(f"Scan {i + 1} ({wire}) failed: {e}")

        # Post-scan measurements
        connect_ms = measure_fresh_connect(canary_pv)
        latency = measure_caget_latency(canary_pv, latency_samples)
        cache = suite.cache_info()
        fd_count = count_open_fds()

        cleared = False
        if clear_cache:
            clear_ca_cache_all()
            cleared = True

        metrics = IterationMetrics(
            iteration=i + 1,
            wire_scanned=wire,
            timestamp=datetime.now().isoformat(),
            connect_time_ms=connect_ms,
            caget_mean_ms=latency["mean"],
            caget_p50_ms=latency["p50"],
            caget_p95_ms=latency["p95"],
            caget_p99_ms=latency["p99"],
            pv_cache_total=cache["pv_cache_total"],
            channel_cache_total=cache["channel_cache_total"],
            open_fd_count=fd_count,
            scan_success=scan_success,
            scan_error=scan_error,
            cache_cleared=cleared,
        )
        results.append(metrics)

        status = "OK" if scan_success else "FAIL"
        print(
            f"[{i + 1}/{iterations}] {wire:10s} {status}  "
            f"cache={cache['pv_cache_total']}/{cache['channel_cache_total']}  "
            f"connect={connect_ms:.1f}ms  "
            f"caget_p50={latency['p50']:.2f}ms  "
            f"fds={fd_count}"
        )

    print(f"{'━' * 70}")
    return results


def print_summary_table(results: list[IterationMetrics]) -> None:
    """Print a formatted summary table."""
    headers = ["iter", "wire", "pv_cache", "ch_cache", "connect_ms", "p50_ms", "p95_ms", "fds", "ok"]
    widths = [4, 10, 8, 8, 10, 7, 7, 5, 4]

    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(header_line)
    print("  ".join("-" * w for w in widths))

    for r in results:
        ok = "Y" if r.scan_success else "N"
        row = [
            str(r.iteration),
            r.wire_scanned,
            str(r.pv_cache_total),
            str(r.channel_cache_total),
            f"{r.connect_time_ms:.1f}",
            f"{r.caget_p50_ms:.2f}",
            f"{r.caget_p95_ms:.2f}",
            str(r.open_fd_count),
            ok,
        ]
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))


def write_csv(results: list[IterationMetrics], output_path: Path) -> None:
    """Write results to CSV."""
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_dict())
    print(f"\nWrote {output_path}")


def plot_degradation(results: list[IterationMetrics], output_path: Path) -> None:
    """Generate a 4-panel degradation plot."""
    import matplotlib.pyplot as plt

    iters = [r.iteration for r in results]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("CA Connection Degradation Over Sequential Scans")

    # Cache growth
    ax = axes[0, 0]
    ax.plot(iters, [r.pv_cache_total for r in results], "o-", label="PV cache")
    ax.plot(iters, [r.channel_cache_total for r in results], "s-", label="Channel cache")
    ax.set_xlabel("Scan iteration")
    ax.set_ylabel("Cache entries")
    ax.set_title("Cache Growth")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Connection time
    ax = axes[0, 1]
    ax.plot(iters, [r.connect_time_ms for r in results], "o-", color="tab:red")
    ax.set_xlabel("Scan iteration")
    ax.set_ylabel("Connection time (ms)")
    ax.set_title("Fresh PV Connection Time")
    ax.grid(True, alpha=0.3)

    # Caget latency
    ax = axes[1, 0]
    ax.plot(iters, [r.caget_p50_ms for r in results], "o-", label="p50")
    ax.plot(iters, [r.caget_p95_ms for r in results], "s-", label="p95")
    ax.plot(iters, [r.caget_p99_ms for r in results], "^-", label="p99")
    ax.set_xlabel("Scan iteration")
    ax.set_ylabel("Latency (ms)")
    ax.set_title("Caget Round-Trip Latency")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # File descriptors
    ax = axes[1, 1]
    ax.plot(iters, [r.open_fd_count for r in results], "o-", color="tab:green")
    ax.set_xlabel("Scan iteration")
    ax.set_ylabel("Open FDs")
    ax.set_title("File Descriptor Count")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Wrote {output_path}")
    plt.close(fig)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark CA connection degradation over sequential wire scans."
    )
    parser.add_argument(
        "--wires",
        nargs="+",
        default=DEFAULT_WIRES,
        help="Wires to cycle through (default: %(default)s)",
    )
    parser.add_argument(
        "--canary-pv",
        default=DEFAULT_CANARY_PV,
        help="PV to probe for latency (default: %(default)s)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help="Number of scans to run (default: %(default)s)",
    )
    parser.add_argument(
        "--scan-mode",
        choices=["otf", "step"],
        default="otf",
        help="Scan mode (default: %(default)s)",
    )
    parser.add_argument(
        "--beampath",
        default="CU_HXR",
        help="Accelerator beampath (default: %(default)s)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear CA cache after each scan (for A/B comparison)",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate matplotlib degradation plot",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for CSV/plot output (default: current dir)",
    )
    parser.add_argument(
        "--latency-samples",
        type=int,
        default=LATENCY_SAMPLES,
        help="Number of caget samples per measurement (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results = run_benchmark(
        wires=args.wires,
        canary_pv=args.canary_pv,
        iterations=args.iterations,
        scan_mode=args.scan_mode,
        beampath=args.beampath,
        clear_cache=args.clear_cache,
        latency_samples=args.latency_samples,
    )

    print_summary_table(results)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = args.output_dir / f"ca_degradation_{timestamp}.csv"
    write_csv(results, csv_path)

    if args.plot:
        plot_path = args.output_dir / f"ca_degradation_{timestamp}.png"
        plot_degradation(results, plot_path)


if __name__ == "__main__":
    main()
