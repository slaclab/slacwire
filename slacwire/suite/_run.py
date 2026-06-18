from __future__ import annotations

import logging
from datetime import datetime

from slac_measurements.wires.scan import WireBeamProfileMeasurement

logger = logging.getLogger("wire_scan_logger")


class RunMixin:
    """Methods for executing wire scans with full analysis."""

    def run_all(
        self,
        scan_mode: str = "otf",
        rms_detector: str | None = None,
        multi_view: bool = True,
        jitter_correction: bool = False,
    ):
        """Run all configured wires in the requested scan mode.

        Args:
            scan_mode: "otf" (on-the-fly) or "step". Default "otf".
            rms_detector: Override detector for RMS calculation. If None,
                uses the device's default detector.
            multi_view: If True, show a single combined 2x2 figure per wire
                (trajectory + profiles) instead of individual plot windows.
            jitter_correction: If True, apply orbit-fit jitter correction
                before analysis.
        """
        show_orig = self.show
        if multi_view:
            self.show = False

        file_prefix = "OTF" if scan_mode.lower() == "otf" else "Step"

        for wire in self.wires:
            self.run_single(
                wire=wire,
                scan_mode=scan_mode,
                rms_detector=rms_detector,
                jitter_correction=jitter_correction,
            )

            if multi_view:
                data = self.latest_run(wire)
                device = self._get_device(wire)
                meta = data.collection_result.metadata
                detector = rms_detector or meta.rms_detector or meta.default_detector
                if ":" in detector:
                    detector = detector.split(":", 1)[0]
                profiles = ()
                if hasattr(data, "fit_result"):
                    profiles = tuple(device.active_profiles())
                self.view.render_multi(
                    data,
                    wire=wire,
                    detector=detector,
                    profiles=profiles,
                    file_prefix=file_prefix,
                    plotdir=self.plotdir,
                    stamp=self._stamp(),
                    show=show_orig,
                    save=self.save_plots,
                )

        self.show = show_orig

    def run_single(
        self,
        wire: str,
        scan_mode: str = "otf",
        rms_detector: str | None = None,
        jitter_correction: bool = False,
    ):
        """Run a single wire in the requested scan mode.

        Args:
            wire: Wire name (e.g. "WS28144"). Must exist in WIRE_AREA_LOOKUP.
            scan_mode: "otf" (on-the-fly) or "step". Default "otf".
            rms_detector: Override detector for RMS calculation. If None,
                uses the device's default detector.
            jitter_correction: If True, apply orbit-fit jitter correction
                before analysis.
        """
        wire_name, _ = self._resolve_wire_and_area(wire)
        device = self._get_device(wire_name)
        mode = scan_mode.lower()

        if mode not in ("otf", "step"):
            raise ValueError(
                f"Invalid scan_mode '{scan_mode}'. Use 'otf' or 'step'."
            )

        self._run_device_scan(
            device=device,
            method=mode,
            scan_fn=lambda dev, **kw: self._measure(
                dev, scan_mode=mode, jitter_correction=jitter_correction, **kw
            ),
            rms_detector=rms_detector,
            file_prefix="OTF" if mode == "otf" else "Step",
        )

    def _measure(
        self,
        device,
        scan_mode: str,
        rms_detector: str | None = None,
        jitter_correction: bool = False,
    ):
        """Create a measurement and execute it."""
        measurement = WireBeamProfileMeasurement(
            beam_profile_device=device, beampath=self.beampath
        )
        return measurement.measure(
            scan_mode=scan_mode,
            rms_detector=rms_detector,
            jitter_correction=jitter_correction,
        )

    def _run_device_scan(
        self,
        device,
        method: str,
        scan_fn,
        rms_detector: str | None,
        file_prefix: str,
    ):
        """Execute common scan flow for a single device and method."""
        scan_started = datetime.now()
        run_stamp = scan_started.strftime("%Y%m%d_%H%M%S")
        default_detector = device.metadata.default_detector
        selected_detector = (
            rms_detector if rms_detector is not None else default_detector
        )
        if ":" in selected_detector:
            selected_detector = selected_detector.split(":", 1)[0]

        try:
            data = scan_fn(device, rms_detector=selected_detector)
            self.results.setdefault(device.name, []).append(data)

            path = None
            if self.save:
                path = self.outdir / f"{file_prefix}_{device.name}_{run_stamp}.h5"
                data.save_to_h5(path)

            plot_paths = []
            if self.save_plots or self.show:
                profiles = ()
                if hasattr(data, "fit_result"):
                    profiles = tuple(device.active_profiles())
                plot_paths = self.view.render(
                    data,
                    wire=device.name,
                    detector=selected_detector,
                    profiles=profiles,
                    file_prefix=file_prefix,
                    plotdir=self.plotdir,
                    stamp=run_stamp,
                    show=self.show,
                    save=self.save_plots,
                )
            scope_data = self._resolve_scope_data_path(
                wire=device.name,
                method=method,
                since=scan_started,
            )

            self.registry.log(
                method=method,
                wire=device.name,
                beampath=self.beampath,
                detector=selected_detector,
                filepath=path,
                scope_data=scope_data,
                plots=plot_paths,
            )
        except Exception as e:
            scope_data = self._resolve_scope_data_path(
                wire=device.name,
                method=method,
                since=scan_started,
            )
            self.registry.log(
                method=method,
                wire=device.name,
                beampath=self.beampath,
                detector=selected_detector,
                scope_data=scope_data,
                status="error",
                error=str(e),
            )
            raise
