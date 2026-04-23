# slacwire

Wire scanner GUI and orchestration package for LCLS beam profile measurements.

`slacwire` provides:
- A PyDM/Qt GUI for running wire scans and visualizing results
- A controller layer (`WireScanSuite`) that orchestrates scans
- A view layer (`WireScanView`) for plotting and rendering
- A persistence layer (`RunRegistry`) for run metadata and audit history

## Package Layout

```text
slacwire/
	pyproject.toml
	slacwire/
		__init__.py
		suite.py          # Controller/orchestration
		view.py           # View/plot rendering
		registry.py       # Registry persistence
		ws_gui.py         # GUI composition and wiring
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

suite.run_single(wire="WS28144", scan_mode="auto")
result = suite.latest_run("WS28144")
```

## GUI Notes

The GUI class is `slacwire.ws_gui.WireScanSuiteGUI` and is designed for PyDM/Qt environments.

At runtime, the GUI:
- Loads YAML configuration from `wire_scan_gui.yaml`
- Uses `WireScanSuite` to execute scans in a worker thread
- Uses `WireScanView` for plotting behavior
- Writes outputs to dated directories under `/u1/lcls/physics/data/wire_scan` (with local fallback)

## MVC Separation in Current Design

- Model/data sources: `slac-devices`, `slac-measurements`, scan results, and registry entries
- Controller: `WireScanSuite` (scan orchestration and state flow)
- View: `WireScanView` + Qt widgets (plot rendering and UI presentation)
- Persistence service: `RunRegistry` (JSON-backed audit registry)

This keeps scan execution logic independent from plotting implementation and file-backed registry management.

## Development Tips

- Keep controller logic in `suite.py` and avoid embedding matplotlib logic there.
- Put rendering and figure composition changes in `view.py`.
- Keep JSON registry and run logging concerns in `registry.py`.
- Prefer relative imports within the `slacwire` package.
