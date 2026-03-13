from __future__ import annotations
import time, datetime, logging, statistics, math
from typing import Optional

from models import (
    BotConfig, PaperOrder, MarketSnapshot,
    OrderSide, OrderStatus, MarketType, BotStats, ExitReason,
)
from config import SHARE_PAYOUT
import bot_storage, database as db

log = logging.getLogger("bot_engine")

_bots: dict[str, BotConfig] = {}
_balances: dict[str, float] = {}
_peak_balances: dict[str, float] = {}
_pause_reasons: dict[str, str | None] = {}
_round_orders: dict[str, dict[tuple, int]] = {}
_round_last_ts: dict[str, dict[tuple, float]] = {}
_consecutive_losses: dict[str, int] = {}
_consecutive_wins: dict[str, int] = {}     # NEW
_orders_today: dict[str, int] = {}
_loss_today: dict[str, float] = {}
_total_resolved_orders: dict[str, int] = {}
_stats_cache: dict[str, BotStats] = {}


async def boot():
    bots = bot_storage.load_all()
    for b in bots:
        _register_runtime(b)
    
    for bot_id, bot in _bots.items():
        # Fetch ALL orders (limit=None)
        orders = await db.get_orders_for_bot(bot_id, None) 
        
        bal = bot.balance; peak = bot.balance; cl = 0; cw = 0
        
        # REMOVED sorted() - The DB already sorted them for us!
        for o in orders:
            if o.status == OrderStatus.RESOLVED_WIN:
                bal = bal - o.cost - o.fee + o.shares * SHARE_PAYOUT
                cl = 0; cw += 1
            elif o.status == OrderStatus.RESOLVED_LOSS:
                bal = bal - o.cost - o.fee; cl += 1; cw = 0
            elif o.status == OrderStatus.EARLY_EXIT:
                rev = (o.exit_price or 0) * o.shares
                bal = bal - o.cost - o.fee - o.exit_fee + rev
                if o.pnl >= 0: cl = 0; cw += 1
                else: cl += 1; cw = 0
            elif o.status == OrderStatus.FILLED:
                bal -= (o.cost + o.fee)
            
            peak = max(peak, bal)
            _round_orders[bot_id][(o.epoch, o.market_type)] = \
                _round_orders[bot_id].get((o.epoch, o.market_type), 0) + 1
        
        # Logic Fix: If 'orders' is everything, we don't need to fetch 'today_ords' 
        # separately to calculate resolved counts. This saves a DB hit.
        resolved = [o for o in orders if o.status in (OrderStatus.RESOLVED_WIN, OrderStatus.RESOLVED_LOSS, OrderStatus.EARLY_EXIT)]
        
        # We still need today_ords for the daily limit/loss tracking
        today_ords = await db.get_orders_for_bot_today(bot_id)
        _orders_today[bot_id] = len(today_ords)
        _loss_today[bot_id] = sum(abs(o.pnl) for o in today_ords if o.status in (OrderStatus.RESOLVED_LOSS, OrderStatus.EARLY_EXIT) and o.pnl < 0)
        
        _total_resolved_orders[bot_id] = len(resolved)
        _balances[bot_id] = bal; _peak_balances[bot_id] = peak
        _consecutive_losses[bot_id] = cl; _consecutive_wins[bot_id] = cw
        
        log.info(f"Loaded «{bot.name}» (Lifetime) bal=${bal:.2f} streak=+{cw}/-{cl}")
    

def _register_runtime(cfg):
    _bots[cfg.id] = cfg
    _balances.setdefault(cfg.id, cfg.balance)
    _peak_balances.setdefault(cfg.id, cfg.balance)
    _round_orders.setdefault(cfg.id, {})
    _round_last_ts.setdefault(cfg.id, {})
    _consecutive_losses.setdefault(cfg.id, 0)
    _consecutive_wins.setdefault(cfg.id, 0)
    _pause_reasons.setdefault(cfg.id, None)
    _orders_today.setdefault(cfg.id, 0)
    _loss_today.setdefault(cfg.id, 0.0)
    _total_resolved_orders.setdefault(cfg.id, 0)

