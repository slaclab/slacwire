#!/usr/bin/env python
"""Soft IOC that mimics what slacwire needs to run a WS28144 OTF scan.

Serves, under the real PV names:
  * WIRE:LI28:144:*      the wire's control PVs (state machine below)
  * EDEF:SYS0:<1-11>:*   EDEF reservation, config, start, count, free
  * IOC:IN20:EV01:EDEF*  EDEF reserve request / available count
  * PNBN:SYS0:<1-140>:*  mask names / bit positions (read by EDEF config)
  * <pv>HST<1-11>        waveform buffers: wire POSN, PMT QDCRAW, BPM X/Y/TMIT

Data sources, in order of authority:
  * waveforms (wire POSN, PMT QDCRAW, 16 BPM X/Y) replay a real scan file
    (--h5); TMIT is synthesized so TMITLOSS reproduces the file's TMITLOSS
  * static PV values come from a JSON file (--values) of the form
    {"static": {"<pv>": <value>, ...}} if given, else the defaults below
The EPICS archiver does not store the *HST* or EDEF PVs, so those can't come
from archived data.

The server binds to 127.0.0.1 only. Point clients at it with:

    export EPICS_CA_ADDR_LIST=127.0.0.1 EPICS_CA_AUTO_ADDR_LIST=NO

Set EPICS_CA_SERVER_PORT to move it off 5064.

Faults (--fault NAME) recreate failures slacwire is written to handle:
  dead-detector   default detector's PMT buffer is all zeros (degenerate fit)
  edef-stall      EDEF CNT freezes at 60% and CTRL stays 1 (acquisition timeout)
  no-beam         BEAMRATE is 0 (preflight refuses: NO_BEAM)
  no-edef         every EDEF slot is held by another user (ReservationError)
  not-homed       wire never reports homed/on (OTF init retries, then fails)
  short-buffer    every HST buffer comes back 90% long (BufferSizeError)
  speed-too-fast  X scan speed above the wire's maximum (preflight refuses)
  stall-midscan   wire sweeps to the middle, then freezes; retract is ignored
  stuck-wire      wire never moves (flat position buffer); retract is ignored

Assumptions not confirmed against the real IOC (marked ASSUMED in code):
  * the wire starts moving when the EDEF is started (CTRL=1) after STARTSCAN
  * SCANSTAT is -1 idle (as archived) and 1 while scanning
  * the lowest free EDEF slot is assigned, like the real reservation
"""
import argparse
import asyncio
import json
import pathlib
import sys
import time

import caproto
import caproto.asyncio.server
import caproto.server
import h5py
import numpy as np

_BEAMCODE_DEFAULT = 2
_EDEF_SYSTEM = "IOC:IN20:EV01"
_FAULTS = (
    "dead-detector",
    "edef-stall",
    "no-beam",
    "no-edef",
    "not-homed",
    "short-buffer",
    "speed-too-fast",
    "stall-midscan",
    "stuck-wire",
)
_FAULT_WIRE = {
    "no-beam": {"beam_rate": 0.0},
    "not-homed": {"homed": 0, "on_status": 0},
    "speed-too-fast": {"x_speed_calc": 1e6},
}
_HERE = pathlib.Path(__file__).parent
_INT_ROLES = frozenset(
    (
        "abort_scan",
        "enabled",
        "homed",
        "initialize",
        "initialize_status",
        "on_status",
        "retract",
        "scan_pulses",
        "scan_status",
        "start_scan",
        "timeout",
        "torque_enable",
        "use_u_wire",
        "use_x_wire",
        "use_y_wire",
    )
)
_MAXN = 4000
_NPNBN = 140
_RATE_MASKS = ("01HZ", "10HZ", "30HZ", "60HZ")
_NSLOTS = 11
_PARKED = 4574.0
_RATE_HZ = 120.0
_STUCK_FAULTS = ("stall-midscan", "stuck-wire")
_TICK_S = 0.05
_TMIT_BASE = 1e9
_USER = "slacwire-sim"


