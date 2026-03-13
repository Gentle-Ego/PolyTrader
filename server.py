from __future__ import annotations
import asyncio, json, time, logging, csv, io, os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, PlainTextResponse
import pathlib

from models import BotConfig, CreateBotRequest, OrderStatus
from optimizer import OptimizeRequest, run_optimization
import database as db, bot_engine, bot_storage, data_collector, analytics

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s  %(message)s")
log = logging.getLogger("server")
SERVER_START_TIME = time.time()
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.get_db()
    await bot_engine.boot()
    tasks = [
        asyncio.create_task(data_collector.collection_loop()),
        asyncio.create_task(data_collector.balance_snapshot_loop()),
        asyncio.create_task(data_collector.cache_cleanup_loop()),
        asyncio.create_task(ws_broadcast_loop()),
    ]
    log.info("🚀  Paper trader started")
    yield
    for t in tasks: t.cancel()

app = FastAPI(title="Polymarket Paper Trader v3", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def index(): return FileResponse("static/index.html")

@app.get("/help")
async def help_page(): return FileResponse("static/help.html")

@app.get("/api/guide")
async def get_guide():
    p = pathlib.Path("GUIDE.md")
    return PlainTextResponse(p.read_text(encoding="utf-8") if p.exists() else "# Guida non trovata")

@app.get("/api/readme")
async def get_readme():
    p = pathlib.Path("README.md")
    return PlainTextResponse(p.read_text(encoding="utf-8") if p.exists() else "# README non trovato")


# ── Market data ────────────────────────────────────────────────
@app.get("/api/snapshot/{market_type}")
async def get_snapshot(market_type: str):
    s = data_collector.latest_snapshots.get(market_type)
    return s.model_dump() if s else {"error": "no data"}

@app.get("/api/results")
async def get_results(limit: int = 100):
    return await db.get_market_results(limit)


# ── Bots CRUD ──────────────────────────────────────────────────
@app.get("/api/bots")
async def list_bots():
    out = []
    for b in bot_engine.list_bots():
        s = await bot_engine.compute_stats(b.id)
        if s: out.append(s.model_dump())
    return out

@app.post("/api/bots")
async def create_bot(req: CreateBotRequest):
    cfg = BotConfig(**req.model_dump())
    bot_engine.register_bot(cfg)
    return {"ok": True, "bot_id": cfg.id}

@app.delete("/api/bots/{bot_id}")
async def delete_bot(bot_id: str):
    bot_engine.remove_bot(bot_id)
    await db.delete_orders_for_bot(bot_id)
    return {"ok": True}

@app.patch("/api/bots/{bot_id}/toggle")
async def toggle_bot(bot_id: str):
    bot = bot_engine.get_bot(bot_id)
    if not bot: return {"error": "not found"}
    bot.enabled = not bot.enabled
    bot_storage.save_bot(bot)
    bot_engine._stats_cache.pop(bot_id, None)
    return {"ok": True, "enabled": bot.enabled}

@app.patch("/api/bots/{bot_id}/reset-pause")
async def reset_pause(bot_id: str):
    bot_engine._pause_reasons[bot_id] = None
    bot_engine._consecutive_losses[bot_id] = 0
    bot_engine._stats_cache.pop(bot_id, None)
    return {"ok": True}

@app.get("/api/bots/{bot_id}/stats")
async def get_bot_stats(bot_id: str):
    s = await bot_engine.compute_stats(bot_id)
    return s.model_dump() if s else {"error": "not found"}

@app.get("/api/bots/{bot_id}/orders")
async def get_bot_orders(bot_id: str, limit: int = 200):
    return [o.model_dump() for o in await db.get_orders_for_bot(bot_id, limit)]

@app.get("/api/bots/{bot_id}/equity")
async def get_equity(bot_id: str):
    orders = await db.get_orders_for_bot(bot_id, 50000)
    bot = bot_engine.get_bot(bot_id)
    if not bot: return []
    resolved = sorted([o for o in orders if o.resolved_at], key=lambda o: o.resolved_at)
    bal = bot.balance
    curve = [{"ts": bot.created_at, "balance": bal, "pnl": 0}]
    for o in resolved:
        bal += o.pnl
        curve.append({"ts": o.resolved_at, "balance": round(bal, 4), "pnl": round(o.pnl, 4)})
    return curve


# ── Clone bot ──────────────────────────────────────────────────
@app.post("/api/bots/{bot_id}/clone")
async def clone_bot(bot_id: str, name: str = ""):
    original = bot_engine.get_bot(bot_id)
    if not original: return {"error": "not found"}
    d = original.model_dump()
    d.pop("id"); d.pop("created_at")
    d["name"] = name or f"{original.name} (clone)"
    new = BotConfig(**d)
    bot_engine.register_bot(new)
    return {"ok": True, "bot_id": new.id}


# ── Analytics ──────────────────────────────────────────────────
@app.get("/api/analytics/comparison")
async def compare_bots():
    out = []
    for b in bot_engine.list_bots():
        s = await bot_engine.compute_stats(b.id)
        if s:
            out.append({
                "bot_id":s.bot_id,"name":s.name,
                "net_pnl":s.net_pnl,"roi_pct":s.roi_pct,
                "win_rate":s.win_rate,"profit_factor":s.profit_factor,
                "sharpe_ratio":s.sharpe_ratio,"max_drawdown_pct":s.max_drawdown_pct,
                "expectancy":s.expectancy,"total_orders":s.total_orders})
    out.sort(key=lambda x: x["net_pnl"], reverse=True)
    return out

@app.get("/api/analytics/market-stats")
async def market_stats():
    return await analytics.compute_market_stats()

@app.get("/api/analytics/bot-hours/{bot_id}")
async def bot_hours(bot_id: str):
    return await analytics.bot_time_analysis(bot_id)

@app.get("/api/analytics/correlations")
async def correlations(market_type: str = "5m"):
    return await analytics.snapshot_outcome_correlation(market_type)

@app.get("/api/analytics/balance-history/{bot_id}")
async def balance_hist(bot_id: str, hours: float = 24):
    return await analytics.get_balance_history(bot_id, hours)

@app.get("/api/analytics/all-balances")
async def all_balances(hours: float = 24):
    return await analytics.get_all_balances_history(hours)


# ── Optimizer ──────────────────────────────────────────────────
@app.post("/api/optimizer/run")
async def run_optimizer(req: OptimizeRequest):
    by_epoch, resolutions = await db.get_all_snapshots_grouped(req.days_back)
    if not resolutions:
        return {"error": "No resolved markets yet — collect data first"}
    result = await run_optimization(req, by_epoch, resolutions)
    return result.model_dump()

@app.post("/api/optimizer/promote")
async def promote_config(config: dict, name: str = "Promoted Bot"):
    """Take an optimizer result config and create a live bot from it."""
    config["name"] = name
    config.pop("id", None); config.pop("created_at", None)
    cfg = BotConfig(**config)
    bot_engine.register_bot(cfg)
    return {"ok": True, "bot_id": cfg.id}


# ── Export ─────────────────────────────────────────────────────
@app.get("/api/export/orders/{bot_id}")
async def export_orders_csv(bot_id: str):
    orders = await db.get_orders_for_bot(bot_id, 50000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id","ts_signal","market_type","epoch","side","entry_price",
                "exit_price","shares","cost","fee","exit_fee","status",
                "exit_reason","pnl","outcome",
                "signal_delta","signal_velocity","signal_volatility","signal_ask","signal_elapsed"])
    for o in orders:
        w.writerow([o.id,o.ts_signal,o.market_type,o.epoch,o.side.value,
                     o.entry_price,o.exit_price,o.shares,o.cost,o.fee,o.exit_fee,
                     o.status.value,o.exit_reason,o.pnl,o.outcome,
                     o.signal_delta,o.signal_velocity,o.signal_volatility,
                     o.signal_ask,o.signal_elapsed])
    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=orders_{bot_id}.csv"})

