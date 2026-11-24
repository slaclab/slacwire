# WS28144 soft IOC

A [caproto](https://github.com/caproto/caproto) IOC that serves the PVs slacwire
touches during an OTF wire scan, under their real names, so `WireScanSuite` and the
GUI can run a full scan with no accelerator. It is a test fixture: beam data comes
from a real scan file you provide, replayed on every scan.

## Install

    pip install caproto h5py numpy

## Run

    python wire_ioc.py --h5 /path/to/OTF_WS28144_20260716_124144.h5

`--h5` is a real `WS28144` OTF scan file written by slacwire. The IOC replays its
wire position, PMT, and BPM X/Y waveforms. slacwire names these files
`<mode>_<wire>_<YYYYMMDD>_<HHMMSS>.h5`, so the example above is an on-the-fly (`OTF`)
scan of `WS28144` started on 2026-07-16 at 12:41:44. A file for another wire will
not work (the IOC reads the `WS28144` dataset); `Step_` files are untested.

Then point slacwire at it, in a separate shell:

    export EPICS_CA_ADDR_LIST=127.0.0.1 EPICS_CA_AUTO_ADDR_LIST=NO
    export PYDM_DEFAULT_PROTOCOL=ca        # GUI only
    pydm slacwire/ws_gui.py

The IOC binds to `127.0.0.1` only. It serves real production PV names, so do not
expose it to a facility network. Set `EPICS_CA_SERVER_PORT` to use a port other
than 5064 (and set the same port on the client).

Other options: `--speed N` runs scans N times faster than 120 Hz, `--busy 1,2,3,4`
sets which EDEF slots other users hold, `--values FILE` loads static PV values
from `{"static": {"<pv>": <value>}}`.

## Running a scan in the GUI

The IOC serves one wire, so select it in the GUI:

| Control | Select |
|---|---|
| Beampath | `CU_SXR` (the source file's beampath) or `CU_HXR`; the IOC serves BPMs for both |
| Area | `LI28` |
| Wire | `WS28144` |
| Detector | `PMT29150` (the default), `PMT756`, `PMT820`, or `TMITLOSS` |
| Apply Jitter Correction | **leave unchecked**: it needs the SLAC online model (`meme`), which the IOC does not provide |
| Normalize by Charge | optional; uses the `BPM27201` toroid |
| Fit method | dropdown under the plots; Gaussian is the default |

Check the X, Y, and U plane boxes you want, then click **Start**. The wire position
display sweeps for about 12 s, then the plots appear. The IOC terminal logs each step
(`reserved`, `wire armed`, `acquired 1453 points`, `freed`).

**Abort** stops the scan and retracts the wire. slacwire's collection loop does not
check for an abort, so the Start button returns only after the acquisition timeout
(about 22 s for 1453 points).

Other wires and areas have no PVs here and will fail to connect.

## What it serves

| PVs | Behavior |
|---|---|
| `WIRE:LI28:144:*` | wire state; `STARTSCAN` arms, `MOTR_RETRACT` ramps back to park |
| `IOC:IN20:EV01:EDEFNAME`, `EDEF:SYS0:<1-11>:*` | EDEF reserve, configure, start, count, free |
| `PNBN:SYS0:<1-140>:*` | mask names and bit positions read during EDEF setup |
| `<pv>HST<1-11>` | waveform buffers: wire `POSN`, PMT `QDCRAW`, BPM `X`/`Y`/`TMIT` |
| `SIOC:SYS0:AL00:TOD`, `:MODE` | GUI header labels |
| `SIM:FAULT` | fault switch (below) |

Replayed from the `--h5` file: wire position, PMTs, and the BPM X/Y buffers of the
jitter BPMs. Synthesized: `TMIT` for all BPMs (so `TMITLOSS` reproduces the file's),
and X/Y for the other BPMs. Buffers are resampled to the point count slacwire
requests, so beam sizes are those of the source scan, not a new measurement.
Waveforms are limited to 4000 points.

## Faults

Start with `--fault NAME`, or switch at run time:

    caput SIM:FAULT stuck-wire
    caput SIM:FAULT none            # clear

No fault is active by default. Faults that change PVs take effect immediately;
the rest are read when a scan starts, so set them before clicking Start.

| Fault | What happens |
|---|---|
| `dead-detector` | default detector's PMT buffer is all zeros (degenerate fit) |
| `edef-stall` | EDEF count freezes at 60% (acquisition timeout) |
| `no-beam` | `BEAMRATE` is 0 (preflight refuses the scan) |
| `no-edef` | all EDEF slots held by other users (`ReservationError`) |
| `not-homed` | wire never reports homed/on (OTF init fails after 3 tries) |
| `short-buffer` | every buffer comes back 90% long (`BufferSizeError`) |
| `speed-too-fast` | X scan speed above the maximum (preflight refuses) |
| `stall-midscan` | wire freezes at mid-sweep; retract is ignored |
| `stuck-wire` | wire never moves; retract is ignored |

## pvlist.json

`wire_ioc.py` requires `pvlist.json` next to it: the wire, BPM, and PMT PV names to
serve. It was generated for `WS28144` by `make_pvlist.py`, which needs `slac-db` and
`slac-devices` importable:

    python make_pvlist.py

## Assumptions not checked against the real IOC

Marked `ASSUMED` in the code: the wire moves when the EDEF starts after `STARTSCAN`;
`SCANSTAT` is -1 idle and 1 while scanning; the lowest free EDEF slot is assigned;
the retract motion takes about 1 s; `SIOC:SYS0:AL00:MODE` reads `Normal`.

## Local paths

slacwire and slac-measurements hardcode `/u1/lcls/physics/...` for logs and the run
registry. On a machine without `/u1`, create those directories or point the
constants (`slacwire/_constants.py`, `_LOG_DIR` in
`slac_measurements/wires/collection/base.py`) at a writable location.
