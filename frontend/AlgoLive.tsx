'use client';

import { AlertTriangle, ChevronDown, ChevronUp, Lock, OctagonX, Power } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { marketOpen, money, time, type Strategy } from './algoData';
import { deskStale, modeLabel, points, stateWord, type LiveActions, type LiveMode, type LiveResponse, type LiveSetting, type LiveSizing, type LiveState, type LiveTotals, type LiveTrade } from './liveData';
import { AlgoIcon, EmptyRow, tone } from './algoUi';
import base from './algos.module.css';
import styles from './algoLive.module.css';

const DEFAULT_CAP = 3;
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;
type Act = (key: string, task: () => Promise<void>) => Promise<void>;

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
  const [open, setOpen] = useState<string | null | undefined>(undefined);   // the algo whose settings are showing; undefined until first load

  const load = useCallback(async () => {
    try { const body = await actions.load(); setLive(body); setError(''); setLimit(body.account.daily_loss_limit ? String(body.account.daily_loss_limit) : ''); }
    catch { setError('Dry-run status is unavailable right now.'); }
  }, [actions]);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const act = useCallback<Act>(async (key, task) => {
    setBusy(key);
    try { await task(); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not save. Please retry.'); }
    finally { setBusy(''); }
  }, [load]);

  if (!live) return <div className={base.card}>
    <EmptyRow>{error || 'Loading dry-run status…'}</EmptyRow>
    {error && <button className={base.outlineButton} onClick={() => void load()}>Try again</button>}
  </div>;

  const { account, desk, limits, states } = live;
  const liveAvailable = limits.modes.includes('live');
  const settings = account.strategies || {};
  const running = catalog.filter(strategy => (settings[strategy.id]?.mode ?? 'off') !== 'off');
  const anyLive = running.some(strategy => settings[strategy.id].mode === 'live');
  const stale = deskStale(desk, marketOpen()) && running.length > 0;
  const shown = open === undefined ? running[0]?.id ?? null : open;
  // Totals of each running algo in the mode it runs in now.
  const sum = running.reduce((total, strategy) => {
    const part: LiveTotals | undefined = states[strategy.id]?.totals?.[settings[strategy.id].mode];
    if (!part) return total;
    return { trades: total.trades + part.trades, winners: total.winners + part.winners, pnl: total.pnl + part.realized_pnl, slip: total.slip + part.entry_slippage_points + part.exit_slippage_points,
      stops: total.stops + part.stop_trades, stopSlip: total.stopSlip + part.stop_slippage_points, skipped: total.skipped + part.skipped, failed: total.failed + part.failed };
  }, { trades: 0, winners: 0, pnl: 0, slip: 0, stops: 0, stopSlip: 0, skipped: 0, failed: 0 });
  const capital = running.reduce((total, strategy) => total + settings[strategy.id].capital, 0);
  const trades = catalog.flatMap(strategy => (states[strategy.id]?.recent || []).map(trade => ({ trade, name: strategy.name, cap: settings[strategy.id]?.slippage_cap ?? DEFAULT_CAP })))
    .sort((a, b) => Date.parse(b.trade.closed_at || b.trade.opened_at) - Date.parse(a.trade.closed_at || a.trade.opened_at));
  const alerts = catalog.flatMap(strategy => (states[strategy.id]?.alerts || []).map(alert => ({ ...alert, name: strategy.name }))).sort((a, b) => Date.parse(b.at) - Date.parse(a.at)).slice(0, 12);
  const limitValue = Number(limit || 0);
  const what = liveAvailable ? 'live and dry-run' : 'dry-run';

  return <div className={styles.live}>
    {error && <div className={base.notice} role="status"><AlertTriangle size={16} />{error}</div>}

    <section className={styles.status} aria-label="Desk status">
      {liveAvailable
        ? <Status tone={desk?.live_unlocked ? 'ok' : 'warn'} label="Server" value={desk?.live_unlocked ? 'Live orders unlocked' : 'Live orders locked'} detail={desk?.live_unlocked ? 'LIVE_TRADING_ENABLED is on.' : 'Set LIVE_TRADING_ENABLED=true on the server to allow real orders. Dry run works without it.'} />
        : <Status tone="lock" label="Dhan orders" value="Switched off" detail="Nothing on this page can place an order." />}
      <Status tone={stale || desk?.broker_error ? 'bad' : desk ? 'ok' : 'idle'} label="Order desk" value={stale ? (desk ? `No update since ${time(desk.at)}` : 'Not running') : desk ? `Running · updated ${time(desk.at)}` : 'Idle'}
        detail={desk?.broker_error || (stale ? 'The worker has not reported during market hours.' : 'Checks every algo once a minute with the paper worker.')} />
      {liveAvailable && <Status tone={desk?.mismatch ? 'bad' : 'ok'} label="Dhan positions" value={desk?.mismatch ? 'Missing part of a trade' : anyLive ? 'Hold the desk’s trades' : 'Nothing live'} detail={desk?.mismatch || 'Checked every minute while a live trade is open. Other positions in the account are ignored.'} />}
      <div className={`${styles.statusItem} ${styles.kill}`}>
        <div className={styles.statusText}>
          <span>Kill switch</span>
          <b className={account.kill_switch ? base.red : ''}>{account.kill_switch ? 'On · no new entries' : 'Off · entries allowed'}</b>
          <small>Stops new {what} entries here. It never touches your Dhan account.</small>
        </div>
        <button className={account.kill_switch ? styles.ghost : styles.dangerSoft} disabled={busy === 'kill'} onClick={() => void act('kill', () => actions.saveAccount({ kill_switch: !account.kill_switch }))}><Power size={14} aria-hidden="true" />{account.kill_switch ? 'Allow entries' : 'Stop new entries'}</button>
      </div>
    </section>

    <section className={styles.tiles} aria-label="Dry-run summary">
      <Tile label={liveAvailable ? 'Running' : 'On dry run'} value={String(running.length)} unit={`of ${plural(catalog.length, 'algo')}`} note={running.length ? `${money(capital)} capital deployed` : 'Switch an algo to Dry run below'} />
      <Tile label={anyLive ? 'P&L from fills' : 'Dry-run P&L'} value={sum.trades ? money(sum.pnl) : '—'} valueClass={sum.trades ? tone(sum.pnl) : ''} note={sum.trades ? `${plural(sum.trades, 'trade')} · ${sum.winners} won` : 'No trades yet'} />
      <Tile label="Cost of real fills" value={sum.trades ? (sum.slip / sum.trades).toFixed(1) : '—'} unit={sum.trades ? 'pts a trade' : ''} note="Worse than the paper price, entry plus exit" />
      <Tile label="On stop-outs" value={sum.stops ? (sum.stopSlip / sum.stops).toFixed(1) : '—'} unit={sum.stops ? 'pts a trade' : ''} valueClass={sum.stops ? styles.amber : ''} note={sum.stops ? `Across ${plural(sum.stops, 'stop')}` : 'No stop-outs yet'} />
      <Tile label="Entries skipped" value={String(sum.skipped)} note={`Past the slippage cap or blocked · ${sum.failed} failed`} />
    </section>

    {liveAvailable && <div className={styles.accountRow}>
      <label className={styles.field}>Daily loss limit
        <span className={styles.inputWrap}><i>₹</i><input inputMode="numeric" value={limit} placeholder="None" onChange={event => setLimit(event.target.value.replace(/[^\d]/g, ''))} aria-label="Daily loss limit in rupees" /></span>
      </label>
      <button className={styles.ghost} disabled={busy === 'limit' || limitValue === (account.daily_loss_limit || 0)} onClick={() => void act('limit', () => actions.saveAccount({ daily_loss_limit: limitValue }))}>Save limit</button>
      <small>After this much live loss in a day, no new live entries until tomorrow. Open trades still exit normally.</small>
      <span className={styles.spacer} />
      {confirmExitAll
        ? <><button className={styles.danger} disabled={busy === 'exitAll'} onClick={() => void act('exitAll', async () => { await actions.saveAccount({ exit_all: true }); setConfirmExitAll(false); })}><OctagonX size={14} aria-hidden="true" />Confirm: exit every live trade</button><button className={base.linkButton} onClick={() => setConfirmExitAll(false)}>Cancel</button></>
        : <button className={styles.ghost} onClick={() => setConfirmExitAll(true)}>Exit all live trades</button>}
    </div>}

    <section className={base.tableCard} aria-labelledby="live-algos">
      <div className={styles.cardHead}><h2 id="live-algos">Algos</h2><small>A saved change takes effect within a minute</small></div>
      <div className={base.tableScroll}><table className={`${base.table} ${styles.algos}`}>
        <thead><tr><th>Algo</th><th>Mode</th><th className={base.num}>Capital</th><th className={base.num}>Lots</th><th>Position now</th><th className={base.num}>Trades</th><th className={base.num}>P&L</th><th className={base.num}>Slippage</th><th><span className={styles.srOnly}>Settings</span></th></tr></thead>
        <tbody>{[...running, ...catalog.filter(strategy => !running.includes(strategy))].map(strategy => <LiveRow key={strategy.id} strategy={strategy} setting={settings[strategy.id]} state={states[strategy.id] || null} sizing={desk?.sizing?.[strategy.id]} limits={limits}
          unlocked={!!desk?.live_unlocked} busy={busy} act={act} actions={actions} open={shown === strategy.id} onToggle={() => setOpen(shown === strategy.id ? null : strategy.id)} />)}</tbody>
      </table></div>
    </section>

    <div className={styles.split}>
      <section className={`${base.tableCard} ${styles.trades}`} aria-labelledby="live-trades">
        <div className={styles.cardHead}><h2 id="live-trades">{liveAvailable ? 'Trades' : 'Dry-run trades'}</h2><small>What a real fill cost against the paper price</small></div>
        {trades.length ? <div className={base.tableScroll}><table className={base.table}>
          <thead><tr><th>Trade</th>{liveAvailable && <th>Mode</th>}<th className={base.num}>Lots</th><th className={base.num}>Paper credit</th><th className={base.num}>Filled credit</th><th>Slippage</th><th>Exit</th><th className={base.num}>P&L</th></tr></thead>
          <tbody>{trades.slice(0, 40).map(({ trade, name, cap }) => <TradeRow key={`${trade.signal_id}${trade.mode}`} trade={trade} name={name} cap={cap} showMode={liveAvailable} />)}</tbody>
        </table></div> : <EmptyRow>No trades yet. They appear here when an algo set to Dry run takes its next paper trade.</EmptyRow>}
      </section>
      <section className={`${base.card} ${styles.alertCard}`} aria-labelledby="live-alerts">
        <h2 id="live-alerts">Desk alerts</h2>
        {alerts.length ? <ul className={styles.alerts}>{alerts.map((alert, index) => <li key={index}><i aria-hidden="true" /><div><b>{alert.subject}</b><small>{alert.name} · {time(alert.at)}{alert.detail ? ` · ${alert.detail}` : ''}</small></div></li>)}</ul>
          : <p className={styles.quiet}>No alerts. Skipped entries, failed orders and exits that needed a wider price show here.</p>}
        <p className={styles.alertNote}>Alerts are also emailed when alert email is set up on the server.</p>
      </section>
    </div>

    <p className={base.caption}>Dry run sends no orders: it fills each leg at the live bid or ask, hedge leg first, so it shows what real fills would have cost, and skips an entry that would cost more than the slippage cap. {liveAvailable ? 'Live sends the same orders to Dhan as limit orders. ' : ''}P&L here is from those fills and excludes brokerage and taxes. Only you can see this tab.</p>
  </div>;
}

