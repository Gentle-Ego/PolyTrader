"""
Bot Optimizer — grid search / random search over parameter space.

Improved historical simulator:
- mirrors the live collector loop more closely
- supports volatility filter, adaptive sizing, risk caps, exposure, auto-disable
- models pending -> filled -> early-exit -> resolution lifecycle in-memory
- resolves/expirs orders at end of each historical round

Still limited by stored data:
- fill price is still derived from the signal snapshot (to stay aligned with bot_engine)
- fills are activated on the first stored snapshot at/after ts_fill
- no queue-position / depth-of-book microstructure simulation
"""
from __future__ import annotations

import datetime as dt
import itertools
import logging
import math
import random
import statistics
import time
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel

from config import SHARE_PAYOUT
from models import BotConfig, ExitReason, MarketType, OrderSide, OrderStatus

log = logging.getLogger("optimizer")


# ═══════════════════════════════════════════════════════════════
# PARAMETER RANGE DEFINITION
# ═══════════════════════════════════════════════════════════════

class ParamRange(BaseModel):
    """One axis in the search space."""
    field: str
    values: list = []
    min_val: Optional[float] = None
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
    base_config: dict = {}
    ranges: list[ParamRange] = []
    method: str = "grid"              # "grid" or "random"
    max_combinations: int = 200
    rank_by: str = "net_pnl"          # net_pnl | sharpe_ratio | profit_factor | expectancy | roi_pct
    min_orders: int = 5
    days_back: int = 7


class BacktestResult(BaseModel):
    config: dict
    total_orders: int = 0              # resolved wins + losses + early exits
    wins: int = 0
    losses: int = 0
    early_exits: int = 0
    expired: int = 0
    unresolved_refunds: int = 0
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
    ending_balance: float = 0


class OptimizeResponse(BaseModel):
    total_tested: int
    total_passed: int
    duration_ms: float
    results: list[BacktestResult]


# ═══════════════════════════════════════════════════════════════
# INTERNAL SIM TYPES
# ═══════════════════════════════════════════════════════════════

@dataclass
class _SimOrder:
    epoch: int
    market_type: str
    side: str
    status: str
    signal_ts: float
    fill_ts: float
    entry_price: float
    shares: float
    cost: float
    fee: float
    signal_delta: float
    signal_velocity: float
    signal_volatility: float
    signal_ask: float
    signal_elapsed: float
    exit_price: Optional[float] = None
    exit_fee: float = 0.0
    exit_reason: Optional[str] = None
    pnl: float = 0.0


# ═══════════════════════════════════════════════════════════════
# GENERATION HELPERS
# ═══════════════════════════════════════════════════════════════

def _generate_configs(req: OptimizeRequest) -> list[dict]:
    """Expand parameter ranges into concrete BotConfig dicts."""
    axes: list[list] = []
    keys: list[str] = []

    for pr in req.ranges:
        expanded = pr.expand()
        if expanded:
            axes.append(expanded)
            keys.append(pr.field)

    if not axes:
        return [req.base_config.copy()]

    combos: list[tuple]
    if req.method == "grid":
        combos = list(itertools.product(*axes))
        if len(combos) > req.max_combinations:
            combos = random.sample(combos, req.max_combinations)
    else:
        seen: set[tuple] = set()
        combos = []
        max_unique = math.prod(len(ax) for ax in axes)
        target = min(req.max_combinations, max_unique)
        while len(combos) < target:
            combo = tuple(random.choice(ax) for ax in axes)
            if combo not in seen:
                seen.add(combo)
                combos.append(combo)

    configs: list[dict] = []
    for combo in combos:
        cfg = req.base_config.copy()
        for k, v in zip(keys, combo):
            cfg[k] = v
        configs.append(cfg)
    return configs


def _in_range(val, lo, hi) -> bool:
    if val is None:
        return False
    if lo is not None and val < lo:
        return False
    if hi is not None and val > hi:
        return False
    return True


def _utc_day(ts: float) -> dt.date:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date()


# ═══════════════════════════════════════════════════════════════
# SIMULATION HELPERS
# ═══════════════════════════════════════════════════════════════