def register_bot(cfg):
    _bots[cfg.id] = cfg
    _balances[cfg.id] = cfg.balance
    _peak_balances[cfg.id] = cfg.balance
    _round_orders[cfg.id] = {}; _round_last_ts[cfg.id] = {}
    _consecutive_losses[cfg.id] = 0; _consecutive_wins[cfg.id] = 0
    _pause_reasons[cfg.id] = None
    _orders_today[cfg.id] = 0
    _loss_today[cfg.id] = 0.0
    _total_resolved_orders[cfg.id] = 0
    _stats_cache.pop(cfg.id, None)
    bot_storage.save_bot(cfg)

def remove_bot(bot_id):
    for d in (_bots,_balances,_peak_balances,_round_orders,
              _round_last_ts,_consecutive_losses,_consecutive_wins,_pause_reasons,
              _orders_today,_loss_today,_total_resolved_orders,_stats_cache):
        d.pop(bot_id, None)
    bot_storage.delete_bot(bot_id)

def get_bot(bot_id): return _bots.get(bot_id)
def list_bots(): return list(_bots.values())
def get_balances(): return dict(_balances)

def _in_range(val, lo, hi):
    if val is None: return False
    if lo is not None and val < lo: return False
    if hi is not None and val > hi: return False
    return True


def _compute_shares(bot: BotConfig, bot_id: str) -> float:
    """Adaptive sizing based on streak."""
    base = bot.shares_per_order
    if not bot.streak_scaling:
        return base
    cw = _consecutive_wins.get(bot_id, 0)
    cl = _consecutive_losses.get(bot_id, 0)
    adjusted = base + (cw * bot.streak_win_bonus) - (cl * bot.streak_loss_reduce)
    return max(bot.min_shares, min(bot.max_shares, adjusted))


async def _check_auto_disable(bot: BotConfig, bot_id: str) -> str | None:
    """Check if bot should be auto-disabled using fast in-memory limits."""
    res_count = _total_resolved_orders.get(bot_id, 0)
    if bot.auto_disable_after is not None and res_count >= bot.auto_disable_after:
        return f"Auto-disabled after {bot.auto_disable_after} orders"
    if bot.auto_disable_if_roi_below is not None and res_count >= bot.auto_disable_min_orders:
        net = (_balances.get(bot_id, bot.balance) - bot.balance)
        roi = (net / bot.balance * 100) if bot.balance else 0
        if roi < bot.auto_disable_if_roi_below:
            return f"ROI {roi:.1f}% below threshold {bot.auto_disable_if_roi_below}%"
    return None


def _check_risk(bot, bid, n_open, today_count, today_loss):
    if bot.max_daily_loss is not None and today_loss >= bot.max_daily_loss:
        return f"Daily loss ${bot.max_daily_loss} reached"
    if bot.max_drawdown_pct is not None:
        peak = _peak_balances.get(bid, bot.balance)
        bal = _balances.get(bid, 0)
        if peak > 0 and (peak - bal) / peak * 100 >= bot.max_drawdown_pct:
            return f"Max drawdown {bot.max_drawdown_pct}%"
    if bot.max_consecutive_losses is not None:
        if _consecutive_losses.get(bid, 0) >= bot.max_consecutive_losses:
            return f"{bot.max_consecutive_losses} consecutive losses"
    if bot.daily_order_limit is not None and today_count >= bot.daily_order_limit:
        return f"Daily limit ({bot.daily_order_limit})"
    if bot.max_open_orders is not None and n_open >= bot.max_open_orders:
        return f"Max open ({bot.max_open_orders})"
    return None


