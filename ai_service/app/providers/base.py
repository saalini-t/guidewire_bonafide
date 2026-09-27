from abc import ABC, abstractmethod
from typing import NamedTuple


class ClassificationOutcome(NamedTuple):
    classification: str
    confidence: float


class LitigationOutcome(NamedTuple):
    signal: str
    confidence: float


class AIProvider(ABC):
    name: str

    @abstractmethod
    def classify_document(self, text: str) -> ClassificationOutcome: ...

    @abstractmethod
    def detect_litigation_signal(self, text: str) -> LitigationOutcome: ...
