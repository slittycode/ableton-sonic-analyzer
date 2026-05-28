"""Unit tests for ``artifact_storage`` — the local/hosted storage seam.

``FilesystemArtifactStorage`` is the only concrete implementation of the
``ArtifactStorage`` Protocol today, but the indirection exists so the hosted
profile can plug in a different backend without touching call sites
(``CLAUDE.md`` Tripwire #6). These tests lock the local-mode contract that
hosted impls must match.
"""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


import artifact_storage  # noqa: E402 — load after sys.path is set


class StoreBytesRoundTripTests(unittest.TestCase):
    """``store_bytes`` → ``resolve_local_path`` → read must be byte-identical."""

    def test_round_trip_preserves_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            payload = b"hello world\x00\x01\x02"
            stored = storage.store_bytes(
                artifact_id="abc123", filename="track.mp3", content=payload,
            )
            self.assertEqual(stored.size_bytes, len(payload))
            self.assertEqual(
                stored.content_sha256, hashlib.sha256(payload).hexdigest(),
            )
            resolved = storage.resolve_local_path(stored.storage_ref)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.read_bytes(), payload)

    def test_filename_suffix_is_preserved_in_destination(self):
        """The destination filename takes the extension from ``filename`` —
        callers downstream rely on the suffix for MIME inference."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            stored = storage.store_bytes(
                artifact_id="r1", filename="audio.flac", content=b"\x00",
            )
            self.assertTrue(stored.storage_ref.endswith(".flac"))

    def test_empty_content_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            stored = storage.store_bytes(
                artifact_id="empty", filename="x.bin", content=b"",
            )
            self.assertEqual(stored.size_bytes, 0)
            self.assertEqual(
                stored.content_sha256, hashlib.sha256(b"").hexdigest(),
            )

    def test_sha256_matches_hashlib(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            payload = bytes(range(256)) * 100
            stored = storage.store_bytes(
                artifact_id="hash", filename="x.bin", content=payload,
            )
            self.assertEqual(
                stored.content_sha256, hashlib.sha256(payload).hexdigest(),
            )


class StoreFileChunkedCopyTests(unittest.TestCase):
    """``store_file`` reads the source in 1 MiB chunks. The streaming hash
    and size must match a one-shot read for files that span multiple chunks."""

    def test_multi_chunk_file_streams_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.wav"
            payload = (b"A" * 1024 + b"B" * 1024) * 2048  # ~4 MiB
            source.write_bytes(payload)

            storage = artifact_storage.FilesystemArtifactStorage(tmp_path / "artifacts")
            stored = storage.store_file(
                artifact_id="big", filename="big.wav", source_path=str(source),
            )
            self.assertEqual(stored.size_bytes, len(payload))
            self.assertEqual(
                stored.content_sha256, hashlib.sha256(payload).hexdigest(),
            )
            resolved = storage.resolve_local_path(stored.storage_ref)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.read_bytes(), payload)

    def test_small_file_below_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "tiny.bin"
            payload = b"x" * 17
            source.write_bytes(payload)

            storage = artifact_storage.FilesystemArtifactStorage(tmp_path / "artifacts")
            stored = storage.store_file(
                artifact_id="t", filename="tiny.bin", source_path=str(source),
            )
            self.assertEqual(stored.size_bytes, 17)
            self.assertEqual(
                stored.content_sha256, hashlib.sha256(payload).hexdigest(),
            )


class DestinationSuffixTests(unittest.TestCase):
    """The suffix fallback chain: ``filename`` suffix → ``source_path`` suffix
    → ``.bin``. The order matters; a regression that flips the chain breaks
    MIME inference for downstream callers."""

    def test_filename_suffix_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.wav"
            source.write_bytes(b"data")
            storage = artifact_storage.FilesystemArtifactStorage(tmp_path / "a")
            stored = storage.store_file(
                artifact_id="r", filename="track.flac", source_path=str(source),
            )
            self.assertTrue(stored.storage_ref.endswith(".flac"))

    def test_falls_back_to_source_path_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "audio.mp3"
            source.write_bytes(b"data")
            storage = artifact_storage.FilesystemArtifactStorage(tmp_path / "a")
            stored = storage.store_file(
                artifact_id="r", filename="noext", source_path=str(source),
            )
            self.assertTrue(stored.storage_ref.endswith(".mp3"))

    def test_falls_back_to_dot_bin_when_no_suffix_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "noext"
            source.write_bytes(b"data")
            storage = artifact_storage.FilesystemArtifactStorage(tmp_path / "a")
            stored = storage.store_file(
                artifact_id="r", filename="noext", source_path=str(source),
            )
            self.assertTrue(stored.storage_ref.endswith(".bin"))


class DeleteTests(unittest.TestCase):
    def test_delete_removes_stored_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            stored = storage.store_bytes(
                artifact_id="d", filename="x.bin", content=b"bye",
            )
            resolved = storage.resolve_local_path(stored.storage_ref)
            self.assertTrue(resolved.exists())
            storage.delete(stored.storage_ref)
            self.assertFalse(resolved.exists())

    def test_delete_is_idempotent_for_same_ref(self):
        """Deleting the same storage_ref twice must not raise. The second call
        finds the file already gone — the local impl swallows the missing-file
        case via ``unlink(missing_ok=True)``, but the Protocol contract is the
        no-raise behavior, not the specific implementation."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            stored = storage.store_bytes(
                artifact_id="d", filename="x.bin", content=b"x",
            )
            storage.delete(stored.storage_ref)
            storage.delete(stored.storage_ref)  # must not raise

    def test_delete_missing_ref_is_safe(self):
        """Deleting a ref that never existed must not raise — protects against
        races where a caller deletes a ref that another caller already cleaned up."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            storage.delete(str(Path(tmp) / "nonexistent.bin"))

    def test_delete_empty_ref_is_safe(self):
        """Empty string is the canonical 'no artifact' value — must not raise."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            storage.delete("")


class ResolveLocalPathTests(unittest.TestCase):
    def test_resolve_empty_ref_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            self.assertIsNone(storage.resolve_local_path(""))

    def test_resolve_returns_path_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = artifact_storage.FilesystemArtifactStorage(Path(tmp))
            stored = storage.store_bytes(
                artifact_id="r", filename="x.bin", content=b"x",
            )
            resolved = storage.resolve_local_path(stored.storage_ref)
            self.assertIsInstance(resolved, Path)


class ArtifactsDirCreationTests(unittest.TestCase):
    def test_artifacts_dir_is_created_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "deep" / "nested" / "artifacts"
            self.assertFalse(target.exists())
            artifact_storage.FilesystemArtifactStorage(target)
            self.assertTrue(target.is_dir())


class StoredArtifactDataclassTests(unittest.TestCase):
    def test_stored_artifact_is_frozen(self):
        artifact = artifact_storage.StoredArtifact(
            storage_ref="/tmp/x.bin", size_bytes=10, content_sha256="deadbeef",
        )
        with self.assertRaises(Exception):
            artifact.size_bytes = 99  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
