"""Storage service for investigation file attachments."""
from __future__ import annotations

from pathlib import Path

from src.config.settings import get_settings


def _storage_root() -> Path:
    return Path(get_settings().storage_root).expanduser().resolve()


def write_attachment(file_id: str, payload: bytes) -> Path:
    root = _storage_root()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{file_id}.csv"
    target.write_bytes(payload)
    return target


def read_attachment(file_id: str) -> Path:
    candidate = _storage_root() / f"{file_id}.csv"
    if not candidate.exists():
        raise FileNotFoundError(file_id)
    return candidate


def remove_attachment(file_id: str) -> None:
    candidate = _storage_root() / f"{file_id}.csv"
    if candidate.exists():
        candidate.unlink()
