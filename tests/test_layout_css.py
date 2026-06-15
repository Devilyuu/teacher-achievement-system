from pathlib import Path


CSS_PATH = Path(__file__).resolve().parents[1] / "app" / "static" / "app.css"
BASE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "templates" / "base.html"
)


def test_dashboard_panels_fill_grid_and_achievement_form_uses_page_width():
    css = CSS_PATH.read_text(encoding="utf-8")

    assert (
        ".dashboard-grid > .panel { width: 100%; height: 100%; margin: 0; }"
        in css
    )
    assert "align-items: stretch;" in css
    assert (
        ".category-panel { display: flex; flex-direction: column;" in css
    )
    assert ".category-panel .audit-note { margin-top: auto; }" in css
    assert ".achievement-form { max-width: 1240px;" in css
    assert (
        ".detail-layout, .dashboard-grid { grid-template-columns: minmax(0, 1fr); }"
        in css
    )
    assert ".dashboard-grid > .panel { min-width: 0;" in css


def test_base_template_versions_application_stylesheet():
    template = BASE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "url_for('static', path='app.css') }}?v=" in template
