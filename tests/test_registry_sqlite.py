import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from slacwire.registry.registry_sqlite import (
    build_wire_name_map,
    convert_run_registry_json_to_sqlite,
)

HAS_SLAC_DB = importlib.util.find_spec("slac_db") is not None


class TestRegistrySQLiteConversion(unittest.TestCase):
    def test_epics_wire_names_mapped_to_mad_names(self):
        base = {
            "beampath": "CU_HXR",
            "method": "matlab_step",
            "plots": [],
            "status": "ok",
        }
        entries = [
            {**base, "run_id": 1, "timestamp": "20260424_120000", "wire": "WIRE:LI28:144"},
            {**base, "run_id": 2, "timestamp": "20260424_123000", "wire": "WS28144"},
            {**base, "run_id": 3, "timestamp": "20260424_130000", "wire": "WIRE:FAKE:999"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_json = tmp_path / "ws_registry_snapshot.json"
            sqlite_path = tmp_path / "ws_registry_snapshot.sqlite3"
            source_json.write_text(json.dumps(entries), encoding="utf-8")

            convert_run_registry_json_to_sqlite(
                source_json, sqlite_path, name_map={"WIRE:LI28:144": "WS28144"}
            )

            with sqlite3.connect(sqlite_path) as conn:
                wires = [
                    row[0]
                    for row in conn.execute("SELECT wire FROM runs ORDER BY run_id")
                ]
            # Unmapped names pass through unchanged
            self.assertEqual(wires, ["WS28144", "WS28144", "WIRE:FAKE:999"])

    @unittest.skipUnless(HAS_SLAC_DB, "requires slac_db device database")
    def test_build_wire_name_map_prefers_active_devices(self):
        name_map = build_wire_name_map()
        # WIRE:LI28:144 is shared with inactive legacy device WS144
        self.assertEqual(name_map["WIRE:LI28:144"], "WS28144")
        self.assertEqual(name_map["WIRE:LTUS:755"], "WS33B")

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
                "scope_data": "/tmp/scope/WS28144_xyz_rq34_20260428_110234_failure.csv",
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
                "scope_data": None,
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
                    SELECT timestamp_raw, timestamp_iso, method, wire, scope_data, status, source_json
                    FROM runs
                    WHERE run_id = 1
                    """
                ).fetchone()
                self.assertEqual(first[0], "20260424_120000")
                self.assertEqual(first[1], "2026-04-24T12:00:00")
                self.assertEqual(first[2], "otf")
                self.assertEqual(first[3], "WS28144")
                self.assertEqual(
                    first[4],
                    "/tmp/scope/WS28144_xyz_rq34_20260428_110234_failure.csv",
                )
                self.assertEqual(first[5], "ok")
                self.assertEqual(first[6], str(source_json))

                second_status = conn.execute(
                    "SELECT status FROM runs WHERE run_id = 2"
                ).fetchone()[0]
                self.assertEqual(second_status, "unknown")

                second_scope = conn.execute(
                    "SELECT scope_data FROM runs WHERE run_id = 2"
                ).fetchone()[0]
                self.assertIsNone(second_scope)

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
                "scope_data": None,
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
                "scope_data": None,
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
                "scope_data": None,
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
