"""Storage service for investigation file attachments."""
from __future__ import annotations

from pathlib import Path

from src.config.settings import get_settings


def _storage_root() -> Path:
    return Path(get_settings().storage_root).expanduser().resolve()


def _candidate_paths(file_id: str) -> list[Path]:
    root = _storage_root()
    candidates = [root / file_id, Path.cwd() / file_id]
    try:
        repo_root = Path(__file__).resolve().parents[2]
        candidates.insert(0, repo_root / file_id)
    except Exception:  # noqa: BLE001
        pass
    uniq: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:  # noqa: BLE001
            resolved = candidate
        if resolved not in seen:
            seen.add(resolved)
            uniq.append(candidate)
    return uniq


def write_attachment(file_id: str, payload: bytes) -> Path:
    for candidate in _candidate_paths(file_id):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            continue
        try:
            candidate.write_bytes(payload)
            return candidate
        except Exception:  # noqa: BLE001
            continue
    target = _storage_root() / file_id
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def read_attachment(file_id: str) -> Path:
    for candidate in _candidate_paths(file_id):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(file_id)


def remove_attachment(file_id: str) -> None:
    for candidate in _candidate_paths(file_id):
        if candidate.exists():
            candidate.unlink()
