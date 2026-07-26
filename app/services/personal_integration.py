import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PersonalIntegrationStatus:
    user_enabled: bool
    feishu_ready: bool
    ai_ready: bool


def _environment_value(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def can_use_personal_sync(username: str) -> bool:
    configured_username = _environment_value("FEISHU_SYNC_USERNAME")
    return bool(configured_username) and username == configured_username


def integration_status(username: str) -> PersonalIntegrationStatus:
    feishu_ready = all(
        _environment_value(name)
        for name in (
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "FEISHU_BASE_TOKEN",
            "FEISHU_TABLE_ID",
        )
    )
    ai_ready = all(
        (
            _environment_value("ACHIEVEMENT_AI_API_KEY"),
            _environment_value(
                "ACHIEVEMENT_AI_BASE_URL",
                "https://api.deepseek.com",
            ),
            _environment_value("ACHIEVEMENT_AI_MODEL", "deepseek-chat"),
        )
    )
    return PersonalIntegrationStatus(
        user_enabled=can_use_personal_sync(username),
        feishu_ready=feishu_ready,
        ai_ready=ai_ready,
    )
