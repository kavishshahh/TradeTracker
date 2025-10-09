export interface Trade {
  id?: string;
  user_id: string;
  date: string;
  exit_date?: string; // Date when trade was closed/exited
  ticker: string;
  buy_price?: number;
  sell_price?: number;
  shares: number;
  risk?: number; // Risk percentage (0-100)
  risk_dollars?: number; // Risk in dollars
  account_balance?: number; // Account balance at time of trade
  notes?: string;
  status: 'open' | 'closed';
  created_at?: string;
  updated_at?: string;
}

export interface FeesConfig {
  brokerage_percentage: number; // Per transaction percentage
  brokerage_max_usd: number; // Maximum brokerage fee in USD
  exchange_transaction_charges_percentage: number; // Exchange transaction charges %
  ifsca_turnover_fees_percentage: number; // IFSCA turnover fees %
  platform_fee_usd: number; // Platform fees per transaction
  withdrawal_fee_usd: number; // Withdrawal fees
  amc_yearly_usd: number; // Annual maintenance charges
  account_opening_fee_usd: number; // One-time account opening fee
  tracking_charges_usd: number; // Monthly tracking charges
  profile_verification_fee_usd: number; // One-time KYC fee
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

export interface StockCategory {
  id?: string;
  user_id: string;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface StockChart {
  id?: string;
  user_id: string;
  category_id: string;
  stock_symbol: string;
  stock_name?: string;
  before_tradingview_url?: string;
  after_tradingview_url?: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
}