'use client';

import { Calendar } from '@/components/ui/calendar';
import { useAuth } from '@/contexts/AuthContext';
import { getTrades } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { Trade } from '@/types/trade';
import { BarChart3, Calendar as CalendarIcon, DollarSign, Download, Filter, Search, Target, TrendingDown, TrendingUp, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { DateRange } from 'react-day-picker';

interface MonthShortcut {
  label: string;
  range: DateRange;
}

interface TradeDetailModalProps {
  trade: Trade | null;
  onClose: () => void;
}

function TradeDetailModal({ trade, onClose }: TradeDetailModalProps) {
  if (!trade) return null;

  const pnl = trade.sell_price && trade.buy_price
    ? (trade.sell_price - trade.buy_price) * trade.shares 
    : 0;
  
  const dollarValue = trade.buy_price ? trade.buy_price * trade.shares : 0;
  
  // Use risk_dollars if available, otherwise calculate from risk percentage and account balance
  const riskAmount = trade.risk_dollars || 0;
  
  // R:R ratio is the ratio of profit/loss to the risk amount
  const rrRatio = trade.status === 'closed' && riskAmount > 0 && pnl !== 0
    ? Math.abs(pnl) / riskAmount
    : 0;
  
  const returnPercentage = trade.buy_price && trade.sell_price 
    ? ((trade.sell_price - trade.buy_price) / trade.buy_price) * 100 
    : 0;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex justify-between items-center p-6 border-b border-gray-200">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">{trade.ticker}</h2>
            <p className="text-sm text-gray-500">Trade Details</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Status Badge */}
          <div className="flex justify-between items-center">
            <span className={`inline-flex px-3 py-1 text-sm font-semibold rounded-full ${
              trade.status === 'closed' 
                ? 'bg-gray-100 text-gray-800' 
                : 'bg-blue-100 text-blue-800'
            }`}>
              {trade.status.charAt(0).toUpperCase() + trade.status.slice(1)}
            </span>
            <span className="text-sm text-gray-500">
              {new Date(trade.date).toLocaleDateString('en-GB', { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
              })}
            </span>
          </div>

          {/* Key Metrics */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-blue-50 rounded-lg p-4">
              <div className="flex items-center">
                <DollarSign className="h-5 w-5 text-blue-500 mr-2" />
                <div>
                  <p className="text-xs font-medium text-blue-600">Position Value</p>
                  <p className="text-lg font-semibold text-blue-900">{formatCurrency(dollarValue)}</p>
                </div>
              </div>
            </div>

            <div className={`rounded-lg p-4 ${pnl >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
              <div className="flex items-center">
                {pnl >= 0 ? (
                  <TrendingUp className="h-5 w-5 text-green-500 mr-2" />
                ) : (
                  <TrendingDown className="h-5 w-5 text-red-500 mr-2" />
                )}
                <div>
                  <p className={`text-xs font-medium ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    P&L
                  </p>
                  <p className={`text-lg font-semibold ${pnl >= 0 ? 'text-green-900' : 'text-red-900'}`}>
                    {trade.status === 'closed' ? formatCurrency(pnl) : 'Open'}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-orange-50 rounded-lg p-4">
              <div className="flex items-center">
                <Target className="h-5 w-5 text-orange-500 mr-2" />
                <div>
                  <p className="text-xs font-medium text-orange-600">Risk Amount</p>
                  <p className="text-lg font-semibold text-orange-900">
                    {riskAmount > 0 ? formatCurrency(riskAmount) : 'Not set'}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-purple-50 rounded-lg p-4">
              <div className="flex items-center">
                <BarChart3 className="h-5 w-5 text-purple-500 mr-2" />
                <div>
                  <p className="text-xs font-medium text-purple-600">R:R Ratio</p>
                  <p className="text-lg font-semibold text-purple-900">
                    {trade.status === 'closed' 
                      ? `1:${rrRatio.toFixed(2)} ${pnl >= 0 ? '(Win)' : '(Loss)'}`
                      : 'Open'
                    }
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Trade Information */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Entry Information */}
            <div className="space-y-4">
              <h3 className="text-lg font-medium text-gray-900">Entry Information</h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Entry Date:</span>
                  <span className="text-sm font-medium text-gray-900">
                    {new Date(trade.date).toLocaleDateString('en-GB')}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Entry Price:</span>
                  <span className="text-sm font-medium text-gray-900">
                    {trade.buy_price ? `$${trade.buy_price.toFixed(2)}` : 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Shares:</span>
                  <span className="text-sm font-medium text-gray-900">{trade.shares}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Risk:</span>
                  <span className="text-sm font-medium text-gray-900">
                    {trade.risk ? `${trade.risk}%` : 'N/A'} ({formatCurrency(riskAmount)})
                  </span>
                </div>
              </div>
            </div>

            {/* Exit Information */}
            <div className="space-y-4">
              <h3 className="text-lg font-medium text-gray-900">Exit Information</h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Exit Price:</span>
                  <span className="text-sm font-medium text-gray-900">
                    {trade.sell_price ? `$${trade.sell_price.toFixed(2)}` : 'Not closed'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Return %:</span>
                  <span className={`text-sm font-medium ${
                    trade.status === 'closed' 
                      ? returnPercentage >= 0 ? 'text-green-600' : 'text-red-600'
                      : 'text-gray-900'
                  }`}>
                    {trade.status === 'closed' 
                      ? `${returnPercentage >= 0 ? '+' : ''}${returnPercentage.toFixed(2)}%` 
                      : 'Open'
                    }
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Days Held:</span>
                  <span className="text-sm font-medium text-gray-900">
                    {Math.ceil((new Date().getTime() - new Date(trade.date).getTime()) / (1000 * 60 * 60 * 24))} days
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-500">Status:</span>
                  <span className="text-sm font-medium text-gray-900 capitalize">{trade.status}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Notes Section */}
          {trade.notes && (
            <div className="space-y-2">
              <h3 className="text-lg font-medium text-gray-900">Notes</h3>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{trade.notes}</p>
              </div>
            </div>
          )}

          {/* Performance Summary */}
          {trade.status === 'closed' && (
            <div className="bg-gray-50 rounded-lg p-4 space-y-3">
              <h3 className="text-lg font-medium text-gray-900">Performance Summary</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Investment:</span>
                  <p className="font-medium">{formatCurrency(dollarValue)}</p>
                </div>
                <div>
                  <span className="text-gray-500">Risk Taken:</span>
                  <p className="font-medium">
                    {formatCurrency(riskAmount)} {trade.risk ? `(${trade.risk}%)` : ''}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Actual P&L:</span>
                  <p className={`font-medium ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {formatCurrency(pnl)}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Risk/Reward:</span>
                  <p className={`font-medium ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    1:{rrRatio.toFixed(2)} {pnl >= 0 ? '(Win)' : '(Loss)'}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end p-6 border-t border-gray-200">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default function TradesView() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [filteredTrades, setFilteredTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'closed'>('all');
  const [dateRange, setDateRange] = useState<DateRange | undefined>();
  const [selectedDateRange, setSelectedDateRange] = useState<DateRange | undefined>();
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const [sortField, setSortField] = useState<'date' | 'ticker' | 'pnl'>('date');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const calendarRef = useRef<HTMLDivElement>(null);
  const { currentUser } = useAuth();

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

  // Helper function to get date range for API calls
  const getDateRange = useCallback((range: DateRange | undefined) => {
    if (!range?.from || !range?.to) {
      return undefined;
    }
    
    const formatDate = (date: Date) => {
      return date.toISOString().split('T')[0];
    };
    
    return {
      startDate: formatDate(range.from),
      endDate: formatDate(range.to)
    };
  }, []);

  // Fetch trades data
  const fetchTrades = useCallback(async () => {
    if (!currentUser) return;
    
    try {
      setLoading(true);
      const dateRangeParams = getDateRange(selectedDateRange);
      
      const response = await getTrades(
        currentUser.uid,
        dateRangeParams?.startDate,
        dateRangeParams?.endDate
      );
      
      const sortedTrades = response.trades.sort((a, b) => 
        new Date(b.date).getTime() - new Date(a.date).getTime()
      );
      
      setTrades(sortedTrades);
    } catch (error) {
      console.error('Error fetching trades:', error);
    } finally {
      setLoading(false);
    }
  }, [currentUser, selectedDateRange, getDateRange]);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  // Apply filters and search
  useEffect(() => {
    let filtered = trades;

    // Apply status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter(trade => trade.status === statusFilter);
    }

    // Apply search filter
    if (searchTerm) {
      filtered = filtered.filter(trade =>
        trade.ticker.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (trade.notes && trade.notes.toLowerCase().includes(searchTerm.toLowerCase()))
      );
    }

    // Apply sorting
    filtered.sort((a, b) => {
      let aVal: any, bVal: any;
      
      switch (sortField) {
        case 'date':
          aVal = new Date(a.date).getTime();
          bVal = new Date(b.date).getTime();
          break;
        case 'ticker':
          aVal = a.ticker;
          bVal = b.ticker;
          break;
        case 'pnl':
          const aPnl = a.sell_price && a.buy_price ? (a.sell_price - a.buy_price) * a.shares : 0;
          const bPnl = b.sell_price && b.buy_price ? (b.sell_price - b.buy_price) * b.shares : 0;
          aVal = aPnl;
          bVal = bPnl;
          break;
        default:
          aVal = a.date;
          bVal = b.date;
      }

      if (sortDirection === 'asc') {
        return aVal > bVal ? 1 : -1;
      } else {
        return aVal < bVal ? 1 : -1;
      }
    });

    setFilteredTrades(filtered);
  }, [trades, searchTerm, statusFilter, sortField, sortDirection]);

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

  const handleDateRangeSelect = (range: DateRange | undefined) => {
    setDateRange(range);
  };

  const handleApplyFilter = () => {
    setSelectedDateRange(dateRange);
    setIsCalendarOpen(false);
  };

  const handleMonthShortcut = (shortcut: MonthShortcut) => {
    setSelectedDateRange(shortcut.range);
    setDateRange(shortcut.range);
  };

  const clearDateFilter = () => {
    setSelectedDateRange(undefined);
    setDateRange(undefined);
  };

  const handleSort = (field: 'date' | 'ticker' | 'pnl') => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const formatDateRange = (range: DateRange | undefined) => {
    if (!range?.from || !range?.to) return 'All Time';
    
    if (range.from.getMonth() === range.to.getMonth() && range.from.getFullYear() === range.to.getFullYear()) {
      return range.from.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    }
    
    return `${range.from.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${range.to.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;
  };

  const calculateStats = () => {
    const totalTrades = filteredTrades.length;
    const closedTrades = filteredTrades.filter(t => t.status === 'closed');
    const openTrades = filteredTrades.filter(t => t.status === 'open');
    
    const totalPnL = closedTrades.reduce((sum, trade) => {
      if (trade.sell_price && trade.buy_price) {
        return sum + (trade.sell_price - trade.buy_price) * trade.shares;
      }
      return sum;
    }, 0);

    const winningTrades = closedTrades.filter(trade => {
      if (trade.sell_price && trade.buy_price) {
        return (trade.sell_price - trade.buy_price) * trade.shares > 0;
      }
      return false;
    }).length;

    const winRate = closedTrades.length > 0 ? (winningTrades / closedTrades.length) * 100 : 0;

    return {
      totalTrades,
      closedTrades: closedTrades.length,
      openTrades: openTrades.length,
      totalPnL,
      winRate
    };
  };

  const stats = calculateStats();

  // Export to CSV function
  const exportToCSV = () => {
    if (filteredTrades.length === 0) {
      alert('No trades to export');
      return;
    }

    // Calculate summary statistics
    const closedTrades = filteredTrades.filter(t => t.status === 'closed');
    const totalPnL = closedTrades.reduce((sum, trade) => {
      if (trade.sell_price && trade.buy_price) {
        return sum + (trade.sell_price - trade.buy_price) * trade.shares;
      }
      return sum;
    }, 0);

    const winningTrades = closedTrades.filter(trade => {
      if (trade.sell_price && trade.buy_price) {
        return (trade.sell_price - trade.buy_price) * trade.shares > 0;
      }
      return false;
    });

    const losingTrades = closedTrades.filter(trade => {
      if (trade.sell_price && trade.buy_price) {
        return (trade.sell_price - trade.buy_price) * trade.shares < 0;
      }
      return false;
    });

    const winRate = closedTrades.length > 0 ? winningTrades.length / closedTrades.length : 0;
    const lossRate = closedTrades.length > 0 ? losingTrades.length / closedTrades.length : 0;

    const avgWin = winningTrades.length > 0 
      ? winningTrades.reduce((sum, trade) => {
          const pnl = (trade.sell_price! - trade.buy_price!) * trade.shares;
          return sum + pnl;
        }, 0) / winningTrades.length 
      : 0;

    const avgLoss = losingTrades.length > 0 
      ? Math.abs(losingTrades.reduce((sum, trade) => {
          const pnl = (trade.sell_price! - trade.buy_price!) * trade.shares;
          return sum + pnl;
        }, 0) / losingTrades.length)
      : 0;

    const avgReward = closedTrades.length > 0 
      ? closedTrades.reduce((sum, trade) => {
          const pnl = trade.sell_price && trade.buy_price 
            ? (trade.sell_price - trade.buy_price) * trade.shares 
            : 0;
          return sum + pnl;
        }, 0) / closedTrades.length 
      : 0;

    const avgRisk = filteredTrades.length > 0 
      ? filteredTrades.reduce((sum, trade) => sum + (trade.risk || 0), 0) / filteredTrades.length 
      : 0;

    const avgRR = avgLoss > 0 ? avgWin / avgLoss : 0;
    const expectancy = (winRate * avgWin) - (lossRate * avgLoss);

    // Get date range for filename
    const dateRangeText = formatDateRange(selectedDateRange).replace(/[^a-zA-Z0-9]/g, '_');
    
    // Create CSV content
    const csvContent = [
      // Header row with summary
      `Pnl ${dateRangeText},${totalPnL.toFixed(6)},,,,,,,,,,,,,,,,,,`,
      // Column headers with statistics
      `Month,Ticker,Buy price,Sell price,shares,$ value,Risk,Shares Sold(1/3),$ Sold(1/3),Sell price(1/3),Pending Shares,Sold rest,Sell price,P/L(Reward),R:R Ratio,Status,Average Reward,${avgReward.toFixed(8)},Win %,${winRate.toFixed(10)}`,
      // Empty row with additional stats
      `,,,,,,,,,,,,,,,,Average Risk,${avgRisk.toFixed(8)},Loss %,${lossRate.toFixed(10)}`,
      // Trade data rows
      ...filteredTrades.map(trade => {
        const pnl = trade.sell_price && trade.buy_price 
          ? (trade.sell_price - trade.buy_price) * trade.shares 
          : 0;
        const dollarValue = trade.buy_price ? trade.buy_price * trade.shares : 0;
        const riskAmountForCSV = trade.risk_dollars || 0;
        const rrRatio = trade.status === 'closed' && riskAmountForCSV > 0 && pnl !== 0
          ? Math.abs(pnl) / riskAmountForCSV
          : 0;
        
        // Format month from date
        const tradeDate = new Date(trade.date);
        const monthYear = tradeDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
        
        return [
          monthYear,
          trade.ticker,
          trade.buy_price || '',
          trade.sell_price || '',
          trade.shares,
          dollarValue.toFixed(4),
          trade.risk,
          '', // Shares Sold(1/3) - empty for now
          '', // $ Sold(1/3) - empty for now  
          '', // Sell price(1/3) - empty for now
          '', // Pending Shares - empty for now
          '', // Sold rest - empty for now
          '', // Sell price - empty for now
          trade.status === 'closed' ? pnl.toFixed(6) : '0.00',
          trade.status === 'closed' ? rrRatio.toFixed(2) : '0.00',
          trade.status === 'closed' ? 'Closed' : 'Open',
          // Additional stats columns (mostly empty for individual trades)
          trade === filteredTrades[0] ? `Average RR` : '', 
          trade === filteredTrades[0] ? avgRR.toFixed(2) : '',
          trade === filteredTrades[0] ? `AvgWin` : '',
          trade === filteredTrades[0] ? avgWin.toFixed(8) : ''
        ].join(',');
      }),
      // Add additional stats rows after trades
      `,,,,,,,,,,,,,,,,,,AvgLoss,${avgLoss.toFixed(7)}`,
      `,,,,,,,,,,,,,,,,Green days,${winningTrades.length},,`,
      `,,,,,,,,,,,,,,,,Red days,${losingTrades.length},Expectancy,${expectancy.toFixed(9)}`,
      `,,,,,,,,,,,,,,,,Win percent,${(winRate * 100).toFixed(8)},,`,
      `,,,,,,,,,,,,,,,,Risk to take,${avgRisk.toFixed(8)},,`
    ].join('\n');

    // Create and download file
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `Market_PL_tracker_${dateRangeText}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">All Trades</h1>
        <p className="mt-1 text-sm text-gray-500">
          View and filter all your trades for {formatDateRange(selectedDateRange)}
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-5">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm font-medium text-gray-500">Total Trades</div>
          <div className="text-2xl font-semibold text-gray-900">{stats.totalTrades}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm font-medium text-gray-500">Open Trades</div>
          <div className="text-2xl font-semibold text-blue-600">{stats.openTrades}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm font-medium text-gray-500">Closed Trades</div>
          <div className="text-2xl font-semibold text-gray-600">{stats.closedTrades}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm font-medium text-gray-500">Total P&L</div>
          <div className={`text-2xl font-semibold ${stats.totalPnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {formatCurrency(stats.totalPnL)}
          </div>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm font-medium text-gray-500">Win Rate</div>
          <div className="text-2xl font-semibold text-gray-900">{stats.winRate.toFixed(1)}%</div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="space-y-4">
          {/* Month Shortcuts */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Quick Date Filters</label>
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

          <div className="flex flex-col sm:flex-row gap-4">
            {/* Search */}
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">Search</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Search className="h-5 w-5 text-gray-400" />
                </div>
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Search by ticker or notes..."
                  className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>

            {/* Status Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as 'all' | 'open' | 'closed')}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="all">All Trades</option>
                <option value="open">Open Only</option>
                <option value="closed">Closed Only</option>
              </select>
            </div>

            {/* Custom Date Range */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Custom Range</label>
              <button
                onClick={() => setIsCalendarOpen(!isCalendarOpen)}
                className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                <CalendarIcon className="h-4 w-4 mr-2" />
                Custom
              </button>
            </div>
          </div>

          {/* Calendar Popup */}
          {isCalendarOpen && (
            <div ref={calendarRef} className="relative mt-4">
              <div className="absolute top-0 left-0 z-10 bg-white border border-gray-200 rounded-md shadow-lg p-4">
                <Calendar
                  mode="range"
                  selected={dateRange}
                  onSelect={handleDateRangeSelect}
                  className="rounded-md"
                  captionLayout="dropdown"
                />
                <div className="mt-4 flex justify-end space-x-2">
                  <button
                    onClick={() => setIsCalendarOpen(false)}
                    className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleApplyFilter}
                    className="px-3 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700"
                  >
                    Apply
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Trades Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-lg font-medium text-gray-900">
                Trades ({filteredTrades.length})
              </h3>
              <p className="text-sm text-gray-500 mt-1">
                Click on any trade row to view detailed information
              </p>
            </div>
            <button 
              onClick={exportToCSV}
              className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              <Download className="h-4 w-4 mr-2" />
              Export CSV
            </button>
          </div>
        </div>
        
        {filteredTrades.length === 0 ? (
          <div className="p-8 text-center">
            <div className="text-gray-400 mb-4">
              <Filter className="mx-auto h-12 w-12" />
            </div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">No trades found</h3>
            <p className="text-gray-500">
              {searchTerm || statusFilter !== 'all' || selectedDateRange
                ? 'Try adjusting your filters to see more results.'
                : 'Start by adding your first trade.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th 
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                    onClick={() => handleSort('date')}
                  >
                    Date {sortField === 'date' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  <th 
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                    onClick={() => handleSort('ticker')}
                  >
                    Ticker {sortField === 'ticker' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Shares
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Entry Price
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Exit Price
                  </th>
                  <th 
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                    onClick={() => handleSort('pnl')}
                  >
                    P&L {sortField === 'pnl' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Risk %
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Notes
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredTrades.map((trade) => {
                  const pnl = trade.sell_price && trade.buy_price
                    ? (trade.sell_price - trade.buy_price) * trade.shares 
                    : 0;
                  
                  return (
                    <tr 
                      key={trade.id} 
                      className="hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => setSelectedTrade(trade)}
                    >
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {new Date(trade.date).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {trade.ticker}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          trade.status === 'closed' 
                            ? 'bg-gray-100 text-gray-800' 
                            : 'bg-blue-100 text-blue-800'
                        }`}>
                          {trade.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {trade.shares}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {trade.buy_price ? `$${trade.buy_price.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {trade.sell_price ? `$${trade.sell_price.toFixed(2)}` : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        {trade.status === 'closed' && trade.sell_price && trade.buy_price ? (
                          <span className={pnl >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>
                            {pnl >= 0 ? '+' : ''}{formatCurrency(pnl)}
                          </span>
                        ) : (
                          <span className="text-gray-500">-</span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {trade.risk}%
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900 max-w-xs truncate">
                        {trade.notes || '-'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Trade Detail Modal */}
      <TradeDetailModal 
        trade={selectedTrade} 
        onClose={() => setSelectedTrade(null)} 
      />
    </div>
  );
}
