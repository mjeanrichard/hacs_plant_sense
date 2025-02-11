"""Custom types for PlantSense."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import PlantSenseCoordinator


@dataclass
class PlantSenseData:
    coordinator: PlantSenseCoordinator