async def evaluate(bot, snap):
    bid = bot.id

    # Auto-disable check
    ad = await _check_auto_disable(bot, bid)
    if ad:
        bot.enabled = False
        bot_storage.save_bot(bot)
        _pause_reasons[bid] = ad
        _stats_cache.pop(bid, None)
        log.info(f"[{bot.name}] AUTO-DISABLED: {ad}")
        return None

    if bot.market_type != MarketType.BOTH and snap.market_type != bot.market_type.value:
        return None

    # Session
    if bot.session_start_utc is not None and bot.session_end_utc is not None:
        h = datetime.datetime.now(datetime.timezone.utc).hour
        if bot.session_start_utc <= bot.session_end_utc:
            if not (bot.session_start_utc <= h < bot.session_end_utc): return None
        else:
            if not (h >= bot.session_start_utc or h < bot.session_end_utc): return None

    elapsed = snap.time_elapsed_s
    if elapsed < bot.min_entry_time_s or elapsed > bot.max_entry_time_s:
        return None

    # Risk
    open_ords = await db.get_open_orders_for_bot(bid)
    today_count = _orders_today.get(bid, 0)
    today_loss = _loss_today.get(bid, 0)
    pr = _check_risk(bot, bid, len(open_ords), today_count, today_loss)
    if pr and _pause_reasons.get(bid) != pr:
        _stats_cache.pop(bid, None)
    _pause_reasons[bid] = pr
    if pr: return None

    # Exposure
    if bot.max_exposure is not None:
        cur_exp = sum(o.cost for o in open_ords)
        ep = snap.ask_up if bot.side == OrderSide.UP else snap.ask_down
        shares = _compute_shares(bot, bid)
        if ep and cur_exp + ep * shares > bot.max_exposure: return None

    # Round limits
    key = (snap.epoch, snap.market_type)
    if not bot.multiple_orders:
        if _round_orders.get(bid, {}).get(key, 0) >= 1: return None
    else:
        if _round_orders.get(bid, {}).get(key, 0) >= bot.max_orders_per_round: return None
        lt = _round_last_ts.get(bid, {}).get(key, 0)
        if lt > 0 and (time.time() - lt) < bot.cooldown_s: return None

    entry = snap.ask_up if bot.side == OrderSide.UP else snap.ask_down
    if not entry or entry <= 0: return None
    eff = min(entry * (1 + bot.slippage_pct / 100), 0.99)
    shares = _compute_shares(bot, bid)
    cost = eff * shares
    fee = cost * (bot.taker_fee_pct / 100)
    if _balances.get(bid, 0) < cost + fee: return None

    # Delta
    ed = snap.delta_pct if bot.side == OrderSide.UP else -snap.delta_pct
    if not _in_range(ed, bot.delta_pct_min, bot.delta_pct_max): return None

    # Velocity
    if bot.delta_velocity_min is not None or bot.delta_velocity_max is not None:
        ev = snap.delta_velocity if bot.side == OrderSide.UP else -snap.delta_velocity
        if not _in_range(ev, bot.delta_velocity_min, bot.delta_velocity_max): return None

    # Volatility
    if bot.volatility_min is not None or bot.volatility_max is not None:
        if not _in_range(snap.volatility_20s, bot.volatility_min, bot.volatility_max):
            return None

    # Book filters
    for field, lo_f, hi_f in [
        ("ask_up", "ask_up_min", "ask_up_max"),
        ("ask_down", "ask_down_min", "ask_down_max"),
        ("bid_up", "bid_up_min", "bid_up_max"),
        ("bid_down", "bid_down_min", "bid_down_max"),
    ]:
        lo = getattr(bot, lo_f); hi = getattr(bot, hi_f)
        if lo is not None or hi is not None:
            if not _in_range(getattr(snap, field), lo, hi): return None

    # Spread
    if bot.spread_max is not None:
        sp = snap.spread_up if bot.side == OrderSide.UP else snap.spread_down
        if sp is None or sp > bot.spread_max: return None

    # CREATE ORDER with signal context
    order = PaperOrder(
        bot_id=bid, ts_signal=time.time(), market_type=snap.market_type,
        epoch=snap.epoch, side=bot.side, entry_price=eff,
        shares=shares, cost=cost, fee=fee, status=OrderStatus.PENDING,
        signal_delta=snap.delta_pct, signal_velocity=snap.delta_velocity,
        signal_volatility=snap.volatility_20s, signal_ask=entry,
        signal_elapsed=elapsed,
    )
    if bot.fill_delay_s and bot.fill_delay_s > 0:
        order.ts_fill = order.ts_signal + bot.fill_delay_s
    else:
        order.ts_fill = order.ts_signal; order.status = OrderStatus.FILLED

    _balances[bid] -= (cost + fee)
    _orders_today[bid] = _orders_today.get(bid, 0) + 1
    _stats_cache.pop(bid, None)
    _round_orders.setdefault(bid, {})[key] = _round_orders.get(bid, {}).get(key, 0) + 1
    _round_last_ts.setdefault(bid, {})[key] = time.time()

    log.info(f"[{bot.name}] SIGNAL {order.side.value}@{eff:.4f}×{shares} "
             f"Δ={snap.delta_pct:.4f}% vol={snap.volatility_20s:.4f}")
    return order


