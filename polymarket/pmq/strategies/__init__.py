"""Strategy registry. Add a new strategy: drop a module here and register its class."""
from .crypto_fair_value import CryptoFairValue
from .sports_pregame_underdog import SportsPregameUnderdog
from .updown_leader import UpDownLeader3m, UpDownLeaderEarly

REGISTRY = {cls.name: cls for cls in (CryptoFairValue, SportsPregameUnderdog, UpDownLeader3m, UpDownLeaderEarly)}


def get(name, **overrides):
    return REGISTRY[name](**overrides)
