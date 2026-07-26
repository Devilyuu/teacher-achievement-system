import importlib
from types import SimpleNamespace

from app import config


FEISHU_ENVIRONMENT_VARIABLES = (
    "FEISHU_SYNC_USERNAME",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_BASE_TOKEN",
    "FEISHU_TABLE_ID",
)
AI_ENVIRONMENT_VARIABLES = (
    "ACHIEVEMENT_AI_API_KEY",
    "ACHIEVEMENT_AI_BASE_URL",
    "ACHIEVEMENT_AI_MODEL",
    "ACHIEVEMENT_AI_TIMEOUT_SECONDS",
)


def test_personal_sync_is_disabled_without_a_configured_username(monkeypatch):
    from app.services.personal_integration import can_use_personal_sync

    monkeypatch.delenv("FEISHU_SYNC_USERNAME", raising=False)

    assert can_use_personal_sync("tcyubin") is False


def test_only_configured_username_can_use_personal_sync(monkeypatch):
    from app.services.personal_integration import can_use_personal_sync

    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "tcyubin")

    assert can_use_personal_sync("tcyubin") is True
    assert can_use_personal_sync("other") is False


def test_feishu_is_ready_only_when_all_server_credentials_exist(monkeypatch):
    from app.services.personal_integration import integration_status

    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "tcyubin")
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "cli_test_secret")
    monkeypatch.setenv("FEISHU_BASE_TOKEN", "base_token")
    monkeypatch.setenv("FEISHU_TABLE_ID", "table_id")

    ready_status = integration_status("tcyubin")

    assert ready_status.user_enabled is True
    assert ready_status.feishu_ready is True

    monkeypatch.delenv("FEISHU_APP_SECRET")

    assert integration_status("tcyubin").feishu_ready is False
    assert "cli_test_secret" not in repr(ready_status)


def test_ai_readiness_reflects_environment_changes_immediately(monkeypatch):
    from app.services.personal_integration import integration_status

    monkeypatch.setenv("ACHIEVEMENT_AI_API_KEY", "test-ai-secret")
    monkeypatch.delenv("ACHIEVEMENT_AI_BASE_URL", raising=False)
    monkeypatch.delenv("ACHIEVEMENT_AI_MODEL", raising=False)

    ready_status = integration_status("any-user")

    assert ready_status.ai_ready is True

    monkeypatch.setenv("ACHIEVEMENT_AI_MODEL", " ")

    assert integration_status("any-user").ai_ready is False
    assert "test-ai-secret" not in repr(ready_status)


def test_personal_integration_service_uses_the_config_snapshot(monkeypatch):
    from app.services.personal_integration import (
        can_use_personal_sync,
        integration_status,
    )

    snapshot = SimpleNamespace(
        allows_username=lambda username: username == "snapshot-user",
        feishu_ready=True,
        ai_ready=False,
    )
    monkeypatch.setattr(
        config,
        "get_personal_integration_config",
        lambda: snapshot,
        raising=False,
    )
    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "environment-user")
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.setenv("ACHIEVEMENT_AI_API_KEY", "environment-ai-key")

    status = integration_status("snapshot-user")

    assert can_use_personal_sync("snapshot-user") is True
    assert status.user_enabled is True
    assert status.feishu_ready is True
    assert status.ai_ready is False


def test_personal_integration_config_snapshot_reads_current_environment(monkeypatch):
    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "first-user")

    first_snapshot = config.get_personal_integration_config()

    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "second-user")

    second_snapshot = config.get_personal_integration_config()

    assert first_snapshot.sync_username == "first-user"
    assert second_snapshot.sync_username == "second-user"


def test_personal_integration_config_snapshot_does_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_SECRET", "feishu-secret-value")
    monkeypatch.setenv("ACHIEVEMENT_AI_API_KEY", "ai-secret-value")

    snapshot = config.get_personal_integration_config()

    assert "feishu-secret-value" not in repr(snapshot)
    assert "ai-secret-value" not in repr(snapshot)


def test_personal_integration_config_has_safe_defaults(monkeypatch):
    try:
        with monkeypatch.context() as integration_environment:
            for variable in FEISHU_ENVIRONMENT_VARIABLES + AI_ENVIRONMENT_VARIABLES:
                integration_environment.delenv(variable, raising=False)

            reloaded = importlib.reload(config)
            snapshot = reloaded.get_personal_integration_config()

            assert snapshot.sync_username == ""
            assert snapshot.feishu_app_id == ""
            assert snapshot.feishu_app_secret == ""
            assert snapshot.feishu_base_token == ""
            assert snapshot.feishu_table_id == ""
            assert snapshot.ai_api_key == ""
            assert snapshot.ai_base_url == "https://api.deepseek.com"
            assert snapshot.ai_model == "deepseek-chat"
            assert snapshot.ai_timeout_seconds == 30
    finally:
        importlib.reload(config)


def test_ai_timeout_is_dynamic_and_bounded(monkeypatch):
    monkeypatch.setenv("ACHIEVEMENT_AI_TIMEOUT_SECONDS", "47.5")
    assert config.get_personal_integration_config().ai_timeout_seconds == 47.5

    monkeypatch.setenv("ACHIEVEMENT_AI_TIMEOUT_SECONDS", "1")
    assert config.get_personal_integration_config().ai_timeout_seconds == 5

    monkeypatch.setenv("ACHIEVEMENT_AI_TIMEOUT_SECONDS", "999")
    assert config.get_personal_integration_config().ai_timeout_seconds == 120

    monkeypatch.setenv("ACHIEVEMENT_AI_TIMEOUT_SECONDS", "not-a-number")
    assert config.get_personal_integration_config().ai_timeout_seconds == 30


def test_config_does_not_cache_personal_integration_environment_values():
    for variable in FEISHU_ENVIRONMENT_VARIABLES + AI_ENVIRONMENT_VARIABLES:
        assert not hasattr(config, variable)
