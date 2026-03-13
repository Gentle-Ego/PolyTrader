<p align="center">
  <h1 align="center">⚡ Polymarket Paper Trader v3</h1>
  <p align="center">
    A full-stack paper trading system for <b>Polymarket BTC Up/Down prediction markets</b>.<br>
    Monitors live 5‑minute and 15‑minute Bitcoin markets in real time, runs unlimited
    configurable bots against them, tracks every order with realistic execution simulation
    (fill delay, taker fees, slippage), and provides a rich analytics dashboard — all
    without risking a single dollar.
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/License-MIT-F7DF1E?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/SQLite-WAL_Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite">
</p>

---

## 📑 Table of Contents

- [What It Does](#-what-it-does)
- [How The Markets Work](#-how-the-markets-work)
- [Features](#-features)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Using The Dashboard](#-using-the-dashboard)
  - [Market Panels](#market-panels)
  - [Creating a Bot](#creating-a-bot)
  - [Bot Cards](#bot-cards)
  - [Bot Detail View](#bot-detail-view)
  - [Leaderboard](#leaderboard)
  - [Market Statistics](#market-statistics)
  - [Strategy Optimizer](#strategy-optimizer)
- [Bot Parameters — Full Reference](#-bot-parameters--full-reference)
  - [Core Settings](#core-settings)
  - [Entry Timing](#entry-timing)
  - [Delta Filters](#delta-filters)
  - [Order Book Filters](#order-book-filters)
  - [Execution Realism](#execution-realism)
  - [Multiple Orders](#multiple-orders)
  - [Adaptive Sizing](#adaptive-sizing)
  - [Risk Management](#risk-management)
  - [Early Exit](#early-exit)
- [The Two Starter Bots](#-the-two-starter-bots)
- [The Optimizer — How To Use It](#-the-optimizer--how-to-use-it)
- [Data Collection & Storage](#-data-collection--storage)
- [API Reference](#-api-reference)
- [How It Works Under The Hood](#-how-it-works-under-the-hood)
  - [1. Market Discovery](#1-market-discovery)
  - [2. Snapshot Collection](#2-snapshot-collection)
  - [3. Bot Evaluation](#3-bot-evaluation)
  - [4. Order Lifecycle](#4-order-lifecycle)
  - [5. Resolution](#5-resolution)
  - [6. Analytics Computation](#6-analytics-computation)
- [Persistence Model](#-persistence-model)
- [Configuration](#-configuration)
- [Tips & Strategy Notes](#-tips--strategy-notes)
- [Troubleshooting](#-troubleshooting)

---

## 🎯 What It Does

Every 5 minutes (and every 15 minutes), Polymarket opens a binary prediction market:

> **"Will Bitcoin's price be higher or lower at the end of this interval?"**

Traders buy **UP** or **DOWN** shares at prices between $0.01–$0.99. When the
interval ends, winning shares pay **$1.00** and losing shares pay **$0.00**.

This system:

1. **Discovers** these markets in real time using deterministic slug generation
2. **Collects** snapshots of BTC price, market odds, order book state, and derived
   signals (delta, velocity, volatility) every 2 seconds
3. **Evaluates** your custom bots against each snapshot, checking 25+ configurable
   filter conditions
4. **Simulates** realistic order execution with fill delays, taker fees, and slippage
5. **Tracks** full PnL, win rate, Sharpe ratio, drawdown, streaks, and more
6. **Optimizes** strategies via grid/random search backtesting against stored data
7. **Displays** everything in a real-time web dashboard with WebSocket live updates

All of this happens with **paper money only** — no wallet, no API keys, no risk.

---

## 📈 How The Markets Work

Timeline of one 5-minute market:

```
0:00          1:00          2:00          3:00          4:00          5:00
  │             │             │             │             │             │
  ├─ Market opens             ├─ Your bot's                ├─ Market resolves
  │  BTC = $87,250            │  entry window               │  BTC = $87,312
  │  Target locked            │  closes (default)           │  → UP wins!
  │                           │                             │
  │  ask_up starts ~0.50      │                             │  UP shares → $1.00
  │  (coin-flip odds)         │                             │  DOWN shares → $0.00
  │                           │                             │
  └─ Snapshots collected every 2 seconds ───────────────────┘
```

**Your profit on a winning trade:**

```
Bought 1 UP share at ask_up = $0.58
Fee (2%)    = $0.0116
Total cost  = $0.5916
Payout      = $1.00
PnL         = $1.00 - $0.5916 = +$0.4084
```

**Your loss on a losing trade:**

```
Bought 1 UP share at ask_up = $0.58
Fee (2%)    = $0.0116
Total cost  = $0.5916
Payout      = $0.00
PnL         = -$0.5916
```

---

## ✨ Features

### Real-Time Market Monitoring

- Live BTC price from Coinbase/Binance (automatic fallback)
- Active 5m and 15m market discovery via deterministic slug generation
- Order book polling: best ask, best bid, spread, midpoint for UP and DOWN
- Derived signals: delta %, delta velocity, 20-second rolling volatility
- Timer bars showing time remaining in each interval

### Multi-Bot Paper Trading

- Create unlimited bots, each with independent parameters and balance
- 25+ configurable filter conditions per bot
- Realistic execution: fill delay, taker fees, slippage simulation
- Adaptive position sizing based on win/loss streaks
- Per-round order limits with cooldown timers
- Automatic risk management: daily loss limits, drawdown caps, streak pauses
- Early exit system: take-profit and stop-loss on bid prices
- Auto-disable bots after N orders or when ROI drops below threshold

### Analytics & Intelligence

- Market statistics: UP/DOWN distribution, average delta, by hour and day
- Condition → outcome correlations (e.g., "when ask_up < 0.55, UP wins 62%")
- Per-bot time-of-day performance breakdown
- Balance history tracked every 5 minutes
- Bot leaderboard ranked by any metric
- Signal context saved on every order for post-mortem analysis

### Strategy Optimizer

- Grid search or random search across parameter ranges
- Backtests against all stored historical snapshots in-memory
- Ranks results by PnL, Sharpe, profit factor, expectancy, or ROI
- One-click promotion of winning configs to live paper bots

### Data Export

- CSV export of all orders (with signal context) per bot
- CSV export of all snapshots per market type
- Full SQLite database for external analysis

### Dashboard

- Real-time WebSocket updates every 2 seconds
- Equity curve charts per bot
- Order history tables with color-coded status
- Bot cloning for A/B testing
- Collapsible parameter documentation built into the UI

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        EXTERNAL APIS                            │
│  Coinbase/Binance (BTC)  Polymarket Gamma  Polymarket CLOB      │
└─────────┬──────────────────────┬───────────────────┬────────────┘
          │                      │                   │
          ▼                      ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  market_finder.py                                               │
│  - Deterministic slug generation (btc-updown-5m-{epoch})        │
│  - BTC spot price fetching (multi-source fallback)              │
│  - CLOB /price and /book queries for UP/DOWN tokens             │
│  - Delta velocity computation (sliding window)                  │
│  - Volatility computation (rolling stdev)                       │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  data_collector.py                                              │
│  - Main loop: runs every 2 seconds                              │
│  - Builds MarketSnapshot for each active interval               │
│  - Persists target prices (survives restarts)                   │
│  - Resolves completed intervals (compares close vs target)      │
│  - Triggers bot evaluation on each snapshot                     │
│  - Balance history loop (every 5 minutes)                       │
└──────┬──────────────────┬──────────────────┬────────────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌────────────┐   ┌──────────────┐   ┌──────────────────┐
│ database.py│   │ bot_engine.py│   │   analytics.py   │
│            │   │              │   │                  │
│ SQLite:    │   │ - Evaluates  │   │ - Market stats   │
│  snapshots │◄──│   all bots   │   │ - Correlations   │
│  orders    │   │ - Fill delay │   │ - Time-of-day    │
│  results   │   │ - Early exit │   │ - Balance history│
│  targets   │   │ - Resolution │   │                  │
│  balance_h │   │ - Risk mgmt  │   └──────────────────┘
└────────────┘   │ - Streak     │
                 │   tracking   │
                 └──────┬───────┘
                        │
                 ┌──────▼───────┐
                 │bot_storage.py│
                 │              │
                 │  bots.json   │
                 │  (configs)   │
                 └──────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  server.py (FastAPI)                                            │
│                                                                 │
│  REST API           WebSocket /ws         Static Files          │
│  /api/bots          (2s broadcasts)       /static/index.html    │
│  /api/snapshot                            /static/app.js        │
│  /api/optimizer                           /static/style.css     │
│  /api/analytics                                                 │
│  /api/export                                                    │
└─────────────────────────────────────────────────────────────────┘
                        │
                        ▼
               ┌──────────────────┐
               │ Browser Dashboard│
               │                  │
               │  Live markets    │
               │  Bot cards       │
               │  Equity charts   │
               │  Order tables    │
               │  Optimizer modal │
               │  Analytics panels│
               └──────────────────┘
```

---

## 📁 Project Structure

```
polymarket-paper-trader/
│
├── server.py            # FastAPI app — REST API + WebSocket + static serving
├── data_collector.py    # Main collection loop (2s interval)
├── market_finder.py     # Polymarket API queries + BTC price + derived signals
├── bot_engine.py        # Bot evaluation, order lifecycle, stats computation
├── bot_storage.py       # JSON file I/O for bot configs
├── optimizer.py         # Grid/random search backtester
├── analytics.py         # Market stats, correlations, balance history
├── database.py          # Async SQLite (snapshots, orders, results)
├── models.py            # All Pydantic models
├── config.py            # Constants and API endpoints
│
├── bots.json            # Bot configurations (auto-created with 2 starters)
├── papertrader.db       # SQLite database (auto-created on first run)
│
├── static/
│   ├── index.html       # Dashboard HTML
│   ├── app.js           # Frontend application (vanilla JS)
│   └── style.css        # Dark theme styles
│
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

---

## 📦 Installation

### Prerequisites

- **Python 3.11** or higher
- **pip**
- Internet connection (for Polymarket and BTC price APIs)

### Steps

```bash
# 1. Clone or download the project
git clone <your-repo-url>
cd polymarket-paper-trader

# 2. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate      # macOS/Linux
# or
venv\Scripts\activate          # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

<details>
<summary>📋 <code>requirements.txt</code> contents</summary>

```
fastapi==0.115.6
uvicorn==0.34.0
httpx==0.28.1
apscheduler==3.11.0
pydantic==2.10.4
aiosqlite==0.20.0
jinja2==3.1.5
python-dateutil==2.9.0
```

</details>

---

## 🚀 Quick Start

```bash
# Start the server
python server.py
```

That's it. Open your browser to:

> **http://localhost:8080**

On first launch, the system will:

1. Create `bots.json` with 2 starter bots (Base Strategy + Sniper)
2. Create `papertrader.db` (empty SQLite database)
3. Begin collecting live market data immediately
4. Start evaluating bots against incoming snapshots
5. Begin the WebSocket broadcast loop for the dashboard

You should see console output like:

```log
2025-01-15 14:30:00 [server]     INFO  🚀 Paper trader started
2025-01-15 14:30:00 [collector]  INFO  Data collector started
2025-01-15 14:30:00 [bot_engine] INFO  Loaded «Base — Delta Momentum UP» (base0001): bal=$100.00
2025-01-15 14:30:00 [bot_engine] INFO  Loaded «Sniper — Velocity + Tight Spread» (snpr0002): bal=$100.00
2025-01-15 14:30:02 [collector]  INFO  [5m] RESOLVED 1736950800 → UP
```

---

## 🖥 Using The Dashboard

### Market Panels

The top two cards show the currently active 5-minute and 15-minute markets:

| Field          | What It Shows                                                      |
| -------------- | ------------------------------------------------------------------ |
| **BTC**        | Current Bitcoin spot price (from Coinbase/Binance)                 |
| **Target**     | The BTC price locked at the start of this interval (the "open")    |
| **Delta %**    | `(current_btc - target) / target × 100` — how far price has moved |
| **Velocity**   | Rate of change of delta (% per second) — is the move accelerating? |
| **Volatility** | Rolling standard deviation of delta over recent ticks              |
| **Ask UP**     | Current price to buy one UP share (what you'd pay)                 |
| **Spread**     | `ask - bid` for the UP token — measures liquidity                  |
| **Time**       | Countdown to interval end                                          |

The colored timer bar below each panel depletes as time runs out.

🟢 Green values = bullish (BTC above target) · 🔴 Red = bearish · 🟡 Yellow = time warning

### Creating a Bot

Click **+ New Bot** in the top right of the bots section. The modal has 9 sections:

1. **Core** — Name, side (UP/DOWN), market type (5m/15m/both)
2. **Timing** — When in the interval the bot can trade
3. **Filters** — Delta, velocity, volatility conditions
4. **Order Book** — Ask/bid price range filters, spread filter
5. **Execution** — Fill delay, fees, slippage, share count
6. **Multi-Order** — Cooldown, per-round cap, global open cap
7. **Adaptive Sizing** — Streak-based scaling
8. **Risk** — Daily loss, drawdown, consecutive loss limits, auto-disable
9. **Early Exit** — Take-profit and stop-loss on bid price

> Leave any field **blank** (or `None`) to skip that filter.
> The bot will only trade when **ALL** non-blank conditions are met simultaneously.

Click **🚀 Create** and the bot starts trading immediately on the next snapshot.

### Bot Cards

Each active bot shows a summary row:

| Column            | Meaning                                                                |
| ----------------- | ---------------------------------------------------------------------- |
| **Name + Status** | Bot name, colored tag (🟢 active, 🔴 disabled, 🟠 risk-paused) |
| **PnL**           | Net profit/loss across all resolved trades                             |
| **Bal**           | Current paper balance                                                  |
| **Ord**           | Total orders placed                                                    |
| **W/L**           | Wins / Losses count                                                    |
| **WR**            | Win rate percentage                                                    |
| **Sharpe**        | Simplified Sharpe ratio (mean PnL / stdev PnL)                        |
| **Streak**        | Current streak (`+3` = three wins in a row, `-2` = two losses)         |

**Actions:**

- ⏸ / ▶ — Pause or resume the bot
- ✕ — Delete the bot and all its orders

Click anywhere on the card to open the **detail view**.

### Bot Detail View

Shows expanded stats, equity chart, and full order history.

**Stats grid** — 16 metrics including ROI, peak balance, max drawdown, expectancy,
average win/loss, best/worst streaks, fees paid, and today's order count.

**Equity chart** — Balance over time, plotted after each resolved order. Uses Chart.js
with a gradient fill.

**Buttons:**

| Button       | Action                                                       |
| ------------ | ------------------------------------------------------------ |
| 📋 **Clone** | Duplicate this bot with a new name (for A/B testing)         |
| ⬇ **CSV**    | Download all orders as CSV (includes signal context)         |
| 🕐 **Hours** | Show win rate breakdown by hour of day (UTC)                 |
| ⚙ **Config** | View the raw JSON configuration                              |
| 🔄 **Reset** | Clear a risk-management pause (only visible when paused)     |

**Order table columns:**

| Column  | Meaning                                                               |
| ------- | --------------------------------------------------------------------- |
| Time    | When the signal fired                                                 |
| Mkt     | `5m` or `15m`                                                         |
| Side    | UP or DOWN                                                            |
| Entry   | Price paid per share (after slippage)                                 |
| Exit    | Price received on early exit (or `—` if held to resolution)           |
| Sh      | Number of shares                                                      |
| $       | Total cost                                                            |
| Fee     | Entry fee + exit fee                                                  |
| PnL     | Profit or loss                                                        |
| Status  | `WIN` / `LOSS` / `EARLY_EXIT` / `PENDING` / `FILLED` / `EXPIRED`     |
| Δ@sig   | Delta % at the moment the signal fired                                |
| Vel@sig | Delta velocity at signal time                                         |

### Leaderboard

Click **🏆 Leaderboard** to see all bots ranked side-by-side by net PnL. The table
shows PnL, ROI, win rate, profit factor, Sharpe, max drawdown, expectancy, and
total orders for each bot. This is how you compare strategies.

### Market Statistics

Click **📊 Market Stats** to reveal:

- **Global stats** — Total resolved markets, UP/DOWN split percentage, average and
  standard deviation of delta at close
- **Condition → Outcome correlations** — Based on your collected data, shows the
  UP win rate when specific conditions hold at ~30-60 seconds into the interval.
  For example: _"When ask_up is between 0.50–0.60 at 30 seconds, UP wins 58% of the time"_

This tells you whether your bot's filters are targeting conditions that actually
predict outcomes.

### Strategy Optimizer

Click **🔬 Optimizer** to open the backtesting modal.

1. Set the **base side** and **market type**
2. Choose **Grid Search** (exhaustive) or **Random** (sampling)
3. Set **max combinations** (default 100)
4. Choose what to **rank by** (PnL, Sharpe, profit factor, expectancy, ROI)
5. Set **minimum orders** threshold (skip configs that trade too rarely)
6. Enter **parameter ranges** as `min,max,step` or explicit `value1,value2,value3`

Example ranges:

```
delta_pct_min:    0.01, 0.15, 0.02   → tests 0.01, 0.03, 0.05, ..., 0.15
ask_up_min:       0.40, 0.60, 0.05   → tests 0.40, 0.45, 0.50, 0.55, 0.60
ask_up_max:       0.60, 0.80, 0.05   → tests 0.60, 0.65, 0.70, 0.75, 0.80
max_entry_time_s: 60, 90, 120, 180   → tests these 4 values
```

Click **🔬 Run Backtest**. Results appear in a table sorted by your chosen metric.
Each row shows the config's backtested PnL, ROI, win rate, profit factor, Sharpe,
max drawdown, expectancy, and the key parameter values.

Click **Deploy** on any row to instantly create a live paper bot with that exact
configuration.

> [!IMPORTANT]
> The optimizer backtests against all snapshots stored in your database.
> You need at least a few days of collected data (1,000+ resolved markets) for
> meaningful results. **More data = more reliable results.**

---

## 🎛 Bot Parameters — Full Reference

### Core Settings

| Parameter     | Type            | Default  | Description                |
| ------------- | --------------- | -------- | -------------------------- |
| `name`        | `string`        | `Bot-1`  | Display name               |
| `side`        | `UP` / `DOWN`   | `UP`     | Which outcome to buy       |
| `market_type` | `5m`/`15m`/`both` | `5m`   | Which interval(s) to trade |
| `balance`     | `float`         | `100.0`  | Starting paper USDC        |

### Entry Timing

| Parameter           | Type           | Default | Description                                                                                      |
| ------------------- | -------------- | ------- | ------------------------------------------------------------------------------------------------ |
| `min_entry_time_s`  | `float`        | `0`     | Skip the first N seconds of each interval. Lets the market stabilize before looking for entries. |
| `max_entry_time_s`  | `float`        | `120`   | Stop considering entries after N seconds. Default = first 2 minutes of a 5-minute market.        |
| `session_start_utc` | `int` or `None` | `None`  | Only trade during these UTC hours. Example: `13` (= 1 PM UTC).                                   |
| `session_end_utc`   | `int` or `None` | `None`  | End of trading session. Supports overnight wrapping (e.g., start=20, end=8).                     |

### Delta Filters

| Parameter            | Type             | Default | Description                                                                                                                                                 |
| -------------------- | ---------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `delta_pct_min`      | `float` or `None` | `0.05`  | Minimum delta % required. For UP bots, BTC must be at least this far above target. For DOWN bots, it's automatically inverted (BTC must be this far below). |
| `delta_pct_max`      | `float` or `None` | `None`  | Maximum delta %. Prevents chasing after large moves that might reverse.                                                                                     |
| `delta_velocity_min` | `float` or `None` | `None`  | Minimum rate of change of delta (%/second). Positive = price accelerating in your direction.                                                                |
| `delta_velocity_max` | `float` or `None` | `None`  | Cap on velocity. Extremely fast moves might indicate a spike that will reverse.                                                                             |
| `volatility_min`     | `float` or `None` | `None`  | Minimum rolling stdev of delta. Requires a certain level of "action" in the market.                                                                         |
| `volatility_max`     | `float` or `None` | `None`  | Maximum volatility. Avoids chaotic markets where outcomes are unpredictable.                                                                                |

### Order Book Filters

| Parameter          | Type             | Default | Description                                                                                             |
| ------------------ | ---------------- | ------- | ------------------------------------------------------------------------------------------------------- |
| `ask_up_min`       | `float` or `None` | `0.50`  | Only buy UP when ask ≥ this. At 0.50, the market thinks UP is a coin flip.                              |
| `ask_up_max`       | `float` or `None` | `0.70`  | Only buy UP when ask ≤ this. At 0.70, you're paying 70¢ for a $1 payout.                                |
| `ask_down_min/max` | `float` or `None` | `None`  | Same filters for the DOWN token.                                                                        |
| `bid_up_min/max`   | `float` or `None` | `None`  | Filter on the UP bid price. Useful for strategies that care about exit liquidity.                       |
| `bid_down_min/max` | `float` or `None` | `None`  | Filter on the DOWN bid price.                                                                           |
| `spread_max`       | `float` or `None` | `None`  | Maximum ask−bid spread for your side. Rejects illiquid markets where the displayed price is unreliable. |

### Execution Realism

| Parameter          | Type             | Default | Description                                                                                                                                 |
| ------------------ | ---------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `fill_delay_s`     | `float` or `None` | `1.0`   | Simulated latency before your order fills. If the market resolves before the delay elapses, the order expires and your balance is refunded. |
| `taker_fee_pct`    | `float`          | `2.0`   | Fee as % of order cost. Polymarket charges ~2% for takers. Applied on entry and on early exit.                                              |
| `slippage_pct`     | `float`          | `0.0`   | Simulated price worsening. Added to the ask price. 0.5% slippage on a $0.60 ask → effective price $0.603.                                   |
| `shares_per_order` | `float`          | `1.0`   | How many shares to buy per signal. Each share costs the ask price and pays $1 if correct.                                                   |

### Multiple Orders

| Parameter              | Type    | Default | Description                                                                                                        |
| ---------------------- | ------- | ------- | ------------------------------------------------------------------------------------------------------------------ |
| `multiple_orders`      | `bool`  | `false` | `false` = max 1 order per interval. `true` = allows repeated entries within the same 5m/15m round.                |
| `max_orders_per_round` | `int`   | `1`     | Hard cap on orders within one interval. Only matters when `multiple_orders = true`.                                |
| `cooldown_s`           | `float` | `30.0`  | Minimum seconds between consecutive orders in the same round. Prevents the bot from firing on every 2-second tick. |
| `max_open_orders`      | `int`   | `5`     | Global cap across ALL active intervals. Prevents over-exposure when multiple intervals overlap.                    |

### Adaptive Sizing

| Parameter            | Type    | Default | Description                                                                                                  |
| -------------------- | ------- | ------- | ------------------------------------------------------------------------------------------------------------ |
| `streak_scaling`     | `bool`  | `false` | Enable streak-based position sizing.                                                                         |
| `streak_win_bonus`   | `float` | `0`     | Add this many shares per consecutive win. E.g., `0.5` → after 3 wins, buy `1 + 3×0.5 = 2.5` shares.         |
| `streak_loss_reduce` | `float` | `0`     | Reduce shares per consecutive loss. E.g., `0.5` → after 2 losses, buy `max(min_shares, 1 - 2×0.5)`.         |
| `min_shares`         | `float` | `1.0`   | Floor — never buy fewer than this.                                                                           |
| `max_shares`         | `float` | `10.0`  | Ceiling — never buy more than this.                                                                          |

### Risk Management

| Parameter                   | Type             | Default | Description                                                                                     |
| --------------------------- | ---------------- | ------- | ----------------------------------------------------------------------------------------------- |
| `max_daily_loss`            | `float` or `None` | `None`  | Auto-pause the bot after losing this much $ in a single UTC day.                                |
| `max_drawdown_pct`          | `float` or `None` | `None`  | Auto-pause when balance drops this % from its peak.                                             |
| `max_consecutive_losses`    | `int` or `None`  | `None`  | Auto-pause after N straight losses. Reset via the dashboard button.                             |
| `daily_order_limit`         | `int` or `None`  | `None`  | Maximum orders per UTC day.                                                                     |
| `max_exposure`              | `float` or `None` | `None`  | Maximum total $ in open (unfilled + filled) positions.                                          |
| `auto_disable_after`        | `int` or `None`  | `None`  | Permanently disable the bot after N total resolved orders. Useful for time-limited experiments. |
| `auto_disable_if_roi_below` | `float` or `None` | `None`  | Permanently disable if ROI drops below this % (checked after `auto_disable_min_orders` trades). |
| `auto_disable_min_orders`   | `int`            | `20`    | Don't check ROI-based auto-disable until this many orders have resolved.                        |

When a risk limit is hit, the bot shows an **⚠ PAUSED** tag with the reason.
Click the bot → click **🔄 Reset** to clear the pause and resume trading.

### Early Exit

| Parameter           | Type             | Default | Description                                                                                                                      |
| ------------------- | ---------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `enable_early_exit` | `bool`           | `false` | Monitor bid prices for filled orders and sell before resolution.                                                                 |
| `take_profit_bid`   | `float` or `None` | `None`  | Sell if the bid for your token reaches this level. E.g., `0.88` → sell at 88¢ to lock in profit instead of waiting for resolution. |
| `stop_loss_bid`     | `float` or `None` | `None`  | Sell if bid drops to this level to cut losses. E.g., `0.18` → sell at 18¢ instead of riding to $0.                                |

> [!NOTE]
> Early exits incur a second taker fee on the exit proceeds.

---

## 🤖 The Two Starter Bots

### Bot 1: "Base — Delta Momentum UP"

> Your original specification. The simplest viable strategy.
>
> **Logic:** _"BTC has moved up at least 0.05% from open, and the market
> prices UP at 50–70¢. Buy early while odds are cheap."_

**Conditions:**

- Side: **UP** · Market: **5m**
- `delta_pct` ≥ 0.05%
- `0.50` ≤ `ask_up` ≤ `0.70`
- Within first 120 seconds
- 1 order per round · 1s fill delay · 2% fee
- $100 balance · No risk limits · No early exit

This is a **momentum-continuation bet**: when BTC starts moving up, it tends to
keep going within a 5-minute window, and the market initially underprices this.

---

### Bot 2: "Sniper — Velocity + Tight Spread"

> A more selective, risk-managed approach designed to illustrate advanced features.
>
> **Logic:** _"BTC is moving up AND accelerating, the spread is tight (liquid
> market), we're past the first 15 seconds (price discovery done),
> it's US trading hours (more volume), and we have risk guardrails."_

**Conditions:**

- Side: **UP** · Market: **5m**
- `delta_pct` 0.03–0.30% · `delta_velocity` ≥ 0.001 (accelerating)
- `volatility` ≤ 0.15 (not chaotic)
- `0.45` ≤ `ask_up` ≤ `0.65` · `spread` ≤ 0.10
- Entry window: 15s–90s · Session: 13–21 UTC (US hours)
- Multiple orders: up to 2/round, 45s cooldown
- Streak scaling: +0.5 shares per consecutive win
- Risk: $10 daily loss cap, 15% max drawdown, 5 consecutive loss pause
- Auto-disable if ROI < -20% after 30 orders
- Early exit: take profit at bid `0.88`, stop loss at bid `0.18`
- $100 balance

This bot trades less often but with higher conviction and built-in protection.

---

## 🔬 The Optimizer — How To Use It

### When To Use It

After collecting at least **3–7 days of continuous data** (1,000+ resolved markets).
The more data, the more reliable the results.

### Step-by-Step

1. Click **🔬 Optimizer** in the dashboard
2. Set base parameters (`side=UP`, `market=5m`)
3. Enter ranges for the parameters you want to sweep:

   ```
   delta_pct_min:    0.01, 0.15, 0.02
   ask_up_min:       0.40, 0.60, 0.05
   ask_up_max:       0.60, 0.85, 0.05
   max_entry_time_s: 60, 90, 120, 150
   ```

   This generates `8 × 5 × 6 × 4 = 960` combinations (capped at `max_combinations`)

4. Choose ranking metric (Sharpe ratio is most robust)
5. Set `min_orders = 10` (skip strategies that barely trade)
6. Click **🔬 Run Backtest**
7. Review the results table — look for:
   - Sharpe > 0.5
   - Win rate > 55%
   - Profit factor > 1.3
   - Reasonable number of orders (not just 5 lucky trades)
8. Click **Deploy** on a promising result to create a live paper bot

### ⚠️ Interpretation Warnings

> [!WARNING]
> - **More orders = more trustworthy.** A config with 200 trades and 55% win rate is
>   far more reliable than one with 12 trades and 75% win rate.
> - **The #1 result is often overfitted.** Look at the top 5–10 and find parameter
>   regions that consistently perform well, not just the single best.
> - **Walk-forward validation is ideal.** The optimizer currently backtests on all data.
>   For maximum reliability, manually test: optimize on week 1–3 data, then check if
>   the winning config also works on week 4 data.

---

## 💾 Data Collection & Storage

### What Gets Collected

Every 2 seconds, for each active 5m and 15m market:

| Data Point          | Source                    | Stored In                                       |
| ------------------- | ------------------------- | ----------------------------------------------- |
| BTC spot price      | Coinbase/Binance          | `snapshots.btc_price`                           |
| Market target price | First BTC seen in epoch   | `target_prices`, `snapshots.target_price`       |
| Delta %             | Computed                  | `snapshots.delta_pct`                           |
| Delta velocity      | Computed (sliding window) | `snapshots.delta_velocity`                      |
| Volatility          | Computed (rolling stdev)  | `snapshots.volatility_20s`                      |
| Ask/Bid UP          | Polymarket CLOB           | `snapshots.ask_up`, `snapshots.bid_up`          |
| Ask/Bid DOWN        | Polymarket CLOB           | `snapshots.ask_down`, `snapshots.bid_down`      |
| Spread, midpoint    | Computed                  | `snapshots.spread_up`, `snapshots.mid_up`, etc. |
| Time remaining      | Computed                  | `snapshots.time_remaining_s`                    |
| Time elapsed        | Computed                  | `snapshots.time_elapsed_s`                      |
| Market outcome      | Resolution logic          | `market_results.outcome`                        |
| Bot orders          | Bot engine                | `orders.*`                                      |
| Signal context      | Bot engine                | `orders.signal_delta`, `signal_velocity`, etc.  |
| Balance timeline    | Every 5 min               | `balance_history`                               |

### Storage Sizes (approximate)

| Duration | Snapshots | Market Results | DB Size  |
| -------- | --------- | -------------- | -------- |
| 1 day    | ~86,400   | ~384           | ~50 MB   |
| 1 week   | ~605,000  | ~2,700         | ~350 MB  |
| 1 month  | ~2.6M     | ~11,500        | ~1.5 GB  |

### Accessing The Data

**From the dashboard:**

- Click ⬇ CSV on any bot to export orders
- Use the API endpoints below

**From Python (direct SQLite):**

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("papertrader.db")

# All snapshots
df = pd.read_sql("SELECT * FROM snapshots ORDER BY ts DESC LIMIT 10000", conn)

# Resolved markets
results = pd.read_sql("SELECT * FROM market_results", conn)

# Join for ML training data
ml_data = pd.read_sql("""
    SELECT s.*, mr.outcome
    FROM snapshots s
    JOIN market_results mr ON s.epoch = mr.epoch AND s.market_type = mr.market_type
    WHERE s.time_elapsed_s BETWEEN 20 AND 60
""", conn)
```

**From the JSON file:**

Bot configurations are human-readable in `bots.json`. You can edit this file
directly (while the server is stopped) to bulk-modify bot parameters.

---

## 📡 API Reference

All endpoints are relative to `http://localhost:8080`.

### Market Data

| Method | Endpoint                 | Description                     |
| ------ | ------------------------ | ------------------------------- |
| `GET`  | `/api/snapshot/5m`       | Latest 5m market snapshot       |
| `GET`  | `/api/snapshot/15m`      | Latest 15m market snapshot      |
| `GET`  | `/api/results?limit=100` | Recent resolved market outcomes |

### Bot Management

| Method   | Endpoint                          | Description                                     |
| -------- | --------------------------------- | ----------------------------------------------- |
| `GET`    | `/api/bots`                       | All bots with full stats                        |
| `POST`   | `/api/bots`                       | Create a new bot (JSON body = `CreateBotRequest`) |
| `DELETE` | `/api/bots/{id}`                  | Delete a bot and all its orders                 |
| `PATCH`  | `/api/bots/{id}/toggle`           | Enable/disable a bot                            |
| `PATCH`  | `/api/bots/{id}/reset-pause`      | Clear risk-management pause                     |
| `GET`    | `/api/bots/{id}/stats`            | Full stats for one bot                          |
| `GET`    | `/api/bots/{id}/orders?limit=200` | Order history                                   |
| `GET`    | `/api/bots/{id}/equity`           | Equity curve (time-series of balance)           |
| `GET`    | `/api/bots/{id}/config`           | Raw bot configuration                           |
| `POST`   | `/api/bots/{id}/clone?name=X`     | Clone a bot                                     |

### Analytics

| Method | Endpoint                                       | Description                       |
| ------ | ---------------------------------------------- | --------------------------------- |
| `GET`  | `/api/analytics/comparison`                    | All bots ranked by PnL            |
| `GET`  | `/api/analytics/market-stats`                  | UP/DOWN distribution, by hour/day |
| `GET`  | `/api/analytics/correlations?market_type=5m`   | Condition→outcome correlations    |
| `GET`  | `/api/analytics/bot-hours/{id}`                | Per-bot hourly performance        |
| `GET`  | `/api/analytics/balance-history/{id}?hours=24` | Balance snapshots                 |
| `GET`  | `/api/analytics/all-balances?hours=24`         | All bots' balance timelines       |

### Optimizer

| Method | Endpoint                        | Description                                                     |
| ------ | ------------------------------- | --------------------------------------------------------------- |
| `POST` | `/api/optimizer/run`            | Run backtest (JSON body = `OptimizeRequest`)                    |
| `POST` | `/api/optimizer/promote?name=X` | Create live bot from optimizer result (JSON body = config dict) |

### Export

| Method | Endpoint                              | Description                          |
| ------ | ------------------------------------- | ------------------------------------ |
| `GET`  | `/api/export/orders/{id}`             | CSV download of all orders for a bot |
| `GET`  | `/api/export/snapshots/5m?limit=5000` | CSV download of snapshots            |

### WebSocket

| Endpoint                 | Description                                                                                                             |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `ws://localhost:8080/ws` | Real-time feed. Broadcasts every 2s: latest snapshots for both markets + summary stats for all bots + server timestamp. |

---

## ⚙️ How It Works Under The Hood

### 1. Market Discovery

Polymarket BTC markets use deterministic URLs. A 5-minute market starting at
Unix timestamp `1736950800` has the slug `btc-updown-5m-1736950800`. The system
computes:

```python
epoch = (int(time.time()) // 300) * 300   # floor to nearest 5-min boundary
slug  = f"btc-updown-5m-{epoch}"
```

This slug is queried against the Gamma API (`gamma-api.polymarket.com/events`)
to get the market's token IDs. This bypasses any indexing delay in Polymarket's
search/discovery system.

### 2. Snapshot Collection

Every 2 seconds, `data_collector.py` runs `_collect_once()`:

1. For each interval type (5m, 15m):
   - Compute current epoch and time remaining
   - Check if the **previous** epoch needs resolution
   - Fetch BTC price (Coinbase, with Binance fallback)
   - Look up or lock the target price for this epoch
   - Query Polymarket for UP/DOWN token prices
   - Compute derived fields (delta, velocity, volatility, spread, midpoint)
   - Save the snapshot to SQLite
   - Feed the snapshot to every active bot for evaluation

### 3. Bot Evaluation

For each snapshot × each enabled bot, `bot_engine.evaluate()` runs this filter chain:

```
Market type match?      → skip if wrong interval
Session hours OK?       → skip if outside trading hours
Entry time window?      → skip if too early or too late
Risk limits OK?         → skip if daily loss / drawdown / streak exceeded
Exposure limit OK?      → skip if too much capital in open orders
Round order limit OK?   → skip if already hit max for this interval
Cooldown elapsed?       → skip if last order too recent (multi-order mode)
Entry price available?  → skip if no ask price from the API
Balance sufficient?     → skip if can't afford cost + fee
Delta in range?         → skip if delta outside [min, max]
Velocity in range?      → skip if velocity outside [min, max]
Volatility in range?    → skip if volatility outside [min, max]
Ask/bid prices in range?→ skip if any book filter fails
Spread acceptable?      → skip if spread too wide
                          ═══════════════════════════
                          ALL PASS → Create PaperOrder
```

If even one condition fails, no order is created. The bot waits for the next tick.

### 4. Order Lifecycle

```
SIGNAL (conditions met, order created)
  │
  ├─ Balance debited (cost + fee deducted immediately)
  │
  ▼
PENDING ──[fill_delay_s]──▶ FILLED
  │                          │
  │                          ├─ Early exit monitoring starts
  │                          │  (if enable_early_exit = true)
  │                          │
  │                          ├─ bid >= take_profit_bid? → EARLY_EXIT (profit)
  │                          ├─ bid <= stop_loss_bid?   → EARLY_EXIT (loss)
  │                          │
  │                          ▼
  │                        [interval ends]
  │                          │
  │                          ├─ side matches outcome?  → WIN  (payout: $1 × shares)
  │                          └─ side doesn't match?    → LOSS (payout: $0)
  │
  └─ [interval ends before fill_delay completes]
       │
       └─ EXPIRED (full refund of cost + fee)
```

### 5. Resolution

When a new epoch begins, the collector resolves the **previous** epoch:

1. Look up the target price (stored in `target_prices` table)
2. Compare to the last BTC price seen during that interval
3. If `close >= target` → outcome = `UP`, else `DOWN`
4. Save to `market_results`
5. Call `bot_engine.resolve_orders()` which:
   - Pays out winning FILLED orders ($1 × shares added to balance)
   - Marks losing FILLED orders (balance already debited)
   - Refunds PENDING orders (expired — fill delay was too long)
   - Updates consecutive win/loss streaks
   - Updates peak balance

### 6. Analytics Computation

- **Market stats** — Aggregates all `market_results`: UP/DOWN counts, average closing
  delta, broken down by hour of day and day of week.
- **Correlations** — For each resolved epoch, grabs the snapshot at ~30–60s elapsed
  and checks: what was `ask_up`? what was `delta`? Did UP win? Buckets these into
  categories and computes the UP win rate per bucket.
- **Bot stats** — Replays all orders for a bot to compute: win rate, profit factor,
  Sharpe ratio, max drawdown, expectancy, streaks, and more. Recalculated on each
  request to stay current.
- **Balance history** — Every 5 minutes, a background loop writes the current balance
  of every bot to `balance_history`, providing a continuous timeline independent of
  trade activity.

---

## 🗃 Persistence Model

The system uses a **hybrid persistence** approach:

| What               | Where                     | Why                                                       |
| ------------------ | ------------------------- | --------------------------------------------------------- |
| Bot configurations | `bots.json`               | Human-readable, git-trackable, editable while stopped     |
| Snapshots          | `papertrader.db` (SQLite) | High volume (~43K rows/day), needs SQL queries            |
| Orders             | `papertrader.db` (SQLite) | Needs indexed lookups by bot_id, epoch, status            |
| Market results     | `papertrader.db` (SQLite) | Needs joins with snapshots for analytics                  |
| Target prices      | `papertrader.db` (SQLite) | Must survive restarts mid-interval                        |
| Balance history    | `papertrader.db` (SQLite) | Time-series data, needs range queries                     |
| Runtime state      | In-memory (Python dicts)  | Balances, streaks, round counts — rebuilt from DB on boot |

**On restart:** The server loads bots from `bots.json`, then replays all orders
from SQLite to reconstruct balances, streaks, and peak values. No data is lost.

**Atomic writes:** `bots.json` is written via tmp-file + rename to prevent
corruption on crash.

**SQLite WAL mode:** Enabled for concurrent reads during writes.

---

## ⚙ Configuration

Edit `config.py` to change system-level settings:

| Constant               | Default            | Description                                   |
| ---------------------- | ------------------ | --------------------------------------------- |
| `POLL_INTERVAL_SEC`    | `2`                | How often to collect snapshots (seconds)      |
| `BALANCE_SNAPSHOT_SEC` | `300`              | How often to record balance history (seconds) |
| `SHARE_PAYOUT`         | `1.0`              | Payout per winning share ($)                  |
| `DB_PATH`              | `"papertrader.db"` | SQLite database filename                      |
| `BOTS_JSON`            | `"bots.json"`      | Bot config filename                           |
| `DELTA_HISTORY_WINDOW` | `10`               | Ticks for velocity calculation                |
| `VOLATILITY_WINDOW`    | `10`               | Ticks for volatility calculation              |

Server port is set in the `server.py` main block (default: `8080`).

---

## 💡 Tips & Strategy Notes

### Getting Started

1. Let the system collect data for **at least 24 hours** before judging any bot
2. The first bot orders may take a few minutes to appear (the bot needs to see a
   matching snapshot within its entry window)
3. Check the **Market Stats** panel first — know the base rate. If UP wins 52% of
   the time, your bot needs to beat that, not just beat 50%

### Strategy Design

- **Fewer filters = more trades = faster statistical significance.** Start simple
  (just delta + ask range), then add filters one at a time
- **The ask price is the most important variable.** Buying at 0.50 gives you a
  breakeven at 51% accuracy. Buying at 0.70 requires 71.4% accuracy to profit
- **Velocity matters more than absolute delta.** A market where delta went
  `0.02% → 0.06%` in 10 seconds is very different from one sitting at `0.06%` for
  a minute
- **Spread is a hidden cost.** A 15¢ spread means the "true" price is far from
  what you'll pay. Use `spread_max` to avoid illiquid markets

### Optimization

- Always look at the **number of trades**, not just the return. 5 trades with
  80% win rate is noise. 200 trades with 58% win rate is signal
- **Test at least 3 different `max_entry_time_s` values** — entry timing is one
  of the highest-impact parameters
- **After finding a good config, clone it and change ONE parameter** to isolate
  what actually drives performance

### Risk Management

- Start with `max_daily_loss` = 10% of balance. You can always loosen it later
- `max_consecutive_losses = 5` is a good starting point. It triggers surprisingly
  often in 50/50 markets
- **Auto-disable** is useful for running many experimental bots without monitoring
  them. Set `auto_disable_after = 50` to run each experiment for exactly 50 trades

---

## 🔧 Troubleshooting

### "No data yet" on market panels

The system needs a few seconds to fetch the first snapshot. If it persists:

- Check your internet connection
- Check if Polymarket is accessible from your location
- Look at the console for error messages

### Bot not placing any orders

Check the console output. Common reasons:

- No active market found (between intervals, or Gamma API returned no results)
- All filter conditions not simultaneously met (delta too low, ask out of range, etc.)
- Entry window already passed (`elapsed > max_entry_time_s`)
- Risk limit hit (check for ⚠ PAUSED tag)
- Balance too low for cost + fee
- The Sniper bot only trades 13–21 UTC — outside those hours it's silent

### Orders stuck in PENDING

The fill delay hasn't elapsed yet. If an order stays PENDING and the interval
resolves, it becomes EXPIRED (fully refunded). This is intentional — it simulates
the realistic scenario where network latency causes a missed fill.

### Database getting large

After a month, `papertrader.db` can reach 1.5 GB. To trim:

```sql
-- Delete old snapshots (keep last 7 days)
DELETE FROM snapshots WHERE ts < unixepoch() - 604800;
-- Reclaim space
VACUUM;
```

### Port 8080 already in use

Change the port in `server.py`:

```python
uvicorn.run("server:app", host="0.0.0.0", port=9090)
```

### "Corrupt bots.json"

If the file gets corrupted, delete it and restart. The system will recreate it
with the two default bots. Your order history in SQLite is preserved.

---

<p align="center">
  <b>Built for research and education. Paper trading only. Not financial advice.</b>
</p>
