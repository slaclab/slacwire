import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slacwire.kpi_cli import main, run_kpi_bundle
from slacwire.registry_sqlite import convert_run_registry_json_to_sqlite


class TestKPICLI(unittest.TestCase):
    def _build_registry_json(self, tmp_path: Path) -> Path:
        entries = [
            {
                "run_id": 1,
                "timestamp": "20260401_010000",
                "method": "otf",
                "wire": "WS28144",
                "beampath": "CU_HXR",
                "detector": "PMT29150",
                "filepath": "/tmp/data1.h5",
                "plots": ["/tmp/p1.png"],
                "status": "ok",
                "error": None,
            },
            {
                "run_id": 2,
                "timestamp": "20260405_020000",
                "method": "step",
                "wire": "WS28144",
                "beampath": "CU_HXR",
                "detector": "PMT29150",
                "filepath": None,
                "plots": [],
                "status": "error",
                "error": "Scan Failed",
            },
        ]
        source_json = tmp_path / "snapshot.json"
        source_json.write_text(json.dumps(entries), encoding="utf-8")
        return source_json

    def _build_sqlite_snapshot(self, tmp_path: Path) -> Path:
        source_json = self._build_registry_json(tmp_path)
        sqlite_path = tmp_path / "snapshot.sqlite3"
        convert_run_registry_json_to_sqlite(source_json, sqlite_path)
        return sqlite_path

    def test_run_kpi_bundle_returns_expected_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = self._build_sqlite_snapshot(Path(tmp))
            bundle = run_kpi_bundle(
                sqlite_path=sqlite_path,
                start_ts="2026-04-01T00:00:00",
                end_ts="2026-05-01T00:00:00",
                cutoff_date="2026-05-01",
            )

            self.assertIn("metadata", bundle)
            self.assertIn("executive_kpi_snapshot", bundle)
            self.assertIn("failures_by_wire", bundle)
            self.assertEqual(bundle["executive_kpi_snapshot"]["total_runs"], 2)
            self.assertEqual(bundle["executive_kpi_snapshot"]["failed_runs"], 1)

    def test_cli_writes_output_bundle_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sqlite_path = self._build_sqlite_snapshot(tmp_path)
            output_dir = tmp_path / "reports"

            exit_code = main(
                [
                    "--sqlite-path",
                    str(sqlite_path),
                    "--start-ts",
                    "2026-04-01T00:00:00",
                    "--end-ts",
                    "2026-05-01T00:00:00",
                    "--cutoff-date",
                    "2026-05-01",
                    "--output-dir",
                    str(output_dir),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "kpi_bundle.json").exists())
            self.assertTrue((output_dir / "executive_kpi_snapshot.json").exists())
            self.assertTrue((output_dir / "failures_by_wire.json").exists())

            loaded = json.loads((output_dir / "kpi_bundle.json").read_text("utf-8"))
            self.assertEqual(loaded["executive_kpi_snapshot"]["total_runs"], 2)

    def test_cli_accepts_json_input_without_existing_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_json = self._build_registry_json(tmp_path)
            output_dir = tmp_path / "reports"

            exit_code = main(
                [
                    "--json-path",
                    str(source_json),
                    "--start-ts",
                    "2026-04-01T00:00:00",
                    "--end-ts",
                    "2026-05-01T00:00:00",
                    "--cutoff-date",
                    "2026-05-01",
                    "--output-dir",
                    str(output_dir),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "kpi_bundle.json").exists())

    def test_cli_json_input_can_persist_converted_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_json = self._build_registry_json(tmp_path)
            output_dir = tmp_path / "reports"
            sqlite_output = tmp_path / "converted.sqlite3"

            exit_code = main(
                [
                    "--json-path",
                    str(source_json),
                    "--sqlite-output-path",
                    str(sqlite_output),
                    "--start-ts",
                    "2026-04-01T00:00:00",
                    "--end-ts",
                    "2026-05-01T00:00:00",
                    "--cutoff-date",
                    "2026-05-01",
                    "--output-dir",
                    str(output_dir),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(sqlite_output.exists())

    def test_cli_uses_default_production_json_path_when_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_json = self._build_registry_json(tmp_path)
            output_dir = tmp_path / "reports"

            with patch(
                "slacwire.kpi_cli.DEFAULT_PRODUCTION_JSON_PATH",
                source_json,
            ):
                exit_code = main(
                    [
                        "--start-ts",
                        "2026-04-01T00:00:00",
                        "--end-ts",
                        "2026-05-01T00:00:00",
                        "--cutoff-date",
                        "2026-05-01",
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "kpi_bundle.json").exists())


if __name__ == "__main__":
    unittest.main()
