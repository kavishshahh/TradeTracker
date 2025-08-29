'use client';

import { Calendar } from '@/components/ui/calendar';
import { useAuth } from '@/contexts/AuthContext';
import { trackEvent, trackPageView, trackUserEngagement } from '@/lib/analytics';
import { getFeesConfig, getMetrics, getMonthlyReturns, getTrades } from '@/lib/api';
import { calculateCompleteTradeFees, calculateNetPnL, formatCurrency, formatPercentage } from '@/lib/utils';
import { FeesConfig, Trade, TradeMetrics } from '@/types/trade';
import { Calculator, Calendar as CalendarIcon, DollarSign, Target, TrendingDown, TrendingUp } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { DateRange } from 'react-day-picker';
import {
    Area,
    AreaChart,
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    Line,
    LineChart,
    Pie,
    PieChart,
    PolarAngleAxis,
    PolarGrid,
    PolarRadiusAxis,
    Radar,
    RadarChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis
} from 'recharts';

interface MetricCardProps {
  title: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
}

interface PeriodStats {
  period: string;
  pnl: number;
  winRate: number;
  expectancy: number;
  trades: number;
  runningBalance: number;
}

interface MonthShortcut {
  label: string;
  range: DateRange;
}

function MetricCard({ title, value, icon: Icon, trend, trendValue }: MetricCardProps) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center">
        <div className="flex-shrink-0">
          <Icon className="h-8 w-8 text-blue-500" />
        </div>
        <div className="ml-5 w-0 flex-1">
          <dl>
            <dt className="text-sm font-medium text-gray-500 truncate">{title}</dt>
            <dd className="flex items-baseline">
              <div className="text-2xl font-semibold text-gray-900">{value}</div>
              {trend && trendValue && (
                <div className={`ml-2 flex items-baseline text-sm font-semibold ${
                  trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : 'text-gray-500'
                }`}>
                  {trend === 'up' ? (
                    <TrendingUp className="h-4 w-4 flex-shrink-0" />
                  ) : trend === 'down' ? (
                    <TrendingDown className="h-4 w-4 flex-shrink-0" />
                  ) : null}
                  <span className="ml-1">{trendValue}</span>
                </div>
              )}
            </dd>
          </dl>
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<TradeMetrics | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [monthlyBalances, setMonthlyBalances] = useState<any[]>([]);
  const [feesConfig, setFeesConfig] = useState<FeesConfig | null>(null);
  const [showNetProfits, setShowNetProfits] = useState(true); // Toggle between gross and net
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState<DateRange | undefined>({
    from: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
    to: new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0)
  });
  const [selectedDateRange, setSelectedDateRange] = useState<DateRange | undefined>(() => {
    const now = new Date();
    return {
      from: new Date(now.getFullYear(), now.getMonth(), 1),
      to: new Date(now.getFullYear(), now.getMonth() + 1, 0)
    };
  });
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);

  const calendarRef = useRef<HTMLDivElement>(null);
  const { currentUser } = useAuth();

  // Helper function to get date range start and end dates
  const getDateRange = useCallback((range: DateRange | undefined) => {
    if (!range?.from || !range?.to) {
      // Return undefined for "All Time" - let backend handle no date filtering
      return {
        startDate: undefined,
        endDate: undefined
      };
    }
    
    // Format as YYYY-MM-DD for consistency with backend
    const formatDate = (date: Date) => {
      return date.toISOString().split('T')[0];
    };
    
    return {
      startDate: formatDate(range.from),
      endDate: formatDate(range.to)
    };
  }, []);

  // Default fees configuration
  const getDefaultFeesConfig = (): FeesConfig => ({
    brokerage_percentage: 0.25,
    brokerage_max_usd: 25,
    exchange_transaction_charges_percentage: 0.12,
    ifsca_turnover_fees_percentage: 0.0001,
    platform_fee_usd: 0,
    withdrawal_fee_usd: 0,
    amc_yearly_usd: 0,
    account_opening_fee_usd: 0,
    tracking_charges_usd: 0,
    profile_verification_fee_usd: 0,
  });

  // Fetch data for selected date range
  const fetchData = useCallback(async () => {
    if (!currentUser) return;
    
    try {
      setLoading(true);
      const { startDate, endDate } = getDateRange(selectedDateRange);
      
      const [metricsData, tradesData, monthlyReturnsData, feesConfigData] = await Promise.all([
        getMetrics(currentUser.uid, startDate, endDate),
        getTrades(currentUser.uid, startDate, endDate),
        getMonthlyReturns(currentUser.uid),
        getFeesConfig(currentUser.uid).catch(() => ({ fees_config: getDefaultFeesConfig() }))
      ]);
      
      setMetrics(metricsData);
      setTrades(tradesData.trades);
      setFeesConfig(feesConfigData.fees_config);
      
      // Transform monthly returns data to match expected format
      const transformedReturns = (monthlyReturnsData.monthly_returns || []).map((returnData: any) => {
        // Convert "December 2024" format to "2024-12" format
        const monthYearMatch = returnData.month.match(/(\w+)\s+(\d{4})/);
        let formattedMonth = returnData.month;
        
        if (monthYearMatch) {
          const [, monthName, year] = monthYearMatch;
          const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                             'July', 'August', 'September', 'October', 'November', 'December'];
          const monthIndex = monthNames.indexOf(monthName);
          if (monthIndex !== -1) {
            formattedMonth = `${year}-${(monthIndex + 1).toString().padStart(2, '0')}`;
          }
        }
        
        return {
          ...returnData,
          month: formattedMonth,
          start_balance: returnData.start_cap,
          end_balance: returnData.close_cap
        };
      });
      
      setMonthlyBalances(transformedReturns);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  }, [currentUser, selectedDateRange, getDateRange]);

  // Calculate adjusted metrics with fees
  const calculateAdjustedMetrics = useCallback((originalMetrics: TradeMetrics, trades: Trade[], feesConfig: FeesConfig) => {
    if (!feesConfig) return originalMetrics;

    const closedTrades = trades.filter(trade => trade.status === 'closed' && trade.sell_price && trade.buy_price);
    
    let totalNetPnL = 0;
    let totalFees = 0;
    let winningTradesNet = 0;
    let losingTradesNet = 0;
    let totalWinsNet = 0;
    let totalLossesNet = 0;

    closedTrades.forEach(trade => {
      const netPnL = calculateNetPnL(trade, feesConfig);
      const fees = calculateCompleteTradeFees(trade, feesConfig);
      
      totalNetPnL += netPnL;
      totalFees += fees.totalFees;
      
      if (netPnL > 0) {
        winningTradesNet++;
        totalWinsNet += netPnL;
      } else if (netPnL < 0) {
        losingTradesNet++;
        totalLossesNet += Math.abs(netPnL);
      }
    });

    const winPercentageNet = closedTrades.length > 0 ? (winningTradesNet / closedTrades.length) * 100 : 0;
    const avgWinNet = winningTradesNet > 0 ? totalWinsNet / winningTradesNet : 0;
    const avgLossNet = losingTradesNet > 0 ? totalLossesNet / losingTradesNet : 0;
    const profitFactorNet = totalLossesNet > 0 ? totalWinsNet / totalLossesNet : 0;
    const tradeExpectancyNet = closedTrades.length > 0 ? totalNetPnL / closedTrades.length : 0;

    return {
      ...originalMetrics,
      net_pnl: totalNetPnL,
      total_fees: totalFees,
      win_percentage: winPercentageNet,
      winning_trades: winningTradesNet,
      losing_trades: losingTradesNet,
      avg_win: avgWinNet,
      avg_loss: avgLossNet,
      profit_factor: profitFactorNet,
      trade_expectancy: tradeExpectancyNet,
    };
  }, []);

  useEffect(() => {
    fetchData();
    // Track dashboard page view
    trackPageView('/dashboard');
    trackUserEngagement('dashboard_view');
  }, [fetchData]);

  // Close calendar when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (calendarRef.current && !calendarRef.current.contains(event.target as Node)) {
        setIsCalendarOpen(false);
      }
    }

    if (isCalendarOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isCalendarOpen]);

  // Handle date range selection
  const handleDateRangeSelect = (range: DateRange | undefined) => {
    setDateRange(range);
  };

  // Apply filter button click
  const handleApplyFilter = () => {
    setSelectedDateRange(dateRange);
    setIsCalendarOpen(false);
    // Track date filter usage
    trackEvent('date_filter_applied', 'dashboard', formatDateRange(dateRange));
    trackUserEngagement('filter_usage', formatDateRange(dateRange));
  };

  // Toggle calendar open/close
  const toggleCalendar = () => {
    setIsCalendarOpen(!isCalendarOpen);
  };

  // Close calendar explicitly
  const closeCalendar = () => {
    setIsCalendarOpen(false);
  };

  // Generate month shortcuts
  const getMonthShortcuts = useCallback((): MonthShortcut[] => {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth();

    return [
      {
        label: 'This Month',
        range: {
          from: new Date(currentYear, currentMonth, 1),
          to: new Date(currentYear, currentMonth + 1, 0)
        }
      },
      {
        label: 'Last Month',
        range: {
          from: new Date(currentYear, currentMonth - 1, 1),
          to: new Date(currentYear, currentMonth, 0)
        }
      },
      {
        label: 'Last 3 Months',
        range: {
          from: new Date(currentYear, currentMonth - 2, 1),
          to: new Date(currentYear, currentMonth + 1, 0)
        }
      },
      {
        label: 'This Quarter',
        range: {
          from: new Date(currentYear, Math.floor(currentMonth / 3) * 3, 1),
          to: new Date(currentYear, Math.floor(currentMonth / 3) * 3 + 3, 0)
        }
      },
      {
        label: 'This Year',
        range: {
          from: new Date(currentYear, 0, 1),
          to: new Date(currentYear, 11, 31)
        }
      },
      {
        label: 'Last Year',
        range: {
          from: new Date(currentYear - 1, 0, 1),
          to: new Date(currentYear - 1, 11, 31)
        }
      }
    ];
  }, []);

  // Handle month shortcut selection
  const handleMonthShortcut = (shortcut: MonthShortcut) => {
    setSelectedDateRange(shortcut.range);
    setDateRange(shortcut.range);
    // Track shortcut usage
    trackEvent('date_shortcut_used', 'dashboard', shortcut.label);
    trackUserEngagement('shortcut_usage', shortcut.label);
  };

  // Clear date filter
  const clearDateFilter = () => {
    setSelectedDateRange(undefined);
    setDateRange(undefined);
    // Track filter clearing
    trackEvent('date_filter_cleared', 'dashboard', 'all_time');
    trackUserEngagement('filter_clear');
  };

  // Helper function to format date range for display
  const formatDateRange = (range: DateRange | undefined) => {
    if (!range?.from || !range?.to) {
      return 'All Time';
    }
    
    if (range.from.getMonth() === range.to.getMonth() && range.from.getFullYear() === range.to.getFullYear()) {
      return range.from.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    }
    
    return `${range.from.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${range.to.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!metrics || !trades || trades.length === 0) {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Trading Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Your trading performance for {formatDateRange(selectedDateRange)}
          </p>
        </div>

        {/* Date Range Selector */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900">Select Date Range</h3>
            <button
              onClick={toggleCalendar}
              className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
              type="button"
            >
              <CalendarIcon className="h-4 w-4 mr-2" />
              {isCalendarOpen ? 'Close Calendar' : 'Open Calendar'}
            </button>
          </div>
          
          {isCalendarOpen && (
            <div ref={calendarRef} className="relative">
              {/* Close Button */}
              <button
                onClick={closeCalendar}
                className="absolute top-2 right-2 p-1 hover:bg-gray-100 rounded-md z-10"
                aria-label="Close calendar"
              >
                <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              
              <Calendar
                mode="range"
                selected={dateRange}
                onSelect={handleDateRangeSelect}
                className="rounded-md border shadow-sm"
                captionLayout="dropdown"
              />
              
              {/* Filter Button */}
              <div className="mt-4 flex justify-end">
                <button
                  onClick={handleApplyFilter}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
                  type="button"
                >
                  Apply Filter
                </button>
              </div>
            </div>
          )}
        </div>

        {/* No Data Message */}
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <div className="text-gray-400 mb-4">
            <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Trading Data Found</h3>
          <p className="text-gray-500 mb-4">
            No trades were found for {formatDateRange(selectedDateRange)}.
          </p>
          <p className="text-sm text-gray-400">
            Try selecting a different date range or check if you have any trades recorded.
          </p>
        </div>
      </div>
    );
  }

  // Get adjusted metrics with fees if available
  const adjustedMetrics = feesConfig && metrics ? calculateAdjustedMetrics(metrics, trades, feesConfig) : metrics;
  const displayMetrics = showNetProfits ? adjustedMetrics : metrics;

  // Prepare P&L curve data (with optional fees calculation)
  const pnlCurveData = trades
    .filter(trade => trade.status === 'closed' && trade.sell_price && trade.buy_price)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
    .reduce((acc, trade, index) => {
      let pnl: number;
      
      if (showNetProfits && feesConfig) {
        pnl = calculateNetPnL(trade, feesConfig);
      } else {
        pnl = (trade.sell_price! - trade.buy_price!) * trade.shares;
      }
      
      const prevValue = acc.length > 0 ? acc[acc.length - 1].equity : 0;
      acc.push({
        date: trade.date,
        equity: prevValue + pnl,
        pnl: pnl
      });
      return acc;
    }, [] as { date: string; equity: number; pnl: number }[]);

  // Create account equity curve with monthly balances and current month profit
  const createAccountEquityCurve = () => {
    if (monthlyBalances.length === 0) {
      return [];
    }

    const equityData: { date: string; equity: number; pnl: number; type: string }[] = [];
    
    // Sort monthly balances chronologically
    const sortedBalances = [...monthlyBalances].sort((a, b) => a.month.localeCompare(b.month));
    
    // Add monthly balance points
    sortedBalances.forEach((balance, index) => {
      // Add start of month point
      equityData.push({
        date: `${balance.month}-01`,
        equity: balance.start_balance,
        pnl: index > 0 ? balance.start_balance - sortedBalances[index - 1].start_balance : 0,
        type: 'month_start'
      });
      
      // Add end of month point if available
      if (balance.end_balance) {
        const daysInMonth = new Date(
          parseInt(balance.month.split('-')[0]), 
          parseInt(balance.month.split('-')[1]), 
          0
        ).getDate();
        
        equityData.push({
          date: `${balance.month}-${daysInMonth.toString().padStart(2, '0')}`,
          equity: balance.end_balance,
          pnl: balance.end_balance - balance.start_balance,
          type: 'month_end'
        });
      }
    });

    // Add current month's trading P&L if we're in the current month
    const currentMonth = new Date().toISOString().substring(0, 7);
    const currentMonthBalance = monthlyBalances.find(b => b.month === currentMonth);
    
    if (currentMonthBalance) {
      // Calculate current month's trading P&L
      const currentMonthTrades = trades.filter(trade => {
        return trade.date.startsWith(currentMonth) && 
               trade.status === 'closed' && 
               trade.sell_price && 
               trade.buy_price;
      });
      
      const currentMonthPnL = currentMonthTrades.reduce((sum, trade) => {
        return sum + (trade.sell_price! - trade.buy_price!) * trade.shares;
      }, 0);
      
      // Add current point
      equityData.push({
        date: new Date().toISOString().split('T')[0],
        equity: currentMonthBalance.start_balance + currentMonthPnL,
        pnl: currentMonthPnL,
        type: 'current'
      });
    }
    
    return equityData.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
  };

  const accountEquityCurveData = createAccountEquityCurve();

  // Generate period stats based on selected date range
  const generatePeriodStats = (): PeriodStats[] => {
    if (!trades.length) return [];

    // Filter trades by selected date range
    const { startDate, endDate } = getDateRange(selectedDateRange);
    const filteredTrades = trades.filter(trade => {
      // If no date range is set (All Time), include all trades
      if (!startDate || !endDate) return true;
      
      const tradeDate = trade.date;
      return tradeDate >= startDate && tradeDate <= endDate;
    });

    const closedTrades = filteredTrades
      .filter(trade => trade.status === 'closed' && trade.sell_price)
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

    if (closedTrades.length === 0) return [];

    // Determine period type based on date range span
    let useWeekly = true; // Default to weekly for "All Time"
    
    if (startDate && endDate) {
      const rangeStart = new Date(startDate);
      const rangeEnd = new Date(endDate);
      const daysDiff = Math.ceil((rangeEnd.getTime() - rangeStart.getTime()) / (1000 * 60 * 60 * 24));
      useWeekly = daysDiff <= 90; // Use weekly for ranges <= 3 months, monthly for longer
    } else {
      // For "All Time", use monthly if we have many trades spread over a long period
      const dateRange = closedTrades.length > 0 
        ? new Date(closedTrades[closedTrades.length - 1].date).getTime() - new Date(closedTrades[0].date).getTime()
        : 0;
      const daysDiff = Math.ceil(dateRange / (1000 * 60 * 60 * 24));
      useWeekly = daysDiff <= 90;
    }

    const periods = new Map<string, Trade[]>();
    
    closedTrades.forEach(trade => {
      const date = new Date(trade.date);
      let periodKey: string;
      
      if (useWeekly) {
        // Get week start (Sunday)
        const weekStart = new Date(date);
        weekStart.setDate(date.getDate() - date.getDay());
        periodKey = weekStart.toISOString().split('T')[0];
      } else {
        // Monthly
        periodKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
      }
      
      if (!periods.has(periodKey)) {
        periods.set(periodKey, []);
      }
      periods.get(periodKey)!.push(trade);
    });

    const stats: PeriodStats[] = [];
    let runningBalance = 0;

          Array.from(periods.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .forEach(([periodKey, periodTrades]) => {
        const pnlValues = periodTrades.map(trade => {
          if (showNetProfits && feesConfig) {
            return calculateNetPnL(trade, feesConfig);
          } else {
            return ((trade.sell_price ?? 0) - (trade.buy_price ?? 0)) * trade.shares;
          }
        });
        
        const totalPnl = pnlValues.reduce((sum, pnl) => sum + pnl, 0);
        const winningTrades = pnlValues.filter(pnl => pnl > 0);
        const losingTrades = pnlValues.filter(pnl => pnl < 0);
        
        const winRate = periodTrades.length > 0 
          ? (winningTrades.length / periodTrades.length) * 100 
          : 0;
          
        const avgWin = winningTrades.length > 0 
          ? winningTrades.reduce((sum, win) => sum + win, 0) / winningTrades.length 
          : 0;
          
        const avgLoss = losingTrades.length > 0 
          ? Math.abs(losingTrades.reduce((sum, loss) => sum + loss, 0) / losingTrades.length) 
          : 0;
          
        const expectancy = (winRate / 100 * avgWin) - ((100 - winRate) / 100 * avgLoss);
        
        runningBalance += totalPnl;

        let displayPeriod: string;
        if (useWeekly) {
          const date = new Date(periodKey);
          displayPeriod = `Week of ${date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
        } else {
          const [year, month] = periodKey.split('-');
          const date = new Date(parseInt(year), parseInt(month) - 1);
          displayPeriod = date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
        }

        stats.push({
          period: displayPeriod,
          pnl: totalPnl,
          winRate,
          expectancy,
          trades: periodTrades.length,
          runningBalance
        });
      });

    return stats;
  };

  const periodStats = generatePeriodStats();
  const latestPeriod = periodStats[periodStats.length - 1];
  const previousPeriod = periodStats[periodStats.length - 2];

  // Check if we have enough data for charts
  const hasPnLChartData = pnlCurveData.length > 0;
  const hasEquityChartData = accountEquityCurveData.length > 0;

  // Prepare win/loss pie chart data
  const pieData = [
    { name: 'Winning Trades', value: displayMetrics?.winning_trades || 0, color: '#10B981' },
    { name: 'Losing Trades', value: displayMetrics?.losing_trades || 0, color: '#EF4444' }
  ];

  // Prepare radar chart data for trading score
  const radarData = [
    { subject: 'Win Rate', A: displayMetrics?.win_percentage || 0, fullMark: 100 },
    { subject: 'Risk Management', A: 75, fullMark: 100 },
    { subject: 'Discipline', A: 80, fullMark: 100 },
    { subject: 'Consistency', A: 70, fullMark: 100 },
    { subject: 'Resilience', A: 85, fullMark: 100 },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Trading Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Your trading performance for {formatDateRange(selectedDateRange)}
          </p>
        </div>
        
        {/* Profit Type Toggle */}
        {feesConfig && (
          <div className="flex items-center space-x-2 bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => {
                setShowNetProfits(false);
                trackEvent('profit_toggle', 'dashboard', 'gross_pnl');
                trackUserEngagement('toggle_profit_view', 'gross');
              }}
              className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                !showNetProfits 
                  ? 'bg-white text-gray-900 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Gross P&L
            </button>
            <button
              onClick={() => {
                setShowNetProfits(true);
                trackEvent('profit_toggle', 'dashboard', 'net_pnl');
                trackUserEngagement('toggle_profit_view', 'net');
              }}
              className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                showNetProfits 
                  ? 'bg-white text-gray-900 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Net P&L (After Fees)
            </button>
          </div>
        )}
      </div>

      {/* Date Range Selector */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-gray-900">Select Date Range</h3>
          <button
            onClick={toggleCalendar}
            className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
            type="button"
          >
            <CalendarIcon className="h-4 w-4 mr-2" />
            {isCalendarOpen ? 'Close Calendar' : 'Open Calendar'}
          </button>
        </div>
        
        {isCalendarOpen && (
          <div ref={calendarRef} className="relative">
            {/* Close Button */}
            <button
              onClick={closeCalendar}
              className="absolute top-2 right-2 p-1 hover:bg-gray-100 rounded-md z-10"
              aria-label="Close calendar"
            >
              <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            
            <Calendar
              mode="range"
              selected={dateRange}
              onSelect={handleDateRangeSelect}
              className="rounded-md border shadow-sm"
              captionLayout="dropdown"
            />
            
            {/* Filter Button */}
            <div className="mt-4 flex justify-end">
              <button
                onClick={handleApplyFilter}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
                type="button"
              >
                Apply Filter
              </button>
            </div>
          </div>
                  )}
        </div>

        {/* Quick Date Filters */}
        <div className="bg-white rounded-lg shadow p-4">
          <label className="block text-sm font-medium text-gray-700 mb-3">Quick Date Filters</label>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={clearDateFilter}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                !selectedDateRange
                  ? 'bg-blue-100 text-blue-800 border-blue-200'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              } border`}
            >
              All Time
            </button>
            {getMonthShortcuts().map((shortcut) => {
              const isSelected = selectedDateRange?.from?.getTime() === shortcut.range.from?.getTime() &&
                                selectedDateRange?.to?.getTime() === shortcut.range.to?.getTime();
              
              return (
                <button
                  key={shortcut.label}
                  onClick={() => handleMonthShortcut(shortcut)}
                  className={`px-3 py-1 text-sm rounded-md transition-colors ${
                    isSelected
                      ? 'bg-blue-100 text-blue-800 border-blue-200'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  } border`}
                >
                  {shortcut.label}
                </button>
              );
            })}
          </div>
        </div>

      {/* Metrics Cards */}
      <div className="space-y-4">
        {/* Total Fees Card (only show when displaying net profits) */}
        {showNetProfits && feesConfig && adjustedMetrics && 'total_fees' in adjustedMetrics && (
          <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-orange-800">Total Trading Fees Paid</p>
                <p className="text-2xl font-bold text-orange-900">
                  {formatCurrency(adjustedMetrics.total_fees as number)}
                </p>
              </div>
              <div className="text-orange-600">
                <Calculator className="h-8 w-8" />
              </div>
            </div>
            <p className="text-xs text-orange-700 mt-1">
              Includes brokerage, exchange charges, and platform fees
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            title={showNetProfits ? "Net P&L (After Fees)" : "Gross P&L"}
            value={formatCurrency(displayMetrics?.net_pnl || 0)}
            icon={DollarSign}
            trend={(displayMetrics?.net_pnl || 0) >= 0 ? 'up' : 'down'}
            trendValue={formatCurrency(Math.abs(displayMetrics?.net_pnl || 0))}
          />
          <MetricCard
            title="Win Rate"
            value={formatPercentage(displayMetrics?.win_percentage || 0)}
            icon={Target}
            trend={(displayMetrics?.win_percentage || 0) >= 50 ? 'up' : 'down'}
            trendValue={`${displayMetrics?.winning_trades || 0}/${displayMetrics?.total_trades || 0}`}
          />
          <MetricCard
            title="Profit Factor"
            value={(displayMetrics?.profit_factor || 0).toFixed(2)}
            icon={TrendingUp}
            trend={(displayMetrics?.profit_factor || 0) >= 1 ? 'up' : 'down'}
            trendValue={`${(displayMetrics?.profit_factor || 0) >= 1 ? 'Profitable' : 'Unprofitable'}`}
          />
          <MetricCard
            title="Expectancy"
            value={formatCurrency(displayMetrics?.trade_expectancy || 0)}
            icon={TrendingUp}
            trend={(displayMetrics?.trade_expectancy || 0) >= 0 ? 'up' : 'down'}
            trendValue={`Per Trade`}
          />
        </div>
      </div>

      {/* Charts Grid */}
      {(hasPnLChartData || hasEquityChartData) ? (
        <div className="space-y-6">
          {/* Trading P&L and Account Equity Curves */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            {/* Trading P&L Curve */}
            {hasPnLChartData && (
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">
                  Trading P&L Curve ({showNetProfits ? 'Net After Fees' : 'Gross'}) - {formatDateRange(selectedDateRange)}
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={pnlCurveData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    />
                    <YAxis tickFormatter={(value: number) => formatCurrency(value)} />
                    <Tooltip 
                      formatter={(value, name) => [formatCurrency(value as number), 'Cumulative P&L']}
                      labelFormatter={(value) => new Date(value).toLocaleDateString('en-US', { 
                        weekday: 'long', 
                        year: 'numeric', 
                        month: 'long', 
                        day: 'numeric' 
                      })}
                      contentStyle={{
                        backgroundColor: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '6px'
                      }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="equity" 
                      stroke="#3B82F6" 
                      strokeWidth={2}
                      dot={{ fill: '#3B82F6', strokeWidth: 2, r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Account Equity Curve */}
            {hasEquityChartData && (
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">
                  Account Equity Value Curve - {formatDateRange(selectedDateRange)}
                </h3>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={accountEquityCurveData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    />
                    <YAxis tickFormatter={(value: number) => formatCurrency(value)} />
                    <Tooltip 
                      formatter={(value, name) => [formatCurrency(value as number), 'Account Value']}
                      labelFormatter={(value) => new Date(value).toLocaleDateString('en-US', { 
                        weekday: 'long', 
                        year: 'numeric', 
                        month: 'long', 
                        day: 'numeric' 
                      })}
                      contentStyle={{
                        backgroundColor: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '6px'
                      }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="equity" 
                      stroke="#10B981" 
                      strokeWidth={2}
                      dot={(props) => {
                        const { payload } = props;
                        let color = '#10B981'; // Default green
                        if (payload?.type === 'current') color = '#F59E0B'; // Orange for current
                        if (payload?.type === 'month_start') color = '#8B5CF6'; // Purple for month starts
                        return <circle {...props} fill={color} r={4} stroke={color} strokeWidth={2} />;
                      }}
                    />
                  </LineChart>
                </ResponsiveContainer>
                
                {/* Legend for Account Equity */}
                <div className="mt-4 flex flex-wrap gap-4 text-xs">
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 rounded-full bg-green-500"></div>
                    <span className="text-gray-600">Month End</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 rounded-full bg-purple-500"></div>
                    <span className="text-gray-600">Month Start</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <div className="w-3 h-3 rounded-full bg-orange-500"></div>
                    <span className="text-gray-600">Current (Live)</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Additional Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Win/Loss Distribution */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Win/Loss Distribution - {formatDateRange(selectedDateRange)}</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {pieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Trading Score Radar */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Trading Score - {formatDateRange(selectedDateRange)}</h3>
          <ResponsiveContainer width="100%" height={300}>
            <RadarChart data={radarData}>
              <PolarGrid />
              <PolarAngleAxis dataKey="subject" />
              <PolarRadiusAxis />
              <Radar
                name="Score"
                dataKey="A"
                stroke="#3B82F6"
                fill="#3B82F6"
                fillOpacity={0.2}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        {/* Recent Performance */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Performance Breakdown ({showNetProfits ? 'Net' : 'Gross'}) - {formatDateRange(selectedDateRange)}
          </h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">Average Win</span>
              <span className="text-sm font-medium text-green-600">
                {formatCurrency(displayMetrics?.avg_win || 0)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">Average Loss</span>
              <span className="text-sm font-medium text-red-600">
                -{formatCurrency(displayMetrics?.avg_loss || 0)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">Total Trades</span>
              <span className="text-sm font-medium text-gray-900">
                {displayMetrics?.total_trades || 0}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">Win/Loss Ratio</span>
              <span className="text-sm font-medium text-gray-900">
                {(displayMetrics?.losing_trades || 0) > 0 
                  ? ((displayMetrics?.winning_trades || 0) / (displayMetrics?.losing_trades || 1)).toFixed(2)
                  : 'N/A'
                }
              </span>
            </div>
            {showNetProfits && feesConfig && adjustedMetrics && 'total_fees' in adjustedMetrics && (
              <div className="flex justify-between items-center border-t pt-4">
                <span className="text-sm text-gray-500">Total Fees Paid</span>
                <span className="text-sm font-medium text-orange-600">
                  -{formatCurrency(adjustedMetrics.total_fees as number)}
                </span>
              </div>
            )}
          </div>
          </div>
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <div className="text-gray-400 mb-4">
            <svg className="mx-auto h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Chart Data Available</h3>
          <p className="text-gray-500">
            No closed trades with complete data found for {formatDateRange(selectedDateRange)}.
          </p>
        </div>
      )}

      {/* Progress Tracking Section */}
      <div className="space-y-6">
        {/* Period Progress Header */}
        <div>
          <h2 className="text-xl font-bold text-gray-900">Period Performance</h2>
          <p className="mt-1 text-sm text-gray-500">
            Track your trading performance over time for {formatDateRange(selectedDateRange)}
          </p>
        </div>

        {/* Current Period Stats */}
        {latestPeriod && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-4">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <DollarSign className="h-8 w-8 text-blue-500" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">
                      Latest Period P&L
                    </dt>
                    <dd className={`text-2xl font-semibold ${
                      latestPeriod.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {formatCurrency(latestPeriod.pnl)}
                    </dd>
                    {previousPeriod && (
                      <dd className="text-sm text-gray-500">
                        vs {formatCurrency(previousPeriod.pnl)} last period
                      </dd>
                    )}
                  </dl>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <Target className="h-8 w-8 text-green-500" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">Win Rate</dt>
                    <dd className="text-2xl font-semibold text-gray-900">
                      {formatPercentage(latestPeriod.winRate)}
                    </dd>
                    {previousPeriod && (
                      <dd className="text-sm text-gray-500">
                        vs {formatPercentage(previousPeriod.winRate)} last period
                      </dd>
                    )}
                  </dl>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <TrendingUp className="h-8 w-8 text-purple-500" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">Expectancy</dt>
                    <dd className={`text-2xl font-semibold ${
                      latestPeriod.expectancy >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {formatCurrency(latestPeriod.expectancy)}
                    </dd>
                    {previousPeriod && (
                      <dd className="text-sm text-gray-500">
                        vs {formatCurrency(previousPeriod.expectancy)} last period
                      </dd>
                    )}
                  </dl>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <CalendarIcon className="h-8 w-8 text-orange-500" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">Trades</dt>
                    <dd className="text-2xl font-semibold text-gray-900">
                      {latestPeriod.trades}
                    </dd>
                    {previousPeriod && (
                      <dd className="text-sm text-gray-500">
                        vs {previousPeriod.trades} last period
                      </dd>
                    )}
                  </dl>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Progress Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Account Balance Over Time */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Account Balance Over Time
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={periodStats}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="period" 
                  tick={{ fontSize: 12 }}
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis tickFormatter={(value) => `$${value.toLocaleString()}`} />
                <Tooltip 
                  formatter={(value) => [formatCurrency(value as number), 'Balance']}
                  labelStyle={{ color: '#374151' }}
                />
                <Area
                  type="monotone"
                  dataKey="runningBalance"
                  stroke="#3B82F6"
                  fill="#3B82F6"
                  fillOpacity={0.1}
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Period P&L */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Period P&L
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={periodStats}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="period" 
                  tick={{ fontSize: 12 }}
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis tickFormatter={(value) => `$${value.toLocaleString()}`} />
                <Tooltip 
                  formatter={(value) => [formatCurrency(value as number), 'P&L']}
                  labelStyle={{ color: '#374151' }}
                />
                <Bar 
                  dataKey="pnl" 
                  fill="#10B981"
                  radius={[2, 2, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Win Rate Trend */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Win Rate Trend
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={periodStats}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="period" 
                  tick={{ fontSize: 12 }}
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis 
                  domain={[0, 100]}
                  tickFormatter={(value) => `${value}%`}
                />
                <Tooltip 
                  formatter={(value) => [`${(value as number).toFixed(1)}%`, 'Win Rate']}
                  labelStyle={{ color: '#374151' }}
                />
                <Line
                  type="monotone"
                  dataKey="winRate"
                  stroke="#10B981"
                  strokeWidth={2}
                  dot={{ fill: '#10B981', strokeWidth: 2, r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Trading Activity */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Trading Activity
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={periodStats}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="period" 
                  tick={{ fontSize: 12 }}
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis />
                <Tooltip 
                  formatter={(value) => [value, 'Trades']}
                  labelStyle={{ color: '#374151' }}
                />
                <Bar 
                  dataKey="trades" 
                  fill="#6366F1"
                  radius={[2, 2, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

    </div>
  );
}
