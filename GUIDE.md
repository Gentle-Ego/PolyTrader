# 📖 User Guide — Polymarket Paper Trader v3

This guide explains how to use the two main features of the Paper Trader:
the **creation of a new Bot** and the **Strategy Optimizer**.

---

## 🤖 What is a Bot?

A bot is an **automated strategy** that monitors the Bitcoin 5-minute and 15-minute markets
on Polymarket and places virtual orders (paper trading) when certain conditions
you set are met.

Each bot has:

- A **virtual balance** (default $100) — no real money is at risk
- A set of **filters** that determine whether it should buy or not
- A **side** (UP or DOWN) — meaning it bets that Bitcoin will go up or down
- Full statistics: PnL, win rate, Sharpe ratio, drawdown, and much more

The bot evaluates conditions **every 2 seconds**. If **ALL conditions are satisfied simultaneously**, it places an order.

---

## ➕ How to Create a New Bot

Click the **+ New Bot** button in the Bots section of the dashboard.
A modal opens with **8 sections**. Here is what each field does:

---

## 1. ⚙️ Core — Basic Settings

| Field      | What it Does                                        | Tip                                             |
| ---------- | --------------------------------------------------- | ----------------------------------------------- |
| **Name**   | Bot name (only for identification)                  | Use descriptive names: "Aggressive UP Momentum" |
| **Side**   | UP = bet BTC rises, DOWN = bet it falls             | Start with UP, it's more intuitive              |
| **Market** | 5m = 5-minute markets, 15m = 15-minute, Both = both | 5m is faster for testing                        |

---

## 2. ⏱ Timing — When the Bot Can Trade

| Field                     | What it Does                               | Tip                                            |
| ------------------------- | ------------------------------------------ | ---------------------------------------------- |
| **Min Entry (s)**         | Ignore the first N seconds of the market   | 10–15s avoids early noise                      |
| **Max Entry (s)**         | Stop searching for entries after N seconds | 120s = first 2 minutes. Lower = more selective |
| **Session Start/End UTC** | Trade only during certain UTC hours        | 13–21 UTC = US trading hours (higher volume)   |

**Example:**
`Min Entry = 15, Max Entry = 90` → the bot trades only between **15 and 90 seconds** of each interval.

---

## 3. 📈 Filters — Price Conditions

| Field                  | What it Does                                                                         | Tip                             |
| ---------------------- | ------------------------------------------------------------------------------------ | ------------------------------- |
| **Δ% Min**             | BTC must have moved up (UP) or down (DOWN) by at least this % from the opening price | 0.03–0.10% is a good range      |
| **Δ% Max**             | Do not buy if the move is too large (could reverse)                                  | 0.30% avoids late entries       |
| **Vel Min**            | Delta must accelerate at least at this speed                                         | 0.001 = minimal acceleration    |
| **Vel Max**            | Avoid extremely strong accelerations (spikes)                                        | Leave empty if not needed       |
| **Volatility Min/Max** | Filter by market volatility                                                          | Max 0.15 avoids chaotic markets |

**How Delta works**

```
Delta % = (Current BTC Price - Target Price) / Target Price × 100

If target = $87,000 and BTC = $87,100:
Delta = +0.115% → BTC has risen → good signal for UP bot
```

---

## 4. 📊 Order Book — Share Price Filters

| Field              | What it Does                                         | Tip                        |
| ------------------ | ---------------------------------------------------- | -------------------------- |
| **Ask UP Min**     | Minimum price of the UP share (do not buy too cheap) | 0.45–0.50                  |
| **Ask UP Max**     | Maximum price (do not overpay)                       | 0.65–0.75                  |
| **Ask DN Min/Max** | Same filters for DOWN shares                         | Only if the bot is DOWN    |
| **Spread Max**     | Maximum difference between ask and bid               | 0.08–0.12 = good liquidity |

**How share pricing works**

```
You buy 1 UP share at $0.60
If BTC rises → you win → you receive $1.00 → profit = $0.40 - fees
If BTC falls → you lose → you receive $0.00 → loss = $0.60 + fees

The lower you buy, the more you earn (but the outcome is less certain)
```

---

## 5. ⚙️ Execution — Realistic Simulation

