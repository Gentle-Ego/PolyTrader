"""
Bot Optimizer — grid search / random search over parameter space.

Usage flow:
  1. User defines parameter RANGES in the UI
  2. System generates N bot configs (grid or random sampling)
  3. Each config is backtested against stored historical snapshots
  4. Results ranked by chosen metric (PnL, Sharpe, PF, etc.)
  5. User can promote any winner to a live paper bot with one click

All backtesting happens in-memory — no DB writes, no side effects.
"""
from __future__ import annotations
import itertools, random, time, logging, math, statistics
from typing import Optional
from pydantic import BaseModel, Field

from models import (
    BotConfig, PaperOrder, MarketSnapshot,
    OrderSide, OrderStatus, MarketType, ExitReason,
)
from config import SHARE_PAYOUT, INTERVALS

log = logging.getLogger("optimizer")


# ═══════════════════════════════════════════════════════════════
# PARAMETER RANGE DEFINITION
# ═══════════════════════════════════════════════════════════════

class ParamRange(BaseModel):
    """One axis in the search space."""
    field: str                        # BotConfig field name
    values: list = []                 # explicit list of values to try
    min_val: Optional[float] = None   # or generate from range
    max_val: Optional[float] = None
    step: Optional[float] = None
    is_int: bool = False

    def expand(self) -> list:
        if self.values:
            return self.values
        if self.min_val is not None and self.max_val is not None and self.step:
            vals = []
            v = self.min_val
            while v <= self.max_val + 1e-9:
                vals.append(int(v) if self.is_int else round(v, 6))
                v += self.step
            return vals
        return []


class OptimizeRequest(BaseModel):
    """What the user sends from the UI."""
    name_prefix: str = "Opt"
    base_config: dict = {}            # fixed fields (side, market_type, etc.)
    ranges: list[ParamRange] = []     # which fields to sweep
    method: str = "grid"              # "grid" or "random"
    max_combinations: int = 200       # cap for random mode
    rank_by: str = "net_pnl"          # net_pnl | sharpe | profit_factor | expectancy | roi_pct
    min_orders: int = 5               # skip configs with fewer resolved orders
    days_back: int = 7                # limit time window to avoid OOM


class BacktestResult(BaseModel):
    config: dict
    total_orders: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0
    net_pnl: float = 0
    gross_profit: float = 0
    gross_loss: float = 0
    profit_factor: float = 0
    sharpe_ratio: float = 0
    max_drawdown_pct: float = 0
    expectancy: float = 0
    roi_pct: float = 0
    avg_entry_price: float = 0


class OptimizeResponse(BaseModel):
    total_tested: int
    total_passed: int               # met min_orders threshold
    duration_ms: float
    results: list[BacktestResult]   # sorted by rank_by, top 50


# ═══════════════════════════════════════════════════════════════
# COMBINATION GENERATOR
# ═══════════════════════════════════════════════════════════════

def _generate_configs(req: OptimizeRequest) -> list[dict]:
    """Expand parameter ranges into concrete BotConfig dicts."""
    axes = []
    keys = []
    for pr in req.ranges:
        expanded = pr.expand()
        if expanded:
            axes.append(expanded)
            keys.append(pr.field)

    if not axes:
        return [req.base_config.copy()]

    if req.method == "grid":
        combos = list(itertools.product(*axes))
        if len(combos) > req.max_combinations:
            combos = random.sample(combos, req.max_combinations)
    else:
        # Random sampling
        combos = []
        for _ in range(req.max_combinations):
            combo = tuple(random.choice(ax) for ax in axes)
            combos.append(combo)

    configs = []
    for combo in combos:
        cfg = req.base_config.copy()
        for k, v in zip(keys, combo):
            cfg[k] = v
        configs.append(cfg)

    return configs


# ═══════════════════════════════════════════════════════════════
# IN-MEMORY BACKTESTER (no DB writes)
# ═══════════════════════════════════════════════════════════════

