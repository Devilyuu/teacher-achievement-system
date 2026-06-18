from datetime import datetime


def current_reporting_year() -> int:
    return datetime.now().year


def default_reporting_year() -> int:
    return current_reporting_year() - 1


def available_reporting_years(
    existing_years: list[int] | tuple[int, ...],
    selected_year: int | None = None,
) -> list[int]:
    years = {
        current_reporting_year(),
        default_reporting_year(),
        *existing_years,
    }
    if selected_year is not None:
        years.add(selected_year)
    return sorted(years, reverse=True)
