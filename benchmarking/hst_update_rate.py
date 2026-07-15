"""Measure the update rate of a BSA history buffer PV.

Reserves a timing buffer (EDEF) to drive updates, subscribes to an HST PV,
and counts how many monitor updates arrive per second.

Usage:
    python benchmarking/hst_update_rate.py
    python benchmarking/hst_update_rate.py --pv WIRE:LI28:444:POSN --duration 10
"""

import argparse
import time
import threading

import epics
from slac_timing import create_buffer


DEFAULT_PV = "WIRE:LI28:144:POSN"
DEFAULT_DURATION = 5.0
DEFAULT_BEAMPATH = "CU_HXR"
N_MEASUREMENTS = 1500


def measure_update_rate(
    base_pvname: str,
    duration: float,
    beampath: str,
) -> None:
    print(f"Reserving timing buffer on {beampath}...")
    buffer = create_buffer(
        beampath=beampath,
        n_measurements=N_MEASUREMENTS,
        user="hst_rate_test",
        name="HST Rate Test",
    )
    buf_num = buffer.number
    hst_pvname = f"{base_pvname}HST{buf_num}"

    print(f"  Reserved EDEF {buf_num}")
    print(f"  Monitoring: {hst_pvname}")
    print(f"  Starting acquisition ({N_MEASUREMENTS} measurements)...\n")

    counts = []
    count = 0
    lock = threading.Lock()

    def on_value_change(value=None, **kw):
        nonlocal count
        with lock:
            count += 1

    pv = epics.PV(hst_pvname, auto_monitor=True, callback=on_value_change)
    pv.wait_for_connection(timeout=5.0)

    if not pv.connected:
        print(f"ERROR: Could not connect to {hst_pvname}")
        buffer.release()
        return

    print(f"  element count: {pv.nelm}")

    buffer.start()

    t_start = time.perf_counter()
    for sec in range(int(duration)):
        time.sleep(1.0)
        with lock:
            counts.append(count)
            count = 0
        print(f"  second {sec + 1}: {counts[-1]} updates/s")

    elapsed = time.perf_counter() - t_start
    total = sum(counts)
    avg_hz = total / elapsed if elapsed > 0 else 0

    print(f"\nSummary:")
    print(f"  PV:            {hst_pvname}")
    print(f"  Total updates: {total}")
    print(f"  Duration:      {elapsed:.1f}s")
    print(f"  Average rate:  {avg_hz:.1f} Hz")
    if pv.nelm:
        bytes_per_update = pv.nelm * 8
        print(f"  Data rate:     {avg_hz * bytes_per_update / 1e6:.2f} MB/s (per PV)")
        print(f"  ×206 PVs:     {avg_hz * bytes_per_update * 206 / 1e6:.1f} MB/s (full orphaned cache)")

    pv.disconnect()
    buffer.release()
    print(f"\n  Buffer {buf_num} released.")


def main():
    parser = argparse.ArgumentParser(
        description="Measure HST PV update rate with a live timing buffer."
    )
    parser.add_argument(
        "--pv",
        default=DEFAULT_PV,
        help="Base PV name without HST suffix (default: %(default)s)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
        help="Seconds to monitor (default: %(default)s)",
    )
    parser.add_argument(
        "--beampath",
        default=DEFAULT_BEAMPATH,
        help="Beampath for buffer reservation (default: %(default)s)",
    )
    args = parser.parse_args()
    measure_update_rate(args.pv, args.duration, args.beampath)


if __name__ == "__main__":
    main()