async def process_pending_fills():
    now = time.time()
    for o in await db.get_pending_orders():
        if o.status == OrderStatus.PENDING and o.ts_fill and now >= o.ts_fill:
            o.status = OrderStatus.FILLED
            _stats_cache.pop(o.bot_id, None)
            await db.save_order(o)


async def process_early_exits(snap):
    for bot in _bots.values():
        if not bot.enable_early_exit: continue
        if bot.take_profit_bid is None and bot.stop_loss_bid is None: continue
        for o in await db.get_open_orders_for_bot(bot.id):
            if o.status != OrderStatus.FILLED: continue
            if o.market_type != snap.market_type or o.epoch != snap.epoch: continue
            cb = snap.bid_up if o.side == OrderSide.UP else snap.bid_down
            if cb is None: continue
            reason = None
            if bot.take_profit_bid is not None and cb >= bot.take_profit_bid:
                reason = ExitReason.EARLY_PROFIT.value
            if bot.stop_loss_bid is not None and cb <= bot.stop_loss_bid:
                reason = ExitReason.EARLY_STOP.value
            if not reason: continue
            rev = cb * o.shares; ef = rev * (bot.taker_fee_pct / 100)
            o.status = OrderStatus.EARLY_EXIT; o.exit_price = cb; o.exit_fee = ef
            o.exit_reason = reason; o.pnl = rev - o.cost - o.fee - ef
            o.ts_exit = o.resolved_at = time.time()
            _balances[bot.id] = _balances.get(bot.id, 0) + rev - ef
            _peak_balances[bot.id] = max(_peak_balances.get(bot.id, 0), _balances[bot.id])
            if o.pnl >= 0:
                _consecutive_losses[bot.id] = 0
                _consecutive_wins[bot.id] = _consecutive_wins.get(bot.id, 0) + 1
            else:
                _consecutive_losses[bot.id] = _consecutive_losses.get(bot.id, 0) + 1
                _consecutive_wins[bot.id] = 0
                _loss_today[bot.id] = _loss_today.get(bot.id, 0.0) + abs(o.pnl)
            _total_resolved_orders[bot.id] = _total_resolved_orders.get(bot.id, 0) + 1
            _stats_cache.pop(bot.id, None)
            await db.save_order(o)


async def resolve_orders(epoch, market_type, outcome):
    for o in await db.get_pending_orders():
        if o.epoch != epoch or o.market_type != market_type: continue
        if o.status == OrderStatus.PENDING:
            o.status = OrderStatus.EXPIRED
            _balances[o.bot_id] = _balances.get(o.bot_id, 0) + o.cost + o.fee; o.pnl = 0
        elif o.status == OrderStatus.FILLED:
            if o.side.value == outcome:
                pay = SHARE_PAYOUT * o.shares; o.pnl = pay - o.cost - o.fee
                o.status = OrderStatus.RESOLVED_WIN
                _balances[o.bot_id] = _balances.get(o.bot_id, 0) + pay
                _consecutive_losses[o.bot_id] = 0
                _consecutive_wins[o.bot_id] = _consecutive_wins.get(o.bot_id, 0) + 1
            else:
                o.pnl = -(o.cost + o.fee); o.status = OrderStatus.RESOLVED_LOSS
                _consecutive_losses[o.bot_id] = _consecutive_losses.get(o.bot_id, 0) + 1
                _consecutive_wins[o.bot_id] = 0
                _loss_today[o.bot_id] = _loss_today.get(o.bot_id, 0.0) + abs(o.pnl)
            _total_resolved_orders[o.bot_id] = _total_resolved_orders.get(o.bot_id, 0) + 1
        else: continue
        o.outcome = outcome; o.resolved_at = time.time()
        _peak_balances[o.bot_id] = max(_peak_balances.get(o.bot_id, 0), _balances.get(o.bot_id, 0))
        _stats_cache.pop(o.bot_id, None)
        await db.save_order(o)
    for bid in _bots:
        _round_orders.get(bid, {}).pop((epoch, market_type), None)
        _round_last_ts.get(bid, {}).pop((epoch, market_type), None)


