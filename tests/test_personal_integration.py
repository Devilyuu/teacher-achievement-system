import importlib

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


def test_personal_integration_config_has_safe_defaults(monkeypatch):
    for variable in FEISHU_ENVIRONMENT_VARIABLES + AI_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    reloaded = importlib.reload(config)

    try:
        assert reloaded.FEISHU_SYNC_USERNAME == ""
        assert reloaded.FEISHU_APP_ID == ""
        assert reloaded.FEISHU_APP_SECRET == ""
        assert reloaded.FEISHU_BASE_TOKEN == ""
        assert reloaded.FEISHU_TABLE_ID == ""
        assert reloaded.ACHIEVEMENT_AI_API_KEY == ""
        assert reloaded.ACHIEVEMENT_AI_BASE_URL == "https://api.deepseek.com"
        assert reloaded.ACHIEVEMENT_AI_MODEL == "deepseek-chat"
    finally:
        importlib.reload(config)
