from __future__ import annotations


class ResultsMixin:
    """Methods for querying, re-plotting, and summarizing results."""

    def latest_run(self, wire: str):
        """Retrieve the most recent run result for a given wire.

        Args:
            wire: Wire name to look up in stored results.
        """
        runs = self.results.get(wire, [])
        if not runs:
            msg = f"No results found for {wire}. Run it first."
            raise KeyError(msg)
        return runs[-1]

    def replot(self, wire: str, detector: str | None = None) -> list:
        """Regenerate plots for the latest run of a wire without re-scanning.

        Args:
            wire: Wire name whose latest result will be re-plotted.
            detector: Detector for profile plots. If None, uses the detector
                recorded in the run metadata.
        """
        data = self.latest_run(wire)
        if detector is None:
            meta = data.collection_result.metadata
            detector = meta.rms_detector or meta.default_detector
        if ":" in detector:
            detector = detector.split(":", 1)[0]

        method = "otf"
        for entry in reversed(self.registry.entries):
            if entry.get("wire") == wire:
                method = entry.get("method", "otf")
                break
        file_prefix = "OTF" if method == "otf" else "Step"

        profiles = tuple(data.fit_result.keys()) if hasattr(data, "fit_result") else ()

        return self.view.render(
            data,
            wire=wire,
            detector=detector,
            profiles=profiles,
            file_prefix=file_prefix,
            plotdir=self.plotdir,
            stamp=self._stamp(),
            show=self.show,
            save=self.save_plots,
        )

    def summary(self) -> None:
        """Print the latest scan result for each wire.

        Takes no arguments. Prints a formatted table of the most recent
        result per configured wire, including sigma values where available.
        """
        _SEP = "─" * 77
        print(f"\nWire Scan Suite  ·  beampath: {self.beampath}")
        print(_SEP)

        wires_with_results = [w for w in self.wires if self.results.get(w)]
        total_runs = sum(len(v) for v in self.results.values())

        if not wires_with_results:
            print("  No results yet.")
            print(_SEP)
            return

        for wire in wires_with_results:
            runs = self.results[wire]
            data = self.latest_run(wire)
            run_count = len(runs)

            method = "—"
            for entry in reversed(self.registry.entries):
                if entry.get("wire") == wire:
                    method = entry.get("method", "—")
                    break

            meta = data.collection_result.metadata
            ts = meta.timestamp
            timestamp = ts.strftime("%Y%m%d_%H%M%S") if ts is not None else "—"
            detector = meta.rms_detector or meta.default_detector

            label = f"{run_count} run" + ("s" if run_count != 1 else "")
            print(f"\n{wire}  ({label})")
            print(f"  Latest  |  {timestamp}  |  {method}  |  detector: {detector}")

            if hasattr(data, "fit_result"):
                for profile, fit in data.fit_result.items():
                    det_fits = fit.detectors
                    if detector not in det_fits:
                        print(f"    {profile} :  no fit")
                        continue
                    sigma = det_fits[detector].sigma
                    print(f"    {profile} :  σ = {sigma:>7.1f} µm")
            else:
                print("    collection-only result (analysis skipped)")

        wire_label = "wire" + ("s" if len(wires_with_results) != 1 else "")
        run_label = "run" + ("s" if total_runs != 1 else "")
        print(f"\n{_SEP}")
        print(f"Total: {len(wires_with_results)} {wire_label}, {total_runs} {run_label}\n")
