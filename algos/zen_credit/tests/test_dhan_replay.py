from datetime import date, datetime, time

import numpy as np
import pandas as pd
import pytest

from backtest.dhan_history import DhanHistoryClient, chunks, option_payload
from backtest.dhan_replay import DhanReplay, atm_panels, parse_series, load_history
from backtest.nifty_2024 import Nifty2024Calendar, expiries_for, lot_size
from backtest.nse_settlement import parse_close
from backtest import nifty_2026
from backtest.dhan_replay import mark_open_trades, supplement_fixed_contracts
from config import StrategyConfig
from utils.time import IST


def test_historical_expiries_and_lots():
    assert expiries_for(date(2024, 4, 10))[:2] == [date(2024, 4, 10), date(2024, 4, 18)]
    assert expiries_for(date(2024, 8, 15))[0] == date(2024, 8, 22)
    assert not Nifty2024Calendar().is_trading_day(date(2024, 5, 20))
    assert not Nifty2024Calendar().is_trading_day(date(2024, 11, 20))
    assert lot_size(date(2024, 4, 25), date(2024, 4, 25)) == 50
    assert lot_size(date(2024, 4, 26), date(2024, 5, 2)) == 25
    assert lot_size(date(2024, 12, 20), date(2024, 12, 26)) == 25
    assert lot_size(date(2024, 12, 20), date(2025, 1, 2)) == 75
    assert lot_size(date(2025, 1, 1), date(2025, 1, 30)) == 25
    with pytest.raises(ValueError):
        Nifty2024Calendar().is_trading_day(date(2026, 1, 1))


def test_september_2026_rollover_and_october_holiday():
    calendar = nifty_2026.Nifty2026Calendar()
    assert nifty_2026.expiries_for(date(2026, 9, 28)) == [date(2026, 9, 29), date(2026, 10, 6)]
    assert nifty_2026.expiries_for(date(2026, 9, 30))[0] == date(2026, 10, 6)
    assert calendar.next_trading_day(date(2026, 10, 1)) == date(2026, 10, 5)
    assert nifty_2026.lot_size(date(2026, 9, 28), date(2026, 9, 29)) == 65
    assert nifty_2026.expiries_for(date(2026, 10, 19))[0] == date(2026, 10, 19)


def test_open_trade_valuation_does_not_close_or_fill_missing_quotes(monkeypatch):
    bars, options = sample()
    replay = DhanReplay(StrategyConfig(), bars, options)
    indicators = pd.DataFrame({"alpha": [.1]*4, "alpha2": [.1]*4}, index=bars.index + pd.Timedelta(minutes=1))
    monkeypatch.setattr(replay, "_indicator_frame", lambda: indicators)
    result = replay.run(end=indicators.index[0].to_pydatetime())
    trades = result.to_frame()
    mark_open_trades(trades, replay, result.last_decision)
    assert trades.iloc[0]["unrealized_pnl"] == 0
    assert pd.isna(trades.iloc[0]["exit_ts"]) and pd.isna(trades.iloc[0]["pnl"])
    replay.quote_index = {}
    mark_open_trades(trades, replay, result.last_decision)
    assert pd.isna(trades.iloc[0]["unrealized_pnl"])


def test_fixed_feed_replaces_rolling_and_preserves_missing_candles(tmp_path, monkeypatch):
    bars, options = sample()
    pd.DataFrame({"SM_EXPIRY_DATE": ["2024-01-04"]*2, "STRIKE_PRICE": [22000]*2,
                  "OPTION_TYPE": ["CE", "PE"], "SECURITY_ID": [1, 2], "LOT_SIZE": [50]*2}).to_csv(
        tmp_path / "dhan_nifty_contracts_2024-01-02.csv", index=False)
    class Client:
        cache_dir = tmp_path
        offline = True
        def __init__(self, *a, **k):
            pass
        def request(self, endpoint, payload):
            return {"timestamp": [int(t.timestamp()) for t in bars.index[:3]],
                    "close": [101, 102, 103], "volume": [10, 20, 30]}
    monkeypatch.setattr("backtest.dhan_replay.DhanHistoryClient", Client)
    merged, audit = supplement_fixed_contracts(Client(), bars, options, date(2024, 1, 2),
                                              Nifty2024Calendar(), expiries_for, lot_size)
    assert audit["fixed_contracts"] == 2
    assert merged.iloc[0]["ce_ltp"] == 101  # rolling price was 200
    assert len(merged) == 3  # the fourth rolling minute must stay absent
    assert set(merged.index.get_level_values("strike")) == {22000}


