"""Local, model-free dashboard compilation and rendering package."""

from .compiler import compile_dashboard
from .schema import (
    ReportDataValidationError,
    validate_dashboard_data,
    validate_report_data,
)

__all__ = [
    "compile_dashboard",
    "validate_dashboard_data",
    "validate_report_data",
    "ReportDataValidationError",
]
