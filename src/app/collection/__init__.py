"""Read-only configuration collection from lab devices."""

from .collector import LabTarget, NetmikoCollector

__all__ = ["LabTarget", "NetmikoCollector"]