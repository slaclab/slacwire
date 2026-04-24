import json
import tempfile
import unittest
from pathlib import Path

from slacwire.registry.kpi_queries import RunRegistryKPIReporter
from slacwire.registry.registry_sqlite import convert_run_registry_json_to_sqlite


class TestRunRegistryKPIReporter(unittest.TestCase):
    def _build_snapshot(self, tmp_path: Path) -> Path:
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
            {
                "run_id": 3,
                "timestamp": "20260410_030000",
                "method": "otf",
                "wire": "WS27644",
                "beampath": "CU_SXR",
                "detector": "PMT11111",
                "filepath": "/tmp/data3.h5",
                "plots": ["/tmp/p3a.png", "/tmp/p3b.png"],
                "status": "ok",
                "error": None,
            },
            {
                "run_id": 4,
                "timestamp": "20260420_040000",
                "method": "step",
                "wire": "WS27644",
                "beampath": "CU_SXR",
                "detector": None,
                "filepath": None,
                "plots": [],
                "status": "weird_status",
                "error": "Bad State",
            },
        ]

        source_json = tmp_path / "ws_registry_snapshot.json"
        sqlite_path = tmp_path / "ws_registry_snapshot.sqlite3"
        source_json.write_text(json.dumps(entries), encoding="utf-8")
        convert_run_registry_json_to_sqlite(source_json, sqlite_path)
        return sqlite_path

    def test_executive_snapshot_and_completion_rates(self):
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = self._build_snapshot(Path(tmp))
            reporter = RunRegistryKPIReporter.from_sqlite_path(sqlite_path)

            snapshot = reporter.executive_kpi_snapshot(
                start_ts="2026-04-01T00:00:00",
                end_ts="2026-05-01T00:00:00",
            )
            self.assertEqual(snapshot["total_runs"], 4)
            self.assertEqual(snapshot["successful_runs"], 2)
            self.assertEqual(snapshot["failed_runs"], 1)
            self.assertEqual(snapshot["unknown_runs"], 1)
            self.assertEqual(snapshot["distinct_wires_scanned"], 2)
            self.assertEqual(snapshot["success_rate_pct"], 50.0)
            self.assertEqual(snapshot["failure_rate_pct"], 25.0)

            file_rate = reporter.file_completion_rate(
                start_ts="2026-04-01T00:00:00",
                end_ts="2026-05-01T00:00:00",
            )
            self.assertEqual(file_rate["runs_with_filepath"], 2)
            self.assertEqual(file_rate["file_completion_rate_pct"], 50.0)

            plot_rate = reporter.plot_completion_rate(
                start_ts="2026-04-01T00:00:00",
                end_ts="2026-05-01T00:00:00",
            )
            self.assertEqual(plot_rate["runs_with_plots"], 2)
            self.assertEqual(plot_rate["plot_completion_rate_pct"], 50.0)

    def test_failure_and_recency_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = self._build_snapshot(Path(tmp))
            reporter = RunRegistryKPIReporter.from_sqlite_path(sqlite_path)

            failures_by_wire = reporter.failures_by_wire(
                start_ts="2026-04-01T00:00:00",
                end_ts="2026-05-01T00:00:00",
            )
            first = failures_by_wire[0]
            self.assertEqual(first["wire"], "WS28144")
            self.assertEqual(first["failed_runs"], 1)
            self.assertEqual(first["wire_failure_rate_pct"], 50.0)

            top_errors = reporter.top_error_signatures(
                start_ts="2026-04-01T00:00:00",
                end_ts="2026-05-01T00:00:00",
            )
            self.assertEqual(top_errors[0]["error_signature"], "scan failed")
            self.assertEqual(top_errors[0]["occurrences"], 1)

            recency = reporter.wire_coverage_recency(cutoff_date="2026-05-01")
            self.assertEqual(len(recency), 2)
            self.assertEqual(recency[0]["recency_bucket"], "red")

            red_count = reporter.red_wires_count(cutoff_date="2026-05-01")
            self.assertEqual(red_count["red_wires"], 1)

    def test_data_quality_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = self._build_snapshot(Path(tmp))
            reporter = RunRegistryKPIReporter.from_sqlite_path(sqlite_path)

            duplicates = reporter.duplicate_run_ids()
            self.assertEqual(duplicates, [])

            status_dist = reporter.status_distribution()
            statuses = {row["status"] for row in status_dist}
            self.assertEqual(statuses, {"ok", "error", "unknown"})

            orphan = reporter.orphan_plot_rows()
            self.assertEqual(orphan["orphan_plot_rows"], 0)

            missing = reporter.missing_required_field_rows()
            self.assertEqual(missing["invalid_required_field_rows"], 0)


if __name__ == "__main__":
    unittest.main()
