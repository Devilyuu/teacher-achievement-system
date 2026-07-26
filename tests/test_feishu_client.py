from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
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


def test_consecutive_record_operations_reuse_one_token_request(feishu_config):
    from app.services.feishu_client import FeishuClient

    token_requests = 0

    def handler(request):
        nonlocal token_requests
        if request.url.path.endswith("/tenant_access_token/internal"):
            token_requests += 1
            return token_response()
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "record": {
                        "record_id": "rec_cached",
                        "fields": {},
                    }
                },
            },
        )

    client = FeishuClient(transport=httpx.MockTransport(handler))

    client.create_record({"成果名称": "首次写入"})
    client.update_record("rec_cached", {"成果名称": "再次写入"})

    assert token_requests == 1


def test_token_refreshes_before_feishu_expiration(monkeypatch, feishu_config):
    from app.services import feishu_client

    current_time = [0.0]
    token_requests = 0
    monkeypatch.setattr(
        feishu_client,
        "monotonic",
        lambda: current_time[0],
        raising=False,
    )

    def handler(request):
        nonlocal token_requests
        token_requests += 1
        return httpx.Response(
            200,
            json={
                "code": 0,
                "tenant_access_token": f"tenant-token-{token_requests}",
                "expire": 100,
            },
        )

    client = feishu_client.FeishuClient(transport=httpx.MockTransport(handler))

    assert client.get_tenant_access_token() == "tenant-token-1"
    current_time[0] = 89
    assert client.get_tenant_access_token() == "tenant-token-1"
    current_time[0] = 91
    assert client.get_tenant_access_token() == "tenant-token-2"
    assert token_requests == 2


def test_token_cache_refreshes_when_app_id_or_secret_changes(feishu_config):
    from app.services.feishu_client import FeishuClient

    token_request_bodies = []

    def handler(request):
        token_request_bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "code": 0,
                "tenant_access_token": f"tenant-token-{len(token_request_bodies)}",
                "expire": 7200,
            },
        )

    client = FeishuClient(transport=httpx.MockTransport(handler))

    assert client.get_tenant_access_token() == "tenant-token-1"
    feishu_config.feishu_app_id = "changed-app-id"
    assert client.get_tenant_access_token() == "tenant-token-2"
    feishu_config.feishu_app_secret = "changed-secret-value"
    assert client.get_tenant_access_token() == "tenant-token-3"

    assert [body["app_id"] for body in token_request_bodies] == [
        "cli_test_app",
        "changed-app-id",
        "changed-app-id",
    ]
    cache_state = repr(client.__dict__)
    assert "super-secret-value" not in cache_state
    assert "changed-secret-value" not in cache_state


def test_concurrent_token_requests_share_one_authentication(feishu_config):
    from app.services.feishu_client import FeishuClient

    worker_count = 8
    start_barrier = threading.Barrier(worker_count)
    count_lock = threading.Lock()
    token_requests = 0

    def handler(request):
        nonlocal token_requests
        with count_lock:
            token_requests += 1
        time.sleep(0.05)
        return token_response()

    client = FeishuClient(transport=httpx.MockTransport(handler))

    def load_token():
        start_barrier.wait()
        return client.get_tenant_access_token()

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        tokens = list(executor.map(lambda _: load_token(), range(worker_count)))

    assert tokens == ["tenant-test-token"] * worker_count
    assert token_requests == 1