| Field              | What it Does                                 | Tip                         |
| ------------------ | -------------------------------------------- | --------------------------- |
| **Fill Delay (s)** | Simulated delay before the order is executed | 1s is realistic             |
| **Fee %**          | Trading commission percentage                | 2% = Polymarket’s real fee  |
| **Slippage %**     | Simulated price deterioration                | 0–0.5% is realistic         |
| **Shares**         | Number of shares to buy per signal           | 1–3 to start                |
| **Multi Orders**   | Allow multiple orders in the same interval   | No = safer                  |
| **Cooldown (s)**   | Pause between orders in the same round       | 30–45s prevents overtrading |
| **Max/Round**      | Maximum orders per interval                  | 1–2                         |
| **Max Open**       | Maximum simultaneous open orders             | 3–5                         |

---

## 6. 📏 Adaptive Sizing — Dynamic Position Sizing

| Field                  | What it Does                                             | Tip                                  |
| ---------------------- | -------------------------------------------------------- | ------------------------------------ |
| **Streak Scaling**     | Increase/decrease shares based on winning/losing streaks | Enable after validating the strategy |
| **Win Bonus Shares**   | Extra shares per consecutive win                         | 0.5 = +0.5 per win                   |
| **Loss Reduce Shares** | Reduce shares per consecutive loss                       | 0.5 protects after losses            |
| **Max Shares**         | Maximum share limit                                      | 5–10                                 |

Example:

Base = 1 share
Win Bonus = 0.5
After 3 wins → `1 + 3×0.5 = 2.5 shares`

---

## 7. 🛡 Risk — Risk Management

| Field                    | What it Does                            | Tip                                               |
| ------------------------ | --------------------------------------- | ------------------------------------------------- |
| **Balance $**            | Starting balance for the bot            | $100 for testing, $500–1000 for proven strategies |
| **Max Daily Loss $**     | Automatic pause after N$ daily losses   | $5–15                                             |
| **Max DD %**             | Pause if balance drops this % from peak | 15–25%                                            |
| **Max Consec Losses**    | Pause after N consecutive losses        | 5–8                                               |
| **Daily Limit**          | Maximum orders per day                  | 20–50                                             |
| **Max Exposure $**       | Maximum total exposure in open orders   | 20–50% of balance                                 |
| **Auto-disable After N** | Disable bot after N total trades        | Useful for experiments                            |
| **Auto-disable ROI <**   | Disable if ROI drops below this %       | -20% is reasonable                                |

⚠️ **Tip:** Always use at least one risk limit.
Without limits, a bad strategy can drain the balance quickly.

---

## 8. 🚪 Early Exit — Early Position Exit

| Field        | What it Does                                          | Tip                         |
| ------------ | ----------------------------------------------------- | --------------------------- |
| **Enable**   | Enable bid price monitoring to exit before resolution | Yes for advanced strategies |
| **TP Bid ≥** | Sell if bid reaches this level (take profit)          | 0.85–0.92                   |
| **SL Bid ≤** | Sell if bid drops to this level (stop loss)           | 0.15–0.25                   |

Example:

You buy UP at **$0.60**.
If the bid rises to **$0.88**, you sell and collect **$0.88 per share** (minus fees).
You lock the profit instead of waiting for final resolution.

---

# 🔬 The Optimizer — What It Is and How to Use It

## What Is It?

The Optimizer is a **backtester** that tests thousands of parameter combinations
against historical data you collected. It shows which configurations
would have worked best in the past.

---

## When Should You Use It?

**After collecting at least 3–7 days of data** (1000+ resolved markets).

The more data you have, the more reliable the results.

---

## How It Works — Step by Step

### 1. Open the Optimizer

Click **🔬 Optimizer** in the Bots section button bar.

---

### 2. Set Base Parameters

- **Base Side:** UP or DOWN
- **Market:** 5m or 15m
- **Method:** Grid Search (tests everything) or Random (random sampling)
- **Max Combos:** number of combinations to test (100 = fast, 500+ = thorough)
- **Rank By:** how results are sorted (Sharpe Ratio is the most reliable)
- **Min Orders:** discard strategies with fewer than N trades (5–10 minimum)

---

### 3. Insert Parameter Ranges

For each parameter you can specify:

Range with step

`min, max, step`

Example:

`0.01, 0.15, 0.02`

Explicit values

`60, 90, 120, 180`

---

### Example

