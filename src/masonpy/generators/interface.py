"""Small incremental interface shared by all masonry algorithms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from masonpy.models import Wall

from .events import GenerationEvent


class WallGenerator(ABC):
    """Base class for algorithms that populate a shared :class:`Wall`."""

    name: str

    @abstractmethod
    def generate_incrementally(self, wall: Wall) -> Iterator[GenerationEvent]:
        """Place and yield stones after any valid existing generator prefix."""

    def generate(self, wall: Wall) -> list[GenerationEvent]:
        """Populate ``wall`` by consuming the incremental generator."""

        return list(self.generate_incrementally(wall))
