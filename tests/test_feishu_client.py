import json
import traceback
from types import SimpleNamespace

import httpx
import pytest

from app import config


@pytest.fixture
def feishu_config(monkeypatch):
    snapshot = SimpleNamespace(
        feishu_ready=True,
        feishu_app_id="cli_test_app",
        feishu_app_secret="super-secret-value",
        feishu_base_token="base_test",
        feishu_table_id="table_test",
    )
    monkeypatch.setattr(
        config,
        "get_personal_integration_config",
        lambda: snapshot,
    )
    return snapshot


def token_response():
    return httpx.Response(
        200,
        json={"code": 0, "tenant_access_token": "tenant-test-token", "expire": 7200},
    )


def test_token_request_uses_current_config_and_bounded_timeouts(
    monkeypatch,
    feishu_config,
):
    from app.services.feishu_client import FeishuClient

    requests = []

    def handler(request):
        requests.append(request)
        return token_response()

    client = FeishuClient(transport=httpx.MockTransport(handler))
    feishu_config.feishu_app_id = "changed_app"

    token = client.get_tenant_access_token()

    assert token == "tenant-test-token"
    assert requests[0].method == "POST"
    assert requests[0].url.path == (
        "/open-apis/auth/v3/tenant_access_token/internal"
    )
    assert json.loads(requests[0].content) == {
        "app_id": "changed_app",
        "app_secret": "super-secret-value",
    }
    timeout = requests[0].extensions["timeout"]
    assert all(value is not None and 0 < value <= 10 for value in timeout.values())


def test_search_posts_exact_platform_id_filter_and_returns_one_match(feishu_config):
    from app.services.feishu_client import FeishuClient, FeishuRecord

    search_requests = []

    def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return token_response()
        search_requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "record_id": "rec_one",
                            "fields": {
                                "成果平台ID": "42",
                                "成果名称": "测试成果",
                            },
                        }
                    ]
                },
            },
        )

    client = FeishuClient(transport=httpx.MockTransport(handler))

    result = client.find_record_by_platform_id(42)

    assert result == FeishuRecord(record_id="rec_one", fields={
        "成果平台ID": "42",
        "成果名称": "测试成果",
    })
    request = search_requests[0]
    assert request.method == "POST"
    assert request.url.path == (
        "/open-apis/bitable/v1/apps/base_test/tables/table_test/records/search"
    )
    assert request.url.params["page_size"] == "20"
    assert request.headers["Authorization"] == "Bearer tenant-test-token"
    assert json.loads(request.content) == {
        "filter": {
            "conjunction": "and",
            "conditions": [
                {
                    "field_name": "成果平台ID",
                    "operator": "is",
                    "value": ["42"],
                }
            ],
        }
    }


def test_search_returns_none_when_no_record_matches(feishu_config):
    from app.services.feishu_client import FeishuClient

    def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return token_response()
        return httpx.Response(200, json={"code": 0, "data": {"items": []}})

    client = FeishuClient(transport=httpx.MockTransport(handler))

    assert client.find_record_by_platform_id("missing") is None


def test_duplicate_search_results_raise_conflict_without_record_body(feishu_config):
    from app.services.feishu_client import FeishuClient, FeishuConflictError

    secret_record_value = "do-not-leak-record-body"

    def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return token_response()
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {"record_id": "rec_1", "fields": {"备注": secret_record_value}},
                        {"record_id": "rec_2", "fields": {"备注": secret_record_value}},
                    ]
                },
            },
        )

    client = FeishuClient(transport=httpx.MockTransport(handler))

    with pytest.raises(FeishuConflictError) as caught:
        client.find_record_by_platform_id(42)

    assert "2" in str(caught.value)
    assert secret_record_value not in repr(caught.value)


def test_create_posts_fields_and_returns_typed_record(feishu_config):
    from app.services.feishu_client import FeishuClient, FeishuRecord

    record_requests = []

    def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return token_response()
        record_requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "record": {
                        "record_id": "rec_created",
                        "fields": {"成果名称": "新成果"},
                    }
                },
            },
        )

    client = FeishuClient(transport=httpx.MockTransport(handler))

    result = client.create_record({"成果名称": "新成果"})

    assert result == FeishuRecord(
        record_id="rec_created",
        fields={"成果名称": "新成果"},
    )
    assert record_requests[0].method == "POST"
    assert record_requests[0].url.path.endswith(
        "/apps/base_test/tables/table_test/records"
    )
    assert json.loads(record_requests[0].content) == {
        "fields": {"成果名称": "新成果"}
    }


