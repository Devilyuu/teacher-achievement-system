from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NGINX_DIR = REPO_ROOT / "deploy" / "nginx"


def test_upload_route_streams_requests_and_limits_abuse():
    config = (NGINX_DIR / "chengguo.youpulab.com.conf").read_text(encoding="utf-8")
    upload_location = config.split("location = /materials/upload {", 1)[1].split("}", 1)[0]

    assert "proxy_request_buffering off;" in upload_location
    assert "limit_conn chengguo_upload_conn 2;" in upload_location
    assert "limit_req zone=chengguo_upload_rate" in upload_location
    assert "limit_conn_status 429;" in upload_location
    assert "limit_req_status 429;" in upload_location


def test_upload_limit_zones_are_declared_in_http_context_include():
    config = (NGINX_DIR / "chengguo-upload-limits.conf").read_text(encoding="utf-8")

    assert "limit_conn_zone $binary_remote_addr zone=chengguo_upload_conn:" in config
    assert "limit_req_zone $binary_remote_addr zone=chengguo_upload_rate:" in config


def test_default_http_server_redirects_teacher_routes_but_preserves_design_app():
    config = (NGINX_DIR / "default-server.conf").read_text(encoding="utf-8")

    assert "listen 80 default_server;" in config
    assert "location /design/" in config
    catch_all = config.split("location / {", 1)[1].split("}", 1)[0]
    assert "return 301 https://chengguo.youpulab.com$request_uri;" in catch_all
    assert "proxy_pass http://127.0.0.1:8001;" not in config
