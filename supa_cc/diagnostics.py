"""Stable public facade for diagnostic collection and rendering."""

from .diagnostic_collectors import (
    DiagnosticService,
    DoctorReport,
)


__all__ = ["DiagnosticService", "DoctorReport"]