def test_chunk_boundaries_and_rolling_payload():
    ranges = list(chunks(date(2024, 1, 1), date(2024, 3, 1)))
    assert ranges[0][0] == date(2024, 1, 1)
    assert ranges[-1][1] == date(2024, 3, 1)
    assert all((b-a).days <= 28 for a,b in ranges)
    assert all(ranges[i][1] == ranges[i+1][0] for i in range(len(ranges)-1))
    assert option_payload(*ranges[0], 2, -3, "PUT")["strike"] == "ATM-3"
    assert option_payload(*ranges[0], 1, 0, "CALL")["expiryCode"] == 1


def test_api_overrun_and_session_filter():
    times = pd.DatetimeIndex([datetime(2024, 1, 1, 9, 15, tzinfo=IST),
                             datetime(2024, 1, 1, 15, 30, tzinfo=IST),
                             datetime(2024, 1, 2, 9, 15, tzinfo=IST)])
    raw = {"timestamp": [t.timestamp() for t in times], "close": [10, 11, 12], "iv": []}
    frame = parse_series(raw, date(2024, 1, 1), date(2024, 1, 2), Nifty2024Calendar())
    assert len(frame) == 1 and frame.iloc[0]["close"] == 10


def test_named_strategy02_disables_target_but_keeps_stop_and_unique_identity(monkeypatch):
    bars,options=sample();minutes=bars.index+pd.Timedelta(minutes=1)
    options.loc[(minutes[1],date(2024,1,4),22000.),'ce_ltp']=5.
    options.loc[(minutes[1],date(2024,1,4),22400.),'ce_ltp']=2.
    options.loc[(minutes[2],date(2024,1,4),22000.),'ce_ltp']=300.
    indicators=pd.DataFrame({'alpha':[.1]*4,'alpha2':[.1]*4},index=minutes)
    first=minutes[0].to_pydatetime();positions=[]
    for name in ('strategy_01','strategy_02'):
        replay=DhanReplay(StrategyConfig(),bars,options,strategy_name=name)
        monkeypatch.setattr(replay,'_indicator_frame',lambda:indicators)
        position=replay.run(end=first).final_position
        positions.append(position)
    assert positions[0].target==10. and positions[1].target is None
    assert positions[0].signal_id!=positions[1].signal_id
    replay=DhanReplay(StrategyConfig(),bars,options,strategy_name='strategy_02')
    monkeypatch.setattr(replay,'_indicator_frame',lambda:indicators)
    result=replay.run(entry_end=first)
    assert len(result.trades)==1 and result.trades[0].exit_reason=='Stop loss'
    assert result.trades[0].exit_ts==minutes[2].to_pydatetime()


def sample():
    index = pd.date_range("2024-01-01 10:14", periods=4, freq="1min", tz=IST)
    bars = pd.DataFrame({"open": [22000]*4, "close": [22000,22050,22050,22050]}, index=index)
    rows = []
    for i, m in enumerate(index + pd.Timedelta(minutes=1)):
        for strike in (22000.,22050.,22400.,22450.):
            # A moving ATM must compare 22050 now with 22050 previously, not 22000.
            ce = (100 + i*10) if strike == 22050 else (200 + i*10)
            if strike >= 22400:
                ce = 20 + i
            rows.append([m,date(2024,1,4),strike,ce,ce/2,10+i,20+i])
    options = pd.DataFrame(rows, columns=["minute","expiry","strike","ce_ltp","pe_ltp","ce_volume","pe_volume"])
    return bars, options.set_index(["minute","expiry","strike"]).sort_index()


