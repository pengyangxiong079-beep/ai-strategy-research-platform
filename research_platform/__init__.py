"""Structured data acquisition and coverage pipeline for strategic research."""

from .pipeline import (
    data_files,
    import_local_observations,
    initialize_data_pipeline,
    load_data_coverage,
    process_acquisition_response,
    run_sufficiency_check,
)

__all__ = [
    "data_files",
    "import_local_observations",
    "initialize_data_pipeline",
    "load_data_coverage",
    "process_acquisition_response",
    "run_sufficiency_check",
]
