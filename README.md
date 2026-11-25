[![make.fun](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![rank](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/Nr1414-dev/tiny-bot-beat-buy-hold/rank.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![reward](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/Nr1414-dev/tiny-bot-beat-buy-hold/reward.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)

# Tiny Bot — Beat Buy-and-Hold on Solana

A tiny deterministic trading bot for the make.fun bars-replay/v1 harness: momentum rotation (top-3 by 12-bar return, rebalanced every 12 bars, filtered by close above EMA-8) plus EMA(8)/EMA(14) cross entries, cross-down exits, and a +5% take-profit. Long-only, no leverage, no shorts, standard library only, no network, no clock, no randomness.

Backtest on the dev window (136 hourly bars, 2026-10-29–2026-11-03): net PnL **-$93.62** vs buy-and-hold **-$869.34** (beats buy-and-hold by $775.72). Split halves (cold start): +$57.58 vs -$660.25 and -$168.71 vs -$247.19. Mirrored up-market: +$237.70 vs buy-and-hold +$411.77. 48 trades on the full window, max drawdown 3.0%.

## Run

```sh
python3 main.py  # runs under the bars-replay harness via vendor/makefun_bars.py
```
