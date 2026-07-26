from dataclasses import dataclass

from app import config


@dataclass(frozen=True)
class PersonalIntegrationStatus:
    user_enabled: bool
    feishu_ready: bool
    ai_ready: bool


def can_use_personal_sync(username: str) -> bool:
    integration_config = config.get_personal_integration_config()
    return integration_config.allows_username(username)


def integration_status(username: str) -> PersonalIntegrationStatus:
    integration_config = config.get_personal_integration_config()
    return PersonalIntegrationStatus(
        user_enabled=integration_config.allows_username(username),
        feishu_ready=integration_config.feishu_ready,
        ai_ready=integration_config.ai_ready,
    )