function Status({ tone: kind, label, value, detail }: { tone: 'ok' | 'idle' | 'warn' | 'bad' | 'lock'; label: string; value: string; detail: string }) {
  return <div className={styles.statusItem}>
    {kind === 'lock' ? <Lock size={18} className={styles.lockIcon} aria-hidden="true" /> : <i className={`${styles.dot} ${styles[`dot_${kind}`]}`} aria-hidden="true" />}
    <div className={styles.statusText}><span>{label}</span><b className={kind === 'bad' ? base.red : ''}>{value}</b><small>{detail}</small></div>
  </div>;
}

function Tile({ label, value, unit, note, valueClass = '' }: { label: string; value: string; unit?: string; note: string; valueClass?: string }) {
  return <div className={styles.tile}><span>{label}</span><b className={valueClass}>{value}{unit ? <em>{unit}</em> : null}</b><small>{note}</small></div>;
}

const lotsLine = (sizing: LiveSizing) => [sizing.monday != null && sizing.monday !== sizing.normal ? `${plural(sizing.monday, 'lot')} on Mondays` : '', sizing.expiry_day !== sizing.normal ? `${plural(sizing.expiry_day, 'lot')} on expiry day` : ''].filter(Boolean).join(' · ');

function LiveRow({ strategy, setting, state, sizing, limits, unlocked, busy, act, actions, open, onToggle }: { strategy: Strategy; setting: LiveSetting | undefined; state: LiveState | null; sizing: LiveSizing | undefined; limits: LiveResponse['limits']; unlocked: boolean; busy: string; act: Act; actions: LiveActions; open: boolean; onToggle: () => void }) {
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
  const capitalBad = capital < limits.min_capital || capital > limits.max_capital;
  const valid = !capitalBad && (lots == null || (lots >= 1 && lots <= 20)) && (slippage == null || (slippage >= 0 && slippage <= 20));
  const goingLive = mode === 'live' && saved.mode !== 'live';
  const key = `save-${strategy.id}`, exitKey = `exit-${strategy.id}`, id = `live-${strategy.id}`;
  const save = () => void act(key, async () => { await actions.saveStrategy(strategy.id, { mode, capital, max_lots: lots, slippage_cap: slippage }); setConfirming(false); });
  const reset = () => { setMode(saved.mode); setCapital(saved.capital); setMaxLots(saved.max_lots ? String(saved.max_lots) : ''); setCap(saved.slippage_cap != null ? String(saved.slippage_cap) : ''); setConfirming(false); };
  const on = saved.mode !== 'off';
  const trade = state?.open_trade ?? null;
  const totals = on ? state?.totals?.[saved.mode] : undefined;
  const slip = totals?.trades ? (totals.entry_slippage_points + totals.exit_slippage_points) / totals.trades : null;
  const lastSkip = state?.skipped?.[state.skipped.length - 1];
  const exitable = !!trade && (trade.state === 'open' || trade.state === 'entering');
  const Chevron = open ? ChevronUp : ChevronDown;

  return <>
    <tr className={`${open ? styles.rowOpen : ''} ${on ? '' : styles.rowOff}`}>
      <td><div className={base.algoCell}><AlgoIcon version={strategy.version} /><b id={id}>{strategy.name}</b></div></td>
      <td><span className={`${styles.modeTag} ${styles[`tag_${saved.mode}`]}`}>{modeLabel[saved.mode]}</span></td>
      <td className={base.num}>{money(saved.capital)}</td>
      <td className={base.num}>{on && sizing ? sizing.normal : '—'}</td>
      <td>{trade ? <>{stateWord[trade.state]} · {trade.sell_strike}/{trade.buy_strike} {trade.option_type}<small>{trade.entry_credit != null ? `Filled ${trade.entry_credit.toFixed(2)} · paper ${trade.paper.net_credit.toFixed(2)}` : `${plural(trade.lots, 'lot')} · paper ${trade.paper.net_credit.toFixed(2)}`}</small></> : on ? 'Flat · waiting for a signal' : 'Not running'}</td>
      <td className={base.num}>{totals?.trades ?? 0}{totals?.trades ? <small>{totals.winners} won</small> : null}</td>
      <td className={`${base.num} ${tone(totals?.realized_pnl)}`}>{totals?.trades ? money(totals.realized_pnl) : '—'}</td>
      <td className={base.num}>{slip == null ? '—' : `${slip.toFixed(1)} pts`}</td>
      <td className={base.num}><button className={styles.toggle} aria-expanded={open} aria-controls={`${id}-panel`} aria-label={`${open ? 'Hide' : 'Show'} settings for ${strategy.name}`} onClick={onToggle}><Chevron size={16} aria-hidden="true" /></button></td>
    </tr>
    {open && <tr className={styles.panelRow}><td colSpan={9}>
      <div className={styles.panel} id={`${id}-panel`} role="group" aria-labelledby={id}>
        <div className={styles.field}><span id={`${id}-mode`}>Mode</span>
          <div className={styles.segments} role="group" aria-labelledby={`${id}-mode`}>{limits.modes.map(item => <button key={item} className={mode === item ? styles[`seg_${item}`] : ''} aria-pressed={mode === item} onClick={() => { setMode(item); setConfirming(false); }}>{modeLabel[item]}</button>)}</div>
          {!limits.modes.includes('live') && <small>Live is not available: Dhan orders are switched off.</small>}
          {mode === 'live' && !unlocked && <small className={base.red}>Server lock is on: entries will be skipped.</small>}
        </div>
        <div className={styles.field}><label htmlFor={`${id}-capital`}>Capital to deploy</label>
          <span className={styles.inputWrap}><i>₹</i><input id={`${id}-capital`} type="number" min={limits.min_capital} max={limits.max_capital} step={10000} value={capital} onChange={event => setCapital(Number(event.target.value))} aria-invalid={capitalBad} /></span>
          <input className={styles.slider} type="range" min={limits.min_capital} max={limits.max_capital} step={10000} value={Math.min(Math.max(capital, limits.min_capital), limits.max_capital)} onChange={event => setCapital(Number(event.target.value))} aria-label={`${strategy.name} capital`} />
          <small className={styles.range}><span>{money(limits.min_capital)}</span><span>{money(limits.max_capital)}</span></small>
        </div>
        <div className={styles.field}><span>What this capital trades</span>
          {sizing && !dirty && on
            ? <><b className={styles.lots}>{plural(sizing.normal, 'lot')}<em>· {sizing.normal * sizing.lot_size} units</em></b>{lotsLine(sizing) && <small>{lotsLine(sizing)}</small>}</>
            : <><b className={styles.lots}>—</b><small>Lots follow the capital and the algo’s own rules. The count shows here within a minute of saving{on || mode !== 'off' ? '' : ' in Dry run'}.</small></>}
        </div>
        <div className={styles.pair}>
          <div className={styles.field}><label htmlFor={`${id}-lots`}>Maximum lots</label>
            <span className={styles.inputWrap}><input id={`${id}-lots`} inputMode="numeric" placeholder="No cap" value={maxLots} onChange={event => setMaxLots(event.target.value.replace(/[^\d]/g, ''))} aria-invalid={lots != null && (lots < 1 || lots > 20)} /></span>
          </div>
          <div className={styles.field}><label htmlFor={`${id}-cap`}>Slippage cap</label>
            <span className={styles.inputWrap}><input id={`${id}-cap`} inputMode="decimal" placeholder={String(DEFAULT_CAP)} value={cap} onChange={event => setCap(event.target.value.replace(/[^\d.]/g, ''))} aria-invalid={slippage != null && (slippage < 0 || slippage > 20)} /><i>pts</i></span>
            <small>An entry that would fill worse than this is skipped.</small>
          </div>
        </div>
        <div className={styles.actions}>
          {goingLive && confirming
            ? <><button className={styles.danger} disabled={!valid || busy === key} onClick={save}>Confirm: trade real money</button><button className={styles.ghost} onClick={() => setConfirming(false)}>Cancel</button></>
            : <><button className={styles.primary} disabled={!dirty || !valid || busy === key} onClick={() => goingLive ? setConfirming(true) : save()}>{busy === key ? 'Saving…' : 'Save changes'}</button>
              {dirty && <button className={styles.ghost} onClick={reset}>Discard</button>}</>}
          {exitable && (confirmExit
            ? <><button className={styles.danger} disabled={busy === exitKey} onClick={() => void act(exitKey, async () => { await actions.exitStrategy(strategy.id); setConfirmExit(false); })}>Confirm exit</button><button className={styles.ghost} onClick={() => setConfirmExit(false)}>Cancel</button></>
            : <button className={styles.ghost} onClick={() => setConfirmExit(true)}>Exit open trade now</button>)}
          {!valid && <small className={base.red}>Check the highlighted values.</small>}
        </div>
      </div>
      {lastSkip && <p className={styles.skip}>Last skipped entry, {time(lastSkip.at)}: {lastSkip.reason}</p>}
    </td></tr>}
  </>;
}