def _in_range(val, lo, hi) -> bool:
    if val is None:
        return False
    if lo is not None and val < lo:
        return False
    if hi is not None and val > hi:
        return False
    return True


def _backtest_single(
    cfg_dict: dict,
    snapshots_by_epoch: dict[tuple[int, str], list[dict]],
    resolutions: dict[tuple[int, str], str],
) -> BacktestResult:
    """
    Run one bot config against all historical snapshots, purely in-memory.
    Returns performance metrics.
    """
    try:
        bot = BotConfig(**cfg_dict)
    except Exception:
        return BacktestResult(config=cfg_dict)

    balance = bot.balance
    peak = balance
    orders = []           # list of (cost, fee, side, epoch, mtype, entry_price, shares)
    entry_prices = []

    # Track per-round
    round_count: dict[tuple, int] = {}
    round_last_ts: dict[tuple, float] = {}

    for (epoch, mtype), snaps in sorted(snapshots_by_epoch.items()):
        if bot.market_type != MarketType.BOTH and mtype != bot.market_type.value:
            continue

        interval_s = INTERVALS.get(mtype, 300)

        for snap in snaps:
            elapsed = snap.get("time_elapsed_s", 0) or 0
            if elapsed < bot.min_entry_time_s or elapsed > bot.max_entry_time_s:
                continue

            # Session filter
            if bot.session_start_utc is not None and bot.session_end_utc is not None:
                import datetime
                h = datetime.datetime.utcfromtimestamp(snap.get("ts", 0)).hour
                if bot.session_start_utc <= bot.session_end_utc:
                    if not (bot.session_start_utc <= h < bot.session_end_utc):
                        continue
                else:
                    if not (h >= bot.session_start_utc or h < bot.session_end_utc):
                        continue

            key = (epoch, mtype)

            # Round limits
            if not bot.multiple_orders:
                if round_count.get(key, 0) >= 1:
                    continue
            else:
                if round_count.get(key, 0) >= bot.max_orders_per_round:
                    continue
                last = round_last_ts.get(key, 0)
                snap_ts = snap.get("ts", 0)
                if last > 0 and (snap_ts - last) < bot.cooldown_s:
                    continue

            # Entry price
            entry = snap.get("ask_up") if bot.side == OrderSide.UP else snap.get("ask_down")
            if not entry or entry <= 0:
                continue
            eff = min(entry * (1 + bot.slippage_pct / 100), 0.99)
            cost = eff * bot.shares_per_order
            fee = cost * (bot.taker_fee_pct / 100)

            if balance < cost + fee:
                continue

            # Delta
            delta = snap.get("delta_pct", 0) or 0
            eff_d = delta if bot.side == OrderSide.UP else -delta
            if not _in_range(eff_d, bot.delta_pct_min, bot.delta_pct_max):
                continue

            # Velocity
            if bot.delta_velocity_min is not None or bot.delta_velocity_max is not None:
                vel = snap.get("delta_velocity", 0) or 0
                ev = vel if bot.side == OrderSide.UP else -vel
                if not _in_range(ev, bot.delta_velocity_min, bot.delta_velocity_max):
                    continue

            # Book filters
            if (bot.ask_up_min is not None or bot.ask_up_max is not None):
                if not _in_range(snap.get("ask_up"), bot.ask_up_min, bot.ask_up_max):
                    continue
            if (bot.ask_down_min is not None or bot.ask_down_max is not None):
                if not _in_range(snap.get("ask_down"), bot.ask_down_min, bot.ask_down_max):
                    continue
            if (bot.bid_up_min is not None or bot.bid_up_max is not None):
                if not _in_range(snap.get("bid_up"), bot.bid_up_min, bot.bid_up_max):
                    continue
            if (bot.bid_down_min is not None or bot.bid_down_max is not None):
                if not _in_range(snap.get("bid_down"), bot.bid_down_min, bot.bid_down_max):
                    continue

            # Spread
            if bot.spread_max is not None:
                sp = snap.get("spread_up") if bot.side == OrderSide.UP else snap.get("spread_down")
                if sp is None or sp > bot.spread_max:
                    continue

            # ORDER
            balance -= (cost + fee)
            round_count[key] = round_count.get(key, 0) + 1
            round_last_ts[key] = snap.get("ts", 0)
            orders.append((cost, fee, bot.side.value, epoch, mtype, eff, bot.shares_per_order))
            entry_prices.append(eff)

    # Resolve all orders
    wins = losses = 0
    gp = gl = 0.0
    pnl_list = []
    for cost, fee, side, epoch, mtype, ep, shares in orders:
        res_key = (epoch, mtype)
        outcome = resolutions.get(res_key)
        if outcome is None:
            # Unresolved — refund
            balance += cost + fee
            continue

        won = side == outcome
        if won:
            payout = SHARE_PAYOUT * shares
            pnl = payout - cost - fee
            balance += payout
            wins += 1
            gp += pnl
        else:
            pnl = -(cost + fee)
            losses += 1
            gl += abs(pnl)

        pnl_list.append(pnl)
        peak = max(peak, balance)

    total = wins + losses
    wr = (wins / total * 100) if total else 0
    pf = (gp / gl) if gl > 0 else (9999 if gp > 0 else 0)
    net = gp - gl

    # Sharpe
    sharpe = 0
    if len(pnl_list) >= 2:
        m = statistics.mean(pnl_list)
        s = statistics.stdev(pnl_list)
        sharpe = m / s if s > 0 else 0

    # Max drawdown
    bal = bot.balance
    pk = bot.balance
    mdd = 0
    for p in pnl_list:
        bal += p
        pk = max(pk, bal)
        if pk > 0:
            mdd = max(mdd, (pk - bal) / pk * 100)

    # Expectancy
    aw = gp / wins if wins else 0
    al = gl / losses if losses else 0
    exp = (wr / 100 * aw) - ((1 - wr / 100) * al) if total else 0

    return BacktestResult(
        config=cfg_dict,
        total_orders=total,
        wins=wins,
        losses=losses,
        win_rate=round(wr, 2),
        net_pnl=round(net, 4),
        gross_profit=round(gp, 4),
        gross_loss=round(gl, 4),
        profit_factor=round(pf, 4),
        sharpe_ratio=round(sharpe, 4),
        max_drawdown_pct=round(mdd, 2),
        expectancy=round(exp, 4),
        roi_pct=round(net / bot.balance * 100, 2) if bot.balance else 0,
        avg_entry_price=round(statistics.mean(entry_prices), 4) if entry_prices else 0,
    )


# ═══════════════════════════════════════════════════════════════
# MAIN OPTIMIZER ENTRY POINT
# ═══════════════════════════════════════════════════════════════

async def run_optimization(
    req: OptimizeRequest,
    snapshots_by_epoch: dict[tuple[int, str], list[dict]],
    resolutions: dict[tuple[int, str], str],
) -> OptimizeResponse:
    """
    Called from the API. Generates configs, backtests each, ranks results.
    """
    t0 = time.time()

    configs = _generate_configs(req)
    log.info(f"Optimizer: testing {len(configs)} configs against {len(snapshots_by_epoch)} epochs")

    results = []
    for cfg in configs:
        r = _backtest_single(cfg, snapshots_by_epoch, resolutions)
        results.append(r)

    # Filter by min_orders
    passed = [r for r in results if r.total_orders >= req.min_orders]

    # Sort
    rank_field = req.rank_by
    passed.sort(key=lambda r: getattr(r, rank_field, 0), reverse=True)

    elapsed_ms = (time.time() - t0) * 1000

    return OptimizeResponse(
        total_tested=len(results),
        total_passed=len(passed),
        duration_ms=round(elapsed_ms, 1),
        results=passed[:50],
    )