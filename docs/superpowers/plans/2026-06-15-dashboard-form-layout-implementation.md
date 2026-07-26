# Dashboard And Form Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the annual dashboard columns and make the achievement form use the same content width as other application pages.

**Architecture:** Keep the existing templates and responsive breakpoints. Apply narrowly scoped CSS overrides and protect them with a static regression test, then verify real geometry in the browser.

**Tech Stack:** FastAPI, Jinja2, CSS, pytest, in-app browser

---

### Task 1: Add layout regression coverage

**Files:**
- Create: `tests/test_layout_css.py`

- [ ] Add a test that reads `app/static/app.css` and verifies the dashboard panels fill their grid cells, the category panel uses flex layout, and the achievement form uses `1240px`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_layout_css.py -q` and confirm it fails before the CSS changes.

### Task 2: Correct dashboard and form sizing

**Files:**
- Modify: `app/static/app.css`
- Modify: `app/templates/base.html`

- [ ] Set dashboard child panels to full width, zero auto margin, and stretched height.
- [ ] Set `.category-panel` to a vertical flex layout and `.audit-note` to `margin-top: auto`.
- [ ] Change `.achievement-form` maximum width to `1240px`.
- [ ] Constrain the responsive dashboard grid with `minmax(0, 1fr)` and add a stylesheet version parameter.
- [ ] Run the focused test and the full pytest suite.

### Task 3: Verify responsive geometry

- [ ] Restart or reload the local server.
- [ ] Measure dashboard panel alignment at `1440x900`.
- [ ] Measure the achievement form against the page header at `1440x900`.
- [ ] Verify both pages at `390x844` have no page-level horizontal overflow.
