from app.models import Achievement, AchievementStatus, ClaimNature


def _missing_text(value: str | None) -> bool:
    return not value or not value.strip()


def calculate_status(achievement: Achievement) -> str:
    required_text_fields = (
        achievement.category,
        achievement.subcategory,
        achievement.claim_nature,
        achievement.title,
    )
    if any(_missing_text(value) for value in required_text_fields):
        return AchievementStatus.needs_info.value

    if achievement.claimed_score is None or achievement.claimed_score <= 0:
        return AchievementStatus.needs_info.value

    if (
        achievement.claim_nature == ClaimNature.process.value
        and _missing_text(achievement.current_stage)
    ):
        return AchievementStatus.needs_info.value

    if not achievement.materials:
        return AchievementStatus.needs_info.value

    return AchievementStatus.ready.value
