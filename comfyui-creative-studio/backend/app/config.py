"""Application configuration loaded from environment variables (prefix ``CS_``).

No absolute user paths are hard-coded: the data directory defaults to ``./data``
relative to the repository root and can be overridden with ``CS_DATA_DIR``.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CS_", env_file=str(REPO_ROOT / ".env"), extra="ignore"
    )

    comfy_url: str = "http://127.0.0.1:8188"
    data_dir: Path = Path("data")
    host: str = "127.0.0.1"
    port: int = 8420
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    poll_interval: float = 1.5
    lost_job_grace: float = 20.0
    # Background job tracker can be disabled (tests drive it manually).
    enable_tracker: bool = True
    # Subfolder of ComfyUI's input directory used for uploaded references.
    comfy_upload_subfolder: str = "creative_studio"
    frontend_dist: Path = Path("frontend/dist")

    def resolve(self, p: Path) -> Path:
        return p if p.is_absolute() else (REPO_ROOT / p)

    @property
    def data_path(self) -> Path:
        return self.resolve(self.data_dir)

    @property
    def media_path(self) -> Path:
        return self.data_path / "media"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_path / 'studio.sqlite3'}"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
