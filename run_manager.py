"""Manage run-level identifiers and metadata."""

from __future__ import annotations

import uuid
from datetime import datetime


def create_run_id() -> str:
    """
    Generate a unique run ID combining timestamp and UUID.
    
    Format: run_YYYYMMDD_HHMMSS_XXXXXX
    where XXXXXX is first 6 chars of UUID hex.
    
    Returns:
        str: A unique run identifier.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_suffix = uuid.uuid4().hex[:6]
    return f"run_{timestamp}_{unique_suffix}"
