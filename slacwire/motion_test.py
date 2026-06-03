"""Beam-less wire motion test — validates motor travel by polling RBV."""

import logging
import time
from datetime import datetime

import numpy as np

from slac_devices.wire import Wire
import slac_measurements.utils
from slac_measurements.wires.collection_results import (
    MeasurementMetadata,
    WireMeasurementCollectionResult,
)

_POLL_INTERVAL_S = 0.05  # 20 Hz
_SETTLE_THRESHOLD_UM = 50  # position change below this = stopped
_SETTLE_COUNT = 20  # consecutive "stopped" readings to confirm done

logger = logging.getLogger(__name__)


def run_motion_test(
    device: Wire,
    poll_interval_s: float = _POLL_INTERVAL_S,
) -> WireMeasurementCollectionResult:
    """
    Execute OTF-style wire motion without beam and record motor RBV.

    Parameters
    ----------
    device : Wire
        Initialized wire device (from slac_devices.reader.create_wire).
    poll_interval_s : float
        Seconds between RBV reads (default 0.05 = 20 Hz).

    Returns
    -------
    WireMeasurementCollectionResult
        Position array in raw_data[device.name], metadata with scan ranges.
    """
    _initialize_with_retry(device)
    positions = _poll_motor_rbv(device, poll_interval_s)

    metadata = MeasurementMetadata(
        wire_name=device.name,
        area=device.area,
        beampath="",
        detectors=[],
        default_detector="",
        scan_ranges={
            "x": tuple(device.x_range),
            "y": tuple(device.y_range),
            "u": tuple(device.u_range),
        },
        timestamp=datetime.now(),
        active_profiles=device.active_profiles(),
        install_angle=device.install_angle,
        notes="beam-less motion test",
    )

    return WireMeasurementCollectionResult(
        raw_data={device.name: np.array(positions)},
        metadata=metadata,
    )


def _initialize_with_retry(device: Wire, max_attempts: int = 3) -> None:
    """Arm wire for OTF motion with retry (mirrors OTF collection pattern)."""
    for attempt in range(1, max_attempts + 1):
        logger.info(
            "Starting motion test on %s (Attempt %s/%s)...",
            device.name, attempt, max_attempts,
        )
        device.start_scan()

        if slac_measurements.utils.wait_until(
            lambda: device.homed and device.on_status
        ):
            logger.info("%s is homed and on.", device.name)
            return

        logger.warning("%s did not become homed and on - retrying...", device.name)

    raise RuntimeError(
        f"Failed to initialize {device.name} after {max_attempts} attempts."
    )


def _poll_motor_rbv(
    device: Wire,
    poll_interval_s: float,
) -> list[float]:
    """Poll motor RBV until motion completes. Returns list of positions."""
    positions = []
    settle_count = 0
    start = time.monotonic()

    while True:
        pos = device.motor_rbv
        positions.append(pos)

        if len(positions) > 1:
            if abs(positions[-1] - positions[-2]) < _SETTLE_THRESHOLD_UM:
                settle_count += 1
            else:
                settle_count = 0

            if settle_count >= _SETTLE_COUNT:
                elapsed = time.monotonic() - start
                logger.info("Wire settled at %.1f um after %.1fs", pos, elapsed)
                break

        time.sleep(poll_interval_s)

    elapsed = time.monotonic() - start
    logger.info("Collected %d position samples over %.1fs", len(positions), elapsed)
    return positions
