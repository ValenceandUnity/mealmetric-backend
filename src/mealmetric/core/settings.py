from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    kill_switch_enabled: bool = Field(default=False, alias="KILL_SWITCH_ENABLED")
    rate_limit_rps: float = Field(default=10.0, alias="RATE_LIMIT_RPS")
    max_request_bytes: int = Field(default=1_048_576, alias="MAX_REQUEST_BYTES")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    db_echo: bool = Field(default=False, alias="DB_ECHO")
    db_connect_timeout_seconds: int = Field(default=5, alias="DB_CONNECT_TIMEOUT_SECONDS")
    secret_key: str | None = Field(default=None, alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    auth_failure_alert_threshold: int = Field(default=5, alias="AUTH_FAILURE_ALERT_THRESHOLD")
    auth_failure_alert_window_seconds: int = Field(
        default=300,
        alias="AUTH_FAILURE_ALERT_WINDOW_SECONDS",
    )
    mealmetric_bff_key_primary: str = Field(alias="MEALMETRIC_BFF_KEY_PRIMARY")
    mealmetric_bff_key_secondary: str | None = Field(
        default=None, alias="MEALMETRIC_BFF_KEY_SECONDARY"
    )
    mealmetric_bff_signature_ttl_seconds: int = Field(
        default=300, alias="MEALMETRIC_BFF_SIGNATURE_TTL_SECONDS"
    )
    mealmetric_bff_allow_insecure_legacy_key: bool = Field(
        default=False, alias="MEALMETRIC_BFF_ALLOW_INSECURE_LEGACY_KEY"
    )
    stripe_secret_key: str = Field(alias="STRIPE_SECRET_KEY")
    stripe_success_url: AnyHttpUrl = Field(alias="STRIPE_SUCCESS_URL")
    stripe_cancel_url: AnyHttpUrl = Field(alias="STRIPE_CANCEL_URL")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_api_version: str | None = Field(default=None, alias="STRIPE_API_VERSION")
    stripe_webhooks_enabled: bool = Field(default=False, alias="STRIPE_WEBHOOKS_ENABLED")
    stripe_webhook_mode: Literal["ingest_only", "process"] = Field(
        default="ingest_only",
        alias="STRIPE_WEBHOOK_MODE",
    )

    @model_validator(mode="after")
    def validate_runtime_contract(self) -> "Settings":
        non_dev_envs = {"staging", "production"}
        if self.app_env.lower() in non_dev_envs and not self.secret_key:
            raise ValueError("SECRET_KEY is required when APP_ENV is staging or production.")
        if self.stripe_webhooks_enabled and not self.stripe_webhook_secret:
            raise ValueError(
                "STRIPE_WEBHOOK_SECRET is required when STRIPE_WEBHOOKS_ENABLED is true."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