async def compute_stats(bot_id):
    if bot_id in _stats_cache:
        return _stats_cache[bot_id]

    bot = _bots.get(bot_id)
    if not bot: return None
    
    # Fetch all orders for lifetime stats
    orders = await db.get_orders_for_bot(bot_id, None)
    today_ords = await db.get_orders_for_bot_today(bot_id)

    resolved = [o for o in orders if o.status in (OrderStatus.RESOLVED_WIN, OrderStatus.RESOLVED_LOSS, OrderStatus.EARLY_EXIT)]
    pending = [o for o in orders if o.status in (OrderStatus.PENDING, OrderStatus.FILLED)]
    expired = [o for o in orders if o.status == OrderStatus.EXPIRED]
    early = [o for o in orders if o.status == OrderStatus.EARLY_EXIT]

    gp = sum(o.pnl for o in resolved if o.pnl > 0)
    gl = abs(sum(o.pnl for o in resolved if o.pnl < 0))
    nw = len([o for o in resolved if o.pnl > 0])
    nl = len([o for o in resolved if o.pnl < 0])
    tr = nw + nl
    wr = (nw / tr * 100) if tr else 0
    pf = (gp / gl) if gl > 0 else (9999 if gp > 0 else 0)
    net = gp - gl
    fees = sum(o.fee + o.exit_fee for o in orders if o.status != OrderStatus.EXPIRED)
    aw = gp / nw if nw else 0; al = gl / nl if nl else 0
    ap = net / tr if tr else 0
    exp = (wr / 100 * aw) - ((1 - wr / 100) * al) if tr else 0
    pnls = [o.pnl for o in resolved]
    sharpe = (statistics.mean(pnls) / statistics.stdev(pnls)) if len(pnls) >= 2 and statistics.stdev(pnls) > 0 else 0

    streak = best = worst = 0
    for o in sorted(resolved, key=lambda x: x.resolved_at or 0):
        streak = (streak + 1 if streak > 0 else 1) if o.pnl > 0 else (streak - 1 if streak < 0 else -1) if o.pnl < 0 else 0
        best = max(best, streak); worst = min(worst, streak)

    bal = bot.balance; pk = bot.balance; mdd = 0
    for o in sorted(resolved, key=lambda x: x.resolved_at or 0):
        bal += o.pnl; pk = max(pk, bal)
        if pk > 0: mdd = max(mdd, (pk - bal) / pk * 100)

    tl = sum(abs(o.pnl) for o in today_ords if o.pnl < 0 and o.status in (OrderStatus.RESOLVED_LOSS, OrderStatus.EARLY_EXIT))

    stats = BotStats(
        bot_id=bot_id, name=bot.name, enabled=bot.enabled,
        paused_reason=_pause_reasons.get(bot_id),
        started_at=bot.created_at,
        balance=round(_balances.get(bot_id, bot.balance), 4),
        initial_balance=bot.balance,
        peak_balance=round(_peak_balances.get(bot_id, bot.balance), 4),
        total_orders=len(orders), wins=nw, losses=nl,
        early_exits=len(early), pending=len(pending), expired=len(expired),
        win_rate=round(wr, 2), gross_profit=round(gp, 4), gross_loss=round(gl, 4),
        profit_factor=round(pf, 4), net_pnl=round(net, 4), total_fees=round(fees, 4),
        roi_pct=round(net / bot.balance * 100, 2) if bot.balance else 0,
        max_drawdown_pct=round(mdd, 2), avg_win=round(aw, 4), avg_loss=round(al, 4),
        avg_pnl_per_order=round(ap, 4), expectancy=round(exp, 4),
        sharpe_ratio=round(sharpe, 4),
        current_streak=streak, best_streak=best, worst_streak=worst,
        orders_today=len(today_ords), loss_today=round(tl, 4),
        consecutive_losses=_consecutive_losses.get(bot_id, 0),
        orders=orders[-50:], config=bot.model_dump())
    _stats_cache[bot_id] = stats
    return stats
