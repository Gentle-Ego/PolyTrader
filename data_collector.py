from __future__ import annotations
import time
import json
import asyncio
import logging

import httpx

from config import INTERVALS, POLL_INTERVAL_SEC, BALANCE_SNAPSHOT_SEC
from market_finder import build_snapshot, current_epoch, time_remaining, fetch_btc_price, cleanup_delta_history
import bot_engine
import database as db
import analytics
from resolution_feed import fetch_resolution_context, OFFICIAL_RESOLUTION_GRACE_SEC

log = logging.getLogger("collector")

_last_btc: dict[tuple, float] = {}
_resolved: set[tuple] = set()
latest_snapshots: dict[str, object] = {}


async def _get_or_set_target(client: httpx.AsyncClient, epoch: int, mtype: str, btc: float) -> float:
    existing = await db.get_target_record(epoch, mtype)
    if existing is not None:
        return float(existing["btc_price"])

    ctx = await fetch_resolution_context(client, mtype, epoch)
    await db.save_target_price(
        epoch,
        mtype,
        btc,
        reference_source=ctx.reference_source,
        condition_id=ctx.condition_id,
        resolution_slug=ctx.slug,
        metadata_json=json.dumps(ctx.details),
    )
    return btc


async def _resolve_previous_round(client: httpx.AsyncClient, label: str, interval_s: int) -> None:
    epoch = current_epoch(interval_s)
    prev = epoch - interval_s
    pk = (prev, label)

    if pk in _resolved:
        return
    if await db.is_epoch_resolved(prev, label):
        _resolved.add(pk)
        return

    target = await db.get_target_record(prev, label)
    if target is None:
        return

    resolved_ts = time.time()
    seconds_since_round_end = resolved_ts - (prev + interval_s)
    if seconds_since_round_end < 0:
        return

    # Prefer Polymarket/Gamma official metadata when available, but do not hang
    # the simulator forever waiting for an API field that may lag or be absent.
    ctx = await fetch_resolution_context(client, label, prev)
    signal_target = float(target["btc_price"])
    signal_close = float(_last_btc.get(pk, signal_target))
    fallback_outcome = "UP" if signal_close >= signal_target else "DOWN"

    if ctx.official_outcome is None and seconds_since_round_end < OFFICIAL_RESOLUTION_GRACE_SEC:
        return

    final_outcome = ctx.official_outcome or fallback_outcome
    resolution_method = ctx.resolution_method if ctx.official_outcome else "internal_spot_fallback"
    reference_source = ctx.reference_source or target.get("reference_source")
    condition_id = ctx.condition_id or target.get("condition_id")

    details = {
        **(ctx.details or {}),
        "signal_target_price": signal_target,
        "signal_close_price": signal_close,
        "grace_elapsed_s": round(seconds_since_round_end, 3),
        "fallback_outcome": fallback_outcome,
        "used_official_outcome": bool(ctx.official_outcome),
    }

    # Give matured pending orders one last chance to fill before settlement.
    await bot_engine.process_pending_fills(now_ts=resolved_ts)

    await db.save_market_result(
        prev,
        label,
        signal_target,
        signal_close,
        final_outcome,
        reference_source=reference_source,
        reference_target_price=None,
        reference_close_price=None,
        reference_outcome=ctx.official_outcome,
        resolution_method=resolution_method,
        condition_id=condition_id,
        details_json=json.dumps(details),
        resolved_at=resolved_ts,
    )
    await bot_engine.resolve_orders(prev, label, final_outcome, resolved_ts=resolved_ts)
    _resolved.add(pk)
    log.info(f"[{label}] RESOLVED {prev} → {final_outcome} via {resolution_method}")


async def _process_snapshot(client: httpx.AsyncClient, label: str, interval_s: int) -> None:
    epoch = current_epoch(interval_s)
    remaining = time_remaining(epoch, interval_s)
    if remaining < 1:
        return

    btc = await fetch_btc_price(client)
    if btc <= 0:
        return

    target = await _get_or_set_target(client, epoch, label, btc)
    snap = await build_snapshot(client, label, target_price=target)
    if not snap:
        return

    _last_btc[(epoch, label)] = snap.btc_price
    await db.save_snapshot(snap)
    latest_snapshots[label] = snap

    await bot_engine.process_early_exits(snap)
    for bot in bot_engine.list_bots():
        if not bot.enabled:
            continue
        order = await bot_engine.evaluate(bot, snap)
        if order:
            await db.save_order(order)

    await bot_engine.process_pending_fills(now_ts=snap.ts)


async def _collect_once(client: httpx.AsyncClient):
    for label, interval_s in INTERVALS.items():
        await _resolve_previous_round(client, label, interval_s)
        await _process_snapshot(client, label, interval_s)


async def collection_loop():
    log.info("Data collector started")
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await _collect_once(client)
            except Exception as e:
                log.exception(f"Collection error: {e}")
            await asyncio.sleep(POLL_INTERVAL_SEC)


async def balance_snapshot_loop():
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


async def cache_cleanup_loop():
    while True:
        await asyncio.sleep(600)
        cutoff = int(time.time()) - 7200
        for k in list(_last_btc):
            if k[0] < cutoff:
                _last_btc.pop(k, None)
        cleanup_delta_history(cutoff)