class Sim:
    """All PV definitions and behavior; ``bind`` connects it to a running server."""

    def __init__(self, h5_path, values_path, busy_slots, speed, fault=None):
        self._pl = json.loads((_HERE / "pvlist.json").read_text())
        self._wire = self._pl["wire_control_name"]
        self._speed = speed
        self._static = _load_static(values_path)
        self._src = _load_h5(h5_path)
        self._armed = False
        self._parked = _PARKED
        self._tasks = {}
        self._pvdb = None
        self._fault = None
        self._fault_init = fault or ""
        self._busy = busy_slots
        self._fault_pvs = []
        self._fault_slots = []
        self.specs = {}
        self._add_wire()
        self._add_edef()
        self._add_pnbn()
        self._add_sim()
        self._add_sioc()
        self._add_buffers()

    def bind(self, pvdb):
        self._pvdb = pvdb

    async def clock(self):
        """Tick SIOC:SYS0:AL00:TOD once a second, like the real time-of-day PV."""
        while True:
            await asyncio.sleep(1)
            await self._set("SIOC:SYS0:AL00:TOD", _tod())

    async def set_fault(self, name):
        """Switch fault mode; return the fault now active ('' for none)."""
        name = "" if name in (None, "none") else str(name)
        if name and name not in _FAULTS:
            sys.stdout.write(f"unknown fault {name!r}; valid: {', '.join(_FAULTS)}\n")
            return self._fault or ""
        await self._clear_fault()
        self._fault = name or None
        if name:
            await self._apply_fault(name)
        sys.stdout.write(f"FAULT MODE: {name or 'off'}\n")
        return name

    async def _acquire(self, n):
        p = f"EDEF:SYS0:{n}"
        meas = int(self._val(f"{p}:MEASCNT"))
        if meas > _MAXN:
            raise ValueError(f"MEASCNT={meas} exceeds waveform limit {_MAXN}")
        scanning = self._armed
        data = self._waveforms(meas)
        pos = data[f"{self._wire}:POSN"]
        await self._set(f"{p}:CNTMAX", meas)
        await self._set(f"{p}:CNT", 0)
        if scanning:
            await self._set(f"{self._wire}:SCANSTAT", 1)  # ASSUMED
        t0 = time.monotonic()
        i = 0
        limit = int(meas * 0.6) if self._fault == "edef-stall" else meas
        while i < limit:
            await asyncio.sleep(_TICK_S)
            i = min(limit, int((time.monotonic() - t0) * _RATE_HZ * self._speed))
            await self._set(f"{p}:CNT", i)
            if scanning and i > 0:
                await self._set(f"{self._wire}:MOTR.RBV", float(pos[i - 1]))
        if limit < meas:
            sys.stdout.write(f"slot {n}: FAULT edef-stall at {i} of {meas}\n")
            return
        for pv, a in data.items():
            if self._fault == "short-buffer":
                a = a[: int(len(a) * 0.9)]
            await self._set(f"{pv}HST{n}", a)
        await self._set(f"{p}:CNT", meas)
        await self._set(f"{p}:CTRL", 0)
        if scanning:
            await self._set(f"{self._wire}:SCANSTAT", -1)
            self._armed = False
        sys.stdout.write(f"slot {n}: acquired {meas} points, scanning={scanning}\n")

    def _add(self, name, value, put=None, **kw):
        self.specs[name] = {"value": value, "put": put, "kw": kw}

    def _add_buffers(self):
        for n in range(1, _NSLOTS + 1):
            for pv in self._buffer_pvs():
                self._add(f"{pv}HST{n}", np.zeros(1), dtype=float, max_length=_MAXN)

    def _add_edef(self):
        self._add(f"{_EDEF_SYSTEM}:EDEFNAME", "", self._on_reserve)
        self._add(f"{_EDEF_SYSTEM}:EDEFAVAIL", _NSLOTS - len(self._busy))
        for n in range(1, _NSLOTS + 1):
            p = f"EDEF:SYS0:{n}"
            name = f"Other User {n}" if n in self._busy else ""
            self._add(f"{p}:NAME", name)
            self._add(f"{p}:USERNAME", "other" if n in self._busy else "")
            self._add(f"{p}:AVGCNT", 1)
            self._add(f"{p}:MEASCNT", 0, self._slot_put(n, self._on_meascnt))
            self._add(f"{p}:BEAMCODE", _BEAMCODE_DEFAULT)
            self._add(f"{p}:CNT", 0)
            self._add(f"{p}:CNTMAX", 0)
            self._add(f"{p}:CTRL", 0, self._slot_put(n, self._on_ctrl))
            self._add(f"{p}:FREE", 0, self._slot_put(n, self._on_free))
            for m in range(1, 6):
                self._add(f"{p}:INCLUSION{m}", 0)
                self._add(f"{p}:EXCLUSION{m}", 0)

    def _add_pnbn(self):
        # POSIT: slac_timing.masks asks for these names; EDEF config maps a
        # bit position b to word b // 32, which must be in 1..5, so b >= 32.
        names = ["pockcel_perm"] + [
            f"RATE_MPS_{p}_{r}" for p in ("HXR", "SXR") for r in _RATE_MASKS
        ]
        for i in range(1, _NPNBN + 1):
            n = names[i - 1] if i <= len(names) else f"MASK{i}"
            self._add(f"PNBN:SYS0:{i}:NAME", n)
            self._add(f"PNBN:SYS0:{i}:BITP", 31 + i)
        for p in ("BYKIK", "BYKIKS"):
            self._add(f"IOC:BSY0:MP01:{p}_RATE", "120 Hz")

    def _add_sim(self):
        # Write a fault name (see module docstring) to switch fault mode; "" or "none" clears it.
        self._add("SIM:FAULT", self._fault_init, self._on_fault)

    def _add_sioc(self):
        # GUI header labels. ASSUMED: MODE text; the real value is not archived here.
        self._add("SIOC:SYS0:AL00:TOD", _tod())
        self._add("SIOC:SYS0:AL00:MODE", "Normal")

    def _add_wire(self):
        r = self._src["ranges"]
        d = {
            "abort_scan": 0,
            "beam_rate": _RATE_HZ,
            "enabled": 1,
            "homed": 1,
            "initialize": 0,
            "initialize_status": 1,
            "install_angle": -45.0,
            "motor": _PARKED,
            "motor_rbv": _PARKED,
            "mps_speed": 0.01,
            "on_status": 1,
            "retract": 0,
            "scan_pulses": 350,
            "scan_status": -1,
            "speed": 300.0,
            "speed_max": 5000.0,
            "speed_min": 10.0,
            "start_scan": 0,
            "temperature": 30.0,
            "timeout": 0,
            "torque_enable": 1,
            "use_u_wire": 1,
            "use_x_wire": 1,
            "use_y_wire": 1,
        }
        for k in "xyu":
            lo, hi = r[f"{k}_start"], r[f"{k}_end"]
            d[f"{k}_wire_inner"] = float(lo)
            d[f"{k}_wire_outer"] = float(hi)
            d[f"{k}_size"] = 0.0
            d[f"{k}_speed_calc"] = (hi - lo) * _RATE_HZ / d["scan_pulses"]
        self._parked = float(self._static.get(f"{self._wire}:MOTR.RBV", _PARKED))
        h = {
            "abort_scan": self._on_stop,
            "initialize": self._on_init,
            "retract": self._on_retract,
            "start_scan": self._on_start_scan,
        }
        for role, pv in self._pl["wire_pvs"].items():
            v = self._static.get(pv, d.get(role, 0.0))
            if role in _INT_ROLES:
                v = int(v)
            else:
                v = float(v)
            self._add(pv, v, h.get(role))

    async def _apply_fault(self, name):
        for role, v in _FAULT_WIRE.get(name, {}).items():
            pv = self._pl["wire_pvs"][role]
            await self._set(pv, int(v) if role in _INT_ROLES else float(v))
            self._fault_pvs.append(pv)
        if name == "no-edef":
            for n in range(1, _NSLOTS + 1):
                if not self._val(f"EDEF:SYS0:{n}:NAME"):
                    await self._set(f"EDEF:SYS0:{n}:NAME", f"Other User {n}")
                    await self._set(f"EDEF:SYS0:{n}:USERNAME", "other")
                    self._fault_slots.append(n)
            await self._set_avail()

    def _buffer_pvs(self):
        r = [f"{self._wire}:POSN"]
        r += [f"{c}:QDCRAW" for c in self._pl["pmts"].values()]
        for b in self._pl["bpms"].values():
            r += [f"{b['control_name']}:{s}" for s in ("X", "Y")]
        r += [f"{c}:TMIT" for c in self._pl["tmit_bpms"]]
        return r

    def _chan(self, name):
        return self._pvdb[name]

    async def _clear_fault(self):
        for pv in self._fault_pvs:
            await self._set(pv, self.specs[pv]["value"])
        self._fault_pvs = []
        for n in self._fault_slots:
            if self._val(f"EDEF:SYS0:{n}:NAME") == f"Other User {n}":
                await self._set(f"EDEF:SYS0:{n}:NAME", "")
                await self._set(f"EDEF:SYS0:{n}:USERNAME", "")
        self._fault_slots = []
        await self._set_avail()

    async def _on_ctrl(self, n, value):
        t = self._tasks.pop(n, None)
        if t:
            t.cancel()
        if int(value) == 1:
            self._tasks[n] = asyncio.create_task(self._acquire(n))

    async def _on_fault(self, value):
        return await self.set_fault(str(value))

    async def _on_free(self, n, value):
        if int(value) != 1:
            return
        await self._on_ctrl(n, 0)
        p = f"EDEF:SYS0:{n}"
        for s in ("NAME", "USERNAME"):
            await self._set(f"{p}:{s}", "")
        await self._set(f"{p}:CNT", 0)
        await self._set_avail()
        sys.stdout.write(f"slot {n}: freed\n")

    async def _on_init(self, value):
        await self._set(f"{self._wire}:MOTR_INIT_STS", 1)

    async def _on_meascnt(self, n, value):
        await self._set(f"EDEF:SYS0:{n}:CNTMAX", int(value))

    async def _on_reserve(self, value):
        value = str(value)
        if not value:
            return
        for n in range(1, _NSLOTS + 1):
            if self._val(f"EDEF:SYS0:{n}:NAME") == value:
                return
        for n in range(1, _NSLOTS + 1):
            if not self._val(f"EDEF:SYS0:{n}:NAME"):
                await self._set(f"EDEF:SYS0:{n}:NAME", value)
                await self._set_avail()
                sys.stdout.write(f"slot {n}: reserved as {value!r}\n")
                return
        sys.stdout.write("reserve request failed: no free slot\n")

    async def _on_retract(self, value):
        """Move the wire back to its parked position (ASSUMED: ~1 s ramp)."""
        if int(value) != 1:
            return
        if self._fault in _STUCK_FAULTS:
            sys.stdout.write("retract ignored: FAULT wire is stuck\n")
            return
        t = self._tasks.pop("retract", None)
        if t:
            t.cancel()
        self._tasks["retract"] = asyncio.create_task(self._retract())
        sys.stdout.write("retract\n")

    async def _on_start_scan(self, value):
        if int(value) == 1:
            self._armed = True
            sys.stdout.write("wire armed\n")

    async def _on_stop(self, value):
        if int(value) == 1:
            for n in [n for n in self._tasks if n != "retract"]:
                await self._on_ctrl(n, 0)
                await self._set(f"EDEF:SYS0:{n}:CTRL", 0)
            self._armed = False
            await self._set(f"{self._wire}:SCANSTAT", -1)
            sys.stdout.write("abort\n")

    async def _retract(self):
        rbv = f"{self._wire}:MOTR.RBV"
        x0 = float(self._val(rbv))
        for i in range(1, 11):
            await asyncio.sleep(0.1)
            await self._set(rbv, x0 + (self._parked - x0) * i / 10)
        await self._set(f"{self._wire}:MOTR", self._parked)

    async def _set(self, name, value):
        await self._chan(name).write(value)

    async def _set_avail(self):
        z = sum(
            1
            for n in range(1, _NSLOTS + 1)
            if not self._val(f"EDEF:SYS0:{n}:NAME")
        )
        await self._set(f"{_EDEF_SYSTEM}:EDEFAVAIL", z)

    def _slot_put(self, n, handler):
        async def f(value):
            await handler(n, value)

        return f

    def _val(self, name):
        v = self._chan(name).value
        return v.decode() if isinstance(v, bytes) else v

    def _waveforms(self, n):
        """Return {pv_without_HST: array(n)} for every buffer PV."""
        s = self._src
        z = {f"{self._wire}:POSN": _fit(s["posn"], n)}
        for k, c in self._pl["pmts"].items():
            z[f"{c}:QDCRAW"] = _fit(s["pmt"][k], n)
        rng = np.random.default_rng(1)
        loss = _fit(s["tmitloss"], n)
        common = 1 + 0.002 * rng.standard_normal(n)
        down = set(self._pl["tmitloss"]["downstream"])
        for c, k in self._pl["tmit_bpms"].items():
            base = self._static.get(f"{c}:TMIT1H", _TMIT_BASE) or _TMIT_BASE
            t = base * common * (1 + 0.0005 * rng.standard_normal(n))
            if k in down:
                t = t * (1 - loss / 100.0)
            z[f"{c}:TMIT"] = t
        for k, b in self._pl["bpms"].items():
            c = b["control_name"]
            for ax in ("x", "y"):
                if k in s["bpm"]:
                    z[f"{c}:{ax.upper()}"] = _fit(s["bpm"][k][ax], n)
                else:
                    b0 = self._static.get(f"{c}:{ax.upper()}1H", 0.0) or 0.0
                    z[f"{c}:{ax.upper()}"] = b0 + 0.005 * rng.standard_normal(n)
        return self._with_fault(z, n)

    def _with_fault(self, z, n):
        """Corrupt the waveforms according to the selected fault."""
        w = f"{self._wire}:POSN"
        if self._fault == "dead-detector":
            d = self._pl["default_detector"].split(":")[0]
            z[f"{self._pl['pmts'][d]}:QDCRAW"] = np.zeros(n)
        elif self._fault == "stall-midscan":
            z[w] = z[w].copy()
            z[w][n // 2 :] = z[w][n // 2 - 1]
        elif self._fault == "stuck-wire":
            z[w] = np.full(n, float(self._val(f"{self._wire}:MOTR.RBV")))
        return z




def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument(
        "--h5",
        required=True,
        help="a real WS28144 OTF scan file (.h5) whose waveforms are replayed",
    )
    a.add_argument(
        "--values",
        default=str(_HERE / "archiver-values.json"),
        help="optional JSON of static PV values (default: archiver-values.json here)",
    )
    a.add_argument("--busy", default="1,2,3,4", help="EDEF slots held by 'other users'")
    a.add_argument("--speed", type=float, default=1.0, help="run scans this much faster")
    a.add_argument(
        "--fault",
        choices=_FAULTS,
        help="recreate a failure; see the module docstring for what each does",
    )
    args = a.parse_args()
    busy = {int(x) for x in args.busy.split(",") if x}
    sim = Sim(args.h5, args.values, busy, args.speed, args.fault)
    asyncio.run(_serve(sim, args.fault))


class _Group(caproto.server.PVGroup):
    """PVGroup whose PVs are all defined dynamically from ``Sim.specs``."""

    def __init__(self, sim, *args, **kwargs):
        for i, (name, s) in enumerate(sim.specs.items()):
            key = f"pv{i}"
            kw = dict(s["kw"])
            if isinstance(s["value"], str):
                kw["dtype"] = caproto.ChannelType.STRING
            p = caproto.server.pvproperty(value=s["value"], name=name, **kw)
            if s["put"]:
                p = p.putter(_putter(s["put"]))
            self._pvs_[key] = p
            p.__set_name__(self, key)
        super().__init__(*args, **kwargs)


def _fit(a, n):
    """Resample array ``a`` to n points."""
    a = np.asarray(a, dtype=float)
    if len(a) == n:
        return a
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)


