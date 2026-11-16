"""Configuración central. Todo se lee de variables de entorno con prefijo ``NMC_``.

Ningún secreto tiene un valor por defecto utilizable: la aplicación se niega a
arrancar si ``NMC_SECRET_KEY`` falta o es demasiado corta.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


def read_version() -> str:
    try:
        return (ROOT_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NMC_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # --- Persistencia ---
    database_url: str = "postgresql+psycopg://nmc:nmc@localhost:5432/nmc"
    backup_dir: str = "./backups"

    # --- Seguridad ---
    secret_key: str = ""
    access_token_minutes: int = 720
    admin_username: str = ""
    admin_password: str = ""
    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 20
    max_login_attempts: int = 8
    login_window_seconds: int = 300

    # --- Embeddings ---
    # hashing   : local, sin dependencias ni descargas. Similitud léxica robusta.
    # fastembed : modelo multilingüe local y gratuito (requiere extra local-embeddings).
    # openai    : cualquier API compatible con /v1/embeddings (puede tener costo).
    embedding_provider: Literal["hashing", "fastembed", "openai"] = "hashing"
    embedding_model: str = ""
    embedding_api_base: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""

    # --- Modelo de lenguaje para redactar respuestas (opcional) ---
    llm_provider: Literal["none", "openai"] = "none"
    llm_model: str = ""
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 60.0

    # --- Módulos ---
    enabled_modules: str = "personal,projects,conversations,documents,knowledge,tasks"

    # --- Ingesta ---
    max_content_chars: int = Field(default=500_000, ge=1_000)
    chunk_chars: int = Field(default=1_200, ge=200)
    chunk_overlap: int = Field(default=150, ge=0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def enabled_module_list(self) -> list[str]:
        return [m.strip() for m in self.enabled_modules.split(",") if m.strip()]

    def validate_runtime(self) -> None:
        """Comprueba la configuración mínima segura antes de servir peticiones."""
        if len(self.secret_key) < 32:
            raise RuntimeError(
                "NMC_SECRET_KEY no está definida o tiene menos de 32 caracteres. "
                'Genera una con: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if self.environment == "production" and "*" in self.cors_origin_list:
            raise RuntimeError("NMC_CORS_ORIGINS no puede ser '*' en producción.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
