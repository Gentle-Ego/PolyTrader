from __future__ import annotations
import time, asyncio, logging
import httpx
from config import INTERVALS, POLL_INTERVAL_SEC, BALANCE_SNAPSHOT_SEC
from market_finder import (build_snapshot, current_epoch, time_remaining,
                           fetch_btc_price, cleanup_delta_history)
import bot_engine, database as db, analytics

log = logging.getLogger("collector")

_last_btc: dict[tuple, float] = {}
_resolved: set[tuple] = set()
latest_snapshots: dict[str, object] = {}

async def _get_or_set_target(epoch, mtype, btc):
    existing = await db.get_target_price(epoch, mtype)
    if existing is not None: return existing
    await db.save_target_price(epoch, mtype, btc)
    return btc

async def _collect_once(client):
    for label, interval_s in INTERVALS.items():
        epoch = current_epoch(interval_s)
        remaining = time_remaining(epoch, interval_s)
        prev = epoch - interval_s; pk = (prev, label)
        if pk not in _resolved:
            pt = await db.get_target_price(prev, label)
            if await db.is_epoch_resolved(prev, label):
                _resolved.add(pk)
            elif pt is not None:
                close = _last_btc.get(pk, pt)
                outcome = "UP" if close >= pt else "DOWN"
                await db.save_market_result(prev, label, pt, close, outcome)
                await bot_engine.resolve_orders(prev, label, outcome)
                _resolved.add(pk)
                log.info(f"[{label}] RESOLVED {prev} → {outcome}")
        if remaining < 1: continue
        btc = await fetch_btc_price(client)
        if btc <= 0: continue
        target = await _get_or_set_target(epoch, label, btc)
        snap = await build_snapshot(client, label, target_price=target)
        if not snap: continue
        _last_btc[(epoch, label)] = snap.btc_price
        await db.save_snapshot(snap)
        latest_snapshots[label] = snap
        await bot_engine.process_early_exits(snap)
        for bot in bot_engine.list_bots():
            if not bot.enabled: continue
            order = await bot_engine.evaluate(bot, snap)
            if order: await db.save_order(order)
    await bot_engine.process_pending_fills()

async def collection_loop():
    log.info("Data collector started")
    async with httpx.AsyncClient() as client:
        while True:
            try: await _collect_once(client)
            except Exception as e: log.exception(f"Collection error: {e}")
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
            if k[0] < cutoff: _last_btc.pop(k, None)
        cleanup_delta_history(cutoff)