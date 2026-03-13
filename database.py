from __future__ import annotations
import time, datetime, aiosqlite
from config import DB_PATH
from models import PaperOrder, OrderStatus

_db: aiosqlite.Connection | None = None

async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA synchronous=NORMAL")
        await _db.execute("PRAGMA busy_timeout=5000")
        await _db.executescript(_SCHEMA)
    return _db

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, market_type TEXT, epoch INTEGER,
    btc_price REAL, target_price REAL, delta_pct REAL,
    delta_velocity REAL DEFAULT 0, volatility_20s REAL DEFAULT 0,
    ask_up REAL, bid_up REAL, ask_down REAL, bid_down REAL,
    spread_up REAL, spread_down REAL, mid_up REAL, mid_down REAL,
    time_remaining_s REAL, time_elapsed_s REAL DEFAULT 0,
    up_token_id TEXT, down_token_id TEXT, condition_id TEXT,
    resolved INTEGER DEFAULT 0, outcome TEXT
);
CREATE INDEX IF NOT EXISTS idx_snap_epoch ON snapshots(epoch);
CREATE INDEX IF NOT EXISTS idx_snap_ts ON snapshots(ts);
CREATE INDEX IF NOT EXISTS idx_snap_mkt_epoch ON snapshots(market_type, epoch);
CREATE INDEX IF NOT EXISTS idx_snap_elapsed ON snapshots(market_type, time_elapsed_s);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, bot_id TEXT,
    ts_signal REAL, ts_fill REAL, ts_exit REAL,
    market_type TEXT, epoch INTEGER, side TEXT,
    entry_price REAL, exit_price REAL, shares REAL,
    cost REAL, fee REAL, exit_fee REAL DEFAULT 0,
    status TEXT, exit_reason TEXT, pnl REAL,
    resolved_at REAL, outcome TEXT,
    signal_delta REAL DEFAULT 0, signal_velocity REAL DEFAULT 0,
    signal_volatility REAL DEFAULT 0, signal_ask REAL DEFAULT 0,
    signal_elapsed REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ord_bot ON orders(bot_id);
CREATE INDEX IF NOT EXISTS idx_ord_epoch ON orders(epoch);
CREATE INDEX IF NOT EXISTS idx_ord_status ON orders(status);

CREATE TABLE IF NOT EXISTS market_results (
    epoch INTEGER, market_type TEXT,
    target_price REAL, close_price REAL,
    outcome TEXT, resolved_at REAL,
    PRIMARY KEY (epoch, market_type)
);

CREATE TABLE IF NOT EXISTS target_prices (
    epoch INTEGER, market_type TEXT, btc_price REAL, ts REAL,
    PRIMARY KEY (epoch, market_type)
);

CREATE TABLE IF NOT EXISTS balance_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT, ts REAL, balance REAL
);
CREATE INDEX IF NOT EXISTS idx_bh_bot ON balance_history(bot_id, ts);
"""


# ── Snapshots ───────────────────────────────────────────────────
async def save_snapshot(s):
    db = await get_db()
    await db.execute(
        """INSERT INTO snapshots
           (ts,market_type,epoch,btc_price,target_price,delta_pct,
            delta_velocity,volatility_20s,ask_up,bid_up,ask_down,bid_down,
            spread_up,spread_down,mid_up,mid_down,
            time_remaining_s,time_elapsed_s,
            up_token_id,down_token_id,condition_id,resolved,outcome)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (s.ts,s.market_type,s.epoch,s.btc_price,s.target_price,
         s.delta_pct,s.delta_velocity,s.volatility_20s,
         s.ask_up,s.bid_up,s.ask_down,s.bid_down,
         s.spread_up,s.spread_down,s.mid_up,s.mid_down,
         s.time_remaining_s,s.time_elapsed_s,
         s.up_token_id,s.down_token_id,s.condition_id,
         int(s.resolved),s.outcome))
    await db.commit()

async def get_recent_snapshots(market_type, limit=200):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM snapshots WHERE market_type=? ORDER BY ts DESC LIMIT ?",
        (market_type, limit))
    return [dict(r) for r in await cur.fetchall()]

async def get_all_snapshots_grouped(days_back: int = 7) -> tuple[dict, dict]:
    """Return (snapshots_by_epoch, resolutions) for backtesting, bounded by time."""
    db = await get_db()
    cutoff = time.time() - (days_back * 86400)
    cur = await db.execute("SELECT * FROM snapshots WHERE ts >= ? ORDER BY epoch, ts", (cutoff,))
    rows = await cur.fetchall()
    by_epoch: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r["epoch"], r["market_type"])
        by_epoch.setdefault(key, []).append(dict(r))

    cur2 = await db.execute("SELECT * FROM market_results")
    res_rows = await cur2.fetchall()
    resolutions = {(r["epoch"], r["market_type"]): r["outcome"] for r in res_rows}
    return by_epoch, resolutions


