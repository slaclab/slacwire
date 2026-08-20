"""CLI entry point for logging a single wire scan run to the Run Registry.

Intended to be called from external processes (e.g. MATLAB) that cannot
import slacwire directly.  Prints the assigned run_id to stdout on success.

Usage::

    slacwire-log-run --wire WIRE:LI24:807 --beampath CU_HXR \\
        --method matlab_step --detector PMT:LI24:800 --status ok

    slacwire-log-run --wire WIRE:LI24:807 --beampath CU_HXR \\
        --method matlab_step --status error --error "Motor stall detected"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Support both `python3 -m slacwire.registry.log_run_cli` (module execution,
# where relative imports work) and `python3 /path/to/log_run_cli.py` (direct
# script execution, where __package__ is None and relative imports fail).
if __package__:
    from .registry import RunRegistry
else:
    # Add the repo root (three levels up from this file) to sys.path so that
    # `slacwire` is importable when the script is invoked directly.
    _repo_root = Path(__file__).resolve().parent.parent.parent
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))
    from slacwire.registry.registry import RunRegistry

from slacwire.suite._constants import _REGISTRY_PATH


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="slacwire-log-run",
        description="Append one wire scan run entry to the slacwire Run Registry.",
    )
    p.add_argument("--wire", required=True, help="Wire device name (EPICS), e.g. WIRE:LI24:807")
    p.add_argument("--beampath", required=True, help="Beampath identifier, e.g. CU_HXR")
    p.add_argument(
        "--method",
        required=True,
        help="Scan method label, e.g. matlab_step",
    )
    p.add_argument("--detector", default=None, help="Detector device name, if known")
    p.add_argument("--filepath", default=None, help="Path to saved data file, if any")
    p.add_argument(
        "--plot",
        dest="plots",
        action="append",
        default=[],
        metavar="PATH",
        help="Path to a saved plot PNG (may be repeated for multiple plots)",
    )
    p.add_argument(
        "--status",
        choices=["ok", "error"],
        default="ok",
        help="Scan outcome: 'ok' (default) or 'error'",
    )
    p.add_argument("--error", default=None, help="Error message when --status=error")
    p.add_argument(
        "--registry-path",
        default=None,
        metavar="PATH",
        help=f"Override default registry JSON path (default: {_REGISTRY_PATH})",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    registry_path = Path(args.registry_path) if args.registry_path else _REGISTRY_PATH

    try:
        registry = RunRegistry(path=registry_path)
        entry = registry.log(
            method=args.method,
            wire=args.wire,
            beampath=args.beampath,
            detector=args.detector or None,
            filepath=args.filepath or None,
            plots=args.plots or [],
            status=args.status,
            error=args.error or None,
        )
        print(entry["run_id"])
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
