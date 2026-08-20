# slacwire

Wire scanner GUI and orchestration package for LCLS beam profile measurements.

`slacwire` provides:
- A PyDM/Qt GUI for running wire scans and visualizing results
- A controller layer (`WireScanSuite`) that orchestrates scans
- A view layer (`WireScanView`) for plotting and rendering
- A persistence layer (`RunRegistry`) for run metadata and audit history
- A reporting utility to convert Run Registry JSON snapshots into SQLite

## Package Layout

```text
slacwire/
	pyproject.toml
	benchmarking/             # Performance and timing benchmarks
	tests/                    # pytest test suite
	slacwire/
		__init__.py
		__main__.py           # CLI entry point (python -m slacwire)
		launch_ws_gui.sh      # Shell script to initialize env and start GUI
		suite/                # Controller/orchestration (mixin-based)
			__init__.py       # Exports WireScanSuite (composed dataclass)
			_base.py          # Dataclass fields, device management, infrastructure
			_run.py           # run_single, run_all scan execution
			_collect.py       # collect_single (raw data, no analysis)
			_motion.py        # Beam-less motion validation tests
			_results.py       # Result queries, display, and caching
			_loader.py        # Load and discover previously saved .h5 scans
			_diagnostics.py   # EPICS CA cache inspection
			_jitter_compare.py # Jitter correction comparison and FFT analysis
			_constants.py     # WIRE_AREA_LOOKUP, Beampath type, paths
		view.py               # View/plot rendering
		registry/
			registry.py       # Registry persistence
			registry_sqlite.py
			kpi_queries.py
			kpi_cli.py
			kpi_daily_summary.py
			log_run_cli.py
		ws_gui.py             # GUI composition and wiring
		wire_scan_gui.ui
		wire_scan_gui.yaml
		widgets/
			measurement.py
			navigation.py
			plots.py
			text_logger.py
```

## Installation

Python 3.10+ is required.

Install in editable mode for development:

```bash
cd slacwire
pip install -e .
```

Primary dependencies are declared in `pyproject.toml`, including:
- `PyQt5`, `qtpy`, `pydm`
- `matplotlib`, `numpy`, `pyyaml`
- `slac-measurements`

## Using the Core API

```python
from slacwire import WireScanSuite

suite = WireScanSuite(
		wires=["WS28144"],
		beampath="CU_HXR",
		detector="PMT29150", # Optional
)

# Controller-level behavior flags are configured on the suite.
suite.save = True
suite.show = False
suite.save_plots = False

suite.run_single(wire="WS28144")
result = suite.latest_run("WS28144")

# Charge normalization (optional)
suite.run_single(wire="WS28144", charge_normalization=True)
suite.run_all(scan_mode="otf", charge_normalization=True)
```

## Jitter Analysis

The `JitterCompareMixin` provides vibration and jitter correction analysis for
comparing beam profiles with and without jitter correction applied:

```python
suite.jitter_compare(wire="WS28144")
suite.residual_compare(wire="WS28144")
suite.fft_spectrum(wire="WS28144")
suite.fft_overlay(wire="WS28144")
suite.vibration_summary(wire="WS28144")
```

These methods compute Gaussian fits on raw and jitter-corrected profiles,
extract residuals, and perform FFT power spectrum analysis to quantify
wire vibration.

## Loading Previous Scans

The `LoaderMixin` allows loading and discovering previously saved `.h5`
scan files:

```python
suite.load_scan("/path/to/scan_2026-07-01_WS28144.h5")
scans = suite.discover_scans(wire="WS28144", subdir="2026-07-01")
```

## CLI Usage

`slacwire` provides a command-line interface via `python -m slacwire`:

```bash
python -m slacwire run --wires WS28144 --beampath CU_HXR --scan-mode otf
python -m slacwire collect WS28144 --beampath CU_HXR
python -m slacwire motion-test WS28144
python -m slacwire replot WS28144
python -m slacwire summary --wires WS28144 WS27644
```

Available commands: `run`, `collect`, `motion-test`, `replot`, `summary`.

## GUI Notes

The GUI class is `slacwire.ws_gui.WireScanSuiteGUI` and is designed for PyDM/Qt environments.

At runtime, the GUI:
- Loads YAML configuration from `wire_scan_gui.yaml`
- Uses `WireScanSuite` to execute scans in a worker thread
- Uses `WireScanView` for plotting behavior
- Writes outputs to dated directories under `/u1/lcls/physics/data/wire_scan`
- Handles unmeasured profiles gracefully with user-facing messages

## MVC Separation in Current Design

- Model/data sources: `slac-devices`, `slac-measurements`, scan results, and registry entries
- Controller: `WireScanSuite` (scan orchestration and state flow)
- View: `WireScanView` + Qt widgets (plot rendering and UI presentation)
- Persistence service: `RunRegistry` (JSON-backed audit registry)

This keeps scan execution logic independent from plotting implementation and file-backed registry management.

## Development Tips

- Keep controller logic in the `suite/` sub-package and avoid embedding matplotlib logic there.
- Add new suite behavior as a new mixin file (`suite/_<feature>.py`) rather than expanding existing modules.
- Put rendering and figure composition changes in `view.py`.
- Keep JSON registry and run logging concerns in `registry/registry.py`.
- Prefer relative imports within the `slacwire` package.
- Set `dev_mode=True` on the suite to suppress registry logging for scan failures during development.
- Run the test suite with `pytest tests/` from the repo root.

## Reporting and Registry CLIs

The `registry/` sub-package provides KPI reporting and run logging tools:

- `slacwire-kpi-report` — convert the JSON run registry to SQLite and generate
  monthly KPI reports. Defaults to the previous calendar month if date range is
  omitted. See `slacwire-kpi-report --help`.
- `slacwire-log-run` — log a run to the registry from the command line.
  See `slacwire-log-run --help`.

Python API:

```python
from slacwire import convert_run_registry_json_to_sqlite, RunRegistryKPIReporter
```

See `registry/kpi_cli.py` and `docs/run_registry_kpi_queries.sql` for details.
