# Export Confirms Annual Submission Design

## Background

The teacher workflow now supports:

- filling yearly achievements;
- uploading support materials;
- confirming that yearly materials are organized from the dashboard;
- reviewing the year before export;
- generating and downloading the annual export package.

However, a teacher can generate the yearly package without first clicking the dashboard confirmation button. In that case, the teacher has effectively completed the yearly submission workflow, but the computed annual status may still show `整理中` because no annual submission record exists.

## Goal

When a teacher generates a personal annual export package, the system should also record or refresh that year's annual submission confirmation. After the export completes, the annual state should be `已导出`.

## User-Facing Behavior

- The export review page primary button should read `确认整理并下载`.
- Clicking it still downloads the ZIP from the existing `/exports/{year}/personal` route.
- The export action should create or refresh the annual submission record before writing the export record.
- Teachers who already confirmed from the dashboard should keep the same behavior; export refreshes the final exported state.

## Scope

In scope:

- Update export generation so it confirms the teacher's annual submission for that year.
- Update the export review page button copy.
- Add regression tests for exporting without prior dashboard confirmation.

Out of scope:

- New database fields.
- New routes.
- Changing ZIP or Excel contents.
- Admin-side workflow changes.
- Blocking export when achievements are incomplete.

## Data Rule

`generate_personal_export(db, user, year)` should ensure there is an `AnnualSubmission` record for `user_id + year` before creating the export record. Because export generation happens after that confirmation, `get_annual_submission_state()` can evaluate the latest export as `已导出`.

## Testing

Add tests that:

- Generate a personal export for a user who has not previously confirmed the year.
- Assert an annual submission record is created.
- Assert `get_annual_submission_state()` returns `已导出`.
- Assert the export review page primary action text is `确认整理并下载` and still links to `/exports/{year}/personal`.
