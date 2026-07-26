# Material Upload Status Feedback Design

## Background

Teachers can upload support materials from an achievement detail page. After upload, the page currently confirms only the number of uploaded files. That proves the upload worked, but it does not tell the teacher whether the achievement has now reached the basic application-ready state.

## Goal

After a successful material upload, show a clearer teacher-side result message on the achievement detail page:

- If the upload makes or leaves the achievement status as `可申报`, tell the teacher that the achievement now meets the basic application conditions.
- If the achievement is still `待完善`, keep the upload confirmation simple and let the existing readiness hints explain what is still missing.
- Keep the wording clear that final recognition remains subject to offline review.

## Scope

In scope:

- Update the teacher achievement detail page upload success message.
- Cover the behavior with a material upload test.
- Reuse the existing `Achievement.status` value calculated after upload.

Out of scope:

- New database fields.
- New workflow statuses.
- Admin-side review features.
- Any automatic score or level recognition.

## Display Rules

When the detail page is opened with an `uploaded` query parameter:

1. If `achievement.status == "可申报"`, show:
   `已上传 X 份材料，当前成果已满足基础申报条件。最终认定仍以线下审核为准。`
2. Otherwise, show the existing upload count confirmation:
   `已上传 X 份材料。`

Failed upload, rename, replace, and material-list behavior stays unchanged.

## Testing

Add a regression assertion to the existing owned-achievement upload test:

- Upload a material to a complete process achievement.
- Confirm the redirect still includes `uploaded=1`.
- Follow the redirected detail page.
- Confirm the page displays both:
  - `当前成果已满足基础申报条件`
  - `最终认定仍以线下审核为准`

This verifies the real teacher workflow: upload material, return to detail, read the next-step status.
