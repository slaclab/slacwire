"""Wire scan suite — high-level orchestration for beam profile measurements.

This sub-package composes WireScanSuite from separate concern modules:
- _base: dataclass fields and infrastructure
- _motion: beam-less motion validation
- _collect: raw data collection (no analysis)
- _run: measurement execution (collection + analysis)
- _results: result queries and display
"""

from __future__ import annotations

from dataclasses import dataclass

from ._base import WireScanSuiteBase
from ._collect import CollectMixin
from ._constants import (
    WIRE_AREA_LOOKUP,
    Beampath,
    _BASE_DIR,
    _SCOPE_DATA_DIR,
    dated_output_dir,
)
from ._diagnostics import DiagnosticsMixin
from ._jitter_compare import JitterCompareMixin
from ._motion import MotionTestMixin
from ._results import ResultsMixin
from ._run import RunMixin


@dataclass
class WireScanSuite(JitterCompareMixin, DiagnosticsMixin, MotionTestMixin, CollectMixin, RunMixin, ResultsMixin, WireScanSuiteBase):
    """High-level orchestration layer for wire scanner beam profile measurements.

    Transforms low-level EPICS device controls (wire positioning, data collection,
    Gaussian fitting) from slac_devices into a complete scientific data
    acquisition system with human-readable results, automated plotting, and
    persistent run tracking.

    This class bridges the gap between the raw measurement/analysis primitives
    (WireMeasurementCollection, WireMeasurementAnalysis, create_wire) and
    operational requirements by providing:

    - Batch processing: Run multiple wires and scan types in sequence
    - Data provenance: Persistent JSON registry of all runs with metadata
    - Automated visualization: Publication-ready trajectory and profile plots
    - Structured file management: Timestamped HDF5 files and PNG plots
    - Simplified API: Single method calls replace multi-step workflows

    Typical usage:
        >>> suite = WireScanSuite(
        ...     wires=["WS28144", "WS27644"],
        ...     beampath="CU_HXR",
        ...     detector="PMT29150"
        ... )
        >>> suite.run_single("WS28144", scan_mode="otf")
        # Executes scans, saves data/plots, updates run registry

    Attributes:
        wires: Wire names (e.g., "WS28144")
        devices: Cached wire device instances created via create_wire()
        beampath: Accelerator beampath identifier (e.g., "CU_HXR", "SC_BSYD")
        detector: Primary detector for measurements (e.g., "PMT29150")
        outdir: Output directory for HDF5 data files
        plotdir: Output directory for PNG plot files
        results: Dict storing measurement results keyed by wire name
        registry: Persistent run registry for audit trail
        save: If ``True``, write HDF5 data files after each scan.
        show: If ``True``, call ``fig.show()`` on each generated plot.
        save_plots: If ``True``, write PNG plot files after each scan.
    """

    pass


__all__ = [
    "WireScanSuite",
    "WIRE_AREA_LOOKUP",
    "Beampath",
    "dated_output_dir",
]