@pytest.mark.parametrize('missing_held_hedge', [False, True])
def test_research_reentry_follows_only_a_real_exit_with_same_completed_inputs(monkeypatch, missing_held_hedge):
    bars, options = sample()
    minutes = bars.index + pd.Timedelta(minutes=1)
    options.loc[(minutes[1], date(2024,1,4), 22000.), 'ce_ltp'] = 300.
    if missing_held_hedge:
        options = options.drop((minutes[1], date(2024,1,4), 22400.))
    cfg = StrategyConfig(strike_reference='last_bar_open', max_short_premium=None)
    indicators = pd.DataFrame({'alpha': [.1]*4, 'alpha2': [.1]*4}, index=minutes)
    runs = []
    for enabled, entry_end in ((False, None), (True, None), (True, minutes[0].to_pydatetime())):
        replay = DhanReplay(cfg, bars, options)
        monkeypatch.setattr(replay, '_indicator_frame', lambda: indicators)
        result = replay.run(end=minutes[1].to_pydatetime(), entry_end=entry_end,
                            reentry_after_exit=enabled)
        runs.append((replay, result))
    baseline, enabled, cutoff = runs
    if missing_held_hedge:
        assert baseline[0].coverage_events
        assert all(result.final_position.entry_ts == minutes[0] for _, result in runs)
        assert all(result.evaluations == 2 for _, result in runs)
    else:
        assert baseline[1].trades[0].exit_reason == 'Stop loss'
        assert baseline[1].final_position is None
        assert cutoff[1].final_position is None and cutoff[1].evaluations == 2
        assert enabled[1].final_position.entry_ts == minutes[1]
        assert enabled[1].evaluations == 3
        second = [d for d in enabled[0].decisions if d['minute'] == minutes[1].isoformat()]
        assert [d['action'] for d in second] == ['exit', 'entry']
        assert len({(d['alpha'], d['alpha2']) for d in second}) == 1
    with pytest.raises(ValueError, match='boolean'):
        baseline[0].run(reentry_after_exit='true')


def test_research_reentry_refreshes_nearest_expiry_quotes_and_lot_size(monkeypatch):
    from strategy.engine import MarketView
    bars, near = sample()
    minutes = bars.index + pd.Timedelta(minutes=1)
    old_expiry, new_expiry = date(2024,1,11), date(2024,1,4)
    old = near.reset_index(); old['expiry'] = old_expiry
    old = old.set_index(['minute', 'expiry', 'strike'])
    old.loc[(minutes[1], old_expiry, 22000.), 'ce_ltp'] = 300.
    near.loc[(minutes[1], new_expiry, 22000.), 'ce_ltp'] = 105.
    options = pd.concat([near, old]).sort_index()
    cfg = StrategyConfig(strike_reference='last_bar_open', max_short_premium=None)
    replay = DhanReplay(cfg, bars, options, lot_resolver=lambda day, expiry: 50 if expiry == new_expiry else 25)
    chain = replay._chain_at(minutes[0], old_expiry, 22000.)
    view = MarketView(minutes[0].to_pydatetime(), bars.iloc[:1], None, chain, [old_expiry], 25,
                      indicators=(.1, .1))
    initial = replay.engine.evaluate(view, None).position
    assert initial.expiry == old_expiry
    replay.trade_details[initial.entry_ts] = {'sell_leg_entry': initial.sell_price,
        'buy_leg_entry': initial.buy_price, 'scheduled_exit': initial.exit_due}
    indicators = pd.DataFrame({'alpha': [.1]*4, 'alpha2': [.1]*4}, index=minutes)
    monkeypatch.setattr(replay, '_indicator_frame', lambda: indicators)
    result = replay.run(start=minutes[1].to_pydatetime(), end=minutes[1].to_pydatetime(),
                        initial_position=initial, reentry_after_exit=True)
    assert result.trades[0].expiry == old_expiry
    assert result.final_position.expiry == new_expiry
    assert result.final_position.sell_price == 105.
    assert result.final_position.lot_size == 50


def test_native_volume_and_fixed_strike_return():
    bars, options = sample()
    panel = atm_panels(options, bars)[date(2024,1,4)]
    assert panel.iloc[1]["atm_strike"] == 22050
    assert panel.iloc[1]["ce_return"] == pytest.approx(.1)
    assert panel.iloc[1]["ce_volume"] == 11  # native candle volume, not rolling-ATM delta
    assert pd.isna(panel.iloc[0]["ce_return"])
    missing = options.drop((panel.index[0], date(2024,1,4), 22050.))
    assert pd.isna(atm_panels(missing, bars)[date(2024,1,4)].iloc[1]["ce_return"])


