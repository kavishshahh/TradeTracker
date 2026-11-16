"""Strategy registry. Add a new strategy: drop a module here and register its class."""
from .crypto_fair_value import CryptoFairValue
from .sports_pregame_underdog import SportsPregameUnderdog
from .updown_leader import UpDownLeader3m, UpDownLeaderEarly
from .updown_latency import UpDownLatency1bp, UpDownLatency2bp, UpDownLatency2bpReal

REGISTRY = {cls.name: cls for cls in (CryptoFairValue, SportsPregameUnderdog, UpDownLeader3m, UpDownLeaderEarly,
                                    UpDownLatency2bp, UpDownLatency2bpReal, UpDownLatency1bp)}


def get(name, **overrides):
    return REGISTRY[name](**overrides)
