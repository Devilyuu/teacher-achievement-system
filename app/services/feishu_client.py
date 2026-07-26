from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from app import config


DEFAULT_BASE_URL = "https://open.feishu.cn"
DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=8.0, pool=3.0)
PERMISSION_CODES = {
    1254302,
    1254303,
    1254304,
    99991672,
    99991679,
}
AUTHENTICATION_CODES = {
    10003,
    99991663,
    99991664,
    99991665,
}


class FeishuError(RuntimeError):
    """Base exception for safe, user-facing Feishu failures."""


class FeishuConfigurationError(FeishuError):
    pass


class FeishuAuthenticationError(FeishuError):
    pass


class FeishuPermissionError(FeishuError):
    pass


class FeishuNetworkError(FeishuError):
    pass


class FeishuResponseError(FeishuError):
    pass


class FeishuConflictError(FeishuError):
    pass


@dataclass(frozen=True)
class FeishuRecord:
    record_id: str
    fields: dict[str, Any] = field(default_factory=dict, repr=False)


class FeishuClient:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        if client is not None and transport is not None:
            raise ValueError("Pass either client or transport, not both")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.Client(
            transport=transport,
            timeout=timeout,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "FeishuClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_tenant_access_token(self) -> str:
        integration_config = self._configuration_snapshot()
        return self._get_tenant_access_token(integration_config)

    def find_record_by_platform_id(
        self,
        platform_id: int | str,
    ) -> FeishuRecord | None:
        records = self.search_records_by_platform_id(platform_id)
        if not records:
            return None
        if len(records) > 1:
            raise FeishuConflictError(
                f"Found {len(records)} Feishu records for one achievement ID"
            )
        return records[0]

    def search_records_by_platform_id(
        self,
        platform_id: int | str,
    ) -> tuple[FeishuRecord, ...]:
        integration_config = self._configuration_snapshot()
        payload = {
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "成果平台ID",
                        "operator": "is",
                        "value": [str(platform_id)],
                    }
                ],
            }
        }
        response = self._authorized_request(
            integration_config,
            "POST",
            self._records_url(integration_config) + "/search",
            params={"page_size": 20},
            json=payload,
        )
        data = response.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise FeishuResponseError("Feishu search response has an invalid shape")
        return tuple(self._record_from(item) for item in data["items"])

    def create_record(self, fields: dict[str, Any]) -> FeishuRecord:
        integration_config = self._configuration_snapshot()
        response = self._authorized_request(
            integration_config,
            "POST",
            self._records_url(integration_config),
            json={"fields": fields},
        )
        return self._record_from_write_response(response)

    def update_record(
        self,
        record_id: str,
        fields: dict[str, Any],
    ) -> FeishuRecord:
        integration_config = self._configuration_snapshot()
        response = self._authorized_request(
            integration_config,
            "PUT",
            f"{self._records_url(integration_config)}/{quote(record_id, safe='')}",
            json={"fields": fields},
        )
        return self._record_from_write_response(response)

    def _configuration_snapshot(self) -> Any:
        integration_config = config.get_personal_integration_config()
        required_values = (
            getattr(integration_config, "feishu_app_id", ""),
            getattr(integration_config, "feishu_app_secret", ""),
            getattr(integration_config, "feishu_base_token", ""),
            getattr(integration_config, "feishu_table_id", ""),
        )
        if not getattr(integration_config, "feishu_ready", False) or not all(
            required_values
        ):
            raise FeishuConfigurationError(
                "Feishu integration is not fully configured"
            )
        return integration_config

    def _get_tenant_access_token(self, integration_config: Any) -> str:
        response = self._request(
            "POST",
            f"{self._base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": integration_config.feishu_app_id,
                "app_secret": integration_config.feishu_app_secret,
            },
            authentication_request=True,
        )
        token = response.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuResponseError(
                "Feishu authentication response has an invalid shape"
            )
        return token

    def _authorized_request(
        self,
        integration_config: Any,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        token = self._get_tenant_access_token(integration_config)
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {token}"
        return self._request(method, url, headers=headers, **kwargs)

    def _request(
        self,
        method: str,
        url: str,
        *,
        authentication_request: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(
                method,
                url,
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.TimeoutException:
            raise FeishuNetworkError("Feishu request timed out") from None
        except httpx.RequestError:
            raise FeishuNetworkError("Feishu network request failed") from None

        if response.status_code == 401:
            raise FeishuAuthenticationError("Feishu authentication was rejected")
        if response.status_code == 403:
            raise FeishuPermissionError("Feishu permission was denied")
        if response.is_error:
            raise FeishuResponseError(
                f"Feishu returned HTTP status {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError:
            raise FeishuResponseError("Feishu returned malformed JSON") from None
        if not isinstance(payload, dict):
            raise FeishuResponseError("Feishu response has an invalid shape")

        code = payload.get("code")
        if not isinstance(code, int):
            raise FeishuResponseError("Feishu response is missing a valid code")
        if code != 0:
            self._raise_api_error(
                code,
                payload.get("msg"),
                authentication_request=authentication_request,
            )
        return payload

    @staticmethod
    def _raise_api_error(
        code: int,
        message: Any,
        *,
        authentication_request: bool,
    ) -> None:
        normalized_message = message.casefold() if isinstance(message, str) else ""
        if authentication_request or code in AUTHENTICATION_CODES:
            raise FeishuAuthenticationError(
                f"Feishu authentication failed with code {code}"
            )
        if code in PERMISSION_CODES or any(
            marker in normalized_message
            for marker in ("permission", "forbidden", "no access", "无权限")
        ):
            raise FeishuPermissionError(
                f"Feishu permission was denied with code {code}"
            )
        raise FeishuResponseError(f"Feishu API returned error code {code}")

    def _records_url(self, integration_config: Any) -> str:
        base_token = quote(integration_config.feishu_base_token, safe="")
        table_id = quote(integration_config.feishu_table_id, safe="")
        return (
            f"{self._base_url}/open-apis/bitable/v1/apps/{base_token}"
            f"/tables/{table_id}/records"
        )

    @staticmethod
    def _record_from_write_response(response: dict[str, Any]) -> FeishuRecord:
        data = response.get("data")
        if not isinstance(data, dict):
            raise FeishuResponseError("Feishu record response has an invalid shape")
        return FeishuClient._record_from(data.get("record"))

    @staticmethod
    def _record_from(value: Any) -> FeishuRecord:
        if not isinstance(value, dict):
            raise FeishuResponseError("Feishu record has an invalid shape")
        record_id = value.get("record_id") or value.get("id")
        fields = value.get("fields", {})
        if not isinstance(record_id, str) or not record_id:
            raise FeishuResponseError("Feishu record is missing its ID")
        if not isinstance(fields, dict):
            raise FeishuResponseError("Feishu record fields have an invalid shape")
        return FeishuRecord(record_id=record_id, fields=fields)
