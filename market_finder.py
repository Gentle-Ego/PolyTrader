from __future__ import annotations
import time, asyncio, logging, collections, statistics as pystats, json
from typing import Optional
import httpx

from config import GAMMA_API, CLOB_API, INTERVALS, DELTA_HISTORY_WINDOW, VOLATILITY_WINDOW
from models import MarketSnapshot

log = logging.getLogger("market_finder")

_delta_history: dict[tuple, collections.deque] = {}
_vol_history: dict[tuple, collections.deque] = {}


def current_epoch(interval_s):
    return (int(time.time()) // interval_s) * interval_s

def time_remaining(epoch, interval_s):
    return max(0.0, (epoch + interval_s) - time.time())


def compute_delta_velocity(epoch, mtype, ts, delta_pct):
    key = (epoch, mtype)
    if key not in _delta_history:
        _delta_history[key] = collections.deque(maxlen=DELTA_HISTORY_WINDOW)
    h = _delta_history[key]
    h.append((ts, delta_pct))
    if len(h) < 2: return 0.0
    dt = ts - h[0][0]
    return (delta_pct - h[0][1]) / dt if dt > 0.5 else 0.0


def compute_volatility(epoch, mtype, delta_pct):
    """Rolling stdev of delta_pct over recent ticks."""
    key = (epoch, mtype)
    if key not in _vol_history:
        _vol_history[key] = collections.deque(maxlen=VOLATILITY_WINDOW)
    h = _vol_history[key]
    h.append(delta_pct)
    if len(h) < 3: return 0.0
    return pystats.stdev(h)


def cleanup_delta_history(cutoff_epoch):
    for k in list(_delta_history):
        if k[0] < cutoff_epoch: del _delta_history[k]
    for k in list(_vol_history):
        if k[0] < cutoff_epoch: del _vol_history[k]


async def _fetch_event(client, slug):
    try:
        r = await client.get(f"{GAMMA_API}/events",
                             params={"slug": slug, "active": "true", "closed": "false"}, timeout=5)
        r.raise_for_status()
        d = r.json()
        return d[0] if isinstance(d, list) and d else None
    except Exception: return None

async def fetch_price(client, token_id, side="BUY"):
    try:
        r = await client.get(f"{CLOB_API}/price",
                             params={"token_id": token_id, "side": side}, timeout=4)
        r.raise_for_status()
        p = float(r.json().get("price", 0))
        return p if p > 0 else None
    except Exception: return None

async def fetch_book(client, token_id):
    try:
        r = await client.get(f"{CLOB_API}/book",
                             params={"token_id": token_id}, timeout=4)
        r.raise_for_status()
        d = r.json()
        return {
            "best_bid": float(d["bids"][0]["price"]) if d.get("bids") else None,
            "best_ask": float(d["asks"][0]["price"]) if d.get("asks") else None,
        }
    except Exception: return {"best_bid": None, "best_ask": None}

_btc_cache = {"price": 0.0, "ts": 0.0}
async def fetch_btc_price(client):
    if time.time() - _btc_cache["ts"] < 0.8 and _btc_cache["price"] > 0:
        return _btc_cache["price"]
    for url, parser in [
        ("https://api.coinbase.com/v2/prices/BTC-USD/spot", lambda d: float(d["data"]["amount"])),
        ("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", lambda d: float(d["price"])),
    ]:
        try:
            r = await client.get(url, timeout=4)
            r.raise_for_status()
            p = parser(r.json())
            if p > 1000:
                _btc_cache.update(price=p, ts=time.time())
                return p
        except Exception: continue
    return _btc_cache["price"]


async def build_snapshot(client, interval_label, target_price=None):
    interval_s = INTERVALS[interval_label]
    epoch = current_epoch(interval_s)
    remaining = time_remaining(epoch, interval_s)
    if remaining < 2: return None

    btc = await fetch_btc_price(client)
    if btc <= 0: return None
    if target_price is None: target_price = btc
    elapsed = interval_s - remaining

    slug = f"btc-updown-{interval_label}-{epoch}"
    event = await _fetch_event(client, slug)
    up_token = down_token = condition_id = None
    if event and "markets" in event:
        mkt = event["markets"][0] if event["markets"] else None
        if mkt:
            condition_id = mkt.get("conditionId") or mkt.get("condition_id") or mkt.get("id")

            # Parse clobTokenIds — Gamma API returns it as a JSON string
            raw_clob = mkt.get("clobTokenIds", "[]")
            if isinstance(raw_clob, str):
                try:
                    clob_ids = json.loads(raw_clob)
                except (ValueError, TypeError):
                    clob_ids = []
            else:
                clob_ids = raw_clob if isinstance(raw_clob, list) else []

            # Parse outcomes — also a JSON string
            raw_outcomes = mkt.get("outcomes", "[]")
            if isinstance(raw_outcomes, str):
                try:
                    outcomes = json.loads(raw_outcomes)
                except (ValueError, TypeError):
                    outcomes = []
            else:
                outcomes = raw_outcomes if isinstance(raw_outcomes, list) else []

            # Match token IDs to UP/DOWN by outcome names
            if len(clob_ids) >= 2 and len(outcomes) >= 2:
                for i, out_name in enumerate(outcomes):
                    if i >= len(clob_ids):
                        break
                    out_lower = out_name.lower() if isinstance(out_name, str) else ""
                    if "up" in out_lower or "yes" in out_lower:
                        up_token = clob_ids[i]
                    elif "down" in out_lower or "no" in out_lower:
                        down_token = clob_ids[i]

            # Fallback: assume first=UP, second=DOWN
            if not up_token and len(clob_ids) >= 2:
                up_token, down_token = clob_ids[0], clob_ids[1]
            if up_token:
                log.debug(f"Tokens: UP={up_token[:16]}… DOWN={down_token[:16] if down_token else 'N/A'}")

    ask_up = bid_up = ask_down = bid_down = None
    if up_token:
        bk, ap, bp = await asyncio.gather(
            fetch_book(client, up_token),
            fetch_price(client, up_token, "BUY"),
            fetch_price(client, up_token, "SELL"))
        ask_up = ap or bk["best_ask"]; bid_up = bp or bk["best_bid"]
    if down_token:
        bk, ap, bp = await asyncio.gather(
            fetch_book(client, down_token),
            fetch_price(client, down_token, "BUY"),
            fetch_price(client, down_token, "SELL"))
        ask_down = ap or bk["best_ask"]; bid_down = bp or bk["best_bid"]

    delta_pct = ((btc - target_price) / target_price * 100) if target_price else 0
    now = time.time()

    return MarketSnapshot(
        ts=now, market_type=interval_label, epoch=epoch,
        btc_price=btc, target_price=target_price, delta_pct=delta_pct,
        delta_velocity=compute_delta_velocity(epoch, interval_label, now, delta_pct),
        volatility_20s=compute_volatility(epoch, interval_label, delta_pct),
        ask_up=ask_up, bid_up=bid_up, ask_down=ask_down, bid_down=bid_down,
        spread_up=(ask_up - bid_up) if (ask_up and bid_up) else None,
        spread_down=(ask_down - bid_down) if (ask_down and bid_down) else None,
        mid_up=((ask_up + bid_up) / 2) if (ask_up and bid_up) else None,
        mid_down=((ask_down + bid_down) / 2) if (ask_down and bid_down) else None,
        time_remaining_s=remaining, time_elapsed_s=elapsed,
        up_token_id=up_token, down_token_id=down_token, condition_id=condition_id)