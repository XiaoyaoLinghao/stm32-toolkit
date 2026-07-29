from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4


def canonical_project_root(path: Path) -> Path:
    """Return the existing project root with links and path aliases resolved."""
    return path.expanduser().resolve(strict=True)


def compute_workspace_id(logical_project_id: UUID, project_root: Path) -> str:
    """Derive a stable workspace identifier for one logical project clone."""
    canonical = str(canonical_project_root(project_root)).replace("\\", "/").casefold()
    value = f"{logical_project_id}\0{canonical}".encode("utf-8")
    return sha256(value).hexdigest()[:24]


def new_session_id() -> str:
    """Create a collision-resistant, filesystem-safe default session identifier."""
    return uuid4().hex
