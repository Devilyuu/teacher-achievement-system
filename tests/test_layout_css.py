from pathlib import Path
import re

from fastapi.testclient import TestClient


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


def test_lucide_icons_are_initialized_without_deferred_dom_event():
    template = BASE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "lucide.min.js') }}\" defer" not in template
    assert 'if (window.lucide) window.lucide.createIcons();' in template
    assert 'window.addEventListener("DOMContentLoaded"' not in template
    sidebar_end = template.index("</aside>")
    workspace_start = template.index("<main ")
    icon_initialization = template.index(
        "if (window.lucide) window.lucide.createIcons();"
    )
    assert sidebar_end < icon_initialization < workspace_start


def test_new_achievement_page_activates_only_new_entry_navigation(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/achievements/new")

    assert response.status_code == 200
    management_link = re.search(
        r'<a href="/achievements" class="([^"]*)">',
        response.text,
    )
    new_entry_link = re.search(
        r'<a href="/achievements/new" class="([^"]*)">',
        response.text,
    )
    assert management_link is not None
    assert new_entry_link is not None
    assert "active" not in management_link.group(1).split()
    assert "active" in new_entry_link.group(1).split()