```
delta_pct_min:     0.01, 0.15, 0.02
ask_up_min:        0.40, 0.60, 0.05
ask_up_max:        0.60, 0.85, 0.05
max_entry_time_s:  60, 90, 120, 150

Total combinations: 8 × 5 × 6 × 4 = 960
```

---

### 4. Click **Run Backtest**

The optimizer tests all combinations in memory and shows the results in a table.

---

### 5. Read the Results

| Metric      | Meaning                   | Good Value             |
| ----------- | ------------------------- | ---------------------- |
| **PnL**     | Net profit/loss           | Positive               |
| **ROI %**   | Return on investment      | > 5%                   |
| **WR**      | Win rate                  | > 55%                  |
| **PF**      | Profit Factor             | > 1.3                  |
| **Sharpe**  | Risk-adjusted return      | > 0.5                  |
| **DD**      | Maximum drawdown          | < 20%                  |
| **Expect.** | Expected profit per trade | Positive               |
| **N**       | Total trades              | Higher = more reliable |

---

### 6. Deploy a Result

Click **Deploy** on a promising row to create a live bot with that configuration.

---

# ⚠️ Important Warnings

1. **More trades = more reliable results.**
   A strategy with 200 trades and 55% win rate is far more reliable than one with 12 trades and 75%.

2. **The #1 result is often overfitted.**
   Look at the top 5–10 strategies instead of blindly picking the best one.

3. **Past performance does not guarantee future results.**
   Always test with paper trading before trusting a strategy.

4. **Walk-forward testing:**
   Optimize using weeks 1–3, then verify if it also works on week 4 data.

---

# 💡 Tips for Effective Strategies

## For Beginners

1. Start with a simple bot: delta_pct_min + ask range
2. Use risk limits: Max Daily Loss = $10, Max DD = 20%
3. Let the bot run for 2–3 days before judging it
4. Avoid changing parameters too often

---

## For Advanced Users

1. Use the optimizer after 5+ days of data collection
2. Test both UP and DOWN strategies
3. Combine filters: delta + velocity + volatility + spread
4. Use time sessions: US vs Asia markets behave differently
5. Enable early exit to lock profits and limit losses
6. Clone winning bots and run A/B tests with small variations

---

## Common Mistakes

❌ Too many restrictive filters → bot never trades
❌ No risk limits → balance gets drained
❌ Judging after 10 trades → statistically meaningless
❌ Optimizing with too little data → unreliable results
❌ Changing strategy every day → strategy never stabilizes

---

# 📊 How to Read the Dashboard

## Bot Cards

| Column     | Meaning                                   |
| ---------- | ----------------------------------------- |
| **PnL**    | Total net profit/loss                     |
| **Bal**    | Current balance                           |
| **Ord**    | Total orders placed                       |
| **W/L**    | Wins / Losses                             |
| **WR**     | Win rate                                  |
| **Sharpe** | Risk-return ratio                         |
| **Streak** | Current streak (+3 = three wins in a row) |

---

## Colors

🟢 Green = positive / BTC above target / bot active
🔴 Red = negative / BTC below target / bot disabled
🟡 Yellow = warning / little time remaining
🟠 Orange = bot paused due to risk limit

---

## Leaderboard

Click **🏆 Leaderboard** to compare all bots ranked by PnL.

---

## Market Statistics

Click **📊 Market Stats** to see:

- UP vs DOWN distribution
- Condition → outcome correlations
  Example: "When ask_up < 0.55, UP wins 62% of the time"

---

# ❓ FAQ

**Does the bot use real money?**
No. Everything is paper trading. No real money is ever at risk.

**How many bots can I create?**
Unlimited, but each bot consumes compute resources.
20–30 active bots is a reasonable limit.

**Why is my bot not trading?**
Your filters are probably too strict. Try widening ranges.

**How do I know if a strategy works?**
Wait for at least 50–100 resolved trades.
Check win rate (>55%), profit factor (>1.2), and Sharpe (>0.3).

**Can I edit an existing bot?**
Not directly from the UI.
You can clone it with different parameters or edit `bots.json` manually.

**What is the Sharpe Ratio?**
It measures return per unit of risk.

Sharpe > 0.5 = good
Sharpe > 1.0 = excellent

Simplified formula:

average(PnL per trade) / standard deviation(PnL per trade)
