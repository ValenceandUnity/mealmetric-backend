import pytest
from pydantic import ValidationError

from mealmetric.core.settings import get_settings


def test_production_requires_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("MEALMETRIC_BFF_KEY_PRIMARY", "test-bff-key")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_SUCCESS_URL", "https://example.com/success")
    monkeypatch.setenv("STRIPE_CANCEL_URL", "https://example.com/cancel")
    get_settings.cache_clear()

    with pytest.raises(ValidationError, match="SECRET_KEY is required"):
        get_settings()
    get_settings.cache_clear()


def test_development_can_omit_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.setenv("MEALMETRIC_BFF_KEY_PRIMARY", "test-bff-key")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_SUCCESS_URL", "https://example.com/success")
    monkeypatch.setenv("STRIPE_CANCEL_URL", "https://example.com/cancel")
    get_settings.cache_clear()

    settings = get_settings()

    assert not settings.secret_key
    get_settings.cache_clear()


def test_webhooks_enabled_requires_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret")
    monkeypatch.setenv("MEALMETRIC_BFF_KEY_PRIMARY", "test-bff-key")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_123")
    monkeypatch.setenv("STRIPE_SUCCESS_URL", "https://example.com/success")
    monkeypatch.setenv("STRIPE_CANCEL_URL", "https://example.com/cancel")
    monkeypatch.setenv("STRIPE_WEBHOOKS_ENABLED", "true")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "")
    get_settings.cache_clear()

    with pytest.raises(ValidationError, match="STRIPE_WEBHOOK_SECRET is required"):
        get_settings()
    get_settings.cache_clear()
