"""Optional privacy-preserving local CV collector."""

from .asset import ASSET_NAME, ASSET_SHA256, verify_asset
from .features import FrameObservation, WindowQualityError, aggregate_window, window_diagnostics

__all__ = [
    "ASSET_NAME", "ASSET_SHA256", "FrameObservation", "WindowQualityError",
    "aggregate_window", "verify_asset", "window_diagnostics",
]
