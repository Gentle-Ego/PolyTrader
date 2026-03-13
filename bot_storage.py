"""
JSON‑file persistence for bot configs.

Everything reads/writes bots.json — the single source of truth for
bot definitions. Orders still live in SQLite (volume is too high for JSON).
"""
from __future__ import annotations
import json, os, time, copy, logging
from pathlib import Path
from typing import Optional

from config import BOTS_JSON
from models import BotConfig

log = logging.getLogger("bot_storage")

_DEFAULT_BOTS_JSON = {
    "bots": [
        {
            "id": "base0001",
            "name": "Base Strategy \u2014 Delta Momentum UP",
            "enabled": True,
            "created_at": 0,
            "side": "UP",
            "market_type": "5m",
            "min_entry_time_s": 0,
            "max_entry_time_s": 120,
            "delta_pct_min": 0.05,
            "delta_pct_max": None,
            "delta_velocity_min": None,
            "delta_velocity_max": None,
            "ask_up_min": 0.50,
            "ask_up_max": 0.70,
            "ask_down_min": None,
            "ask_down_max": None,
            "bid_up_min": None,
            "bid_up_max": None,
            "bid_down_min": None,
            "bid_down_max": None,
            "spread_max": None,
            "session_start_utc": None,
            "session_end_utc": None,
            "fill_delay_s": 1.0,
            "taker_fee_pct": 2.0,
            "slippage_pct": 0.0,
            "shares_per_order": 1,
            "multiple_orders": False,
            "cooldown_s": 30,
            "max_orders_per_round": 1,
            "max_open_orders": 5,
            "balance": 100.0,
            "max_daily_loss": None,
            "max_drawdown_pct": None,
            "max_consecutive_losses": None,
            "daily_order_limit": None,
            "max_exposure": None,
            "enable_early_exit": False,
            "take_profit_bid": None,
            "stop_loss_bid": None,
        },
        {
            "id": "snpr0002",
            "name": "Sniper \u2014 Tight Spread + Velocity",
            "enabled": True,
            "created_at": 0,
            "side": "UP",
            "market_type": "5m",
            "min_entry_time_s": 15,
            "max_entry_time_s": 90,
            "delta_pct_min": 0.03,
            "delta_pct_max": 0.30,
            "delta_velocity_min": 0.001,
            "delta_velocity_max": None,
            "ask_up_min": 0.45,
            "ask_up_max": 0.65,
            "ask_down_min": None,
            "ask_down_max": None,
            "bid_up_min": None,
            "bid_up_max": None,
            "bid_down_min": None,
            "bid_down_max": None,
            "spread_max": 0.10,
            "session_start_utc": 13,
            "session_end_utc": 21,
            "fill_delay_s": 1.0,
            "taker_fee_pct": 2.0,
            "slippage_pct": 0.5,
            "shares_per_order": 1,
            "multiple_orders": True,
            "cooldown_s": 45,
            "max_orders_per_round": 2,
            "max_open_orders": 4,
            "balance": 100.0,
            "max_daily_loss": 10.0,
            "max_drawdown_pct": 15.0,
            "max_consecutive_losses": 5,
            "daily_order_limit": 20,
            "max_exposure": 30.0,
            "enable_early_exit": True,
            "take_profit_bid": 0.88,
            "stop_loss_bid": 0.18,
        },
    ]
}


def _ensure_file() -> Path:
    """Create bots.json with defaults if it doesn't exist."""
    p = Path(BOTS_JSON)
    if not p.exists():
        log.info(f"Creating {BOTS_JSON} with 2 default bots")
        p.write_text(json.dumps(_DEFAULT_BOTS_JSON, indent=2), encoding="utf-8")
    return p


def _read_raw() -> dict:
    p = _ensure_file()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "bots" not in data:
            data["bots"] = []
        return data
    except (json.JSONDecodeError, IOError) as e:
        log.error(f"Corrupt {BOTS_JSON}, resetting: {e}")
        p.write_text(json.dumps(_DEFAULT_BOTS_JSON, indent=2), encoding="utf-8")
        return copy.deepcopy(_DEFAULT_BOTS_JSON)


def _write_raw(data: dict):
    p = Path(BOTS_JSON)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)  # atomic on most OS


# ── Public API ──────────────────────────────────────────────────

def load_all() -> list[BotConfig]:
    """Read every bot from bots.json → list[BotConfig]."""
    data = _read_raw()
    bots: list[BotConfig] = []
    for raw in data["bots"]:
        # Fill created_at with current time if it was 0
        if raw.get("created_at", 0) == 0:
            raw["created_at"] = time.time()
        try:
            bots.append(BotConfig(**raw))
        except Exception as e:
            log.warning(f"Skipping bad bot entry: {e}")
    return bots


def save_bot(bot: BotConfig):
    """Add or update a bot in bots.json."""
    data = _read_raw()
    # Replace if exists, else append
    found = False
    for i, raw in enumerate(data["bots"]):
        if raw.get("id") == bot.id:
            data["bots"][i] = json.loads(bot.model_dump_json())
            found = True
            break
    if not found:
        data["bots"].append(json.loads(bot.model_dump_json()))
    _write_raw(data)
    log.info(f"Saved bot {bot.name} ({bot.id}) to {BOTS_JSON}")


def delete_bot(bot_id: str):
    """Remove a bot from bots.json."""
    data = _read_raw()
    data["bots"] = [b for b in data["bots"] if b.get("id") != bot_id]
    _write_raw(data)
    log.info(f"Deleted bot {bot_id} from {BOTS_JSON}")


def update_field(bot_id: str, field: str, value):
    """Update a single field on a bot and flush to disk."""
    data = _read_raw()
    for raw in data["bots"]:
        if raw.get("id") == bot_id:
            raw[field] = value
            break
    _write_raw(data)