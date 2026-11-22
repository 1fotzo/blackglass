"""Etherscan API v2 client. The key stays in the request and out of stored payloads."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from blackglass.chain.ethereum import ReconError
from blackglass.core.envfile import load_local_env

API = "https://api.etherscan.io/v2/api"
ENV_KEY = "BLACKGLASS_ETHERSCAN_API_KEY"
Transport = Callable[[str], dict[str, object]]


class EtherscanClient:
    def __init__(self, api_key: str, transport: Transport | None = None) -> None:
        if not api_key:
            raise ReconError(f"{ENV_KEY} is not set")
        self._key = api_key
        self._transport = transport or _http_get

    def fetch(self, chain_id: int, module: str, action: str, params: dict[str, str]) -> object:
        query = {"chainid": str(chain_id), "module": module, "action": action, **params, "apikey": self._key}
        url = API + "?" + urllib.parse.urlencode(query)
        try:
            payload = self._transport(url)
        except ReconError:
            raise
        except Exception as exc:
            raise ReconError("indexer request failed") from exc
        if not isinstance(payload, dict) or "result" not in payload:
            raise ReconError("indexer response has no result")
        result = payload["result"]
        if str(payload.get("status", "1")) == "0":
            message = str(payload.get("message", ""))
            detail = result if isinstance(result, str) else ""
            if _empty(message) or _empty(detail):
                return []
            raise ReconError("indexer refused the read")
        return _scrub(result, self._key)


def client_from_env(transport: Transport | None = None) -> EtherscanClient:
    load_local_env()
    return EtherscanClient(os.environ.get(ENV_KEY, ""), transport=transport)


def _http_get(url: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ReconError("indexer request failed") from exc
    if not isinstance(payload, dict):
        raise ReconError("indexer response has no result")
    return payload


def _empty(message: str) -> bool:
    text = message.lower()
    return "no transactions found" in text or "no records found" in text


def _scrub(value: object, secret: str) -> object:
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[redacted]")
    if isinstance(value, list):
        return [_scrub(item, secret) for item in value]
    if isinstance(value, dict):
        return {str(key): _scrub(item, secret) for key, item in value.items()}
    return value