@app.get("/api/export/snapshots/{market_type}")
async def export_snapshots(market_type: str, limit: int = 5000):
    rows = await db.get_recent_snapshots(market_type, limit)
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(buf, media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=snapshots_{market_type}.csv"})


# ── System stats ───────────────────────────────────────────────
@app.get("/api/system-stats")
async def system_stats():
    return await _build_system_stats()

async def _build_system_stats():
    dbase = await db.get_db()
    snap_count = (await (await dbase.execute("SELECT COUNT(*) FROM snapshots")).fetchone())[0]
    result_count = (await (await dbase.execute("SELECT COUNT(*) FROM market_results")).fetchone())[0]
    db_size = os.path.getsize(db.DB_PATH) if os.path.exists(db.DB_PATH) else 0
    return {
        "db_size_bytes": db_size,
        "total_snapshots": snap_count,
        "total_results": result_count,
        "uptime_seconds": round(time.time() - SERVER_START_TIME, 1),
    }


# ── Recent snapshots (for seeding live charts on page load) ────
@app.get("/api/snapshots/recent/{market_type}")
async def recent_snapshots_for_chart(market_type: str, limit: int = 60):
    rows = await db.get_recent_snapshots(market_type, limit)
    # Return oldest-first for chart seeding
    rows.reverse()
    return [{"ts": r["ts"], "delta_pct": r["delta_pct"], "ask_up": r["ask_up"]} for r in rows]


# ── WebSocket ──────────────────────────────────────────────────
_ws_clients: set[WebSocket] = set()

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    print(f"WS ACCEPTED. Total clients: {len(_ws_clients)}, id: {id(_ws_clients)}", flush=True)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: _ws_clients.discard(ws)

async def ws_broadcast_loop():
    while True:
        await asyncio.sleep(2)
        if not _ws_clients: continue
        try:
            payload = {}
            for label in ("5m","15m"):
                s = data_collector.latest_snapshots.get(label)
                if s: payload[label] = s.model_dump()
            bots = []
            for b in bot_engine.list_bots():
                s = await bot_engine.compute_stats(b.id)
                if s:
                    bots.append({
                        "bot_id":s.bot_id,"name":s.name,"enabled":s.enabled,
                        "paused_reason":s.paused_reason,
                        "balance":s.balance,"net_pnl":s.net_pnl,
                        "win_rate":s.win_rate,"total_orders":s.total_orders,
                        "wins":s.wins,"losses":s.losses,"early_exits":s.early_exits,
                        "pending":s.pending,"profit_factor":s.profit_factor,
                        "roi_pct":s.roi_pct,"sharpe_ratio":s.sharpe_ratio,
                        "max_drawdown_pct":s.max_drawdown_pct,
                        "expectancy":s.expectancy,"current_streak":s.current_streak,
                        "consecutive_losses":s.consecutive_losses,
                        "orders_today":s.orders_today})
            payload["bots"] = bots
            payload["server_time"] = time.time()
            try:
                payload["system_stats"] = await _build_system_stats()
            except Exception:
                pass
            msg = json.dumps(payload, default=str)
            dead = set()
            for c in _ws_clients:
                try: await c.send_text(msg)
                except: dead.add(c)
            _ws_clients.difference_update(dead)
        except Exception as e:
            log.exception(f"Exception in ws_broadcast_loop: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=False)