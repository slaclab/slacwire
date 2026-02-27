# SLAC Wire Scanner Application - AI Coding Agent Instructions

## Project Overview
Python application for automated wire scanner beam profile measurements at SLAC Linear Accelerator. Provides both a PyDM-based GUI (`wire_scan_gui.py`) and programmatic API (`ws_suite.py`) for particle beam characterization using wire scanners positioned along accelerator beampaths.

## Architecture & Components

### Dual Interface Design
- **GUI Application** (`wire_scan_gui.py`): PyQt5/PyDM interface for operators, integrates with EPICS control system PVs
- **Programmatic API** (`ws_suite.py`): Standalone Python class for batch/automated scans with plotting and data management
- Both use `lcls_tools.common` library for wire device abstraction and measurement/analysis

### Key Modules
- `wire_scan_gui.py`: Main GUI with threaded scanning (`WireScanThread`), real-time plotting, Physics eLog integration
- `ws_suite.py`: `WireScanSuite` dataclass for programmatic control, run tracking, automated plotting
- `h5_io.py`: HDF5 serialization for `WireBeamProfileMeasurementResult` objects (handles namedtuples/dataclasses)
- `save_util.py`: Date-based directory structure at `/u1/lcls/physics/data/wire_scan/YYYY/MM/DD`
- `widgets/`: Modular Qt widgets (measurement controls, navigation, matplotlib canvases, text logger)

## Critical Naming Conventions

### Wire Identifier Format
Wires use `WIRE_NAME:AREA` format (e.g., `WS28144:L3`, `WS31:LTUH`). Always split on `:` to extract name and area:
```python
wire_name, area = wire.split(":")
device = create_wire(area, wire_name)
```

### Configuration Structure
`wire_scan_gui.yaml` maps beampaths → areas → wire lists. Example:
```yaml
CU_HXR:
    LI28: ['WS27644:L3', 'WS28144:L3']
```
Beampaths starting with `SC_` are LCLS-II (SC linac), `CU_` are copper linac (LCLS-I).

## Scan Workflow & Logic

### Automatic Scan Mode Selection
Scan type determined by beam rate in `WireScanThread`:
- **Step scan**: beam_rate ≤ 120 Hz (slower, more accurate)
- **OTF scan**: 120 Hz < beam_rate ≤ 16,000 Hz (faster, continuous motion)
- **Error**: beam_rate > 16,000 Hz (too fast)

### Profile Dimensions
Beam profiles measured in three orientations:
- **x**: Horizontal (0°)
- **y**: Vertical (90°)
- **u**: Diagonal (45°)

### Coordinate Transformation
Stage positions converted to beam coordinates with angular scaling:
```python
scale = 1 if profile == "u" else np.cos(np.deg2rad(45))
beam_position = stage_position * scale
```
Plots show both coordinate systems via secondary x-axis.

## Data Management Patterns

### Run Tracking (ws_suite.py)
`WireScanSuite` maintains:
- `run_registry`: List of run metadata (run_id, timestamp, method, filepath, plots, status)
- `results`: Dict keyed by method ("otf"/"step") and wire name storing measurement objects
- `run_counter`: Incremental ID for each scan

### File Naming
All files timestamped as `{prefix}_{YYYYMMDD_HHMMSS}.{ext}`:
```python
filepath = outdir / f"OTF_WS28144_{self._stamp()}.h5"
plot_path = plotdir / f"OTF_Profile_x_WS28144_{self._stamp()}.png"
```

### HDF5 Storage
- Arrays saved as datasets, scalar/string metadata as attributes
- Non-serializable values converted via `json.dumps()` or `str()`
- Lists of arrays stored in HDF5 groups with numeric keys ("0", "1", ...)

## Development & Deployment

### Production Environment
- Deployed at `/usr/local/lcls/tools/python/hla/slacwire`
- Runs on LCLS physics workstations with EPICS channel access
- Writes to shared filesystem at `/u1/lcls/physics/data/wire_scan/`

### Testing Considerations
- Control system PVs unavailable outside SLAC network; mock `lcls_tools.common` objects for testing
- Wire metadata includes `.detectors` and `.bpms_before_wire` attributes
- Physics eLog requires logbook name: "lcls2" for SC beampaths, "lcls" for CU beampaths

### Pre-commit Hooks
Project uses pre-commit configuration (`.pre-commit-config.yaml`). Run before committing:
```bash
pre-commit run --all-files
```

## GUI-Specific Patterns

### Signal Flow
```
NavigationWidget.areaChanged
  → MeasurementWidget.update_area()
  → wire_combo populated
  → MeasurementWidget.wireChanged
  → update_parameters() (set PV channels)
  → update_plots()
```

### Thread Safety
All measurement collection runs in `WireScanThread` to prevent GUI blocking. Emits:
- `scan_complete(wire_name, WireBeamProfileMeasurementResult)` on success
- `scan_failed(wire_name, Exception)` on error

Always re-enable `startButton` in both success/failure handlers.

### Plotting Updates
Profile plots redrawn on:
- Wire selection change
- Detector selection change
- Profile dimension toggle (x/y/u radio buttons)
- New scan completion (`dataChanged` signal)

## Common Pitfalls

1. **Coordinate confusion**: Stage positions ≠ beam positions. Use transformation functions for secondary axis.
2. **Wire format**: Don't forget to split `wire.split(":")` when passing to `create_wire()`
3. **Thread lifecycle**: Never access Qt widgets from `WireScanThread.run()`, use signals
4. **HDF5 compatibility**: `save_measurement_result()` only handles numpy arrays, lists of arrays, and JSON-serializable types
5. **Path assumptions**: `/u1/lcls/...` paths are production-specific; use `dated_dir()` for proper directory creation

## External Dependencies

- **lcls_tools.common**: SLAC package for EPICS device abstraction (`create_wire()`, `WireMeasurementCollection`, `WireMeasurementAnalysis`)
- **PyDM**: Qt framework for EPICS channel display widgets (PVs set via `.channel` property)
- **physicselog**: SLAC logbook integration (`elog.submit_entry(logbook, username, title, text, image_path)`)

## Example Workflows

### Programmatic Scan
```python
suite = WireScanSuite(wires=["WS28144:L3"], beampath="CU_HXR")
suite.run(do_otf=True, do_step=False, save=True, save_plots=True)
latest = suite._latest_run("otf", "WS28144")
```

### Adding New Widget
Inherit from Qt base class, define `pyqtSignal` for inter-widget communication, connect signals in `wire_scan_gui.py` `init_ui()`.
