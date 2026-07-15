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
	slacwire/
		__init__.py
		suite/                # Controller/orchestration (mixin-based)
			__init__.py       # Exports WireScanSuite (composed dataclass)
			_base.py          # Dataclass fields, device management, infrastructure
			_run.py           # run_single, run_all scan execution
			_collect.py       # collect_single (raw data, no analysis)
			_motion.py        # Beam-less motion validation tests
			_results.py       # Result queries, display, and caching
			_diagnostics.py   # EPICS CA cache inspection
			_constants.py     # WIRE_AREA_LOOKUP, Beampath type, paths
		view.py               # View/plot rendering
		otf_motion_test.py    # OTF motion integration test
		step_motion_test.py   # Step motion integration test
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
```

## GUI Notes

The GUI class is `slacwire.ws_gui.WireScanSuiteGUI` and is designed for PyDM/Qt environments.

At runtime, the GUI:
- Loads YAML configuration from `wire_scan_gui.yaml`
- Uses `WireScanSuite` to execute scans in a worker thread
- Uses `WireScanView` for plotting behavior
- Writes outputs to dated directories under `/u1/lcls/physics/data/wire_scan`

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

## Reporting: JSON to SQLite Snapshot Conversion

For weekly/monthly reporting, keep scan-time JSON writes unchanged and convert a
snapshot of the registry to SQLite when needed:

```python
from slacwire import convert_run_registry_json_to_sqlite

summary = convert_run_registry_json_to_sqlite(
	source_json="/path/to/ws_registry_2026-04-24.json",
	sqlite_path="/path/to/ws_registry_2026-04-24.sqlite3",
)

print(summary)
```

The converter creates:
- `runs` table with KPI-focused metadata, including `timestamp_raw`,
  `timestamp_iso`, `source_json`, and `ingested_at`
- `run_plots` table with one row per plot path

Companion management-report query pack:
- `docs/run_registry_kpi_queries.sql`

Python companion (SQLAlchemy):

```python
from slacwire import RunRegistryKPIReporter

reporter = RunRegistryKPIReporter.from_sqlite_path(
	"/path/to/ws_registry_2026-04-24.sqlite3"
)

snapshot = reporter.executive_kpi_snapshot(
	start_ts="2026-04-01T00:00:00",
	end_ts="2026-05-01T00:00:00",
)
print(snapshot)

failure_by_wire = reporter.failures_by_wire(
	start_ts="2026-04-01T00:00:00",
	end_ts="2026-05-01T00:00:00",
)
print(failure_by_wire)
```

CLI companion for production/ops use:

```bash
slacwire-kpi-report \
	--sqlite-path /path/to/ws_registry_2026-04-24.sqlite3 \
	--start-ts 2026-04-01T00:00:00 \
	--end-ts 2026-05-01T00:00:00 \
	--cutoff-date 2026-05-01 \
	--output-dir /path/to/reports/2026-04
```

Production default JSON path shortcut (uses
`/u1/lcls/physics/data/wire_scan/ws_run_registry.json`):

```bash
slacwire-kpi-report \
	--start-ts 2026-04-01T00:00:00 \
	--end-ts 2026-05-01T00:00:00 \
	--cutoff-date 2026-05-01 \
	--output-dir /path/to/reports/2026-04
```

JSON-only workflow (no existing SQLite needed):

```bash
slacwire-kpi-report \
	--json-path /path/to/ws_run_registry.json \
	--start-ts 2026-04-01T00:00:00 \
	--end-ts 2026-05-01T00:00:00 \
	--cutoff-date 2026-05-01 \
	--output-dir /path/to/reports/2026-04
```

Optional: persist the converted SQLite file while running from JSON input:

```bash
slacwire-kpi-report \
	--json-path /path/to/ws_run_registry.json \
	--sqlite-output-path /path/to/ws_registry_2026-04.sqlite3 \
	--output-dir /path/to/reports/2026-04
```

If `--start-ts` and `--end-ts` are omitted, the CLI defaults to the previous
full calendar month.

By default, conversion will not overwrite an existing SQLite file. Pass
`overwrite=True` only when you explicitly want replacement.
