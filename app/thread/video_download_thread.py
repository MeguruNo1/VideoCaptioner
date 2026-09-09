"""Backward-compatible import path for the shared download service and Qt adapters."""
import sys
from app.core import download_service

sys.modules[__name__] = download_service
