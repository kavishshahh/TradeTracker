"""Named strategy selection without changing serialized StrategyConfig fields."""
from __future__ import annotations

from config import StrategyConfig

STRATEGIES={'description':'Original supplied-description interpretation',
            'strategy_01':'Geometric-volume credit spread research candidate',
            'strategy_02':'Variance-scaled credit spread research candidate'}


def strategy_names():
    return tuple(STRATEGIES)


def get_strategy(name='description'):
    if name=='description':return None
    if name=='strategy_01':
        from strategy import strategy_01_geometric_credit
        return strategy_01_geometric_credit
    if name=='strategy_02':
        from strategy import strategy_02_variance_credit
        return strategy_02_variance_credit
    raise ValueError(f'Unknown strategy: {name}')


def apply_profile(name='description',cfg=None):
    module=get_strategy(name)
    return module.apply_profile(cfg) if module else (cfg or StrategyConfig())


def calculate_indicators(bars,panel,name='description',cfg=None):
    module=get_strategy(name)
    if module:return module.calculate_indicators(bars,panel)
    import pandas as pd
    from strategy.alpha import calculate_alpha,observed_price_change
    from strategy.alpha2 import calculate_alpha2
    cfg=cfg or StrategyConfig()
    alpha=calculate_alpha(bars,cfg.alpha_lookback_minutes,cfg.price_change_horizon_minutes)
    alpha.index+=pd.Timedelta(minutes=1)
    change=observed_price_change(bars,cfg.price_change_horizon_minutes);change.index+=pd.Timedelta(minutes=1)
    beta=calculate_alpha2(change,panel,cfg.alpha2_lookback_minutes,cfg.volume_short_window,
        cfg.volume_baseline_window,cfg.volatility_window,factor_lag_bars=cfg.alpha2_factor_lag_bars)
    return pd.DataFrame({'alpha':alpha,'alpha2':beta.reindex(alpha.index)},index=alpha.index)


def create_engine(name,cfg,calendar,**kwargs):
    module=get_strategy(name)
    if module:return module.create_engine(cfg,calendar,**kwargs)
    from strategy.engine import StrategyEngine
    engine=StrategyEngine(cfg,calendar,**kwargs);engine.strategy_name='description'
    return engine


def create_named_engine(module,cfg,calendar,**kwargs):
    """Shared named execution; each module owns indicators and target policy."""
    import hashlib
    import numpy as np
    import pandas as pd
    from strategy.engine import StrategyEngine
    from utils.time import IST
    class NamedCreditEngine(StrategyEngine):
        strategy_name=module.STRATEGY_NAME
        def indicators(self,view):
            if view.indicators is not None:return float(view.indicators[0]),float(view.indicators[1]),{}
            frame=module.calculate_indicators(view.spot_bars,module.panel_from_snapshots(view.spot_bars,view.snapshots))
            minute=pd.Timestamp(view.now).tz_convert(IST).floor('min')
            if minute not in frame.index:return float('nan'),float('nan'),{}
            row=frame.loc[minute]
            return float(row.alpha),float(row.alpha2),{k:float(v) if np.isfinite(v) else None
                for k,v in row.items() if k not in ('alpha','alpha2')}
        def evaluate(self,view,position):
            result=super().evaluate(view,position)
            if result.action=='entry' and result.position is not None:
                result.position.signal_id=hashlib.sha256(
                    f'{module.STRATEGY_NAME}|{result.position.signal_id}'.encode()).hexdigest()[:20]
                if not getattr(module,'PROFIT_TARGET_ENABLED',True):
                    result.position.target=None
                    result.diagnostics={**result.diagnostics,'profit_target_mode':'disabled','target':None}
            return result
    return NamedCreditEngine(module.apply_profile(cfg),calendar,**kwargs)
