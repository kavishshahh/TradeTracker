from datetime import date

import pytest

from data.providers.base import MarketDataError
from data.providers.nse import parse_expiries, parse_lot_sizes, parse_option_chain
from data.providers.yahoo import parse_yahoo_chart
from main import redact
from tests.conftest import load_fixture

EXP = date(2026, 9, 29)


def test_parse_option_chain_fixture():
    snap = parse_option_chain(load_fixture("nse_option_chain_sample.json"), EXP)
    assert snap.spot == pytest.approx(23140.5)
    assert snap.timestamp.tzinfo is not None
    q = snap.quote(23150, "CE")
    assert q is not None and (q.ltp is None or q.ltp > 0) and q.cum_volume >= 0
    assert all(k[1] in ("CE", "PE") for k in snap.quotes)


def test_parse_option_chain_rejects_bad_payload():
    with pytest.raises(MarketDataError):
        parse_option_chain({"records": {"data": []}}, EXP)
    payload = load_fixture("nse_option_chain_sample.json")
    with pytest.raises(MarketDataError):
        parse_option_chain(payload, date(2030, 1, 1))       # expiry not present


def test_non_positive_ltp_is_not_a_price():
    payload = load_fixture("nse_option_chain_sample.json")
    row = payload["records"]["data"][0]
    row["CE"]["lastPrice"] = -5
    snap = parse_option_chain(payload, EXP)
    assert snap.quote(row["strikePrice"], "CE").ltp is None


def test_expiries_and_lot_size():
    exps = parse_expiries(load_fixture("nse_contract_info_sample.json"))
    assert exps[0] == EXP and exps == sorted(exps)
    lots = parse_lot_sizes(load_fixture("nse_fo_mktlots_sample.csv"))
    assert lots["SEP-26"] == 65
    with pytest.raises(MarketDataError):
        parse_lot_sizes(load_fixture("nse_fo_mktlots_sample.csv"), "NOPE")


def test_yahoo_parse(tmp_path):
    payload = {"chart": {"result": [{"timestamp": [1790313300, 1790313360],
                                     "indicators": {"quote": [{"open": [1, 2], "high": [1, 2],
                                                               "low": [1, 2], "close": [1, 2]}]}}]}}
    df = parse_yahoo_chart(payload)
    assert str(df.index.tz) == "Asia/Kolkata"
    with pytest.raises(MarketDataError):
        parse_yahoo_chart({"chart": {}})


def test_redaction(monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2-xyz")
    assert "hunter2-xyz" not in redact("login failed for pw hunter2-xyz")
    assert redact("password=abc123 token: zzz") == "password=*** token: ***"
