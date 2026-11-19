"""Strategy registry. Add a new strategy: drop a module here and register its class."""
from .crypto_fair_value import CryptoFairValue
from .sports_pregame_underdog import SportsPregameUnderdog
from .updown_leader import UpDownLeader3m, UpDownLeaderEarly
from .updown_latency import UpDownLatency1bp, UpDownLatency2bp, UpDownLatency2bpReal
from .long_dated_no import LongDatedNo
from .copy_wallet import CopyC8b9Politics

REGISTRY = {cls.name: cls for cls in (CryptoFairValue, SportsPregameUnderdog, UpDownLeader3m, UpDownLeaderEarly,
                                    UpDownLatency2bp, UpDownLatency2bpReal, UpDownLatency1bp,
                                    CopyC8b9Politics,
                                    LongDatedNo)}


def get(name, **overrides):
    return REGISTRY[name](**overrides)
