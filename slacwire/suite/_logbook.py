from __future__ import annotations

import getpass
import importlib
import logging
from pathlib import Path

logger = logging.getLogger("wire_scan_logger")


class LogbookMixin:
    """Post wire scan results to the SLAC physics logbook."""

    def post_to_logbook(
        self,
        title: str,
        body: str = "",
        attachment: str | None = None,
    ) -> None:
        """Post an arbitrary entry to the physics logbook.

        Uses physicselog.submit_entry under the hood.

        Args:
            title: Logbook entry title.
            body: Logbook entry body text.
            attachment: Optional file path (image) to attach.

        Raises:
            RuntimeError: If the logbook post fails.
        """
        logbook = self._resolve_logbook()
        username = getpass.getuser()

        physicselog = importlib.import_module("physicselog")
        physicselog.submit_entry(
            logbook=logbook,
            username=username,
            title=title,
            entry_text=body or None,
            attachment=attachment,
            thumbnail=attachment,
        )

        logbook_label = "LCLS-II" if logbook == "lcls2" else "LCLS"
        logger.info("Posted to %s logbook: %s", logbook_label, title)

    def post_last_to_logbook(
        self,
        wire: str,
        profile: str | None = None,
        title: str | None = None,
        body: str | None = None,
    ) -> None:
        """Post the latest scan result for a wire to the physics logbook.

        Args:
            wire: Wire name whose latest result will be posted.
            profile: If given, attach only that profile's plot. If None,
                attach the first available plot from the latest render.
            title: Override the auto-generated logbook entry title.
            body: Override the auto-generated logbook entry body.

        Raises:
            KeyError: If no results exist for the wire.
            RuntimeError: If the logbook post fails.
        """
        data = self.latest_run(wire)
        meta = data.collection_result.metadata
        detector = meta.rms_detector or meta.default_detector
        if ":" in detector:
            detector = detector.split(":", 1)[0]

        if title is None:
            if profile:
                title = f"{wire} Scan v. {detector} - {profile} Profile"
            else:
                title = f"{wire} Scan v. {detector}"

        if body is None:
            body = f"Wire scan for {wire} using {detector}."

        plots = self._logbook_plots(wire, profile)
        attachment = str(plots[0]) if plots else None
        self.post_to_logbook(title=title, body=body, attachment=attachment)

    def _resolve_logbook(self) -> str:
        """Map the suite beampath to the physicselog logbook name."""
        if self.beampath.startswith("SC"):
            return "lcls2"
        return "lcls"

    def _logbook_plots(self, wire: str, profile: str | None) -> list[Path]:
        """Collect plot file paths for a logbook post.

        Looks up saved plots from the registry. If none are found (e.g.
        save_plots was False), re-renders and saves them.
        """
        for entry in reversed(self.registry.entries):
            if entry.get("wire") == wire and entry.get("status", "ok") == "ok":
                plots = entry.get("plots", [])
                if plots:
                    paths = [Path(p) for p in plots if Path(p).exists()]
                    if profile:
                        paths = [p for p in paths if f"Profile_{profile}_" in p.name]
                    if paths:
                        return paths
                break

        plot_paths = self.replot(wire)
        if profile:
            plot_paths = [p for p in plot_paths if f"Profile_{profile}_" in p.name]
        return plot_paths


# --- elog_client implementation (not yet released) ---
# def post_to_logbook(
#     self,
#     title: str,
#     body: str = "",
#     file_paths: list[str] | None = None,
#     tags: list[str] | None = None,
# ) -> None:
#     logbook = self._resolve_logbook()
#
#     if tags is None:
#         tags = ["Wire Scan"]
#
#     elog = importlib.import_module("elog_client")
#     status_code, result = elog.post(
#         title=title,
#         body=body,
#         tags=tags,
#         logbooks=[logbook],
#         file_paths=file_paths or [],
#     )
#
#     if status_code not in (200, 201):
#         msg = f"Logbook post failed ({status_code}): {result}"
#         logger.error(msg)
#         raise RuntimeError(msg)
#
#     logbook_label = "LCLS-II" if logbook == "physics_lcls2elog" else "LCLS"
#     logger.info("Posted to %s logbook: %s", logbook_label, title)
