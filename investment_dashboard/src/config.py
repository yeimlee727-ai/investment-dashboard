from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    base_dir: Path = BASE_DIR
    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite:///db/investment_dashboard.sqlite3"
    )
    dart_api_key: str | None = os.getenv("DART_API_KEY") or None
    app_env: str = os.getenv("APP_ENV", "local")

    @property
    def resolved_database_url(self) -> str:
        if self.database_url.startswith(
            "sqlite:///"
        ) and not self.database_url.startswith("sqlite:////"):
            relative_path = self.database_url.replace("sqlite:///", "", 1)
            return f"sqlite:///{self.base_dir / relative_path}"
        return self.database_url


settings = Settings()
