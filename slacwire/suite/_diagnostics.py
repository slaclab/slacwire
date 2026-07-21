from __future__ import annotations

import logging

logger = logging.getLogger("wire_scan_logger")


class DiagnosticsMixin:
    """Read-only CA cache inspection for wire scan sessions."""

    def cache_info(self) -> dict:
        """Return a snapshot of the EPICS CA cache state.

        Returns a dict with keys:
            context: Current CA context ID (or None)
            pv_cache_total: Total entries in the global PV object cache
            channel_cache_total: Total entries in the context's channel cache
            per_device: Dict mapping wire name -> count of matching PV cache
                entries. Also contains "EDEF" and "BSA" keys with counts of
                PVs matching those subsystems.
        """
        import epics.ca
        from epics.pv import _PVcache_

        ctx = epics.ca.current_context()
        context_cache = epics.ca._cache.get(ctx, {}) if ctx is not None else {}

        per_device: dict[str, int] = {}
        for wire_name in self.devices:
            wire = self.devices[wire_name]
            ctrl = wire.controls_information.control_name
            count = sum(
                1 for name in context_cache if ctrl in name
            )
            per_device[wire_name] = count
        per_device["EDEF"] = sum(1 for name in context_cache if "EDEF" in name)
        per_device["BSA"] = sum(1 for name in context_cache if "BSA" in name)

        return {
            "context": ctx,
            "pv_cache_total": len(_PVcache_),
            "channel_cache_total": len(context_cache),
            "per_device": per_device,
        }

    def cache_pvs(self) -> dict[str, list[str]]:
        """Return actual PV names in the cache, grouped by device.

        Returns a dict mapping wire name -> sorted list of cached PV names.
        Additional keys "EDEF" and "BSA" group PVs belonging to those
        subsystems. "_unmatched" contains PVs that don't match any configured
        wire device or subsystem.
        """
        import epics.ca
        from epics.pv import _PVcache_

        ctx = epics.ca.current_context()
        context_cache = epics.ca._cache.get(ctx, {}) if ctx is not None else {}

        all_names = list(context_cache.keys())
        all_names.extend(pvid[0] for pvid in _PVcache_ if pvid[0] not in context_cache)

        grouped: dict[str, list[str]] = {wire: [] for wire in self.devices}
        grouped["EDEF"] = []
        grouped["BSA"] = []
        grouped["_unmatched"] = []

        ctrl_map = {
            wire_name: self.devices[wire_name].controls_information.control_name
            for wire_name in self.devices
        }

        for name in all_names:
            if "EDEF" in name:
                grouped["EDEF"].append(name)
            elif "BSA" in name:
                grouped["BSA"].append(name)
            else:
                matched = False
                for wire_name, ctrl in ctrl_map.items():
                    if ctrl in name:
                        grouped[wire_name].append(name)
                        matched = True
                        break
                if not matched:
                    grouped["_unmatched"].append(name)

        return {k: sorted(v) for k, v in grouped.items()}

    def cache_summary(self) -> None:
        """Print a formatted summary of CA cache state."""
        info = self.cache_info()

        lines = [
            "CA Cache Diagnostics",
            f"  Context:        {info['context']}",
            f"  PV objects:     {info['pv_cache_total']}",
            f"  Channel pool:   {info['channel_cache_total']}",
            "  Per device:",
        ]
        for wire, count in sorted(info["per_device"].items()):
            lines.append(f"    {wire:12s}  {count}")

        summary = "\n".join(lines)
        print(summary)
