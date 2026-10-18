from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import httpx

from marketdata.providers import Candle, ProviderError

TIME_SERIES_URL = "https://api.twelvedata.com/time_series"
NEW_YORK = ZoneInfo("America/New_York")
SESSION_CLOSE = time(16, 0)


def fetch_daily(
    symbol: str,
    *,
    bars: int,
    timeout: float,
    api_key: str,
    transport: httpx.BaseTransport | None = None,
    now_ny: datetime | None = None,
) -> list[Candle]:
    if now_ny is None:
        now_ny = datetime.now(NEW_YORK)

    params = {
        "symbol": symbol,
        "interval": "1day",
        "outputsize": bars,
        "order": "asc",
        "adjust": "all",
    }
    headers = {"Authorization": f"apikey {api_key}"}

    if transport is not None:
        client = httpx.Client(transport=transport, timeout=timeout)
    else:
        client = httpx.Client(timeout=timeout)

    with client:
        try:
            response = client.get(TIME_SERIES_URL, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError("provider_error", str(exc)) from exc

    payload = _decode_payload(response)
    _raise_for_error(payload, response.status_code)
    candles = _parse_candles(payload)
    candles.sort(key=lambda candle: candle.date)
    return _drop_incomplete_session(candles, now_ny)


def _decode_payload(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError("invalid_response", str(exc)) from exc
    if not isinstance(payload, dict):
        raise ProviderError("invalid_response", "Provider response was not a JSON object.")
    return payload


def _raise_for_error(payload: dict, status_code: int) -> None:
    is_error = payload.get("status") == "error" or "code" in payload or status_code >= 400
    if not is_error:
        return
    code = payload.get("code")
    if not isinstance(code, int):
        code = status_code
    raise ProviderError(_reason_for_code(code), str(payload.get("message", "")))


def _reason_for_code(code: int) -> str:
    if code in (401, 403):
        return "auth_failed"
    if code == 404:
        return "symbol_not_found"
    if code == 429:
        return "rate_limited"
    return "provider_error"


def _parse_candles(payload: dict) -> list[Candle]:
    values = payload.get("values")
    if values is None:
        raise ProviderError("invalid_response", "Provider response had no values array.")
    if not isinstance(values, list):
        raise ProviderError("invalid_response", "Provider values was not a list.")
    if not values:
        raise ProviderError("no_data", "Provider returned no daily bars.")
    return [_parse_candle(value) for value in values]


def _parse_candle(value: object) -> Candle:
    if not isinstance(value, dict):
        raise ProviderError("invalid_response", "Provider value was not a JSON object.")
    try:
        return Candle(
            date=date.fromisoformat(value["datetime"]),
            open=Decimal(value["open"]),
            high=Decimal(value["high"]),
            low=Decimal(value["low"]),
            close=Decimal(value["close"]),
            volume=_parse_volume(value.get("volume")),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ProviderError("invalid_response", str(exc)) from exc


def _parse_volume(raw: object) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return int(Decimal(text))


def _drop_incomplete_session(candles: list[Candle], now_ny: datetime) -> list[Candle]:
    if now_ny.time() < SESSION_CLOSE:
        return [candle for candle in candles if candle.date < now_ny.date()]
    return [candle for candle in candles if candle.date <= now_ny.date()]