def _load_h5(path):
    with h5py.File(path, "r") as h:
        rd = h["collection_result/raw_data"]
        r = h["collection_result/metadata/scan_ranges"].attrs
        return {
            "posn": rd["WS28144"][()],
            "tmitloss": rd["TMITLOSS"][()],
            "pmt": {k: rd[k][()] for k in rd if k.startswith("PMT")},
            "bpm": {
                k: {"x": rd[k]["x"][()], "y": rd[k]["y"][()]}
                for k in rd
                if k.startswith("BPM")
            },
            "ranges": {k: float(v) for k, v in r.items()},
        }


def _load_static(path):
    p = pathlib.Path(path)
    if not p.exists():
        sys.stdout.write(f"no {p}; using built-in defaults\n")
        return {}
    z = json.loads(p.read_text())["static"]
    sys.stdout.write(f"{p}: {len(z)} static values\n")
    return z


def _putter(handler):
    async def f(group, instance, value):
        r = await handler(value)
        return value if r is None else r

    return f


async def _serve(sim, fault):
    g = _Group(sim, prefix="")
    sim.bind(g.pvdb)
    c = caproto.asyncio.server.Context(g.pvdb, interfaces=["127.0.0.1"])
    sys.stdout.write(f"serving {len(g.pvdb)} PVs on 127.0.0.1\n")
    if fault:
        await sim.set_fault(fault)
    z = asyncio.create_task(sim.clock())
    await c.run(log_pv_names=False)


def _tod():
    return time.strftime("%m/%d/%Y %H:%M:%S")


if __name__ == "__main__":
    main()
