"""CLI entry point for slacwire: python -m slacwire --help"""

import argparse
import sys

from .suite import WIRE_AREA_LOOKUP, Beampath


VALID_WIRES = sorted(WIRE_AREA_LOOKUP.keys())
VALID_BEAMPATHS = ["CU_HXR", "CU_SXR", "SC_HXR", "SC_SXR", "SC_BSYD", "SC_DIAG0"]


def _add_common_args(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--wires", nargs="+", default=["WS28144"], metavar="WIRE",
        help=f"Wire names to configure. Choices: {', '.join(VALID_WIRES)}",
    )
    parser.add_argument(
        "--beampath", default="CU_HXR", choices=VALID_BEAMPATHS,
        help="Accelerator beampath (default: CU_HXR)",
    )
    parser.add_argument(
        "--detector", default=None, metavar="DET",
        help="Primary detector (e.g., PMT29150). Defaults to device default.",
    )
    parser.add_argument(
        "--no-save", dest="save", action="store_false",
        help="Skip writing HDF5 data files",
    )
    parser.add_argument(
        "--no-show", dest="show", action="store_false",
        help="Don't display plots interactively",
    )
    parser.add_argument(
        "--no-plots", dest="save_plots", action="store_false",
        help="Skip writing PNG plot files",
    )


def _build_suite(args):
    from .suite import WireScanSuite

    return WireScanSuite(
        wires=args.wires,
        beampath=args.beampath,
        detector=args.detector,
        save=args.save,
        show=args.show,
        save_plots=args.save_plots,
    )


def cmd_run(args):
    suite = _build_suite(args)
    if args.wire:
        suite.run_single(
            wire=args.wire,
            scan_mode=args.scan_mode,
            rms_detector=args.rms_detector,
        )
    else:
        suite.run_all(
            scan_mode=args.scan_mode,
            rms_detector=args.rms_detector,
        )


def cmd_collect(args):
    suite = _build_suite(args)
    suite.collect_single(wire=args.wire, scan_mode=args.scan_mode)


def cmd_motion_test(args):
    suite = _build_suite(args)
    result = suite.motion_test(wire=args.wire)
    print(result)


def cmd_replot(args):
    suite = _build_suite(args)
    paths = suite.replot(wire=args.wire, detector=args.replot_detector)
    for p in paths:
        print(p)


def cmd_summary(args):
    suite = _build_suite(args)
    suite.summary()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="slacwire",
        description="Wire scanner beam profile measurement CLI for LCLS",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # -- run --
    p_run = subparsers.add_parser(
        "run",
        help="Run wire scan(s) with full analysis",
        description="Execute beam profile scan with Gaussian fitting and plotting.",
    )
    _add_common_args(p_run)
    p_run.add_argument(
        "--wire", default=None, metavar="WIRE",
        help="Single wire to scan. If omitted, scans all configured wires.",
    )
    p_run.add_argument(
        "--scan-mode", default="otf", choices=["otf", "step"],
        help="Scan mode: 'otf' (on-the-fly) or 'step' (default: otf)",
    )
    p_run.add_argument(
        "--rms-detector", default=None, metavar="DET",
        help="Override detector for RMS calculation",
    )
    p_run.set_defaults(func=cmd_run)

    # -- collect --
    p_collect = subparsers.add_parser(
        "collect",
        help="Collect raw data only (no analysis)",
        description="Acquire raw wire scan data without Gaussian fitting.",
    )
    _add_common_args(p_collect)
    p_collect.add_argument(
        "wire", metavar="WIRE",
        help="Wire to collect from (e.g., WS28144)",
    )
    p_collect.add_argument(
        "--scan-mode", default="otf", choices=["otf", "step"],
        help="Scan mode: 'otf' (on-the-fly) or 'step' (default: otf)",
    )
    p_collect.set_defaults(func=cmd_collect)

    # -- motion-test --
    p_motion = subparsers.add_parser(
        "motion-test",
        help="Run beam-less motion validation",
        description="Move wire through full range without beam to validate hardware.",
    )
    _add_common_args(p_motion)
    p_motion.add_argument(
        "wire", metavar="WIRE",
        help="Wire to test (e.g., WS28144)",
    )
    p_motion.set_defaults(func=cmd_motion_test)

    # -- replot --
    p_replot = subparsers.add_parser(
        "replot",
        help="Regenerate plots from the latest run",
        description="Re-render plots for a previous scan without re-acquiring data.",
    )
    _add_common_args(p_replot)
    p_replot.add_argument(
        "wire", metavar="WIRE",
        help="Wire whose latest result to re-plot",
    )
    p_replot.add_argument(
        "--replot-detector", default=None, metavar="DET",
        help="Override detector for plot. Defaults to run's recorded detector.",
    )
    p_replot.set_defaults(func=cmd_replot)

    # -- summary --
    p_summary = subparsers.add_parser(
        "summary",
        help="Print summary of latest results",
        description="Display the most recent scan result for each configured wire.",
    )
    _add_common_args(p_summary)
    p_summary.set_defaults(func=cmd_summary)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
