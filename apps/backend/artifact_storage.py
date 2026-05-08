from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredArtifact:
    storage_ref: str
    size_bytes: int
    content_sha256: str


class ArtifactStorage(Protocol):
    def store_bytes(
        self,
        *,
        artifact_id: str,
        filename: str,
        content: bytes,
    ) -> StoredArtifact: ...

    def store_file(
        self,
        *,
        artifact_id: str,
        filename: str,
        source_path: str,
    ) -> StoredArtifact: ...

    def delete(self, storage_ref: str) -> None: ...

    def resolve_local_path(self, storage_ref: str) -> Path | None: ...


class FilesystemArtifactStorage:
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def store_bytes(
        self,
        *,
        artifact_id: str,
        filename: str,
        content: bytes,
    ) -> StoredArtifact:
        destination = self._destination_for(artifact_id, filename)
        destination.write_bytes(content)
        return StoredArtifact(
            storage_ref=str(destination),
            size_bytes=len(content),
            content_sha256=hashlib.sha256(content).hexdigest(),
        )

    def store_file(
        self,
        *,
        artifact_id: str,
        filename: str,
        source_path: str,
    ) -> StoredArtifact:
        source = Path(source_path)
        destination = self._destination_for(artifact_id, filename, source_path=source_path)
        digest = hashlib.sha256()
        size_bytes = 0
        with source.open("rb") as src, destination.open("wb") as dest:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dest.write(chunk)
                digest.update(chunk)
                size_bytes += len(chunk)
        return StoredArtifact(
            storage_ref=str(destination),
            size_bytes=size_bytes,
            content_sha256=digest.hexdigest(),
        )

    def delete(self, storage_ref: str) -> None:
        if not storage_ref:
            return
        try:
            Path(storage_ref).unlink(missing_ok=True)
        except OSError:
            pass

    def resolve_local_path(self, storage_ref: str) -> Path | None:
        if not storage_ref:
            return None
        return Path(storage_ref)

    def _destination_for(
        self,
        artifact_id: str,
        filename: str,
        *,
        source_path: str | None = None,
    ) -> Path:
        suffix = (
            Path(filename).suffix
            or (Path(source_path).suffix if source_path else "")
            or ".bin"
        )
        return self.artifacts_dir / f"{artifact_id}{suffix}"
