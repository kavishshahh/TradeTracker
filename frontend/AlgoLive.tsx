'use client';

import { AlertTriangle, CircleCheck, Lock, OctagonX, Power, Radio } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { marketOpen, money, time, type Strategy } from './algoData';
import { averageSlippage, deskStale, modeLabel, points, stateWord, stopSlippage, type LiveActions, type LiveMode, type LiveResponse, type LiveSetting, type LiveState, type LiveTrade } from './liveData';
import { AlgoIcon, EmptyRow, tone } from './algoUi';
import base from './algos.module.css';
import styles from './algoLive.module.css';

/** Algo Lab > Dry run (owner only): switch an algo between the modes the API offers, set the capital it
 *  deploys, and see what the order desk did. Saving stores a setting; the worker acts on it within a minute.
 *  Live trading is switched off in the code, so the API offers only Off and Dry run and the live-only
 *  controls (server lock, Dhan position check, loss limit) stay hidden until it is switched on. */
export default function AlgoLive({ catalog, actions }: { catalog: Strategy[]; actions: LiveActions }) {
  const [live, setLive] = useState<LiveResponse | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [confirmExitAll, setConfirmExitAll] = useState(false);
  const [limit, setLimit] = useState('');

  const load = useCallback(async () => {
    try { const body = await actions.load(); setLive(body); setError(''); setLimit(body.account.daily_loss_limit ? String(body.account.daily_loss_limit) : ''); }
    catch { setError('Live trading status is unavailable right now.'); }
  }, [actions]);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const act = useCallback(async (key: string, task: () => Promise<void>) => {
    setBusy(key);
    try { await task(); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not save. Please retry.'); }
    finally { setBusy(''); }
  }, [load]);

  if (!live) return <div className={base.card}>
    <EmptyRow>{error || 'Loading live trading status…'}</EmptyRow>
    {error && <button className={base.outlineButton} onClick={() => void load()}>Try again</button>}
  </div>;

  const { account, desk, limits, states } = live;
  const liveAvailable = limits.modes.includes('live');
  const settings = account.strategies || {};
  const anyLive = Object.values(settings).some(item => item.mode === 'live');
  const stale = deskStale(desk, marketOpen()) && Object.values(settings).some(item => item.mode !== 'off');
  const trades = catalog.flatMap(strategy => (states[strategy.id]?.recent || []).map(trade => ({ trade, name: strategy.name }))).sort((a, b) => Date.parse(b.trade.closed_at || b.trade.opened_at) - Date.parse(a.trade.closed_at || a.trade.opened_at));
  const alerts = catalog.flatMap(strategy => (states[strategy.id]?.alerts || []).map(alert => ({ ...alert, name: strategy.name }))).sort((a, b) => Date.parse(b.at) - Date.parse(a.at)).slice(0, 12);
  const limitValue = Number(limit || 0);

  return <div className={styles.live}>
    <p className={styles.intro}><Radio size={15} aria-hidden="true" />{liveAvailable ? 'Real orders in your Dhan account that copy each algo’s paper trades. Changes take effect within a minute. Only you can see this tab.' : 'Dry run copies each algo’s paper trades at the live bid and ask, at the capital you choose. No order is sent to Dhan. Only you can see this tab.'}</p>
    {error && <div className={base.notice} role="status"><AlertTriangle size={16} />{error}</div>}

    <div className={styles.status}>
      {liveAvailable
        ? <Status label="Server" ok={!!desk?.live_unlocked} good="Live orders unlocked" bad="Live orders locked" detail={desk?.live_unlocked ? 'LIVE_TRADING_ENABLED is on' : 'Set LIVE_TRADING_ENABLED=true on the server to allow real orders. Dry run works without it.'} icon="lock" />
        : <Status label="Dhan orders" ok good="Switched off" bad="" detail="Live trading is switched off in the code. Nothing on this page can place an order." />}
      <Status label="Order desk" ok={!stale} good={desk ? `Updated ${time(desk.at)}` : 'Idle'} bad={desk ? `No update since ${time(desk.at)}` : 'Not running'} detail={desk?.broker_error || (stale ? 'The worker has not reported during market hours.' : 'Runs with the paper worker, once a minute.')} />
      {liveAvailable && <Status label="Dhan positions" ok={!desk?.mismatch} good={anyLive ? 'Hold the desk’s trades' : 'Nothing live'} bad="Missing part of a trade" detail={desk?.mismatch || 'Checked every minute while a live trade is open. Other positions in the account are ignored.'} />}
      <div className={`${styles.statusItem} ${account.kill_switch ? styles.bad : ''}`}>
        <span className={styles.statusLabel}>Kill switch</span>
        <b>{account.kill_switch ? 'On: no new entries' : 'Off'}</b>
        <small>Stops new {liveAvailable ? 'live and ' : ''}dry-run entries here. It does not use Dhan’s kill switch or touch your Dhan account.</small>
        <button className={account.kill_switch ? base.outlineButton : styles.danger} disabled={busy === 'kill'} onClick={() => void act('kill', () => actions.saveAccount({ kill_switch: !account.kill_switch }))}><Power size={13} />{account.kill_switch ? 'Turn off' : 'Stop new entries'}</button>
      </div>
    </div>

    {liveAvailable && <div className={styles.accountRow}>
      <label className={styles.field}>Daily loss limit
        <span className={styles.inputWrap}><i>₹</i><input inputMode="numeric" value={limit} placeholder="None" onChange={event => setLimit(event.target.value.replace(/[^\d]/g, ''))} aria-label="Daily loss limit in rupees" /></span>
      </label>
      <button className={base.outlineButton} disabled={busy === 'limit' || limitValue === (account.daily_loss_limit || 0)} onClick={() => void act('limit', () => actions.saveAccount({ daily_loss_limit: limitValue }))}>Save limit</button>
      <small>After this much live loss in a day, no new live entries until tomorrow. Open trades still exit normally.</small>
      <span className={styles.spacer} />
      {confirmExitAll
        ? <><button className={styles.danger} disabled={busy === 'exitAll'} onClick={() => void act('exitAll', async () => { await actions.saveAccount({ exit_all: true }); setConfirmExitAll(false); })}><OctagonX size={13} />Confirm: exit every live trade</button><button className={base.linkButton} onClick={() => setConfirmExitAll(false)}>Cancel</button></>
        : <button className={base.outlineButton} onClick={() => setConfirmExitAll(true)}>Exit all live trades</button>}
    </div>}

    <div className={styles.rows}>
      {catalog.map(strategy => <LiveRow key={strategy.id} strategy={strategy} setting={settings[strategy.id]} state={states[strategy.id] || null} sizing={desk?.sizing?.[strategy.id]} limits={limits} unlocked={!!desk?.live_unlocked} busy={busy} act={act} actions={actions} />)}
    </div>

    <section aria-label="Dry-run trades">
      <h2 className={styles.heading}>Trades<small>Fill prices against the paper price</small></h2>
      {trades.length ? <div className={base.tableCard}><div className={base.tableScroll}><table className={base.table}>
        <thead><tr><th>Trade</th><th>Algo</th><th>Mode</th><th className={base.num}>Lots</th><th className={base.num}>Paper credit</th><th className={base.num}>Filled credit</th><th className={base.num}>Slippage</th><th>Exit</th><th className={base.num}>P&L</th></tr></thead>
        <tbody>{trades.slice(0, 40).map(({ trade, name }) => <TradeRow key={`${trade.signal_id}${trade.mode}`} trade={trade} name={name} />)}</tbody>
      </table></div></div> : <div className={base.tableCard}><EmptyRow>No dry-run trades yet. They appear here when an algo set to Dry run takes its next paper trade.</EmptyRow></div>}
    </section>

    {alerts.length > 0 && <section aria-label="Desk alerts">
      <h2 className={styles.heading}>Alerts<small>Also emailed when alert email is set up on the server</small></h2>
      <ul className={styles.alerts}>{alerts.map((alert, index) => <li key={index}><time>{time(alert.at)}</time><b>{alert.name}</b><span>{alert.subject}{alert.detail ? `: ${alert.detail}` : ''}</span></li>)}</ul>
    </section>}

    <p className={base.caption}>Dry run sends no orders: it fills each leg at the live bid or ask, hedge leg first, so it shows what real fills would have cost, and skips an entry that would cost more than the slippage cap. {liveAvailable ? 'Live sends the same orders to Dhan as limit orders. ' : ''}P&L here is from those fills and excludes brokerage and taxes.</p>
  </div>;
}

function Status({ label, ok, good, bad, detail, icon }: { label: string; ok: boolean; good: string; bad: string; detail: string; icon?: 'lock' }) {
  const Icon = ok ? CircleCheck : icon === 'lock' ? Lock : AlertTriangle;
  return <div className={`${styles.statusItem} ${ok ? '' : icon === 'lock' ? styles.warn : styles.bad}`}>
    <span className={styles.statusLabel}>{label}</span>
    <b><Icon size={14} aria-hidden="true" />{ok ? good : bad}</b>
    <small>{detail}</small>
  </div>;
}

function LiveRow({ strategy, setting, state, sizing, limits, unlocked, busy, act, actions }: { strategy: Strategy; setting: LiveSetting | undefined; state: LiveState | null; sizing: { lot_size: number; normal: number; expiry_day: number; monday: number | null } | undefined; limits: LiveResponse['limits']; unlocked: boolean; busy: string; act: (key: string, task: () => Promise<void>) => Promise<void>; actions: LiveActions }) {
  const saved = { mode: setting?.mode ?? 'off' as LiveMode, capital: setting?.capital ?? limits.min_capital, max_lots: setting?.max_lots ?? null, slippage_cap: setting?.slippage_cap ?? null };
  const [mode, setMode] = useState<LiveMode>(saved.mode);
  const [capital, setCapital] = useState(saved.capital);
  const [maxLots, setMaxLots] = useState(saved.max_lots ? String(saved.max_lots) : '');
  const [cap, setCap] = useState(saved.slippage_cap != null ? String(saved.slippage_cap) : '');
  const [confirming, setConfirming] = useState(false);
  const [confirmExit, setConfirmExit] = useState(false);
  // Follow the saved values when another device or a reload changes them.
  useEffect(() => { setMode(saved.mode); setCapital(saved.capital); setMaxLots(saved.max_lots ? String(saved.max_lots) : ''); setCap(saved.slippage_cap != null ? String(saved.slippage_cap) : ''); }, [saved.mode, saved.capital, saved.max_lots, saved.slippage_cap]);

  const lots = maxLots ? Number(maxLots) : null, slippage = cap ? Number(cap) : null;
  const dirty = mode !== saved.mode || capital !== saved.capital || lots !== saved.max_lots || slippage !== saved.slippage_cap;
  const valid = capital >= limits.min_capital && capital <= limits.max_capital && (lots == null || (lots >= 1 && lots <= 20)) && (slippage == null || (slippage >= 0 && slippage <= 20));
  const goingLive = mode === 'live' && saved.mode !== 'live';
  const key = `save-${strategy.id}`;
  const save = () => void act(key, async () => { await actions.saveStrategy(strategy.id, { mode, capital, max_lots: lots, slippage_cap: slippage }); setConfirming(false); });
  const trade = state?.open_trade ?? null;
  const totals = state?.totals?.[saved.mode === 'off' ? 'live' : saved.mode];
  const lastSkip = state?.skipped?.[state.skipped.length - 1];

  return <article className={`${styles.row} ${saved.mode === 'live' ? styles.rowLive : ''}`} aria-labelledby={`live-${strategy.id}`}>
    <header className={styles.rowHead}>
      <AlgoIcon version={strategy.version} />
      <h3 id={`live-${strategy.id}`}>{strategy.name}</h3>
      <span className={`${styles.modeTag} ${styles[`tag_${saved.mode}`]}`}>{modeLabel[saved.mode]}</span>
      {trade && <span className={styles.tradeState}>{stateWord[trade.state]}: {trade.lots} lot{trade.lots === 1 ? '' : 's'} {trade.sell_strike}/{trade.buy_strike} {trade.option_type}{trade.entry_credit != null ? ` at ${trade.entry_credit.toFixed(2)} (paper ${trade.paper.net_credit.toFixed(2)})` : ''}</span>}
      <span className={styles.spacer} />
      {trade && (trade.state === 'open' || trade.state === 'entering') && (confirmExit
        ? <><button className={styles.danger} disabled={busy === `exit-${strategy.id}`} onClick={() => void act(`exit-${strategy.id}`, async () => { await actions.exitStrategy(strategy.id); setConfirmExit(false); })}>Confirm exit</button><button className={base.linkButton} onClick={() => setConfirmExit(false)}>Cancel</button></>
        : <button className={base.outlineButton} onClick={() => setConfirmExit(true)}>Exit now</button>)}
    </header>

    <div className={styles.controls}>
      <div className={styles.field}>Mode
        <div className={base.pills} role="group" aria-label={`${strategy.name} mode`}>{limits.modes.map(item => <button key={item} className={mode === item ? base.pillActive : ''} aria-pressed={mode === item} onClick={() => { setMode(item); setConfirming(false); }}>{modeLabel[item]}</button>)}</div>
      </div>
      <label className={styles.field}>Capital to deploy
        <span className={styles.inputWrap}><i>₹</i><input type="number" min={limits.min_capital} max={limits.max_capital} step={10000} value={capital} onChange={event => setCapital(Number(event.target.value))} aria-invalid={capital < limits.min_capital || capital > limits.max_capital} /></span>
        <input className={styles.slider} type="range" min={limits.min_capital} max={limits.max_capital} step={10000} value={Math.min(Math.max(capital, limits.min_capital), limits.max_capital)} onChange={event => setCapital(Number(event.target.value))} aria-label={`${strategy.name} capital`} />
        <small>{money(limits.min_capital)} to {money(limits.max_capital)}</small>
      </label>
      <label className={styles.field}>Maximum lots
        <span className={styles.inputWrap}><input inputMode="numeric" placeholder="No cap" value={maxLots} onChange={event => setMaxLots(event.target.value.replace(/[^\d]/g, ''))} /></span>
        <small>{sizing && !dirty ? `Trades ${sizing.normal} lot${sizing.normal === 1 ? '' : 's'} (${sizing.normal * sizing.lot_size} units)${sizing.expiry_day !== sizing.normal ? `, ${sizing.expiry_day} on expiry day` : ''}${sizing.monday != null && sizing.monday !== sizing.normal ? `, ${sizing.monday} on Mondays` : ''}` : 'Lots follow the capital; the count shows after saving'}</small>
      </label>
      <label className={styles.field}>Slippage cap
        <span className={styles.inputWrap}><input inputMode="decimal" placeholder="3" value={cap} onChange={event => setCap(event.target.value.replace(/[^\d.]/g, ''))} /><i>pts</i></span>
        <small>An entry worse than this is skipped</small>
      </label>
      <div className={styles.saveCell}>
        {goingLive && confirming
          ? <><button className={styles.danger} disabled={!valid || busy === key} onClick={save}>Confirm: trade real money</button><button className={base.linkButton} onClick={() => setConfirming(false)}>Cancel</button></>
          : <button className={base.outlineButton} disabled={!dirty || !valid || busy === key} onClick={() => goingLive ? setConfirming(true) : save()}>{busy === key ? 'Saving…' : 'Save'}</button>}
        {mode === 'live' && !unlocked && <small className={base.red}>Server lock is on: entries will be skipped</small>}
        {!valid && <small className={base.red}>Check the highlighted values</small>}
      </div>
    </div>

    <dl className={styles.stats}>
      <div><dt>Trades</dt><dd>{totals?.trades ?? 0}{totals?.trades ? <small>{totals.winners} won</small> : null}</dd></div>
      <div><dt>{saved.mode === 'live' ? 'P&L from fills' : 'Dry-run P&L'}</dt><dd className={tone(totals?.realized_pnl)}>{money(totals?.realized_pnl ?? 0)}</dd></div>
      <div><dt>Slippage per trade</dt><dd>{points(averageSlippage(totals))}</dd></div>
      <div><dt>Slippage on stop-outs</dt><dd>{points(stopSlippage(totals))}</dd></div>
      <div><dt>Entries skipped / failed</dt><dd>{totals?.skipped ?? 0} / {totals?.failed ?? 0}</dd></div>
    </dl>
    {lastSkip && <p className={styles.skip}>Last skipped entry, {time(lastSkip.at)}: {lastSkip.reason}</p>}
  </article>;
}

function TradeRow({ trade, name }: { trade: LiveTrade; name: string }) {
  const slip = trade.entry_slippage == null ? null : trade.entry_slippage + (trade.exit_slippage ?? 0);
  return <tr>
    <td><b>NIFTY {trade.expiry} {trade.sell_strike}/{trade.buy_strike} {trade.option_type}</b><small>{time(trade.opened_at)}{trade.closed_at ? ` to ${time(trade.closed_at)}` : ''}</small></td>
    <td>{name}</td>
    <td><span className={`${styles.modeTag} ${styles[`tag_${trade.mode}`]}`}>{modeLabel[trade.mode]}</span></td>
    <td className={base.num}>{trade.lots}<small>paper {trade.paper.lots}</small></td>
    <td className={base.num}>{trade.paper.net_credit.toFixed(2)}</td>
    <td className={base.num}>{trade.entry_credit == null ? '—' : trade.entry_credit.toFixed(2)}</td>
    <td className={`${base.num} ${slip == null ? '' : tone(-slip)}`}>{points(slip)}</td>
    <td>{trade.state === 'failed' ? <span className={base.red}>Not entered</span> : trade.exit_reason || '—'}{trade.state === 'failed' && trade.exit_reason ? <small>{trade.exit_reason}</small> : null}</td>
    <td className={`${base.num} ${tone(trade.pnl)}`}>{money(trade.pnl, 2)}</td>
  </tr>;
}
