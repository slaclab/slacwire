import tempfile
import unittest
from pathlib import Path

from slacwire.config import WireConfig, get_wire_config, set_wire_config


class TestWireConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.tmp.name)
        self.tmp.close()

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)

    def test_get_returns_defaults_when_no_row_exists(self):
        config = get_wire_config("WS28144", "CU_HXR", db_path=self.db_path)
        assert config == WireConfig()
        assert config.fitting_method == "gaussian"
        assert config.detector is None
        assert config.toroid is None
        assert config.charge_normalization is False
        assert config.jitter_correction is False
        assert config.jitter_bpms is None

    def test_set_and_get_roundtrip(self):
        set_wire_config(
            "WS28144", "CU_HXR",
            fitting_method="asymmetric",
            detector="PMT29150",
            toroid="BPM2",
            charge_normalization=True,
            jitter_correction=True,
            jitter_bpms=["BPM27201", "BPM27301"],
            db_path=self.db_path,
        )
        config = get_wire_config("WS28144", "CU_HXR", db_path=self.db_path)
        assert config.fitting_method == "asymmetric"
        assert config.detector == "PMT29150"
        assert config.toroid == "BPM2"
        assert config.charge_normalization is True
        assert config.jitter_correction is True
        assert config.jitter_bpms == ["BPM27201", "BPM27301"]

    def test_upsert_updates_existing_row(self):
        set_wire_config(
            "WS28144", "CU_HXR",
            fitting_method="gaussian",
            jitter_correction=False,
            db_path=self.db_path,
        )
        set_wire_config(
            "WS28144", "CU_HXR",
            jitter_correction=True,
            db_path=self.db_path,
        )
        config = get_wire_config("WS28144", "CU_HXR", db_path=self.db_path)
        assert config.jitter_correction is True
        assert config.fitting_method == "gaussian"

    def test_different_beampaths_are_independent(self):
        set_wire_config(
            "WS28144", "CU_HXR",
            detector="PMT29150",
            db_path=self.db_path,
        )
        set_wire_config(
            "WS28144", "SC_HXR",
            detector="LBLM03A",
            db_path=self.db_path,
        )
        cu = get_wire_config("WS28144", "CU_HXR", db_path=self.db_path)
        sc = get_wire_config("WS28144", "SC_HXR", db_path=self.db_path)
        assert cu.detector == "PMT29150"
        assert sc.detector == "LBLM03A"

    def test_null_jitter_bpms_falls_through(self):
        set_wire_config(
            "WS28144", "CU_HXR",
            fitting_method="rms_raw",
            db_path=self.db_path,
        )
        config = get_wire_config("WS28144", "CU_HXR", db_path=self.db_path)
        assert config.jitter_bpms is None

    def test_set_with_no_fields_is_noop_on_existing(self):
        set_wire_config(
            "WS28144", "CU_HXR",
            fitting_method="asymmetric",
            db_path=self.db_path,
        )
        set_wire_config("WS28144", "CU_HXR", db_path=self.db_path)
        config = get_wire_config("WS28144", "CU_HXR", db_path=self.db_path)
        assert config.fitting_method == "asymmetric"


if __name__ == "__main__":
    unittest.main()
