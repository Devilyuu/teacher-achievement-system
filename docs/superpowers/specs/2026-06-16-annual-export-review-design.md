# Annual Export Review Design

## Background

Teachers can already generate a personal annual export package from `/exports/{year}/personal`. That route immediately builds and downloads the ZIP package, records the latest export for the year, and marks the year's achievements as `已纳入导出`.

The missing teacher-side step is a confirmation page before generation. Without it, a teacher cannot quickly see whether the selected year still has incomplete achievements or understand that regenerating will replace the latest retained package for that year.

## Goal

Add a teacher-facing annual export review page before generating the package.

The page should answer three questions:

1. Which year am I about to export?
2. How many achievements and support materials will be included?
3. Are there incomplete achievements I should fix before generating?

## Recommended Flow

1. Teacher clicks `导出年度材料` from the achievement list or `生成年度材料` from export history.
2. System opens `/exports/{year}/review`.
3. Teacher reviews yearly counts and incomplete items.
4. Teacher either:
   - goes back to the achievement list to continue fixing items, or
   - clicks `确认生成并下载` to call the existing `/exports/{year}/personal` route.

## Page Content

The review page will show:

- selected year;
- total achievement count;
- count of `可申报` and `已纳入导出` achievements grouped as ready for export;
- count of `待完善` and `草稿` achievements grouped as needing attention;
- total uploaded support material count;
- reminder that final score and level recognition remain subject to offline review;
- reminder that only the latest generated package is retained for each year;
- a list of incomplete achievements with title, category, status, material count, and link to detail;
- action buttons:
  - `返回继续整理` linking to `/achievements?year={year}`;
  - `确认生成并下载` linking to `/exports/{year}/personal`.

## Scope

In scope:

- Add `GET /exports/{year}/review`.
- Add `app/templates/exports/review.html`.
- Route achievement-list and export-history generation links to the review page.
- Cover the route and entry links with tests.

Out of scope:

- Changing generated ZIP contents.
- Changing Excel fields.
- Blocking export when incomplete achievements exist.
- Admin export behavior.
- New database tables or statuses.

## Data Rules

- The review page queries only the current user's achievements for the selected year.
- `可申报` and `已纳入导出` count as ready for export.
- Any other status counts as needing attention.
- Material count is the sum of each achievement's uploaded material count.
- An empty year is allowed and should show counts as zero; the teacher can return to add achievements.

## Testing

Add tests for:

- Authenticated teacher can open `/exports/2026/review` and see the selected year's counts, ready/incomplete counts, material count, offline-review reminder, and links.
- The review page lists only the current user's incomplete achievements.
- Achievement-list export entry points to `/exports/{selected_year}/review`.
- Export-history generation and regeneration links point to `/exports/{year}/review`.

Existing export download tests remain unchanged because `/exports/{year}/personal` continues to generate and download the package.
