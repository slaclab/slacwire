"""Beam-less step-scan motion test — validates motor travel at discrete positions."""

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

_WIRE_TOLERANCE_UM = 250
_RETRACT_WAIT_S = 2

logger = logging.getLogger(__name__)


def run_step_motion_test(
    device: Wire,
    timeout_s: float = 10.0,
) -> WireMeasurementCollectionResult:
    """
    Execute step-scan style wire motion without beam and record motor RBV.

    Moves the wire to each inner/outer position for all active profiles,
    verifying that the motor reaches each target within tolerance before
    advancing.

    Parameters
    ----------
    device : Wire
        Initialized wire device (from slac_devices.reader.create_wire).
    timeout_s : float
        Max seconds to wait for the motor to reach each position.

    Returns
    -------
    WireMeasurementCollectionResult
        Position array in raw_data[device.name], metadata with scan ranges.
    """
    _initialize_step_with_retry(device)
    positions = _get_step_positions(device)
    recorded = _step_through_positions(device, positions, timeout_s)
    _retract(device)

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
        notes="beam-less step motion test",
    )

    return WireMeasurementCollectionResult(
        raw_data={device.name: np.array(recorded)},
        metadata=metadata,
    )


def _initialize_step_with_retry(device: Wire, max_attempts: int = 3) -> None:
    """Initialize wire for step-scan mode with retry until enabled."""
    if device.enabled:
        logger.info("%s is already enabled.", device.name)
        return

    for attempt in range(1, max_attempts + 1):
        logger.info(
            "Initializing %s for step motion test (Attempt %s/%s)...",
            device.name, attempt, max_attempts,
        )
        device.initialize()

        if slac_measurements.utils.wait_until(lambda: device.enabled):
            logger.info("%s initialized (enabled).", device.name)
            return

        logger.warning("%s did not enable - retrying...", device.name)

    raise RuntimeError(
        f"Failed to initialize {device.name} after {max_attempts} attempts."
    )


def _get_step_positions(device: Wire) -> list[int]:
    """Return sorted inner/outer positions for all active profiles."""
    positions = []
    for profile in device.active_profiles():
        positions.append(getattr(device, f"{profile}_wire_inner"))
        positions.append(getattr(device, f"{profile}_wire_outer"))
    return sorted(positions)


def _step_through_positions(
    device: Wire,
    positions: list[int],
    timeout_s: float,
) -> list[float]:
    """Move to each position, wait for arrival, record RBV."""
    recorded = []
    total = len(positions)
    start = time.monotonic()

    for i, target in enumerate(positions):
        speed = int(device.speed_max)
        device.speed = speed
        device.motor = target

        logger.info(
            "Moving to %d um (step %d/%d, speed=%d)...",
            target, i + 1, total, speed,
        )

        if not slac_measurements.utils.wait_until(
            lambda t=target: abs(device.motor_rbv - t) < _WIRE_TOLERANCE_UM,
            timeout=timeout_s,
        ):
            raise RuntimeError(
                f"{device.name} did not reach position {target} within {timeout_s}s."
            )

        rbv = device.motor_rbv
        recorded.append(rbv)
        logger.info(
            "Arrived at step %d/%d: target=%d, rbv=%.1f",
            i + 1, total, target, rbv,
        )

    elapsed = time.monotonic() - start
    logger.info(
        "Step motion test complete: %d positions in %.1fs", total, elapsed,
    )
    return recorded


def _retract(device: Wire) -> None:
    """Retract wire after step motion test."""
    logger.info("Retracting %s...", device.name)
    time.sleep(_RETRACT_WAIT_S)
    device.retract()
    time.sleep(_RETRACT_WAIT_S)
    logger.info("Retracted. Motor RBV: %.1f", device.motor_rbv)