function TradeRow({ trade, name, cap, showMode }: { trade: LiveTrade; name: string; cap: number; showMode: boolean }) {
  const slip = trade.entry_slippage == null ? null : trade.entry_slippage + (trade.exit_slippage ?? 0);
  return <tr>
    <td><b>NIFTY {trade.expiry} {trade.sell_strike}/{trade.buy_strike} {trade.option_type}</b><small>{name} · {time(trade.opened_at)}{trade.closed_at ? ` to ${time(trade.closed_at)}` : ', open'}</small></td>
    {showMode && <td><span className={`${styles.modeTag} ${styles[`tag_${trade.mode}`]}`}>{modeLabel[trade.mode]}</span></td>}
    <td className={base.num}>{trade.lots}{trade.lots !== trade.paper.lots ? <small>paper {trade.paper.lots}</small> : null}</td>
    <td className={base.num}>{trade.paper.net_credit.toFixed(2)}</td>
    <td className={base.num}>{trade.entry_credit == null ? '—' : trade.entry_credit.toFixed(2)}</td>
    <td>{slip == null ? '—' : <span className={styles.slip}><i aria-hidden="true"><i className={slip >= cap ? styles.slipOver : ''} style={{ width: `${Math.min(100, Math.max(0, slip) / 5 * 100)}%` }} /></i>{points(slip)}</span>}</td>
    <td>{trade.state === 'failed' ? <span className={base.red}>Not entered</span> : trade.exit_reason || (trade.closed_at ? '—' : 'Open')}{trade.state === 'failed' && trade.exit_reason ? <small>{trade.exit_reason}</small> : null}</td>
    <td className={`${base.num} ${tone(trade.pnl)}`}>{money(trade.pnl, 2)}</td>
  </tr>;
}
