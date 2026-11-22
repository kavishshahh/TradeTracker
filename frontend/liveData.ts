// Algo Lab > Live (owner only): the owner's live-trading settings and what the worker's order desk reported.
// Served by GET /algos/live; saved with PUT /algos/live/strategies/{id} and PUT /algos/live/account.
// The page never talks to the broker: it stores settings, and the worker acts on them within a minute.

export type LiveMode = 'off' | 'dry_run' | 'live';
export type LiveSetting = { mode: LiveMode; capital: number; max_lots?: number | null; slippage_cap?: number | null; exit_now?: string | null; updated_at?: string };
export type LiveTotals = { trades: number; winners: number; realized_pnl: number; entry_slippage_points: number; exit_slippage_points: number; slippage_rupees: number; stop_trades: number; stop_slippage_points: number; failed: number; skipped: number };
export type LiveTrade = {
  signal_id: string; mode: LiveMode; state: 'entering' | 'open' | 'exiting' | 'closed' | 'failed'; opened_at: string; closed_at: string | null;
  expiry: string; option_type: string; sell_strike: number; buy_strike: number; lots: number; units: number; capital: number;
  entry_credit: number | null; exit_value: number | null; pnl: number | null; exit_reason: string | null;
  entry_slippage: number | null; exit_slippage: number | null; paper: { net_credit: number; lots: number }; notes?: string[];
};
export type LiveSkip = { signal_id: string; at: string; mode: LiveMode; reason: string };
export type LiveAlert = { at: string; subject: string; detail: string };
export type LiveState = { open_trade: LiveTrade | null; totals: Partial<Record<LiveMode, LiveTotals>>; recent: LiveTrade[]; skipped: LiveSkip[]; alerts: LiveAlert[]; updated_at: string | null };
export type LiveSizing = { lot_size: number; normal: number; expiry_day: number; monday: number | null };
export type LiveDesk = { at: string; live_unlocked: boolean; mismatch: string | null; broker_error: string | null; kill_switch: boolean; settings_readable: boolean; sizing?: Record<string, LiveSizing> };
export type LiveAccount = { kill_switch?: boolean; daily_loss_limit?: number | null; exit_all?: string | null; strategies?: Record<string, LiveSetting> };
export type LiveResponse = { account: LiveAccount; states: Record<string, LiveState | null>; desk: LiveDesk | null; limits: { min_capital: number; max_capital: number; modes: LiveMode[] } };
export type LiveActions = {
  load: () => Promise<LiveResponse>;
  saveStrategy: (id: string, setting: { mode: LiveMode; capital: number; max_lots: number | null; slippage_cap: number | null }) => Promise<void>;
  saveAccount: (change: { kill_switch?: boolean; daily_loss_limit?: number; exit_all?: boolean }) => Promise<void>;
  exitStrategy: (id: string) => Promise<void>;
};

export const modeLabel: Record<LiveMode, string> = { off: 'Off', dry_run: 'Dry run', live: 'Live' };
export const stateWord: Record<LiveTrade['state'], string> = { entering: 'Entering', open: 'In trade', exiting: 'Exiting', closed: 'Closed', failed: 'Entry failed' };
/** Average points lost to fills per closed trade; positive is worse than the paper price. */
export const averageSlippage = (totals: LiveTotals | undefined) => totals && totals.trades ? (totals.entry_slippage_points + totals.exit_slippage_points) / totals.trades : null;
export const stopSlippage = (totals: LiveTotals | undefined) => totals && totals.stop_trades ? totals.stop_slippage_points / totals.stop_trades : null;
export const points = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)} pts`;
/** The desk writes a heartbeat every minute while anything is configured; older than three minutes in market hours means it is not running. */
export const deskStale = (desk: LiveDesk | null, open: boolean) => open && (!desk || Date.now() - Date.parse(desk.at) > 180_000);
