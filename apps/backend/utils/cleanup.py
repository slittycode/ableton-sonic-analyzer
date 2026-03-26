import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_ARTIFACT_CLEANUP_MAX = 100

logger = logging.getLogger(__name__)


def _current_time() -> datetime:
    return datetime.now()


def _resolve_cleanup_max() -> int:
    raw_value = os.getenv("ARTIFACT_CLEANUP_MAX", str(DEFAULT_ARTIFACT_CLEANUP_MAX)).strip()
    try:
        limit = int(raw_value)
    except ValueError:
        logger.warning(
            "[artifact-cleanup] Invalid ARTIFACT_CLEANUP_MAX=%r. Falling back to %s.",
            raw_value,
            DEFAULT_ARTIFACT_CLEANUP_MAX,
        )
        return DEFAULT_ARTIFACT_CLEANUP_MAX
    if limit < 0:
        logger.warning(
            "[artifact-cleanup] Negative ARTIFACT_CLEANUP_MAX=%s is invalid. Falling back to %s.",
            limit,
            DEFAULT_ARTIFACT_CLEANUP_MAX,
        )
        return DEFAULT_ARTIFACT_CLEANUP_MAX
    return limit


def _is_exempt(path: Path, artifacts_dir: Path) -> bool:
    if path.name.endswith(".keep"):
        return True
    relative_parts = path.relative_to(artifacts_dir).parts
    return "preserved" in relative_parts


def cleanup_artifacts(runtime_dir: str | Path, ttl_hours: float = 24) -> None:
    artifacts_dir = Path(runtime_dir) / "artifacts"
    if not artifacts_dir.is_dir():
        logger.info("[artifact-cleanup] Artifacts directory does not exist: %s", artifacts_dir)
        return

    cutoff = _current_time() - timedelta(hours=ttl_hours)
    expired_candidates: list[Path] = []

    for path in artifacts_dir.rglob("*"):
        if not path.is_file() or _is_exempt(path, artifacts_dir):
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        if modified_at >= cutoff:
            continue
        expired_candidates.append(path)

    for path in expired_candidates:
        logger.info("[artifact-cleanup] Would delete expired artifact: %s", path)

    max_deletions = _resolve_cleanup_max()
    if len(expired_candidates) > max_deletions:
        logger.warning(
            "[artifact-cleanup] Found %s expired artifacts but ARTIFACT_CLEANUP_MAX=%s; aborting cleanup. "
            "Raise ARTIFACT_CLEANUP_MAX to confirm a larger cleanup run.",
            len(expired_candidates),
            max_deletions,
        )
        return

    for path in expired_candidates:
        try:
            path.unlink()
            logger.info("[artifact-cleanup] Deleted expired artifact: %s", path)
        except FileNotFoundError:
            logger.warning("[artifact-cleanup] Artifact disappeared before deletion: %s", path)
        except OSError as exc:
            logger.warning(
                "[artifact-cleanup] Failed to delete expired artifact %s: %s",
                path,
                exc,
            )