def test_original_contract_quotes_and_slippage():
    bars, options = sample()
    replay = DhanReplay(StrategyConfig(), bars, options, .5)
    minute = bars.index[1] + pd.Timedelta(minutes=1)
    chain = replay._chain_at(minute, date(2024,1,4), 22050)
    assert chain.quote(22000,"CE").ltp == 210  # old strike is retained after ATM changes
    assert chain.quote(22050,"CE").bid == 109.5
    assert chain.quote(22050,"CE").ask == 110.5
    missing = options.drop((minute, date(2024,1,4), 22050.))
    chain = DhanReplay(StrategyConfig(), bars, missing)._chain_at(minute,date(2024,1,4),22050)
    assert chain.quote(22050,"CE").ltp is None  # cannot silently move short strike


def test_cache_does_not_contain_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("DHAN_CLIENT_ID", "test-client-private")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "test-token-private")
    client = DhanHistoryClient(tmp_path)
    class Response:
        status_code = 200
        def json(self):
            return {"timestamp": [], "close": []}
    monkeypatch.setattr(client.session, "post", lambda *a, **k: Response())
    payload = {"fromDate": "2024-01-01", "toDate": "2024-01-02"}
    assert client.request("intraday", payload)["timestamp"] == []
    import gzip
    with gzip.open(next(tmp_path.glob("*.gz")), "rt") as f:
        text = f.read()
    assert "test-token-private" not in text and "test-client-private" not in text
    assert DhanHistoryClient(tmp_path, offline=True).request("intraday", payload)["timestamp"] == []
    with pytest.raises(ValueError):
        client.request("orders", {})


def test_entry_cutoff_keeps_exit_monitoring(monkeypatch):
    bars, options = sample()
    cfg = StrategyConfig()
    replay = DhanReplay(cfg, bars, options)
    indicators = pd.DataFrame({"alpha": [.1]*4, "alpha2": [.1]*4}, index=bars.index + pd.Timedelta(minutes=1))
    monkeypatch.setattr(replay, "_indicator_frame", lambda: indicators)
    end = indicators.index[0].to_pydatetime()
    result = replay.run(entry_end=end)
    assert len(result.trades) == 1
    assert result.trades[0].entry_ts == end
    assert result.evaluations > 1  # still evaluates held position beyond entry cutoff


def test_chunked_replay_carries_original_position_and_matches_monolithic_run(monkeypatch):
    from dataclasses import asdict,replace
    bars,options=sample()
    cfg=replace(StrategyConfig(),stop_loss_margin_fraction=.01)
    indicators=pd.DataFrame({'alpha':[.1]*4,'alpha2':[.1]*4},index=bars.index+pd.Timedelta(minutes=1))
    first=indicators.index[0].to_pydatetime()
    full=DhanReplay(cfg,bars,options)
    monkeypatch.setattr(full,'_indicator_frame',lambda:indicators)
    expected=full.run(entry_end=first)
    left=DhanReplay(cfg,bars.iloc[:1],options.loc[options.index.get_level_values('minute')<=first])
    monkeypatch.setattr(left,'_indicator_frame',lambda:indicators)
    a=left.run(entry_end=first,include_open_trade=False)
    assert not a.trades and a.final_position is not None
    right=DhanReplay(cfg,bars.iloc[1:],options.loc[options.index.get_level_values('minute')>first])
    right.trade_details=left.trade_details.copy()
    right._last_decision=a.last_decision
    monkeypatch.setattr(right,'_indicator_frame',lambda:indicators)
    b=right.run(entry_end=first,initial_position=a.final_position,include_open_trade=False)
    assert len(b.trades)==1 and b.final_position is None
    assert [asdict(t) for t in expected.trades]==[asdict(t) for t in b.trades]


