from __future__ import annotations

import asyncio
import logging
import time

import httpx

from config import BALANCE_SNAPSHOT_SEC, INTERVALS, POLL_INTERVAL_SEC
from market_finder import (
    build_snapshot,
    cleanup_delta_history,
    current_epoch,
    fetch_btc_price,
    time_remaining,
)
import analytics
import bot_engine
import database as db

log = logging.getLogger("collector")

_last_btc: dict[tuple[int, str], float] = {}
_resolved: set[tuple[int, str]] = set()
latest_snapshots: dict[str, object] = {}


async def _get_or_set_target(epoch: int, mtype: str, btc: float) -> float:
    existing = await db.get_target_price(epoch, mtype)
    if existing is not None:
        return existing
    await db.save_target_price(epoch, mtype, btc)
    return btc


async def _resolve_previous_round(label: str, interval_s: int, resolved_ts: float) -> None:
    """
    Resolve the previous epoch for this market label.

    Important ordering:
      1) first advance pending fills up to the resolution timestamp;
      2) then resolve the round outcome.

    This avoids wrongly expiring orders whose fill time had already passed
    before the round actually settled.
    """
    prev = current_epoch(interval_s) - interval_s
    prev_key = (prev, label)
    if prev_key in _resolved:
        return

    if await db.is_epoch_resolved(prev, label):
        _resolved.add(prev_key)
        return

    target_price = await db.get_target_price(prev, label)
    if target_price is None:
        return

    close_price = _last_btc.get(prev_key, target_price)
    outcome = "UP" if close_price >= target_price else "DOWN"

    # Let all due pending orders fill before settling the market.
    await bot_engine.process_pending_fills(now_ts=resolved_ts)

    await db.save_market_result(prev, label, target_price, close_price, outcome)
    await bot_engine.resolve_orders(prev, label, outcome, resolved_ts=resolved_ts)
    _resolved.add(prev_key)
    log.info(f"[{label}] RESOLVED {prev} -> {outcome} (target={target_price:.2f}, close={close_price:.2f})")


async def _process_snapshot(client: httpx.AsyncClient, label: str, interval_s: int) -> None:
    epoch = current_epoch(interval_s)
    remaining = time_remaining(epoch, interval_s)

    # Always attempt resolution first when a new epoch has started.
    await _resolve_previous_round(label, interval_s, time.time())

    # Skip collection in the final second to avoid noisy near-boundary snapshots.
    if remaining < 1:
        return

    btc = await fetch_btc_price(client)
    if btc <= 0:
        return

    target = await _get_or_set_target(epoch, label, btc)
    snap = await build_snapshot(client, label, target_price=target)
    if not snap:
        return

    _last_btc[(epoch, label)] = snap.btc_price
    await db.save_snapshot(snap)
    latest_snapshots[label] = snap

    # Keep event ordering aligned with the optimizer/live model:
    # snapshot -> early exits -> new signals -> pending fills due by this snapshot ts.
    await bot_engine.process_early_exits(snap)

    for bot in bot_engine.list_bots():
        if not bot.enabled:
            continue
        order = await bot_engine.evaluate(bot, snap)
        if order:
            await db.save_order(order)

    await bot_engine.process_pending_fills(now_ts=snap.ts)


async def _collect_once(client: httpx.AsyncClient) -> None:
    for label, interval_s in INTERVALS.items():
        await _process_snapshot(client, label, interval_s)

    # Fallback flush in case no fresh snapshot was produced for a label in this loop.
    await bot_engine.process_pending_fills(now_ts=time.time())


async def collection_loop() -> None:
    log.info("Data collector started")
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await _collect_once(client)
            except Exception as e:
                log.exception(f"Collection error: {e}")
            await asyncio.sleep(POLL_INTERVAL_SEC)


async def balance_snapshot_loop() -> None:
    """Periodically record all bot balances for the timeline chart."""
    log.info(f"Balance snapshot loop started (every {BALANCE_SNAPSHOT_SEC}s)")
    while True:
        await asyncio.sleep(BALANCE_SNAPSHOT_SEC)
        try:
            bals = bot_engine.get_balances()
            if bals:
                await analytics.record_balance_snapshots(bals)
        except Exception as e:
            log.exception(f"Balance snapshot error: {e}")


async def cache_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(600)
        cutoff = int(time.time()) - 7200
        for k in list(_last_btc):
            if k[0] < cutoff:
                _last_btc.pop(k, None)
        cleanup_delta_history(cutoff)
