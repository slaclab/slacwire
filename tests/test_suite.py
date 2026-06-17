import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sys
import types
from unittest.mock import MagicMock, patch

# Provide lightweight stubs so this test can run without full accelerator stack.
fake_slac_devices = types.ModuleType("slac_devices")
fake_slac_devices_reader = types.ModuleType("slac_devices.reader")
fake_slac_devices_reader.create_wire = MagicMock()
fake_slac_devices.reader = fake_slac_devices_reader

fake_slac_measurements = types.ModuleType("slac_measurements")
fake_slac_measurements_wires = types.ModuleType("slac_measurements.wires")
fake_slac_measurements_scan = types.ModuleType("slac_measurements.wires.scan")


class _DummyMeasurement:
    def __init__(self, *args, **kwargs):
        pass

    def measure(self, *args, **kwargs):
        return None


fake_slac_measurements_scan.WireBeamProfileMeasurement = _DummyMeasurement
fake_slac_measurements.wires = fake_slac_measurements_wires

sys.modules.setdefault("slac_devices", fake_slac_devices)
sys.modules.setdefault("slac_devices.reader", fake_slac_devices_reader)
sys.modules.setdefault("slac_measurements", fake_slac_measurements)
sys.modules.setdefault("slac_measurements.wires", fake_slac_measurements_wires)
sys.modules.setdefault("slac_measurements.wires.scan", fake_slac_measurements_scan)

from slacwire.suite import WireScanSuite, dated_output_dir


class _FakeData:
    def __init__(self):
        self.profiles = {"x": object()}
        self.saved_to = None

    def save_to_h5(self, path):
        self.saved_to = path


class _FakeDevice:
    def __init__(self, name="WS28144", beam_rate=1000, detector="PMT29150",
                 active_profiles=("x", "y")):
        self.name = name
        self.beam_rate = beam_rate
        self.metadata = SimpleNamespace(default_detector=detector)
        self._active_profiles = list(active_profiles)

    def active_profiles(self):
        return self._active_profiles


class TestWireScanSuite(unittest.TestCase):
    def test_dated_output_dir_creates_ymd_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dt = datetime(2026, 4, 17, 10, 30, 0)
            path = dated_output_dir(dt=dt, base_dir=Path(tmp))
            expected = Path(tmp) / "2026" / "04" / "17"
            self.assertEqual(path, expected)
            self.assertTrue(path.exists())
            self.assertTrue((path / "plots").exists())

    def test_suite_default_plotdir_is_under_outdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp) / "2026" / "04" / "17"
            with patch.object(WireScanSuite, "_build_view", return_value=MagicMock()):
                suite = WireScanSuite(wires=[], outdir=outdir)
            self.assertEqual(suite.plotdir, outdir / "plots")
            self.assertTrue(suite.plotdir.exists())

    def test_suite_plotdir_is_always_under_outdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp) / "2026" / "04" / "17"
            custom_plotdir = Path(tmp) / "somewhere_else" / "plots"
            with patch.object(WireScanSuite, "_build_view", return_value=MagicMock()):
                suite = WireScanSuite(
                    wires=[],
                    outdir=outdir,
                    plotdir=custom_plotdir,
                )
            self.assertEqual(suite.plotdir, outdir / "plots")
            self.assertTrue(suite.plotdir.exists())

    def test_run_device_scan_uses_suite_flags_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(WireScanSuite, "_build_view", return_value=MagicMock()):
                suite = WireScanSuite(
                    wires=[], outdir=Path(tmp), plotdir=Path(tmp) / "plots"
                )
            suite.save = False
            suite.show = False
            suite.save_plots = False
            suite.registry = MagicMock()
            suite.view = MagicMock()
            suite.view.render.return_value = []

            data = _FakeData()
            device = _FakeDevice()

            suite._run_device_scan(
                device=device,
                method="otf",
                scan_fn=lambda _device, rms_detector=None: data,
                rms_detector=None,
                file_prefix="OTF",
            )

            suite.view.render.assert_called_once()
            render_kwargs = suite.view.render.call_args.kwargs
            self.assertFalse(render_kwargs["show"])
            self.assertFalse(render_kwargs["save"])
            self.assertEqual(render_kwargs["profiles"], ("x", "y"))

            suite.registry.log.assert_called_once()
            log_kwargs = suite.registry.log.call_args.kwargs
            self.assertEqual(log_kwargs["method"], "otf")
            self.assertEqual(log_kwargs["wire"], "WS28144")
            self.assertIsNone(log_kwargs["filepath"])
            self.assertIsNone(log_kwargs["scope_data"])

    def test_run_device_scan_logs_error_and_reraises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(WireScanSuite, "_build_view", return_value=MagicMock()):
                suite = WireScanSuite(
                    wires=[], outdir=Path(tmp), plotdir=Path(tmp) / "plots"
                )
            suite.registry = MagicMock()
            suite.view = MagicMock()
            device = _FakeDevice()

            def failing_scan(_device, rms_detector=None):
                raise RuntimeError("scan failed")

            with self.assertRaises(RuntimeError):
                suite._run_device_scan(
                    device=device,
                    method="step",
                    scan_fn=failing_scan,
                    rms_detector=None,
                    file_prefix="Step",
                )

            log_kwargs = suite.registry.log.call_args.kwargs
            self.assertEqual(log_kwargs["status"], "error")
            self.assertIn("scan failed", log_kwargs["error"])
            self.assertIsNone(log_kwargs["scope_data"])

    def test_resolve_scope_data_path_picks_recent_otf_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(WireScanSuite, "_build_view", return_value=MagicMock()):
                suite = WireScanSuite(wires=[], outdir=Path(tmp))

            wire = "WS28144"
            wire_dir = Path(tmp) / wire
            wire_dir.mkdir(parents=True)
            older = wire_dir / "WS28144_xy_rq33_20260428_110100_success.csv"
            newer = wire_dir / "WS28144_xy_rq34_20260428_110234_failure.csv"
            older.write_text("old", encoding="utf-8")
            newer.write_text("new", encoding="utf-8")

            with patch("slacwire.suite._base._SCOPE_DATA_DIR", Path(tmp)):
                resolved = suite._resolve_scope_data_path(
                    wire=wire,
                    method="otf",
                    since=datetime.now(),
                )

            self.assertEqual(resolved, newer)

    @patch.object(WireScanSuite, "_make_device")
    @patch.object(WireScanSuite, "_run_step_device")
    @patch.object(WireScanSuite, "_run_otf_device")
    def test_run_single_defaults_to_otf_and_allows_step(
        self, mock_run_otf, mock_run_step, mock_make_device
    ):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(WireScanSuite, "_build_view", return_value=MagicMock()):
                suite = WireScanSuite(
                    wires=[],
                    outdir=Path(tmp),
                    plotdir=Path(tmp) / "plots",
                )

            mock_make_device.return_value = _FakeDevice(beam_rate=1000)
            suite.run_single("WS28144")
            mock_run_otf.assert_called_once()

            mock_run_otf.reset_mock()
            suite.devices.clear()
            suite.run_single("WS28144", scan_mode="step")
            mock_run_step.assert_called_once()


if __name__ == "__main__":
    unittest.main()