@pytest.mark.parametrize('missing_hedge', [False, True])
def test_prepared_quote_index_matches_independent_replays_and_preserves_gaps(monkeypatch, missing_hedge):
    from dataclasses import asdict, replace
    from backtest.dhan_replay import prepare_option_quotes
    bars, options = sample()
    indicators = pd.DataFrame({'alpha': [.1]*4, 'alpha2': [.1]*4},
                              index=bars.index+pd.Timedelta(minutes=1))
    if missing_hedge:
        options.loc[(indicators.index[1], date(2024, 1, 4), 22400.), 'ce_ltp'] = np.nan
    # An unsorted source must produce the same deterministic contract chains.
    options = options.iloc[::-1]
    before = options.copy(deep=True)
    cfg = replace(StrategyConfig(), stop_loss_margin_fraction=.01)
    prepared = prepare_option_quotes(options)
    baseline = DhanReplay(cfg, bars, options)
    engines = [DhanReplay(cfg, bars, options, prepared_quotes=prepared) for _ in range(2)]
    assert engines[0].quote_index is engines[1].quote_index is prepared.quote_index
    assert engines[0].engine is not engines[1].engine
    assert engines[0].trade_details is not engines[1].trade_details
    assert engines[0].decisions is not engines[1].decisions
    assert engines[0].coverage_events is not engines[1].coverage_events
    results = []
    for replay in [baseline, *engines]:
        monkeypatch.setattr(replay, '_indicator_frame', lambda: indicators)
        results.append(replay.run(entry_end=indicators.index[0].to_pydatetime()))
    assert results[0].trades
    if missing_hedge:
        assert baseline.coverage_events  # Exercise held-leg missing-quote behavior.
    for replay, result in zip(engines, results[1:]):
        assert asdict(result) == asdict(results[0])
        assert replay.decisions == baseline.decisions
        assert replay.coverage_events == baseline.coverage_events
        assert replay.trade_details == baseline.trade_details
    pd.testing.assert_frame_equal(options, before)
    key = next(iter(prepared.quote_index))
    with pytest.raises(TypeError):
        prepared.quote_index[key] = ([], [])
    for array in prepared.quote_index[key]:
        with pytest.raises(ValueError):
            array.flat[0] = 0
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(ValueError, match='different historical chunk'):
        DhanReplay(cfg, bars, options.copy(), prepared_quotes=prepared)


@pytest.mark.parametrize('slippage', [0, 2.5])
def test_lazy_quote_mapping_preserves_eager_prices_placeholders_and_duplicates(slippage):
    from dataclasses import FrozenInstanceError, replace
    from data.providers.base import OptionChainSnapshot, OptionQuote
    bars, options = sample()
    # Include duplicates where the last row is invalid for one side, but valid
    # for the other. Eager construction retains the last VALID side price.
    duplicate = options.iloc[:1].copy()
    duplicate['ce_ltp'] = np.nan
    duplicate['pe_ltp'] = 0.
    options = pd.concat([options, duplicate])
    options.iloc[1, options.columns.get_loc('ce_ltp')] = np.inf
    options.iloc[2, options.columns.get_loc('pe_ltp')] = -1.
    replay = DhanReplay(replace(StrategyConfig(), strike_reference='last_bar_open'),
                        bars, options, slippage_points=slippage)
    for ts in bars.index + pd.Timedelta(minutes=1):
        for expiry in set(options.index.get_level_values('expiry')) | {date(2024, 1, 11)}:
            actual = replay._chain_at(ts, expiry, float(bars.loc[ts-pd.Timedelta(minutes=1), 'close']))
            eager = OptionChainSnapshot(actual.underlying, expiry, ts, actual.spot)
            strikes, prices = replay.quote_index.get((ts, expiry), ([], []))
            for strike, pair in zip(strikes, prices):
                for side, price in zip(('CE', 'PE'), pair):
                    if np.isfinite(price) and price >= 0:
                        eager.quotes[(float(strike), side)] = OptionQuote(float(strike), side, float(price),
                            max(0, float(price)-slippage), float(price)+slippage, None)
            opening = float(bars.loc[ts-pd.Timedelta(minutes=1), 'open'])
            references = {float(np.floor((v+25-1e-8)/50)*50) for v in (actual.spot, opening)}
            for strike in references:
                for side in ('CE', 'PE'):
                    eager.quotes.setdefault((strike, side), OptionQuote(strike, side, None, None, None, None))
            assert dict(actual.quotes) == eager.quotes
            assert len(actual.quotes) == len(eager.quotes)
            assert actual.strikes == eager.strikes
            assert actual.to_rows(ts) == eager.to_rows(ts)
            assert actual.quote(99999, 'CE') is None
            assert actual.quote(actual.strikes[0], 'XX') is None
            with pytest.raises(TypeError):
                actual.quotes[(22000., 'CE')] = None
            with pytest.raises(FrozenInstanceError):
                actual.quotes.slippage = 99