def test_config_switch_cannot_mix_token_cache_state(monkeypatch):
    from app.services.feishu_client import FeishuClient

    app_1 = SimpleNamespace(
        feishu_ready=True,
        feishu_app_id="app-1",
        feishu_app_secret="secret-1",
        feishu_base_token="base_test",
        feishu_table_id="table_test",
    )
    app_2 = SimpleNamespace(
        feishu_ready=True,
        feishu_app_id="app-2",
        feishu_app_secret="secret-2",
        feishu_base_token="base_test",
        feishu_table_id="table_test",
    )
    thread_config = threading.local()
    comparison_started = threading.Event()
    release_reader = threading.Event()
    control = SimpleNamespace(armed=False, reader_ident=None)

    class ControlledCacheKey:
        def __init__(self, app_id):
            self.app_id = app_id

        def __eq__(self, other):
            should_pause = (
                control.armed
                and threading.get_ident() == control.reader_ident
                and self.app_id == "app-1"
                and isinstance(other, ControlledCacheKey)
                and other.app_id == "app-1"
            )
            if should_pause:
                comparison_started.set()
                if not release_reader.wait(timeout=2):
                    raise AssertionError("timed out waiting to resume App1 cache read")
            return (
                isinstance(other, ControlledCacheKey)
                and self.app_id == other.app_id
            )

    class ControlledClient(FeishuClient):
        def _token_cache_key(self, integration_config):
            return ControlledCacheKey(integration_config.feishu_app_id)

    monkeypatch.setattr(
        config,
        "get_personal_integration_config",
        lambda: thread_config.value,
    )

    def handler(request):
        request_body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "tenant_access_token": f"token-{request_body['app_id']}",
                "expire": 7200,
            },
        )

    client = ControlledClient(transport=httpx.MockTransport(handler))
    thread_config.value = app_1
    assert client.get_tenant_access_token() == "token-app-1"
    control.armed = True

    def read_app_1_token():
        thread_config.value = app_1
        control.reader_ident = threading.get_ident()
        return client.get_tenant_access_token()

    with ThreadPoolExecutor(max_workers=1) as executor:
        app_1_future = executor.submit(read_app_1_token)
        assert comparison_started.wait(timeout=2)
        thread_config.value = app_2
        try:
            app_2_token = client.get_tenant_access_token()
        finally:
            release_reader.set()
        app_1_token = app_1_future.result(timeout=2)

    assert app_1_token == "token-app-1"
    assert app_2_token == "token-app-2"


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


def test_duplicate_on_later_page_raises_conflict_and_sends_page_token(feishu_config):
    from app.services.feishu_client import FeishuClient, FeishuConflictError

    search_requests = []

    def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return token_response()
        search_requests.append(request)
        if len(search_requests) == 1:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [{"record_id": "rec_1", "fields": {}}],
                        "has_more": True,
                        "page_token": "next-page-token",
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [{"record_id": "rec_2", "fields": {}}],
                    "has_more": False,
                },
            },
        )

    client = FeishuClient(transport=httpx.MockTransport(handler))

    with pytest.raises(FeishuConflictError):
        client.find_record_by_platform_id(42)

    assert len(search_requests) == 2
    assert "page_token" not in search_requests[0].url.params
    assert search_requests[1].url.params["page_token"] == "next-page-token"
    assert json.loads(search_requests[0].content) == json.loads(
        search_requests[1].content
    )


def test_search_stops_at_maximum_page_count(monkeypatch, feishu_config):
    from app.services import feishu_client

    monkeypatch.setattr(feishu_client, "MAX_SEARCH_PAGES", 2, raising=False)
    search_count = 0

    def handler(request):
        nonlocal search_count
        if request.url.path.endswith("/tenant_access_token/internal"):
            return token_response()
        search_count += 1
        if search_count > 2:
            raise AssertionError("search requested more pages than the configured limit")
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [],
                    "has_more": True,
                    "page_token": f"page-token-{search_count}",
                },
            },
        )

    client = feishu_client.FeishuClient(transport=httpx.MockTransport(handler))

    with pytest.raises(feishu_client.FeishuResponseError) as caught:
        client.find_record_by_platform_id(42)

    assert "page limit" in str(caught.value).lower()
    assert search_count == 2


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


@pytest.mark.parametrize("code", [False, True])
def test_boolean_response_code_is_rejected_as_malformed(feishu_config, code):
    from app.services.feishu_client import FeishuClient, FeishuResponseError

    def handler(request):
        return httpx.Response(
            200,
            json={
                "code": code,
                "tenant_access_token": "must-not-be-accepted",
                "expire": 7200,
            },
        )

    with pytest.raises(FeishuResponseError):
        FeishuClient(
            transport=httpx.MockTransport(handler)
        ).get_tenant_access_token()


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
