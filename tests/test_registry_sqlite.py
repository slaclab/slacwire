import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from slacwire.registry.registry_sqlite import convert_run_registry_json_to_sqlite


class TestRegistrySQLiteConversion(unittest.TestCase):
    def test_converts_json_snapshot_into_runs_and_plots_tables(self):
        entries = [
            {
                "run_id": 1,
                "timestamp": "20260424_120000",
                "method": "otf",
                "wire": "WS28144",
                "beampath": "CU_HXR",
                "detector": "PMT29150",
                "filepath": "/tmp/OTF_WS28144_20260424_120000.h5",
                "plots": ["/tmp/plots/a.png", "/tmp/plots/b.png"],
                "status": "ok",
                "error": None,
            },
            {
                "run_id": 2,
                "timestamp": "20260424_123000",
                "method": "step",
                "wire": "WS27644",
                "beampath": "CU_SXR",
                "detector": None,
                "filepath": None,
                "plots": [],
                "status": "weird_status",
                "error": "scan failed",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_json = tmp_path / "ws_registry_snapshot.json"
            sqlite_path = tmp_path / "ws_registry_snapshot.sqlite3"
            source_json.write_text(json.dumps(entries), encoding="utf-8")

            summary = convert_run_registry_json_to_sqlite(source_json, sqlite_path)

            self.assertEqual(summary.runs_inserted, 2)
            self.assertEqual(summary.plots_inserted, 2)
            self.assertEqual(summary.source_json, source_json)
            self.assertEqual(summary.sqlite_path, sqlite_path)

            with sqlite3.connect(sqlite_path) as conn:
                row_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
                self.assertEqual(row_count, 2)

                first = conn.execute(
                    """
                    SELECT timestamp_raw, timestamp_iso, method, wire, status, source_json
                    FROM runs
                    WHERE run_id = 1
                    """
                ).fetchone()
                self.assertEqual(first[0], "20260424_120000")
                self.assertEqual(first[1], "2026-04-24T12:00:00")
                self.assertEqual(first[2], "otf")
                self.assertEqual(first[3], "WS28144")
                self.assertEqual(first[4], "ok")
                self.assertEqual(first[5], str(source_json))

                second_status = conn.execute(
                    "SELECT status FROM runs WHERE run_id = 2"
                ).fetchone()[0]
                self.assertEqual(second_status, "unknown")

                plot_rows = conn.execute(
                    """
                    SELECT run_id, plot_index, plot_path
                    FROM run_plots
                    ORDER BY run_id, plot_index
                    """
                ).fetchall()
                self.assertEqual(
                    plot_rows,
                    [
                        (1, 0, "/tmp/plots/a.png"),
                        (1, 1, "/tmp/plots/b.png"),
                    ],
                )

    def test_refuses_to_overwrite_existing_sqlite_without_flag(self):
        entries = [
            {
                "run_id": 1,
                "timestamp": "20260424_120000",
                "method": "otf",
                "wire": "WS28144",
                "beampath": "CU_HXR",
                "detector": "PMT29150",
                "filepath": None,
                "plots": [],
                "status": "ok",
                "error": None,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_json = tmp_path / "ws_registry_snapshot.json"
            sqlite_path = tmp_path / "ws_registry_snapshot.sqlite3"
            source_json.write_text(json.dumps(entries), encoding="utf-8")

            convert_run_registry_json_to_sqlite(source_json, sqlite_path)

            with self.assertRaises(FileExistsError):
                convert_run_registry_json_to_sqlite(source_json, sqlite_path)

    def test_overwrite_replaces_existing_sqlite_when_enabled(self):
        first_entries = [
            {
                "run_id": 1,
                "timestamp": "20260424_120000",
                "method": "otf",
                "wire": "WS28144",
                "beampath": "CU_HXR",
                "detector": "PMT29150",
                "filepath": None,
                "plots": [],
                "status": "ok",
                "error": None,
            }
        ]
        second_entries = [
            {
                "run_id": 10,
                "timestamp": "20260425_010101",
                "method": "step",
                "wire": "WS27644",
                "beampath": "CU_HXR",
                "detector": "PMT28144",
                "filepath": None,
                "plots": [],
                "status": "ok",
                "error": None,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_json = tmp_path / "ws_registry_snapshot.json"
            sqlite_path = tmp_path / "ws_registry_snapshot.sqlite3"

            source_json.write_text(json.dumps(first_entries), encoding="utf-8")
            convert_run_registry_json_to_sqlite(source_json, sqlite_path)

            source_json.write_text(json.dumps(second_entries), encoding="utf-8")
            convert_run_registry_json_to_sqlite(
                source_json,
                sqlite_path,
                overwrite=True,
            )

            with sqlite3.connect(sqlite_path) as conn:
                run_ids = conn.execute(
                    "SELECT run_id FROM runs ORDER BY run_id"
                ).fetchall()
                self.assertEqual(run_ids, [(10,)])


if __name__ == "__main__":
    unittest.main()
