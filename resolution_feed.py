from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from config import GAMMA_API

log = logging.getLogger("resolution_feed")

DEFAULT_CHAINLINK_SOURCE = "https://data.chain.link/streams/btc-usd"
OFFICIAL_RESOLUTION_GRACE_SEC = 45.0


@dataclass
class ResolutionContext:
    slug: str
    reference_source: str | None = None
    condition_id: str | None = None
    official_outcome: str | None = None
    event_found: bool = False
    event_closed: bool = False
    resolution_method: str = "unavailable"
    details: dict[str, Any] = field(default_factory=dict)


# ── Helpers ─────────────────────────────────────────────────────
def normalize_binary_outcome(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return "UP" if val else "DOWN"
    s = str(val).strip().upper()
    if s in {"UP", "YES", "WIN", "TRUE", "1"}:
        return "UP"
    if s in {"DOWN", "NO", "LOSS", "FALSE", "0"}:
        return "DOWN"
    return None


def parse_jsonish_list(raw: Any) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


async def _safe_get_json(client: httpx.AsyncClient, url: str, params: dict) -> Any:
    try:
        r = await client.get(url, params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


async def _fetch_gamma_by_slug(client: httpx.AsyncClient, slug: str) -> tuple[dict | None, dict | None]:
    # Try both endpoints. Gamma event metadata is often easiest for resolution source;
    # market endpoint may still surface useful direct winner fields.
    event = None
    for params in [
        {"slug": slug},
        {"slug": slug, "limit": 1},
        {"slug": slug, "active": "false"},
        {"slug": slug, "closed": "true"},
        {"slug": slug, "archived": "true"},
        {"slug": slug, "active": "false", "closed": "true"},
    ]:
        data = await _safe_get_json(client, f"{GAMMA_API}/events", params)
        if isinstance(data, list) and data:
            event = data[0]
            break

    market = None
    for params in [
        {"slug": slug},
        {"slug": slug, "limit": 1},
        {"slug": slug, "active": "false"},
        {"slug": slug, "closed": "true"},
        {"slug": slug, "archived": "true"},
    ]:
        data = await _safe_get_json(client, f"{GAMMA_API}/markets", params)
        if isinstance(data, list) and data:
            market = data[0]
            break

    if market is None and event and isinstance(event.get("markets"), list) and event["markets"]:
        market = event["markets"][0]

    return event, market


def _extract_direct_outcome(*sources: dict | None) -> str | None:
    keys = (
        "winner",
        "winningOutcome",
        "winning_outcome",
        "resolvedOutcome",
        "resolved_outcome",
        "result",
        "outcome",
        "finalOutcome",
        "final_outcome",
    )
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in keys:
            if key in src:
                outcome = normalize_binary_outcome(src.get(key))
                if outcome:
                    return outcome
    return None


def _extract_price_based_outcome(market: dict | None, event: dict | None) -> str | None:
    # Strict threshold by design: only trust obviously resolved 1/0 prices.
    sources = [market, event]
    for src in sources:
        if not isinstance(src, dict):
            continue
        raw_outcomes = src.get("outcomes")
        raw_prices = src.get("outcomePrices")
        outcomes = parse_jsonish_list(raw_outcomes)
        prices = parse_jsonish_list(raw_prices)
        if len(outcomes) < 2 or len(prices) < 2:
            continue

        pairs: list[tuple[str | None, float]] = []
        for out_name, price in zip(outcomes, prices):
            try:
                pairs.append((normalize_binary_outcome(out_name), float(price)))
            except Exception:
                continue

        if len(pairs) < 2:
            continue

        for label, price in pairs:
            if label and price >= 0.999:
                return label
    return None


async def fetch_resolution_context(client: httpx.AsyncClient, market_type: str, epoch: int) -> ResolutionContext:
    slug = f"btc-updown-{market_type}-{epoch}"
    event, market = await _fetch_gamma_by_slug(client, slug)

    reference_source = None
    condition_id = None
    event_closed = False
    details: dict[str, Any] = {"slug": slug}

    if isinstance(event, dict):
        details["event_id"] = event.get("id")
        details["event_closed"] = bool(event.get("closed"))
        details["event_active"] = event.get("active")
        reference_source = event.get("resolutionSource") or reference_source
        event_closed = event_closed or bool(event.get("closed"))

    if isinstance(market, dict):
        details["market_id"] = market.get("id")
        details["market_closed"] = bool(market.get("closed"))
        details["market_active"] = market.get("active")
        details["market_end"] = market.get("endDateIso") or market.get("endDate")
        reference_source = market.get("resolutionSource") or reference_source
        condition_id = market.get("conditionId") or market.get("condition_id") or condition_id
        event_closed = event_closed or bool(market.get("closed"))

    official_outcome = _extract_direct_outcome(market, event)
    if official_outcome is None:
        official_outcome = _extract_price_based_outcome(market, event)

    return ResolutionContext(
        slug=slug,
        reference_source=reference_source or DEFAULT_CHAINLINK_SOURCE,
        condition_id=condition_id,
        official_outcome=official_outcome,
        event_found=bool(event or market),
        event_closed=event_closed,
        resolution_method="polymarket_official" if official_outcome else "unavailable",
        details=details,
    )