def _compute_shares(bot: BotConfig, consecutive_wins: int, consecutive_losses: int) -> float:
    base = bot.shares_per_order
    if not bot.streak_scaling:
        return base
    adjusted = base + (consecutive_wins * bot.streak_win_bonus) - (consecutive_losses * bot.streak_loss_reduce)
    return max(bot.min_shares, min(bot.max_shares, adjusted))


def _check_auto_disable(
    bot: BotConfig,
    balance: float,
    resolved_count: int,
) -> Optional[str]:
    if bot.auto_disable_after is not None and resolved_count >= bot.auto_disable_after:
        return f"Auto-disabled after {bot.auto_disable_after} orders"
    if bot.auto_disable_if_roi_below is not None and resolved_count >= bot.auto_disable_min_orders:
        roi = ((balance - bot.balance) / bot.balance * 100) if bot.balance else 0.0
        if roi < bot.auto_disable_if_roi_below:
            return f"ROI {roi:.1f}% below threshold {bot.auto_disable_if_roi_below}%"
    return None


def _check_risk(
    bot: BotConfig,
    balance: float,
    peak_balance: float,
    consecutive_losses: int,
    orders_today: int,
    loss_today: float,
    open_orders_count: int,
) -> Optional[str]:
    if bot.max_daily_loss is not None and loss_today >= bot.max_daily_loss:
        return f"Daily loss ${bot.max_daily_loss} reached"
    if bot.max_drawdown_pct is not None and peak_balance > 0:
        drawdown_pct = (peak_balance - balance) / peak_balance * 100
        if drawdown_pct >= bot.max_drawdown_pct:
            return f"Max drawdown {bot.max_drawdown_pct}%"
    if bot.max_consecutive_losses is not None and consecutive_losses >= bot.max_consecutive_losses:
        return f"{bot.max_consecutive_losses} consecutive losses"
    if bot.daily_order_limit is not None and orders_today >= bot.daily_order_limit:
        return f"Daily limit ({bot.daily_order_limit})"
    if bot.max_open_orders is not None and open_orders_count >= bot.max_open_orders:
        return f"Max open ({bot.max_open_orders})"
    return None


def _update_peak_and_dd(balance: float, peak_balance: float, max_dd: float) -> tuple[float, float]:
    peak_balance = max(peak_balance, balance)
    if peak_balance > 0:
        max_dd = max(max_dd, (peak_balance - balance) / peak_balance * 100)
    return peak_balance, max_dd


def _passes_session(bot: BotConfig, snap_ts: float) -> bool:
    if bot.session_start_utc is None or bot.session_end_utc is None:
        return True
    h = dt.datetime.fromtimestamp(snap_ts, tz=dt.timezone.utc).hour
    if bot.session_start_utc <= bot.session_end_utc:
        return bot.session_start_utc <= h < bot.session_end_utc
    return h >= bot.session_start_utc or h < bot.session_end_utc


def _passes_filters(bot: BotConfig, snap: dict) -> bool:
    elapsed = snap.get("time_elapsed_s", 0) or 0
    if elapsed < bot.min_entry_time_s or elapsed > bot.max_entry_time_s:
        return False

    ed = (snap.get("delta_pct", 0) or 0)
    ed = ed if bot.side == OrderSide.UP else -ed
    if not _in_range(ed, bot.delta_pct_min, bot.delta_pct_max):
        return False

    if bot.delta_velocity_min is not None or bot.delta_velocity_max is not None:
        ev = (snap.get("delta_velocity", 0) or 0)
        ev = ev if bot.side == OrderSide.UP else -ev
        if not _in_range(ev, bot.delta_velocity_min, bot.delta_velocity_max):
            return False

    if bot.volatility_min is not None or bot.volatility_max is not None:
        if not _in_range(snap.get("volatility_20s", 0), bot.volatility_min, bot.volatility_max):
            return False

    for field, lo_f, hi_f in [
        ("ask_up", "ask_up_min", "ask_up_max"),
        ("ask_down", "ask_down_min", "ask_down_max"),
        ("bid_up", "bid_up_min", "bid_up_max"),
        ("bid_down", "bid_down_min", "bid_down_max"),
    ]:
        lo = getattr(bot, lo_f)
        hi = getattr(bot, hi_f)
        if lo is not None or hi is not None:
            if not _in_range(snap.get(field), lo, hi):
                return False

    if bot.spread_max is not None:
        spread = snap.get("spread_up") if bot.side == OrderSide.UP else snap.get("spread_down")
        if spread is None or spread > bot.spread_max:
            return False

    return True


