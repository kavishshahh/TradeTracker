"""Email alerts. Two kinds only: a new ENTRY, or an EXIT of an open position.

Everything else (no-trade cycles, stale data, errors) goes to the log and the
/run-cycle JSON response, never to the inbox. Bodies are fixed plain text; the
two formatters below define them byte for byte. Send failures never propagate:
the runner records the email as failed and retries it on a later cycle (at most
``EmailConfig.max_attempts`` times); a sent email is never sent again.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage

from config import EmailConfig
from utils.time import fmt_expiry, fmt_num, fmt_signed

log = logging.getLogger(__name__)


def _strike(k: float) -> str:
    return f"{k:.0f}" if float(k).is_integer() else f"{k:.2f}"


def format_entry_email(spot: float, expiry: date, option_type: str, sell_strike: float, buy_strike: float,
                       lots: int, units: int, sell_price: float, buy_price: float, net_credit: float,
                       stop_loss: float, target: float | None, max_loss: float, max_profit: float) -> str:
    return "\n".join([
        f"NIFTY {fmt_num(spot)}  | Expiry {fmt_expiry(expiry)}",
        f"SELL  {_strike(sell_strike)} {option_type}   Qty {lots} lot ({units})   @ {fmt_num(sell_price)}",
        f"BUY   {_strike(buy_strike)} {option_type}   Qty {lots} lot ({units})   @ {fmt_num(buy_price)}",
        f"Net credit: {fmt_num(net_credit)}",
        f"Stop loss:  {fmt_num(stop_loss)}   (exit if spread value reaches this)",
        f"Target:     {fmt_num(target) if target is not None else 'Disabled'}",
        f"Max loss:   {fmt_num(max_loss)}",
        f"Max profit: {fmt_num(max_profit)}",
    ])


def format_exit_email(sell_strike: float, buy_strike: float, option_type: str, expiry: date,
                      entry_value: float, exit_value: float, pnl: float, pnl_pct: float, reason: str) -> str:
    return "\n".join([
        f"EXIT {_strike(sell_strike)}/{_strike(buy_strike)} {option_type}  {fmt_expiry(expiry)}",
        f"Entry {fmt_num(entry_value)}  ->  Exit {fmt_num(exit_value)}",
        f"P&L: {fmt_signed(pnl)} ({fmt_signed(pnl_pct)}%)",
        f"Reason: {reason}",
    ])


@dataclass
class SendResult:
    ok: bool
    detail: str


class EmailNotifier:
    def __init__(self, cfg: EmailConfig, smtp_factory=None):
        self.cfg = cfg
        self.smtp_factory = smtp_factory          # tests inject a mock SMTP server
        self.sent = 0
        self.failures = 0

    # ----------------------------------------------------------------- send
    def _send(self, subject: str, text: str) -> SendResult:
        if not self.cfg.enabled:
            log.info("email disabled; would have sent: %s", subject)
            return SendResult(True, "email disabled")
        if not self.cfg.is_configured():
            log.error("email not configured; alert not sent: %s", subject)
            return SendResult(False, "SMTP not configured (see .env.example)")
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.cfg.sender
        msg["To"] = ", ".join(self.cfg.recipient_list)
        msg.set_content(text)   # text/plain, utf-8
        try:
            context = ssl.create_default_context()
            if self.smtp_factory is not None:
                server = self.smtp_factory(self.cfg.host, self.cfg.port)
            elif self.cfg.port == 465:
                server = smtplib.SMTP_SSL(self.cfg.host, self.cfg.port, timeout=20, context=context)
            else:
                server = smtplib.SMTP(self.cfg.host, self.cfg.port, timeout=20)
            with server as s:
                if self.cfg.use_tls and self.cfg.port != 465:
                    s.starttls(context=context)
                if self.cfg.username and self.cfg.password:
                    s.login(self.cfg.username, self.cfg.password)
                s.send_message(msg)
            self.sent += 1
            log.info("sent email: %s", subject)
            return SendResult(True, "sent")
        except Exception as exc:  # noqa: BLE001 - never fatal
            self.failures += 1
            log.error("email send failed (%s): %s", type(exc).__name__, exc)
            return SendResult(False, f"{type(exc).__name__}: {exc}")

    # -------------------------------------------------------------- alerts
    def send_entry(self, row) -> SendResult:
        body = format_entry_email(row.spot_at_entry, _as_date(row.expiry), row.option_type,
                                  row.sell_strike, row.buy_strike, row.lots, row.units, row.sell_price,
                                  row.buy_price, row.net_credit, row.stop_loss, row.target,
                                  row.max_loss, row.max_profit)
        return self._send(self.cfg.entry_subject, body)

    def send_exit(self, row) -> SendResult:
        body = format_exit_email(row.sell_strike, row.buy_strike, row.option_type, _as_date(row.expiry),
                                 row.net_credit, row.exit_value, row.pnl, row.pnl_pct, row.exit_reason)
        return self._send(self.cfg.exit_subject, body)


def _as_date(d) -> date:
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
