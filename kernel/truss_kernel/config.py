"""Truss kernel configuration."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TRUSS_", extra="ignore")

    app_name: str = "Truss Kernel"
    version: str = "0.1.0"
    debug: bool = True

    # PostgreSQL (asyncpg driver)
    database_url: str = "postgresql+asyncpg://postgres:admin@127.0.0.1:5432/truss"

    # Auth
    jwt_secret: str = "dev-secret-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24h

    # Plugins: builtin ship inside the kernel; external dir is user-supplied
    builtin_plugins_dir: str = "plugins_builtin"
    external_plugins_dir: str = "../plugins"

    # CORS (comma separated origins)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # AI vault: Fernet key material for encrypting user-supplied API keys at rest
    ai_vault_secret: str = "dev-vault-secret-change-me-in-production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
