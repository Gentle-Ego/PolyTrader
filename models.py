"""
All Pydantic models — with new adaptive sizing, volatility filter,
auto-disable, and optimizer types.
"""
from __future__ import annotations
import uuid, time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class MarketType(str, Enum):
    M5 = "5m"; M15 = "15m"; BOTH = "both"

class OrderSide(str, Enum):
    UP = "UP"; DOWN = "DOWN"

class OrderStatus(str, Enum):
    PENDING = "PENDING"; FILLED = "FILLED"; EARLY_EXIT = "EARLY_EXIT"
    RESOLVED_WIN = "WIN"; RESOLVED_LOSS = "LOSS"; EXPIRED = "EXPIRED"

class ExitReason(str, Enum):
    RESOLUTION = "RESOLUTION"; EARLY_PROFIT = "EARLY_PROFIT"; EARLY_STOP = "EARLY_STOP"


class MarketSnapshot(BaseModel):
    ts: float = Field(default_factory=time.time)
    market_type: str
    epoch: int
    btc_price: float
    target_price: float
    delta_pct: float
    delta_velocity: float = 0.0
    volatility_20s: float = 0.0        # NEW: rolling 20s stdev of delta
    ask_up: Optional[float] = None
    bid_up: Optional[float] = None
    ask_down: Optional[float] = None
    bid_down: Optional[float] = None
    spread_up: Optional[float] = None
    spread_down: Optional[float] = None
    mid_up: Optional[float] = None
    mid_down: Optional[float] = None
    time_remaining_s: float
    time_elapsed_s: float = 0.0
    up_token_id: Optional[str] = None
    down_token_id: Optional[str] = None
    condition_id: Optional[str] = None
    resolved: bool = False
    outcome: Optional[str] = None


class BotConfig(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Bot-1"
    enabled: bool = True
    created_at: float = Field(default_factory=time.time)

    side: OrderSide = OrderSide.UP
    market_type: MarketType = MarketType.M5

    min_entry_time_s: float = 0.0
    max_entry_time_s: float = 120.0

    delta_pct_min: Optional[float] = 0.05
    delta_pct_max: Optional[float] = None
    delta_velocity_min: Optional[float] = None
    delta_velocity_max: Optional[float] = None

    # NEW: volatility filter
    volatility_min: Optional[float] = None     # min rolling stdev of delta
    volatility_max: Optional[float] = None     # max — avoid crazy markets

    ask_up_min: Optional[float] = 0.50
    ask_up_max: Optional[float] = 0.70
    ask_down_min: Optional[float] = None
    ask_down_max: Optional[float] = None
    bid_up_min: Optional[float] = None
    bid_up_max: Optional[float] = None
    bid_down_min: Optional[float] = None
    bid_down_max: Optional[float] = None
    spread_max: Optional[float] = None

    session_start_utc: Optional[int] = None
    session_end_utc: Optional[int] = None

    fill_delay_s: Optional[float] = 1.0
    taker_fee_pct: float = 2.0
    slippage_pct: float = 0.0

    shares_per_order: float = 1.0
    multiple_orders: bool = False
    cooldown_s: float = 30.0
    max_orders_per_round: int = 1
    max_open_orders: int = 5

    # NEW: adaptive sizing
    streak_scaling: bool = False           # scale shares based on streak
    streak_win_bonus: float = 0.0          # add this many shares per consecutive win (e.g. 0.5)
    streak_loss_reduce: float = 0.0        # reduce shares per consecutive loss
    min_shares: float = 1.0               # floor
    max_shares: float = 10.0              # ceiling

    balance: float = 100.0
    max_daily_loss: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_consecutive_losses: Optional[int] = None
    daily_order_limit: Optional[int] = None
    max_exposure: Optional[float] = None

    # NEW: auto-disable
    auto_disable_after: Optional[int] = None    # disable after N total orders (for testing)
    auto_disable_if_roi_below: Optional[float] = None  # disable if ROI drops below this %
    auto_disable_min_orders: int = 20           # only check auto-disable after this many

    enable_early_exit: bool = False
    take_profit_bid: Optional[float] = None
    stop_loss_bid: Optional[float] = None


class PaperOrder(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    bot_id: str
    ts_signal: float
    ts_fill: Optional[float] = None
    ts_exit: Optional[float] = None
    market_type: str
    epoch: int
    side: OrderSide
    entry_price: float
    exit_price: Optional[float] = None
    shares: float = 1.0
    cost: float = 0.0
    fee: float = 0.0
    exit_fee: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    exit_reason: Optional[str] = None
    pnl: float = 0.0
    resolved_at: Optional[float] = None
    outcome: Optional[str] = None
    # NEW: snapshot context at signal time
    signal_delta: float = 0.0
    signal_velocity: float = 0.0
    signal_volatility: float = 0.0
    signal_ask: float = 0.0
    signal_elapsed: float = 0.0


class BotStats(BaseModel):
    bot_id: str
    name: str
    enabled: bool
    paused_reason: Optional[str] = None
    started_at: float
    balance: float
    initial_balance: float
    peak_balance: float = 0.0
    total_orders: int = 0
    wins: int = 0
    losses: int = 0
    early_exits: int = 0
    pending: int = 0
    expired: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    net_pnl: float = 0.0
    total_fees: float = 0.0
    roi_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_pnl_per_order: float = 0.0
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    current_streak: int = 0
    best_streak: int = 0
    worst_streak: int = 0
    orders_today: int = 0
    loss_today: float = 0.0
    consecutive_losses: int = 0
    orders: list[PaperOrder] = []
    config: Optional[dict] = None


class CreateBotRequest(BaseModel):
    name: str = "New Bot"
    side: OrderSide = OrderSide.UP
    market_type: MarketType = MarketType.M5
    min_entry_time_s: float = 0.0
    max_entry_time_s: float = 120.0
    delta_pct_min: Optional[float] = 0.05
    delta_pct_max: Optional[float] = None
    delta_velocity_min: Optional[float] = None
    delta_velocity_max: Optional[float] = None
    volatility_min: Optional[float] = None
    volatility_max: Optional[float] = None
    ask_up_min: Optional[float] = 0.50
    ask_up_max: Optional[float] = 0.70
    ask_down_min: Optional[float] = None
    ask_down_max: Optional[float] = None
    bid_up_min: Optional[float] = None
    bid_up_max: Optional[float] = None
    bid_down_min: Optional[float] = None
    bid_down_max: Optional[float] = None
    spread_max: Optional[float] = None
    session_start_utc: Optional[int] = None
    session_end_utc: Optional[int] = None
    fill_delay_s: Optional[float] = 1.0
    taker_fee_pct: float = 2.0
    slippage_pct: float = 0.0
    shares_per_order: float = 1.0
    multiple_orders: bool = False
    cooldown_s: float = 30.0
    max_orders_per_round: int = 1
    max_open_orders: int = 5
    streak_scaling: bool = False
    streak_win_bonus: float = 0.0
    streak_loss_reduce: float = 0.0
    min_shares: float = 1.0
    max_shares: float = 10.0
    balance: float = 100.0
    max_daily_loss: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_consecutive_losses: Optional[int] = None
    daily_order_limit: Optional[int] = None
    max_exposure: Optional[float] = None
    auto_disable_after: Optional[int] = None
    auto_disable_if_roi_below: Optional[float] = None
    auto_disable_min_orders: int = 20
    enable_early_exit: bool = False
    take_profit_bid: Optional[float] = None
    stop_loss_bid: Optional[float] = None