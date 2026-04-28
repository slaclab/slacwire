import json
import tempfile
import unittest
from pathlib import Path

from slacwire.registry import RunRegistry


class TestRunRegistry(unittest.TestCase):
    def test_log_persists_and_increments_run_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            registry = RunRegistry(path=path)

            first = registry.log(
                method="otf",
                wire="WS28144",
                beampath="CU_HXR",
                scope_data="/tmp/scope/WS28144/WS28144_xy_rq1_20260424_120000_success.csv",
            )
            second = registry.log(method="step", wire="WS28144", beampath="CU_HXR")

            self.assertEqual(first["run_id"], 1)
            self.assertEqual(second["run_id"], 2)
            self.assertTrue(path.exists())

            with open(path, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
            self.assertEqual(len(on_disk), 2)
            self.assertEqual(first["scope_data"], "/tmp/scope/WS28144/WS28144_xy_rq1_20260424_120000_success.csv")
            self.assertIsNone(second["scope_data"])
            self.assertEqual(on_disk[-1]["method"], "step")

    def test_new_instance_loads_existing_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            seed = [
                {
                    "run_id": 7,
                    "timestamp": "20260423_120000",
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
            with open(path, "w", encoding="utf-8") as f:
                json.dump(seed, f)

            registry = RunRegistry(path=path)
            entry = registry.log(method="step", wire="WS28144", beampath="CU_HXR")

            self.assertEqual(registry.entries[0]["run_id"], 7)
            self.assertEqual(entry["run_id"], 8)

    def test_bad_json_file_is_tolerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text("{not-valid-json", encoding="utf-8")

            registry = RunRegistry(path=path)
            self.assertEqual(registry.entries, [])

            entry = registry.log(method="otf", wire="WS28144", beampath="CU_HXR")
            self.assertEqual(entry["run_id"], 1)


if __name__ == "__main__":
    unittest.main()
