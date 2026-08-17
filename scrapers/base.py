
from __future__ import annotations

from abc import ABC, abstractmethod

from job import Job


class BaseScraper(ABC):

    @abstractmethod
    def buscar_vagas(self) -> list[Job]:
        pass