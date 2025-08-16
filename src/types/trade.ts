export interface Trade {
  id?: string;
  user_id: string;
  date: string;
  ticker: string;
  buy_price: number;
  sell_price?: number;
  shares: number;
  risk: number;
  notes?: string;
  status: 'open' | 'closed';
  created_at?: string;
  updated_at?: string;
}

export interface TradeMetrics {
  net_pnl: number;
  trade_expectancy: number;
  profit_factor: number;
  win_percentage: number;
  avg_win: number;
  avg_loss: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
}

export interface DailyStats {
  date: string;
  pnl: number;
  trade_count: number;
  trades: Trade[];
}
