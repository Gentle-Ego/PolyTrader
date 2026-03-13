"""
Market & bot analytics — computed from stored data.

Provides:
 - Market statistics (UP/DOWN distribution, avg delta, etc.)
 - Time-of-day performance heatmaps
 - Parameter correlation analysis
 - Balance history tracking
"""
from __future__ import annotations
import time, datetime, statistics, logging, math
from collections import defaultdict
from typing import Optional

import database as db

log = logging.getLogger("analytics")


# ═══════════════════════════════════════════════════════════════
# MARKET STATISTICS
# ═══════════════════════════════════════════════════════════════

async def compute_market_stats() -> dict:
    """
    Aggregate stats across all resolved markets.
    """
    results = await db.get_market_results(limit=5000)
    if not results:
        return {"total": 0}

    total = len(results)
    ups = [r for r in results if r["outcome"] == "UP"]
    downs = [r for r in results if r["outcome"] == "DOWN"]

    deltas = []
    for r in results:
        if r["target_price"] and r["close_price"] and r["target_price"] > 0:
            d = (r["close_price"] - r["target_price"]) / r["target_price"] * 100
            deltas.append(d)

    # By market type
    by_type = defaultdict(lambda: {"total": 0, "up": 0, "down": 0})
    for r in results:
        mt = r.get("market_type", "5m")
        by_type[mt]["total"] += 1
        if r["outcome"] == "UP":
            by_type[mt]["up"] += 1
        else:
            by_type[mt]["down"] += 1

    # By hour of day
    by_hour = defaultdict(lambda: {"total": 0, "up": 0, "down": 0})
    for r in results:
        if r.get("resolved_at"):
            h = datetime.datetime.utcfromtimestamp(r["resolved_at"]).hour
            by_hour[h]["total"] += 1
            if r["outcome"] == "UP":
                by_hour[h]["up"] += 1
            else:
                by_hour[h]["down"] += 1

    # By day of week
    by_dow = defaultdict(lambda: {"total": 0, "up": 0, "down": 0})
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for r in results:
        if r.get("resolved_at"):
            dow = datetime.datetime.utcfromtimestamp(r["resolved_at"]).weekday()
            by_dow[dow_names[dow]]["total"] += 1
            if r["outcome"] == "UP":
                by_dow[dow_names[dow]]["up"] += 1
            else:
                by_dow[dow_names[dow]]["down"] += 1

    return {
        "total": total,
        "up_count": len(ups),
        "down_count": len(downs),
        "up_pct": round(len(ups) / total * 100, 1) if total else 0,
        "down_pct": round(len(downs) / total * 100, 1) if total else 0,
        "avg_delta": round(statistics.mean(deltas), 4) if deltas else 0,
        "median_delta": round(statistics.median(deltas), 4) if deltas else 0,
        "std_delta": round(statistics.stdev(deltas), 4) if len(deltas) >= 2 else 0,
        "by_type": dict(by_type),
        "by_hour": {str(h): v for h, v in sorted(by_hour.items())},
        "by_day_of_week": dict(by_dow),
    }


# ═══════════════════════════════════════════════════════════════
# TIME-OF-DAY PERFORMANCE FOR A BOT
# ═══════════════════════════════════════════════════════════════

async def bot_time_analysis(bot_id: str) -> dict:
    """
    Break down a bot's performance by hour of day.
    """
    orders = await db.get_orders_for_bot(bot_id, 50000)
    resolved = [o for o in orders if o.status in ("WIN", "LOSS", "EARLY_EXIT")]

    by_hour = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
    for o in resolved:
        if o.ts_signal:
            h = datetime.datetime.utcfromtimestamp(o.ts_signal).hour
            by_hour[h]["trades"] += 1
            if o.pnl > 0:
                by_hour[h]["wins"] += 1
            by_hour[h]["pnl"] += o.pnl

    result = {}
    for h in range(24):
        d = by_hour[h]
        wr = (d["wins"] / d["trades"] * 100) if d["trades"] else 0
        result[str(h)] = {
            "trades": d["trades"],
            "wins": d["wins"],
            "win_rate": round(wr, 1),
            "pnl": round(d["pnl"], 4),
        }
    return result


# ═══════════════════════════════════════════════════════════════
# SNAPSHOT CONDITION ANALYSIS
# ═══════════════════════════════════════════════════════════════

