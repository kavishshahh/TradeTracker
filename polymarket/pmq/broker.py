"""Fill simulation + risk checks. Same rules for backtest and paper so results are comparable."""
from .core import Fill, taker_fee

MIN_SHARES = 5.0


def _walk(ladder, want_usd=None, want_shares=None, limit=None, buy=True):
    """Consume (price, size) levels best-first. Returns (shares, avg_price)."""
    got_sh, spent = 0.0, 0.0
    for px, sz in ladder:
        if limit is not None and ((buy and px > limit + 1e-9) or (not buy and px < limit - 1e-9)):
            break
        if want_usd is not None:
            take = min(sz, (want_usd - spent) / px)
        else:
            take = min(sz, want_shares - got_sh)
        if take <= 0:
            break
        got_sh += take
        spent += take * px
        if (want_usd is not None and spent >= want_usd - 1e-6) or (want_shares is not None and got_sh >= want_shares - 1e-9):
            break
    return got_sh, (spent / got_sh if got_sh else None)


def execute(order, snap, portfolio, risk, slip=0.0):
    """Try to fill `order` against the snapshot. Returns Fill or (None, reason)."""
    m = snap.market
    cid = m["condition_id"]
    o = order.outcome
    rate = m.get("fee_rate", 0.0)
    min_sh = max(MIN_SHARES, m.get("min_size") or MIN_SHARES)

    if order.side == "BUY":
        if risk.get("one_entry_per_market", True) and portfolio.held(cid):
            return None, "already in market"
        if len({k[0] for k in portfolio.pos}) >= risk.get("max_open_markets", 50):
            return None, "max open markets"
        # The per-bet cap may not make a bet impossible: Polymarket's minimum is 5 shares, which
        # costs more than a small cap once the price is above ~50c. Allow just enough for the minimum.
        floor = 0 if risk.get("min_order_usd") else min_sh * (snap.ask[o] or 0) * 1.05
        usd = min(order.usd, portfolio.cash * 0.999, max(risk.get("max_order_usd", 1e9), floor))
        if portfolio.exposure() + usd > risk.get("max_exposure_usd", 1e9):
            usd = risk["max_exposure_usd"] - portfolio.exposure()
        ladder = snap.ask_depth[o] if snap.ask_depth[o] else ([(snap.ask[o], 1e12)] if snap.ask[o] else [])
        ladder = [(min(px + slip, 0.999), sz) for px, sz in ladder]
        if not ladder:
            return None, "no asks"
        sh, px = _walk(ladder, want_usd=usd, limit=order.limit)
        # Resting orders need 5 shares; a marketable order only needs $1 (set via risk["min_order_usd"]).
        min_usd = risk.get("min_order_usd")
        too_small = (not sh) or (sh * px < min_usd if min_usd else sh < min_sh)
        if too_small:
            return None, f"below min size ({sh:.2f} sh, usd {usd:.2f})"
        fee = taker_fee(rate, px, sh)
        if sh * px + fee > portfolio.cash:
            sh = (portfolio.cash - 0.01) / (px * (1 + rate * (1 - px)))
            if (sh * px < min_usd) if min_usd else (sh < min_sh):
                return None, "insufficient cash"
            fee = taker_fee(rate, px, sh)
        return Fill(snap.t, cid, o, "BUY", round(sh, 4), round(px, 6), fee, order.reason, m.get("question", "")), None

    # SELL
    held = portfolio.held(cid, o)
    if held <= 0:
        return None, "nothing to sell"
    want = held if not order.shares else min(order.shares, held)
    bid = snap.bid[o]
    if bid is None:
        return None, "no bids"
    ladder = [(max(bid - slip, 0.001), 1e12)]
    sh, px = _walk(ladder, want_shares=want, limit=order.limit, buy=False)
    if not sh:
        return None, "limit not met"
    return Fill(snap.t, cid, o, "SELL", round(sh, 4), round(px, 6), taker_fee(rate, px, sh), order.reason,
                m.get("question", "")), None