# ═══════════════════════════════════════════════════════════════
# IN-MEMORY BACKTESTER
# ═══════════════════════════════════════════════════════════════

def _backtest_single(
    cfg_dict: dict,
    snapshots_by_epoch: dict[tuple[int, str], list[dict]],
    resolutions: dict[tuple[int, str], str],
) -> BacktestResult:
    try:
        bot = BotConfig(**cfg_dict)
    except Exception:
        return BacktestResult(config=cfg_dict)

    # Flatten all snapshots globally by timestamp so 5m/15m can interact via shared balance/risk.
    events: list[tuple[tuple[int, str], dict]] = []
    for key, snaps in snapshots_by_epoch.items():
        epoch, mtype = key
        if bot.market_type != MarketType.BOTH and mtype != bot.market_type.value:
            continue
        ordered = sorted(snaps, key=lambda s: (s.get("ts", 0), s.get("time_elapsed_s", 0)))
        for snap in ordered:
            events.append((key, snap))
    events.sort(key=lambda item: (item[1].get("ts", 0), item[1].get("market_type", ""), item[1].get("epoch", 0)))

    if not events:
        return BacktestResult(config=cfg_dict)

    last_index_for_key: dict[tuple[int, str], int] = {}
    for idx, (key, _) in enumerate(events):
        last_index_for_key[key] = idx

    balance = bot.balance
    peak_balance = bot.balance
    max_dd = 0.0
    consecutive_wins = 0
    consecutive_losses = 0
    resolved_count = 0
    orders_today = 0
    loss_today = 0.0
    current_day: Optional[dt.date] = None
    paused_reason: Optional[str] = None
    disabled = False

    wins = 0
    losses = 0
    early_exits = 0
    expired = 0
    unresolved_refunds = 0
    gross_profit = 0.0
    gross_loss = 0.0
    pnl_list: list[float] = []
    entry_prices: list[float] = []

    round_count: dict[tuple[int, str], int] = {}
    round_last_ts: dict[tuple[int, str], float] = {}
    open_orders: list[_SimOrder] = []

    def _open_exposure() -> float:
        return sum(o.cost for o in open_orders)

    def _resolve_round(key: tuple[int, str]) -> None:
        nonlocal balance, peak_balance, max_dd
        nonlocal wins, losses, early_exits, expired, unresolved_refunds
        nonlocal consecutive_wins, consecutive_losses, resolved_count, loss_today
        nonlocal gross_profit, gross_loss

        outcome = resolutions.get(key)
        survivors: list[_SimOrder] = []
        for o in open_orders:
            if (o.epoch, o.market_type) != key:
                survivors.append(o)
                continue

            if o.status == OrderStatus.PENDING.value:
                balance += o.cost + o.fee
                peak_balance, max_dd = _update_peak_and_dd(balance, peak_balance, max_dd)
                expired += 1 if outcome is not None else 0
                unresolved_refunds += 1 if outcome is None else 0
                continue

            if o.status == OrderStatus.FILLED.value and outcome is None:
                balance += o.cost + o.fee
                peak_balance, max_dd = _update_peak_and_dd(balance, peak_balance, max_dd)
                unresolved_refunds += 1
                continue

            if o.status == OrderStatus.FILLED.value:
                if o.side == outcome:
                    payout = SHARE_PAYOUT * o.shares
                    pnl = payout - o.cost - o.fee
                    balance += payout
                    wins += 1
                    gross_profit += pnl
                    consecutive_wins += 1
                    consecutive_losses = 0
                else:
                    pnl = -(o.cost + o.fee)
                    losses += 1
                    gross_loss += abs(pnl)
                    consecutive_losses += 1
                    consecutive_wins = 0
                    loss_today += abs(pnl)
                resolved_count += 1
                pnl_list.append(pnl)
                peak_balance, max_dd = _update_peak_and_dd(balance, peak_balance, max_dd)
                continue

            survivors.append(o)

        open_orders[:] = survivors

    for idx, (key, snap) in enumerate(events):
        snap_ts = snap.get("ts", 0) or 0
        snap_day = _utc_day(snap_ts)
        if current_day is None or snap_day != current_day:
            current_day = snap_day
            orders_today = 0
            loss_today = 0.0

        # 1) Early exits first, matching collector loop ordering.
        if bot.enable_early_exit and (bot.take_profit_bid is not None or bot.stop_loss_bid is not None):
            survivors: list[_SimOrder] = []
            for o in open_orders:
                if o.status != OrderStatus.FILLED.value:
                    survivors.append(o)
                    continue
                if o.market_type != snap.get("market_type") or o.epoch != snap.get("epoch"):
                    survivors.append(o)
                    continue

                cur_bid = snap.get("bid_up") if o.side == OrderSide.UP.value else snap.get("bid_down")
                if cur_bid is None:
                    survivors.append(o)
                    continue

                reason = None
                if bot.take_profit_bid is not None and cur_bid >= bot.take_profit_bid:
                    reason = ExitReason.EARLY_PROFIT.value
                if bot.stop_loss_bid is not None and cur_bid <= bot.stop_loss_bid:
                    reason = ExitReason.EARLY_STOP.value

                if not reason:
                    survivors.append(o)
                    continue

                revenue = cur_bid * o.shares
                exit_fee = revenue * (bot.taker_fee_pct / 100)
                pnl = revenue - o.cost - o.fee - exit_fee
                balance += revenue - exit_fee
                peak_balance, max_dd = _update_peak_and_dd(balance, peak_balance, max_dd)

                o.exit_price = cur_bid
                o.exit_fee = exit_fee
                o.exit_reason = reason
                o.pnl = pnl

                early_exits += 1
                resolved_count += 1
                pnl_list.append(pnl)
                if pnl >= 0:
                    wins += 1
                    gross_profit += pnl
                    consecutive_wins += 1
                    consecutive_losses = 0
                else:
                    losses += 1
                    gross_loss += abs(pnl)
                    consecutive_losses += 1
                    consecutive_wins = 0
                    loss_today += abs(pnl)

            open_orders = survivors

        # 2) New signal evaluation.
        if not disabled:
            paused_reason = _check_auto_disable(bot, balance, resolved_count)
            if paused_reason:
                disabled = True

        if not disabled and _passes_session(bot, snap_ts) and _passes_filters(bot, snap):
            open_count = len(open_orders)
            paused_reason = _check_risk(
                bot=bot,
                balance=balance,
                peak_balance=peak_balance,
                consecutive_losses=consecutive_losses,
                orders_today=orders_today,
                loss_today=loss_today,
                open_orders_count=open_count,
            )

            if paused_reason is None:
                round_orders = round_count.get(key, 0)
                last_ts = round_last_ts.get(key, 0)
                if not bot.multiple_orders and round_orders >= 1:
                    paused_reason = "Round order limit"
                elif bot.multiple_orders:
                    if round_orders >= bot.max_orders_per_round:
                        paused_reason = "Round order limit"
                    elif last_ts > 0 and (snap_ts - last_ts) < bot.cooldown_s:
                        paused_reason = "Cooldown"

            shares = _compute_shares(bot, consecutive_wins, consecutive_losses)
            entry = snap.get("ask_up") if bot.side == OrderSide.UP else snap.get("ask_down")
            if paused_reason is None and entry and entry > 0:
                eff = min(entry * (1 + bot.slippage_pct / 100), 0.99)
                cost = eff * shares
                fee = cost * (bot.taker_fee_pct / 100)

                if bot.max_exposure is not None and (_open_exposure() + cost) > bot.max_exposure:
                    paused_reason = "Exposure"

                if paused_reason is None and balance >= cost + fee:
                    fill_delay = max(bot.fill_delay_s or 0.0, 0.0)
                    order = _SimOrder(
                        epoch=snap.get("epoch", 0),
                        market_type=snap.get("market_type", ""),
                        side=bot.side.value,
                        status=OrderStatus.PENDING.value if fill_delay > 0 else OrderStatus.FILLED.value,
                        signal_ts=snap_ts,
                        fill_ts=snap_ts + fill_delay,
                        entry_price=eff,
                        shares=shares,
                        cost=cost,
                        fee=fee,
                        signal_delta=snap.get("delta_pct", 0) or 0,
                        signal_velocity=snap.get("delta_velocity", 0) or 0,
                        signal_volatility=snap.get("volatility_20s", 0) or 0,
                        signal_ask=entry,
                        signal_elapsed=snap.get("time_elapsed_s", 0) or 0,
                    )
                    open_orders.append(order)
                    balance -= (cost + fee)
                    peak_balance, max_dd = _update_peak_and_dd(balance, peak_balance, max_dd)
                    orders_today += 1
                    round_count[key] = round_orders + 1
                    round_last_ts[key] = snap_ts
                    entry_prices.append(eff)

        # 3) Pending fills after evaluation, matching collector loop ordering.
        for o in open_orders:
            if o.status == OrderStatus.PENDING.value and snap_ts >= o.fill_ts:
                o.status = OrderStatus.FILLED.value

        # 4) End-of-round resolution/expiry.
        if idx == last_index_for_key[key]:
            _resolve_round(key)

    # Safety: refund anything still left open (e.g. unresolved latest epochs).
    survivors: list[_SimOrder] = []
    for o in open_orders:
        balance += o.cost + o.fee
        peak_balance, max_dd = _update_peak_and_dd(balance, peak_balance, max_dd)
        unresolved_refunds += 1
    open_orders = survivors

    total_orders = wins + losses + early_exits
    win_rate = (wins / total_orders * 100) if total_orders else 0.0
    net_pnl = balance - bot.balance
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (9999.0 if gross_profit > 0 else 0.0)

    sharpe = 0.0
    if len(pnl_list) >= 2:
        mean_pnl = statistics.mean(pnl_list)
        stdev_pnl = statistics.stdev(pnl_list)
        sharpe = mean_pnl / stdev_pnl if stdev_pnl > 0 else 0.0

    avg_win = gross_profit / wins if wins else 0.0
    avg_loss = gross_loss / losses if losses else 0.0
    expectancy = ((win_rate / 100) * avg_win) - ((1 - win_rate / 100) * avg_loss) if total_orders else 0.0
    roi_pct = (net_pnl / bot.balance * 100) if bot.balance else 0.0

    return BacktestResult(
        config=cfg_dict,
        total_orders=total_orders,
        wins=wins,
        losses=losses,
        early_exits=early_exits,
        expired=expired,
        unresolved_refunds=unresolved_refunds,
        win_rate=round(win_rate, 2),
        net_pnl=round(net_pnl, 4),
        gross_profit=round(gross_profit, 4),
        gross_loss=round(gross_loss, 4),
        profit_factor=round(profit_factor, 4),
        sharpe_ratio=round(sharpe, 4),
        max_drawdown_pct=round(max_dd, 2),
        expectancy=round(expectancy, 4),
        roi_pct=round(roi_pct, 2),
        avg_entry_price=round(statistics.mean(entry_prices), 4) if entry_prices else 0.0,
        ending_balance=round(balance, 4),
    )


# ═══════════════════════════════════════════════════════════════
# MAIN OPTIMIZER ENTRY POINT
# ═══════════════════════════════════════════════════════════════

async def run_optimization(
    req: OptimizeRequest,
    snapshots_by_epoch: dict[tuple[int, str], list[dict]],
    resolutions: dict[tuple[int, str], str],
) -> OptimizeResponse:
    t0 = time.time()
    configs = _generate_configs(req)
    log.info("Optimizer: testing %s configs against %s epochs", len(configs), len(snapshots_by_epoch))

    results = [_backtest_single(cfg, snapshots_by_epoch, resolutions) for cfg in configs]
    passed = [r for r in results if r.total_orders >= req.min_orders]

    rank_field = req.rank_by
    passed.sort(key=lambda r: getattr(r, rank_field, 0), reverse=True)

    elapsed_ms = (time.time() - t0) * 1000
    return OptimizeResponse(
        total_tested=len(results),
        total_passed=len(passed),
        duration_ms=round(elapsed_ms, 1),
        results=passed[:50],
    )
