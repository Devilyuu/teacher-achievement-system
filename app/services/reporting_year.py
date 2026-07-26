from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Achievement, UserReportingYear


MIN_REPORTING_YEAR = 2000
MAX_REPORTING_YEAR = 2100


class ReportingYearError(ValueError):
    pass


class InvalidReportingYearError(ReportingYearError):
    pass


class ReportingYearInUseError(ReportingYearError):
    pass


class ReportingYearProtectedError(ReportingYearError):
    pass


@dataclass(frozen=True)
class ReportingYearItem:
    year: int
    is_default: bool
    achievement_count: int
    can_remove: bool


def current_reporting_year() -> int:
    return datetime.now().year


def default_reporting_year() -> int:
    """Return the system fallback used outside a signed-in user context."""
    return current_reporting_year()


def validate_reporting_year(year: int) -> int:
    if year < MIN_REPORTING_YEAR or year > MAX_REPORTING_YEAR:
        raise InvalidReportingYearError(
            f"Reporting year must be between {MIN_REPORTING_YEAR} and "
            f"{MAX_REPORTING_YEAR}."
        )
    return year


def available_reporting_years(
    existing_years: list[int] | tuple[int, ...],
    selected_year: int | None = None,
    preference_years: list[int] | tuple[int, ...] = (),
) -> list[int]:
    years = {
        current_reporting_year(),
        *existing_years,
        *preference_years,
    }
    if selected_year is not None:
        years.add(validate_reporting_year(selected_year))
    return sorted(years, reverse=True)


def get_user_default_year(db: Session, user_id: int) -> int:
    record = (
        db.query(UserReportingYear)
        .filter(
            UserReportingYear.user_id == user_id,
            UserReportingYear.is_default.is_(True),
        )
        .order_by(UserReportingYear.updated_at.desc(), UserReportingYear.id.desc())
        .first()
    )
    return record.year if record else current_reporting_year()


def get_user_reporting_years(
    db: Session,
    user_id: int,
    selected_year: int | None = None,
) -> list[int]:
    preference_years = [
        row[0]
        for row in (
            db.query(UserReportingYear.year)
            .filter(UserReportingYear.user_id == user_id)
            .all()
        )
    ]
    achievement_years = [
        row[0]
        for row in (
            db.query(Achievement.year)
            .filter(Achievement.user_id == user_id)
            .distinct()
            .all()
        )
    ]
    return available_reporting_years(
        achievement_years,
        selected_year,
        preference_years,
    )


def get_user_reporting_year_items(
    db: Session,
    user_id: int,
    selected_year: int | None = None,
) -> list[ReportingYearItem]:
    default_year = get_user_default_year(db, user_id)
    counts = dict(
        db.query(Achievement.year, func.count(Achievement.id))
        .filter(Achievement.user_id == user_id)
        .group_by(Achievement.year)
        .all()
    )
    return [
        ReportingYearItem(
            year=year,
            is_default=year == default_year,
            achievement_count=counts.get(year, 0),
            can_remove=(
                year != current_reporting_year()
                and counts.get(year, 0) == 0
            ),
        )
        for year in get_user_reporting_years(db, user_id, selected_year)
    ]


def add_user_reporting_year(
    db: Session,
    user_id: int,
    year: int,
) -> UserReportingYear:
    validate_reporting_year(year)
    record = (
        db.query(UserReportingYear)
        .filter_by(user_id=user_id, year=year)
        .one_or_none()
    )
    if record is None:
        record = UserReportingYear(user_id=user_id, year=year)
        db.add(record)
        try:
            db.commit()
            db.refresh(record)
        except IntegrityError:
            db.rollback()
            record = (
                db.query(UserReportingYear)
                .filter_by(user_id=user_id, year=year)
                .one()
            )
    return record


def set_user_default_year(
    db: Session,
    user_id: int,
    year: int,
) -> UserReportingYear:
    validate_reporting_year(year)
    record = add_user_reporting_year(db, user_id, year)
    (
        db.query(UserReportingYear)
        .filter(
            UserReportingYear.user_id == user_id,
            UserReportingYear.id != record.id,
        )
        .update(
            {UserReportingYear.is_default: False},
            synchronize_session=False,
        )
    )
    record.is_default = True
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return record


def remove_user_reporting_year(
    db: Session,
    user_id: int,
    year: int,
) -> None:
    validate_reporting_year(year)
    if year == current_reporting_year():
        raise ReportingYearProtectedError(
            "The current natural year is always available."
        )
    achievement_count = (
        db.query(func.count(Achievement.id))
        .filter(Achievement.user_id == user_id, Achievement.year == year)
        .scalar()
        or 0
    )
    if achievement_count:
        raise ReportingYearInUseError(
            "A reporting year containing achievements cannot be removed."
        )

    record = (
        db.query(UserReportingYear)
        .filter_by(user_id=user_id, year=year)
        .one_or_none()
    )
    if record is not None:
        db.delete(record)
        db.commit()
