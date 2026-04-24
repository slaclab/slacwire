"""Top-level package exports for slacwire.

Imports are intentionally lazy so users can access lightweight modules
(``registry``) without requiring full runtime dependencies used by the
GUI/controller stack.
"""

from importlib import import_module

__all__ = [
	"WireScanSuite",
	"WireScanView",
	"RunRegistry",
	"RegistrySQLiteSummary",
	"convert_run_registry_json_to_sqlite",
	"RunRegistryKPIReporter",
]


def __getattr__(name):
	if name == "WireScanSuite":
		return import_module("slacwire.suite").WireScanSuite
	if name == "WireScanView":
		return import_module("slacwire.view").WireScanView
	if name == "RunRegistry":
		return import_module("slacwire.registry").RunRegistry
	if name == "RegistrySQLiteSummary":
		return import_module("slacwire.registry_sqlite").RegistrySQLiteSummary
	if name == "convert_run_registry_json_to_sqlite":
		return import_module("slacwire.registry_sqlite").convert_run_registry_json_to_sqlite
	if name == "RunRegistryKPIReporter":
		return import_module("slacwire.kpi_queries").RunRegistryKPIReporter
	raise AttributeError(f"module 'slacwire' has no attribute {name!r}")