async def snapshot_outcome_correlation(market_type: str = "5m", limit: int = 2000) -> dict:
    """
    For each resolved epoch, grab the snapshot at ~30s and ~60s elapsed,
    and compute: what was ask_up / delta_pct at that time, and did UP win?
    Useful for seeing "when ask_up < 0.55 at 30s, UP wins X% of the time."
    """
    results = await db.get_market_results(limit=limit)
    res_map = {(r["epoch"], r["market_type"]): r["outcome"] for r in results}

    buckets = {
        "ask_up_below_50": {"total": 0, "up_wins": 0},
        "ask_up_50_60": {"total": 0, "up_wins": 0},
        "ask_up_60_70": {"total": 0, "up_wins": 0},
        "ask_up_above_70": {"total": 0, "up_wins": 0},
        "delta_positive": {"total": 0, "up_wins": 0},
        "delta_negative": {"total": 0, "up_wins": 0},
        "delta_above_005": {"total": 0, "up_wins": 0},
        "delta_above_010": {"total": 0, "up_wins": 0},
    }

    # Grab snapshots for early in each epoch
    dbase = await db.get_db()
    cur = await dbase.execute(
        """SELECT epoch, market_type, ask_up, delta_pct, time_elapsed_s
           FROM snapshots
           WHERE market_type = ? AND time_elapsed_s BETWEEN 25 AND 65
           ORDER BY epoch, time_elapsed_s""",
        (market_type,),
    )
    rows = await cur.fetchall()

    seen_epochs = set()
    for row in rows:
        key = (row["epoch"], row["market_type"])
        if key in seen_epochs:
            continue
        seen_epochs.add(key)

        outcome = res_map.get(key)
        if not outcome:
            continue

        ask_up = row["ask_up"]
        delta = row["delta_pct"]
        up_won = outcome == "UP"

        if ask_up is not None:
            if ask_up < 0.50:
                buckets["ask_up_below_50"]["total"] += 1
                if up_won: buckets["ask_up_below_50"]["up_wins"] += 1
            elif ask_up < 0.60:
                buckets["ask_up_50_60"]["total"] += 1
                if up_won: buckets["ask_up_50_60"]["up_wins"] += 1
            elif ask_up < 0.70:
                buckets["ask_up_60_70"]["total"] += 1
                if up_won: buckets["ask_up_60_70"]["up_wins"] += 1
            else:
                buckets["ask_up_above_70"]["total"] += 1
                if up_won: buckets["ask_up_above_70"]["up_wins"] += 1

        if delta is not None:
            if delta > 0:
                buckets["delta_positive"]["total"] += 1
                if up_won: buckets["delta_positive"]["up_wins"] += 1
            else:
                buckets["delta_negative"]["total"] += 1
                if up_won: buckets["delta_negative"]["up_wins"] += 1
            if delta > 0.05:
                buckets["delta_above_005"]["total"] += 1
                if up_won: buckets["delta_above_005"]["up_wins"] += 1
            if delta > 0.10:
                buckets["delta_above_010"]["total"] += 1
                if up_won: buckets["delta_above_010"]["up_wins"] += 1

    # Compute percentages
    output = {}
    for k, v in buckets.items():
        output[k] = {
            "total": v["total"],
            "up_wins": v["up_wins"],
            "up_win_pct": round(v["up_wins"] / v["total"] * 100, 1) if v["total"] else 0,
        }

    return output


# ═══════════════════════════════════════════════════════════════
# BALANCE HISTORY TRACKER
# ═══════════════════════════════════════════════════════════════

async def record_balance_snapshots(bot_balances: dict[str, float]):
    """
    Called periodically (every 5 min) to persist a balance snapshot
    for every active bot. Stored in balance_history table.
    """
    dbase = await db.get_db()
    now = time.time()
    for bot_id, balance in bot_balances.items():
        await dbase.execute(
            "INSERT INTO balance_history (bot_id, ts, balance) VALUES (?,?,?)",
            (bot_id, now, round(balance, 4)),
        )
    await dbase.commit()


async def get_balance_history(bot_id: str, hours: float = 24) -> list[dict]:
    """Retrieve balance snapshots for a bot over the last N hours."""
    cutoff = time.time() - (hours * 3600)
    dbase = await db.get_db()
    cur = await dbase.execute(
        """SELECT ts, balance FROM balance_history
           WHERE bot_id = ? AND ts >= ?
           ORDER BY ts ASC""",
        (bot_id, cutoff),
    )
    rows = await cur.fetchall()
    return [{"ts": r["ts"], "balance": r["balance"]} for r in rows]


async def get_all_balances_history(hours: float = 24) -> dict[str, list[dict]]:
    """All bots' balance history for overlay chart."""
    cutoff = time.time() - (hours * 3600)
    dbase = await db.get_db()
    cur = await dbase.execute(
        """SELECT bot_id, ts, balance FROM balance_history
           WHERE ts >= ? ORDER BY ts ASC""",
        (cutoff,),
    )
    rows = await cur.fetchall()
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["bot_id"]].append({"ts": r["ts"], "balance": r["balance"]})
    return dict(out)