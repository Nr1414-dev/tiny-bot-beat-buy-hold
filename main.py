"""Tiny bot — momentum rotation + EMA-cross entries (bars-replay/v1, Python).

Strategy (Hybrid H + TP5): cross-sectional momentum rotation top-3 by 12-bar
return, rebalanced every 12 bars, entries filtered by close > EMA(8);
EMA(8)/EMA(14) cross-up entries into free slots on every other bar;
cross-down exits every bar; take-profit +5% (value >= 1.05 x cost).
Long-only, no leverage, no shorts. Stake: equity/3 per rotation buy
(capped at 25% equity), equity/7 per cross entry (capped at 25% equity).

Deterministic: standard library only, no clock / env / network / random.
EMAs seeded exactly like the house baselines (mean of the first span),
float64 arithmetic only. Entry tested on the dev window (136 bars),
both split halves (cold start) and a mirrored up-market window.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

FAST = 8
SLOW = 14
FILT = 8
LOOKBACK = 12
EVERY = 12
TOPN = 3
MAX_SLIP = 100
TP_NUM = 21  # take profit: value * 20 >= cost * 21  (value >= 1.05 * cost)
TP_DEN = 20

SYMBOLS = ["FARTCOIN", "JITOSOL", "POPCAT", "RAY", "SOL", "WETH", "WIF"]


class Ema:
    """One EMA: mean of the first span of closes, then 2/(span+1) steps."""

    def __init__(self, span):
        self.span = span
        self.warm = []
        self.value = None

    def step(self, close):
        if self.value is not None:
            self.value += (2 / (self.span + 1)) * (close - self.value)
            return
        self.warm.append(close)
        if len(self.warm) == self.span:
            self.value = sum(self.warm) / self.span


class Series:
    """Per-symbol indicator state."""

    def __init__(self):
        self.fast = Ema(FAST)
        self.slow = Ema(SLOW)
        self.filt = Ema(FILT)
        self.closes = []
        self.gap = None
        self.now = None
        self.down = False


SERIES = {s: Series() for s in SYMBOLS}


def _check_orders(state, orders):
    """Guard: a reply must never ask the market for the impossible.
    Sells only for held symbols (full quantity), buys only for unheld
    symbols (once each), at most max_orders_per_bar, total buy notional
    within the cash this reply may spend. Raises on violation so a bug
    fails loudly in testing instead of silently losing fills live."""
    caps = state.hello["caps"]
    seen_buy = set()
    spend = 0
    assert len(orders) <= caps["max_orders_per_bar"], "too many orders"
    for o in orders:
        sym = o["symbol"]
        if o["side"] == "sell":
            held = state.positions.get(sym)
            assert held is not None and o["qty"] == held.qty, "bad sell"
        else:
            assert sym not in state.positions, "buy of a held symbol"
            assert sym not in seen_buy, "duplicate buy"
            seen_buy.add(sym)
            spend += o["notional_quote_units"]
    assert spend <= state.cash, "buys exceed cash"


def on_batch(state, batch):
    cross_up = set()
    fresh = set()
    for bar in batch["bars"]:
        sym = bar["symbol"]
        if sym not in SERIES:
            continue
        fresh.add(sym)
        s = SERIES[sym]
        close = int(bar["c"])
        s.closes.append(close)
        s.fast.step(close)
        s.slow.step(close)
        s.filt.step(close)
        if s.fast.value is None or s.slow.value is None:
            continue
        s.gap = s.now
        s.now = s.fast.value - s.slow.value
        if s.now < 0 and s.gap is not None and s.gap >= 0:
            s.down = True
        if s.now >= 0:
            s.down = False
        if s.gap is not None and s.now > 0 and s.gap <= 0:
            cross_up.add(sym)

    if state.warming_up:
        return []

    caps = state.hello["caps"]
    fees = state.hello["fees"]
    max_orders = caps["max_orders_per_bar"]
    max_weight = caps["max_weight_bps"]
    # u64 hello fields arrive as decimal strings: parse before math.
    min_notional = int(fees["min_notional_quote_units"])

    sells = []
    for sym in SYMBOLS:
        if sym not in fresh:
            continue
        held = state.positions.get(sym)
        if held is None:
            continue
        s = SERIES[sym]
        leave = s.down
        if not leave:
            value = state.value(sym, held.qty)
            if value * TP_DEN >= held.cost * TP_NUM:
                leave = True
        if leave:
            sells.append({"side": "sell", "symbol": sym, "qty": held.qty,
                          "max_slippage_bps": MAX_SLIP})

    orders = sells[:max_orders]
    sold = {o["symbol"] for o in sells}

    # Cash left for buys in this reply (sells fund the NEXT open, never this reply).
    cash = state.cash
    equity = state.equity

    def stake(divisor):
        room = max_weight * equity // makefun_bars.BPS
        return min(equity // divisor, room, cash)

    if (state.seq + 1) % EVERY == 0:
        scored = []
        for sym in SYMBOLS:
            s = SERIES[sym]
            if len(s.closes) <= LOOKBACK:
                continue
            if s.filt.value is None or s.closes[-1] <= s.filt.value:
                continue
            scored.append((s.closes[-1] / s.closes[-1 - LOOKBACK], sym))
        scored.sort(key=lambda x: (-x[0], x[1]))
        top = [sym for _, sym in scored[:TOPN]]
        for sym in SYMBOLS:
            if sym in state.positions and sym not in top and sym not in sold:
                held = state.positions[sym]
                if len(orders) < max_orders:
                    orders.append({"side": "sell", "symbol": sym, "qty": held.qty,
                                   "max_slippage_bps": MAX_SLIP})
        for sym in top:
            if sym in state.positions or len(orders) >= max_orders:
                continue
            size = stake(TOPN)
            if size < min_notional:
                continue
            orders.append({"side": "buy", "symbol": sym,
                           "notional_quote_units": size,
                           "max_slippage_bps": MAX_SLIP})
            cash -= size
        _check_orders(state, orders)
        return orders

    slots = min(len(SYMBOLS), caps["max_open_positions"])
    room = slots - len(state.positions)
    for sym in SYMBOLS:
        if room <= 0 or len(orders) >= max_orders:
            break
        if sym in cross_up and sym not in state.positions:
            size = stake(slots)
            if size < min_notional:
                break
            orders.append({"side": "buy", "symbol": sym,
                           "notional_quote_units": size,
                           "max_slippage_bps": MAX_SLIP})
            cash -= size
            room -= 1
    _check_orders(state, orders)
    return orders


makefun_bars.run(on_batch)
