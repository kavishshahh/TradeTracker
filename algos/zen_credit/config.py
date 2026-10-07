"""Central configuration. No secrets in source.

Strategy parameters live in :class:`StrategyConfig`. Its defaults implement the
supplied description with a causal five-bar delay of its complete forward formula.
Volume/volatility windows, sizing and exits are documented assumptions where the
description is incomplete. The service selects a named profile with STRATEGY_NAME;
that profile pins its formula settings after loading deployment capital/margin.

Infrastructure settings are grouped the same way as the rest of the Dhan algo
projects: ``data`` (market data), ``email`` (SMTP), ``runtime``
(logging, cron token). ``.env`` is read for local runs only; Render injects real
environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent          # zen_credit/
REPO_ROOT = ROOT_DIR.parent                          # repository root (data/, reports/, .env)

# One server environment shared by the API and paper worker.
BACKEND_ENV = ROOT_DIR.parents[1] / "backend/.env"
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_ENV, override=False)
except ImportError:
    pass


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    return str(_env(name, str(default))).lower() in {"1", "true", "yes", "on"}


def _env_time(name: str, default: str) -> time:
    hh, mm = str(_env(name, default)).split(":")
    return time(int(hh), int(mm))


def _env_date(name: str, default: str) -> date:
    return date.fromisoformat(str(_env(name, default)))


@dataclass(frozen=True)
class StrategyConfig:
    # --- provider description -------------------------------------------------
    alpha_lookback_minutes: int = 800          # "lookback period of 800 minutes"
    alpha2_lookback_minutes: int = 300         # "300-minute time-series rank"
    price_change_horizon_minutes: int = 5      # "5-minute forward price change"
    bullish_threshold: float = 0.8             # "exceed 0.8"
    bearish_threshold: float = 0.2             # "fall below 0.2"
    signal_start: time = time(10, 15)          # "10:15 AM to 2:15 PM"
    signal_end: time = time(14, 15)
    spread_distance: int = 400                 # "400 points below/above"
    strike_reference: str = "spot"             # ATM at decision time, as described
    max_short_premium: float | None = None     # description supplies no premium cap
    # --- alpha2 details not stated by the provider (documented choices) -------
    volume_short_window: int = 5               # same horizon as the price change
    volume_baseline_window: int = 300          # the only alpha2 window provided
    volatility_window: int = 300               # the only alpha2 window provided
    alpha2_factor_lag_bars: int = 5            # delay starting-bar factors with the forward change
    # --- risk / exits: measured from the provider trade history ---------------
    stop_loss_margin_fraction: float = 0.05    # SL = 5% of normal-day margin per lot
    target_spread_value: float = 10.0          # target when spread value <= 10 points
    time_exit: time = time(14, 53)             # next-trading-day square-off time
    # Optional provider-history replay profile, inferred from timestamp clusters.
    # Empty by default: forward testing always uses the configured time_exit.
    historical_time_exit_start: date | None = None
    historical_time_exit_end: date | None = None
    historical_time_exit: time = time(15, 0)
    # --- sizing -----------------------------------------------------------------
    capital: float = 320000.0                  # provider "max capital"
    monday_capital_fraction: float = 1.0       # no Monday allocation rule in supplied description
    monday_allocation_start: date = date(2026, 4, 6)
    margin_to_width_ratio: float = 2.25        # broker margin / (width * lot size), normal day
    expiry_day_margin_multiplier: float = 1.54 # extra expiry-day margin (sizing only)
    margin_per_lot_override: float | None = None
    # --- market structure ---------------------------------------------------------
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    underlying: str = "NIFTY"


def load_strategy_config() -> StrategyConfig:
    override = _env("MARGIN_PER_LOT")
    premium = _env("MAX_SHORT_PREMIUM")
    return StrategyConfig(
        alpha_lookback_minutes=_env_int("ALPHA_LOOKBACK_MINUTES", 800),
        alpha2_lookback_minutes=_env_int("ALPHA2_LOOKBACK_MINUTES", 300),
        price_change_horizon_minutes=_env_int("PRICE_CHANGE_HORIZON_MINUTES", 5),
        bullish_threshold=_env_float("BULLISH_THRESHOLD", 0.8),
        bearish_threshold=_env_float("BEARISH_THRESHOLD", 0.2),
        signal_start=_env_time("SIGNAL_START_TIME", "10:15"),
        signal_end=_env_time("SIGNAL_END_TIME", "14:15"),
        spread_distance=_env_int("SPREAD_DISTANCE", 400),
        strike_reference=str(_env("STRIKE_REFERENCE", "spot")),
        max_short_premium=float(premium) if premium else None,
        volume_short_window=_env_int("VOLUME_SHORT_WINDOW", 5),
        volume_baseline_window=_env_int("VOLUME_BASELINE_WINDOW", 300),
        volatility_window=_env_int("VOLATILITY_WINDOW", 300),
        alpha2_factor_lag_bars=_env_int("ALPHA2_FACTOR_LAG_BARS", _env_int("PRICE_CHANGE_HORIZON_MINUTES", 5)),
        stop_loss_margin_fraction=_env_float("STOP_LOSS_MARGIN_FRACTION", 0.05),
        target_spread_value=_env_float("TARGET_SPREAD_VALUE", 10.0),
        time_exit=_env_time("TIME_EXIT", "14:53"),
        capital=_env_float("CAPITAL", 320000.0),
        monday_capital_fraction=_env_float("MONDAY_CAPITAL_FRACTION", 1.0),
        monday_allocation_start=_env_date("MONDAY_ALLOCATION_START", "2026-04-06"),
        margin_to_width_ratio=_env_float("MARGIN_TO_WIDTH_RATIO", 2.25),
        expiry_day_margin_multiplier=_env_float("EXPIRY_DAY_MARGIN_MULTIPLIER", 1.54),
        margin_per_lot_override=float(override) if override else None,
        underlying=_env("NIFTY_SYMBOL", "NIFTY"),
    )


# --------------------------------------------------------------------------- #
@dataclass
class DataConfig:
    provider: str = field(default_factory=lambda: _env("DATA_PROVIDER", "dhan"))
    nse_base_url: str = field(default_factory=lambda: _env("NSE_DATA_URL", "https://www.nseindia.com"))
    nse_holiday_url: str = field(default_factory=lambda: _env(
        "NSE_HOLIDAY_URL", "https://www.nseindia.com/api/holiday-master?type=trading"))
    nse_lot_size_url: str = field(default_factory=lambda: _env(
        "NSE_LOT_SIZE_URL", "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"))
    yahoo_chart_url: str = field(default_factory=lambda: _env(
        "YAHOO_CHART_URL", "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI"))
    holiday_cache_hours: int = field(default_factory=lambda: _env_int("HOLIDAY_CACHE_HOURS", 24))
    request_timeout: float = field(default_factory=lambda: _env_float("HTTP_TIMEOUT_SECONDS", 10.0))
    max_retries: int = field(default_factory=lambda: _env_int("HTTP_RETRIES", 3))
    # market data older than this is stale -> no trade
    max_data_age_seconds: int = field(default_factory=lambda: _env_int("MAX_DATA_AGE_SECONDS", 180))
    entry_price_source: str = field(default_factory=lambda: _env("ENTRY_PRICE_SOURCE", "ltp"))
    # Legacy isolated-test compatibility only. Production workers use Firestore
    # and do not require or read DATABASE_URL for execution storage.
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "") or "")


@dataclass
class EmailConfig:
    host: str = field(default_factory=lambda: _env("SMTP_HOST", "") or "")
    port: int = field(default_factory=lambda: _env_int("SMTP_PORT", 587))
    username: str = field(default_factory=lambda: _env("SMTP_USERNAME", "") or "")
    password: str = field(default_factory=lambda: _env("SMTP_PASSWORD", "") or "", repr=False)
    sender: str = field(default_factory=lambda: _env("EMAIL_FROM", "") or "")
    recipients: str = field(default_factory=lambda: _env("EMAIL_TO", "") or "")
    use_tls: bool = field(default_factory=lambda: _env_bool("SMTP_USE_TLS", True))
    enabled: bool = field(default_factory=lambda: _env_bool("EMAIL_ENABLED", False))
    entry_subject: str = field(default_factory=lambda: _env("ENTRY_EMAIL_SUBJECT", "Zen Credit Algo | NIFTY ENTRY"))
    exit_subject: str = field(default_factory=lambda: _env("EXIT_EMAIL_SUBJECT", "Zen Credit Algo | NIFTY EXIT"))
    max_attempts: int = 5

    @property
    def recipient_list(self) -> list[str]:
        return [a.strip() for a in self.recipients.split(",") if a.strip()]

    def is_configured(self) -> bool:
        return bool(self.host and self.sender and self.recipient_list)


@dataclass
class RuntimeConfig:
    # Named profiles pin their tested formula/risk settings; capital and broker
    # margin remain deployment settings. Use description for the legacy overrides.
    strategy_name: str = field(default_factory=lambda: _env("STRATEGY_NAME", "strategy_01") or "strategy_01")
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    log_dir: Path = ROOT_DIR / "logs"
    # Shared secret for POST /run-cycle. Unset means every request is refused.
    cron_token: str = field(default_factory=lambda: _env("CRON_TOKEN", "") or "", repr=False)


@dataclass
class Config:
    strategy: StrategyConfig = field(default_factory=load_strategy_config)
    data: DataConfig = field(default_factory=DataConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)


def load_config() -> Config:
    """Fresh config from the current environment (tests use this)."""
    return Config()


CONFIG = Config()