def test_update_puts_only_supplied_fields_to_record_path(feishu_config):
    from app.services.feishu_client import FeishuClient

    record_requests = []

    def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return token_response()
        record_requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "record": {
                        "record_id": "rec_existing",
                        "fields": {"成果名称": "更新成果"},
                    }
                },
            },
        )

    client = FeishuClient(transport=httpx.MockTransport(handler))

    result = client.update_record("rec_existing", {"成果名称": "更新成果"})

    assert result.record_id == "rec_existing"
    assert record_requests[0].method == "PUT"
    assert record_requests[0].url.path.endswith(
        "/apps/base_test/tables/table_test/records/rec_existing"
    )
    assert json.loads(record_requests[0].content) == {
        "fields": {"成果名称": "更新成果"}
    }


def test_missing_configuration_raises_typed_error_without_secret(monkeypatch):
    from app.services.feishu_client import FeishuClient, FeishuConfigurationError

    snapshot = SimpleNamespace(
        feishu_ready=False,
        feishu_app_id="",
        feishu_app_secret="missing-secret-marker",
        feishu_base_token="",
        feishu_table_id="",
    )
    monkeypatch.setattr(
        config,
        "get_personal_integration_config",
        lambda: snapshot,
    )

    with pytest.raises(FeishuConfigurationError) as caught:
        FeishuClient(transport=httpx.MockTransport(lambda request: token_response())).get_tenant_access_token()

    assert "missing-secret-marker" not in repr(caught.value)


def test_token_api_failure_raises_authentication_error_without_body(feishu_config):
    from app.services.feishu_client import FeishuAuthenticationError, FeishuClient

    body_secret = "secret-from-auth-response"

    def handler(request):
        return httpx.Response(
            200,
            json={"code": 10003, "msg": body_secret},
        )

    with pytest.raises(FeishuAuthenticationError) as caught:
        FeishuClient(transport=httpx.MockTransport(handler)).get_tenant_access_token()

    assert body_secret not in repr(caught.value)
    assert feishu_config.feishu_app_secret not in repr(caught.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, text="full forbidden body must stay private"),
        httpx.Response(
            200,
            json={"code": 1254302, "msg": "permission detail must stay private"},
        ),
    ],
)
def test_http_403_and_permission_code_raise_permission_error(
    feishu_config,
    response,
):
    from app.services.feishu_client import FeishuClient, FeishuPermissionError

    def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return token_response()
        return response

    with pytest.raises(FeishuPermissionError) as caught:
        FeishuClient(transport=httpx.MockTransport(handler)).create_record(
            {"成果名称": "测试"}
        )

    assert "must stay private" not in repr(caught.value)


def test_timeout_raises_network_error_without_request_details(feishu_config):
    from app.services.feishu_client import FeishuClient, FeishuNetworkError

    def handler(request):
        raise httpx.ReadTimeout("private timeout details", request=request)

    with pytest.raises(FeishuNetworkError) as caught:
        FeishuClient(transport=httpx.MockTransport(handler)).get_tenant_access_token()

    assert "private timeout details" not in repr(caught.value)
    assert "private timeout details" not in "".join(
        traceback.format_exception(caught.value)
    )
    assert feishu_config.feishu_base_token not in repr(caught.value)


def test_other_request_failure_raises_network_error(feishu_config):
    from app.services.feishu_client import FeishuClient, FeishuNetworkError

    def handler(request):
        raise httpx.ConnectError("private network details", request=request)

    with pytest.raises(FeishuNetworkError) as caught:
        FeishuClient(transport=httpx.MockTransport(handler)).get_tenant_access_token()

    assert "private network details" not in repr(caught.value)
    assert "private network details" not in "".join(
        traceback.format_exception(caught.value)
    )


def test_malformed_json_raises_response_error_without_full_body(feishu_config):
    from app.services.feishu_client import FeishuClient, FeishuResponseError

    body_secret = "malformed-body-secret"

    def handler(request):
        return httpx.Response(200, text=f"not-json:{body_secret}")

    with pytest.raises(FeishuResponseError) as caught:
        FeishuClient(transport=httpx.MockTransport(handler)).get_tenant_access_token()

    assert body_secret not in repr(caught.value)


def test_malformed_success_shape_raises_response_error(feishu_config):
    from app.services.feishu_client import FeishuClient, FeishuResponseError

    def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return token_response()
        return httpx.Response(200, json={"code": 0, "data": {"items": "not-a-list"}})

    with pytest.raises(FeishuResponseError):
        FeishuClient(
            transport=httpx.MockTransport(handler)
        ).find_record_by_platform_id(42)


def test_injected_httpx_client_is_supported(feishu_config):
    from app.services.feishu_client import FeishuClient

    transport = httpx.MockTransport(lambda request: token_response())
    with httpx.Client(transport=transport) as http_client:
        client = FeishuClient(client=http_client)

        assert client.get_tenant_access_token() == "tenant-test-token"
