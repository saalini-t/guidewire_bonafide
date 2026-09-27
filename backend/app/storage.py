"""StorageBackend abstraction for document bytes (docs/ARCHITECTURE.md
Document Storage). PostgreSQL stores only metadata + extracted text —
never document bytes. LocalStorageBackend is the only implementation for
the MVP; swapping in S3/Azure/GCS later means adding one class here, no
caller changes.
"""
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import settings


class StorageBackend(ABC):
    @abstractmethod
    def save(self, claim_id: str, filename: str, content: bytes) -> str:
        """Persist bytes, return an opaque storage path/URI."""

    @abstractmethod
    def load(self, storage_path: str) -> bytes:
        """Retrieve previously saved bytes by their storage path/URI."""


class LocalStorageBackend(StorageBackend):
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, claim_id: str, filename: str, content: bytes) -> str:
        claim_dir = self.root / claim_id
        claim_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        (claim_dir / unique_name).write_bytes(content)
        return f"{claim_id}/{unique_name}"

    def load(self, storage_path: str) -> bytes:
        return (self.root / storage_path).read_bytes()


_STORAGE_ROOT = (Path(__file__).resolve().parent.parent / settings.document_storage_path).resolve()
storage_backend: StorageBackend = LocalStorageBackend(_STORAGE_ROOT)