# ── Target prices ──────────────────────────────────────────────
async def save_target_price(epoch, market_type, btc_price):
    db = await get_db()
    await db.execute(
        "INSERT OR IGNORE INTO target_prices VALUES (?,?,?,?)",
        (epoch, market_type, btc_price, time.time()))
    await db.commit()

async def get_target_price(epoch, market_type):
    db = await get_db()
    cur = await db.execute(
        "SELECT btc_price FROM target_prices WHERE epoch=? AND market_type=?",
        (epoch, market_type))
    row = await cur.fetchone()
    return float(row["btc_price"]) if row else None


# ── Market results ──────────────────────────────────────────────
async def save_market_result(epoch, market_type, target_price, close_price, outcome):
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO market_results VALUES (?,?,?,?,?,?)",
        (epoch, market_type, target_price, close_price, outcome, time.time()))
    await db.commit()

async def get_market_results(limit=100):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM market_results ORDER BY resolved_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in await cur.fetchall()]

async def is_epoch_resolved(epoch, market_type):
    db = await get_db()
    cur = await db.execute(
        "SELECT 1 FROM market_results WHERE epoch=? AND market_type=?",
        (epoch, market_type))
    return (await cur.fetchone()) is not None


# ── Orders ──────────────────────────────────────────────────────
async def save_order(o: PaperOrder):
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO orders
           (id,bot_id,ts_signal,ts_fill,ts_exit,market_type,epoch,side,
            entry_price,exit_price,shares,cost,fee,exit_fee,
            status,exit_reason,pnl,resolved_at,outcome,
            signal_delta,signal_velocity,signal_volatility,signal_ask,signal_elapsed)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (o.id,o.bot_id,o.ts_signal,o.ts_fill,o.ts_exit,
         o.market_type,o.epoch,o.side.value,
         o.entry_price,o.exit_price,o.shares,o.cost,o.fee,o.exit_fee,
         o.status.value,o.exit_reason,o.pnl,o.resolved_at,o.outcome,
         o.signal_delta,o.signal_velocity,o.signal_volatility,
         o.signal_ask,o.signal_elapsed))
    await db.commit()

def _row_to_order(r) -> PaperOrder:
    return PaperOrder(
        id=r["id"],bot_id=r["bot_id"],ts_signal=r["ts_signal"],
        ts_fill=r["ts_fill"],ts_exit=r["ts_exit"],
        market_type=r["market_type"],epoch=r["epoch"],side=r["side"],
        entry_price=r["entry_price"],exit_price=r["exit_price"],
        shares=r["shares"],cost=r["cost"],fee=r["fee"],
        exit_fee=r["exit_fee"] or 0,status=r["status"],
        exit_reason=r["exit_reason"],pnl=r["pnl"],
        resolved_at=r["resolved_at"],outcome=r["outcome"],
        signal_delta=r["signal_delta"] or 0,
        signal_velocity=r["signal_velocity"] or 0,
        signal_volatility=r["signal_volatility"] or 0,
        signal_ask=r["signal_ask"] or 0,
        signal_elapsed=r["signal_elapsed"] or 0)

async def get_orders_for_bot(bot_id, limit=500):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM orders WHERE bot_id=? ORDER BY ts_signal DESC LIMIT ?",
        (bot_id, limit))
    return [_row_to_order(r) for r in await cur.fetchall()]

async def get_pending_orders():
    db = await get_db()
    cur = await db.execute("SELECT * FROM orders WHERE status IN ('PENDING','FILLED')")
    return [_row_to_order(r) for r in await cur.fetchall()]

async def get_open_orders_for_bot(bot_id):
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM orders WHERE bot_id=? AND status IN ('PENDING','FILLED')",
        (bot_id,))
    return [_row_to_order(r) for r in await cur.fetchall()]

async def get_orders_for_bot_today(bot_id):
    midnight = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=0,minute=0,second=0,microsecond=0).timestamp()
    db = await get_db()
    cur = await db.execute(
        "SELECT * FROM orders WHERE bot_id=? AND ts_signal>=?",
        (bot_id, midnight))
    return [_row_to_order(r) for r in await cur.fetchall()]

async def delete_orders_for_bot(bot_id):
    db = await get_db()
    await db.execute("DELETE FROM orders WHERE bot_id=?", (bot_id,))
    await db.execute("DELETE FROM balance_history WHERE bot_id=?", (bot_id,))
    await db.commit()