def test_conflicting_contract_quotes_are_excluded():
    class Client:
        def request(self, endpoint, payload):
            epoch = datetime(2024,1,1,10,14,tzinfo=IST).timestamp()
            if endpoint == "intraday":
                return {"timestamp":[epoch], "open":[22000], "high":[22001], "low":[21999],
                        "close":[22000], "volume":[0]}
            offset = 0 if payload["strike"] == "ATM" else int(payload["strike"][3:])
            strike = 22000 + offset*50
            if offset in (-2,-1):
                strike = 21900
            raw = {"timestamp":[epoch], "strike":[strike], "close":[100+offset],
                   "volume":[20], "spot":[22000], "iv":[]}
            side = "ce" if payload["drvOptionType"] == "CALL" else "pe"
            return {"data":{side:raw}}
    _, options, conflicts = load_history(Client(), date(2024,1,1),date(2024,1,2),progress=lambda *a, **k:None)
    assert len(conflicts) == 8  # two offsets, two sides, two expiry codes
    assert 21900 not in options.index.get_level_values("strike")


def test_settlement_is_dated_and_never_visible_before_expiry():
    source = "https://nsearchives.nseindia.com/content/indices/ind_close_all_04012024.csv"
    text = "Index Name,Index Date,Closing Index Value\nNifty 50,04-01-2024,22000.25\n"
    settlement = parse_close(text,date(2024,1,4),source)
    assert settlement.spot == 22000.25 and settlement.expiry == date(2024,1,4)
    with pytest.raises(ValueError):
        parse_close(text,date(2024,1,5),source)
    bars, options = sample()
    calls = []
    def loader(expiry):
        calls.append(expiry)
        return settlement
    replay = DhanReplay(StrategyConfig(),bars,options,settlement_loader=loader)
    assert replay._settlement_at(datetime(2024,1,4,14,tzinfo=IST),date(2024,1,4)) is None
    assert not calls
    assert replay._settlement_at(datetime(2024,1,5,9,16,tzinfo=IST),date(2024,1,4)) == settlement


def test_official_settlement_retries_timeout_then_caches_verified_archive(tmp_path,monkeypatch):
    from backtest.nse_settlement import NSESettlementClient
    import requests
    from types import SimpleNamespace
    text='Index Name,Index Date,Closing Index Value\nNifty 50,02-12-2025,26032.20\n'
    calls=[]
    def fetch(*args,**kwargs):
        calls.append(args[0])
        if len(calls)==1:raise requests.Timeout('transient archive timeout')
        return SimpleNamespace(status_code=200,text=text)
    monkeypatch.setattr(requests,'get',fetch)
    client=NSESettlementClient(tmp_path)
    result=client.get(date(2025,12,2))
    assert result.spot==26032.2 and len(calls)==2
    assert (tmp_path/'nse_2025-12-02.csv').read_text()==text
    assert client.get(date(2025,12,2)) is result and len(calls)==2
    assert NSESettlementClient(tmp_path,offline=True).get(date(2025,12,2))==result


def test_official_settlement_rejects_wrong_date_without_caching_a_price(tmp_path,monkeypatch):
    from backtest.nse_settlement import NSESettlementClient
    import requests
    from types import SimpleNamespace
    text='Index Name,Index Date,Closing Index Value\nNifty 50,01-12-2025,26175.75\n'
    calls=[]
    def fetch(*args,**kwargs):
        calls.append(args[0]);return SimpleNamespace(status_code=200,text=text)
    monkeypatch.setattr(requests,'get',fetch)
    assert NSESettlementClient(tmp_path).get(date(2025,12,2)) is None
    assert len(calls)==1 and not (tmp_path/'nse_2025-12-02.csv').exists()
