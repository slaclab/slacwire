#!/usr/bin/env python
"""Write pvlist.json: every PV the IOC serves, resolved from slac-db.

Needs slac-db and slac-devices importable. wire_ioc.py reads pvlist.json from
its own directory.
"""
import importlib.resources
import json
import pathlib
import sys

import slac_devices.reader
import yaml

_DB = importlib.resources.files("slac_db") / "package_data/yaml"
_WIRE = "WS28144"


def main():
    d = _load("L3.yaml")
    w = d["wires"][_WIRE]
    bpms = {
        k: {
            "control_name": v["controls_information"]["control_name"],
            "z": v["metadata"]["sum_l_meters"],
        }
        for k, v in d["bpms"].items()
    }
    pmts = {}
    for f in ("LI29.yaml", "LTUH.yaml"):
        for k, v in _load(f)["pmts"].items():
            if k in w["metadata"]["detectors"] or any(
                x.startswith(k + ":") for x in w["metadata"]["detectors"]
            ):
                pmts[k] = v["controls_information"]["control_name"]
    # TMITLoss reads TMITHST from every BPM on the beampath, in every area; serve HXR and SXR.
    # POSIT: same iteration as slac_measurements.tmit_loss._get_bpm_data, whose
    # area collections include BPMs that are not on the CU_SXR beampath.
    tmit = {
        v.controls_information.control_name: k
        for bp in ("CU_HXR", "CU_SXR")
        for a in slac_devices.reader.create_beampath(
            bp, device_types={"bpms"}
        ).areas.values()
        if a.bpm_collection
        for k, v in a.bpm_collection.bpms.items()
    }
    r = {
        "wire": _WIRE,
        "wire_pvs": w["controls_information"]["PVs"],
        "wire_control_name": w["controls_information"]["control_name"],
        "bpms": bpms,
        "pmts": pmts,
        "tmit_bpms": tmit,
        "tmitloss": w["metadata"]["tmitloss"],
        "jitter_bpms": w["metadata"]["jitter_bpms"],
        "charge_toroids": w["metadata"]["charge_toroids"],
        "default_detector": w["metadata"]["default_detector"],
    }
    p = pathlib.Path(__file__).with_name("pvlist.json")
    p.write_text(json.dumps(r, indent=1, sort_keys=True))
    sys.stdout.write(f"{p}: {len(r['wire_pvs'])} wire pvs, {len(bpms)} bpms, {len(tmit)} tmit bpms, {len(pmts)} pmts\n")


def _load(name):
    return yaml.safe_load((_DB / name).read_text())


if __name__ == "__main__":
    main()
