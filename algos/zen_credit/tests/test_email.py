from datetime import date

from config import EmailConfig
from notifications.email import EmailNotifier, format_entry_email, format_exit_email
from tests.conftest import FakeSMTP

NL = chr(10)


def test_entry_email_exact():
    body = format_entry_email(spot=23140.5, expiry=date(2026, 9, 29), option_type="CE", sell_strike=23250,
                              buy_strike=23650, lots=5, units=325, sell_price=107.15, buy_price=11.45,
                              net_credit=95.70, stop_loss=140.70, target=10.0, max_loss=98897.5,
                              max_profit=31102.5)
    assert body == (
        "NIFTY 23140.50  | Expiry 29-Sep-2026\n"
        "SELL  23250 CE   Qty 5 lot (325)   @ 107.15\n"
        "BUY   23650 CE   Qty 5 lot (325)   @ 11.45\n"
        "Net credit: 95.70\n"
        "Stop loss:  140.70   (exit if spread value reaches this)\n"
        "Target:     10.00\n"
        "Max loss:   98897.50\n"
        "Max profit: 31102.50"
    )


def test_exit_email_exact():
    body = format_exit_email(23250, 23650, "CE", date(2026, 9, 29), 95.70, 59.85, 11651.25, 3.64, "Time exit")
    assert body == (
        "EXIT 23250/23650 CE  29-Sep-2026\n"
        "Entry 95.70  ->  Exit 59.85\n"
        "P&L: +11651.25 (+3.64%)\n"
        "Reason: Time exit"
    )
    loss = format_exit_email(23400, 23000, "PE", date(2026, 9, 29), 93.05, 148.45, -18005.0, -5.63, "Stop loss")
    assert loss.splitlines()[2] == "P&L: -18005.00 (-5.63%)"


def test_smtp_plain_text_and_no_password_leak():
    cfg = EmailConfig(host="smtp.test", port=587, username="user", password="s3cret-pass",
                      sender="from@x", recipients="to@x", use_tls=True, enabled=True)
    assert "s3cret-pass" not in repr(cfg)
    ok = EmailNotifier(cfg, smtp_factory=FakeSMTP)._send("NIFTY ENTRY", "BODY").ok
    assert ok and len(FakeSMTP.sent) == 1
    msg = FakeSMTP.sent[0]
    assert msg["Subject"] == "NIFTY ENTRY" and msg.get_content_type() == "text/plain"
    assert msg.get_content().rstrip(NL) == "BODY"


def test_smtp_not_configured_fails_safely():
    cfg = EmailConfig(host="", sender="", recipients="", password="", enabled=True)
    assert EmailNotifier(cfg)._send("s", "b").ok is False


def test_notifier_entry_exit_use_exact_bodies_and_subjects():
    from types import SimpleNamespace
    cfg = EmailConfig(host="h", sender="a@x", recipients="b@x, c@x", password="", enabled=True)
    row = SimpleNamespace(spot_at_entry=23140.5, expiry=date(2026, 9, 29), option_type="CE", sell_strike=23250,
                          buy_strike=23650, lots=5, units=325, sell_price=107.15, buy_price=11.45,
                          net_credit=95.70, stop_loss=140.70, target=10.0, max_loss=98897.5, max_profit=31102.5,
                          exit_value=59.85, pnl=11651.25, pnl_pct=3.64, exit_reason="Time exit")
    n = EmailNotifier(cfg, smtp_factory=FakeSMTP)
    assert n.send_entry(row).ok and n.send_exit(row).ok
    e, x = FakeSMTP.sent
    assert e["Subject"] == "Zen Credit Algo | NIFTY ENTRY" and x["Subject"] == "Zen Credit Algo | NIFTY EXIT" and e["To"] == "b@x, c@x"
    assert e.get_content().rstrip(NL) == format_entry_email(23140.5, date(2026, 9, 29), "CE", 23250, 23650, 5,
                                                            325, 107.15, 11.45, 95.70, 140.70, 10.0,
                                                            98897.5, 31102.5)
    assert x.get_content().rstrip(NL) == format_exit_email(23250, 23650, "CE", date(2026, 9, 29), 95.70,
                                                           59.85, 11651.25, 3.64, "Time exit")
