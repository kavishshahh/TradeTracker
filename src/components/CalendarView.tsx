'use client';

import { useAuth } from '@/contexts/AuthContext';
import { trackEvent, trackPageView, trackUserEngagement } from '@/lib/analytics';
import { getFeesConfig, getTrades } from '@/lib/api';
import { calculateNetPnL, formatCurrency, formatShares } from '@/lib/utils';
import { DailyStats, FeesConfig, Trade } from '@/types/trade';
import { BarChart, Calendar, ChevronLeft, ChevronRight, TrendingUp } from 'lucide-react';
import { useEffect, useState } from 'react';

interface CalendarDayProps {
  date: Date;
  stats: DailyStats | null;
  isCurrentMonth: boolean;
  isToday: boolean;
  onClick: (date: Date, stats: DailyStats | null) => void;
}

function CalendarDay({ date, stats, isCurrentMonth, isToday, onClick }: CalendarDayProps) {
  const hasData = stats && stats.trade_count > 0;
  const isProfit = stats && stats.pnl > 0;
  const isLoss = stats && stats.pnl < 0;

  return (
    <button
      onClick={() => {
        onClick(date, stats);
        if (hasData) {
          trackEvent('calendar_day_click', 'calendar', date.toISOString().split('T')[0], stats?.trade_count);
          trackUserEngagement('day_interaction', `trades_${stats?.trade_count}`);
        }
      }}
      className={`
        h-20 w-full p-1 text-left hover:bg-gray-50 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700 transition-colors
        ${!isCurrentMonth ? 'text-gray-400 dark:text-gray-600 bg-gray-50 dark:bg-gray-800' : 'text-gray-900 dark:text-white bg-white dark:bg-gray-800'}
        ${isToday ? 'ring-2 ring-blue-500 dark:ring-blue-400' : ''}
        ${hasData ? 'cursor-pointer' : ''}
      `}
    >
      <div className="flex flex-col h-full">
        <span className={`text-sm font-medium ${isToday ? 'text-blue-600 dark:text-blue-400' : ''}`}>
          {date.getDate()}
        </span>
        
        {hasData && (
          <div className="flex-1 flex flex-col justify-end">
            <div className={`text-xs px-1 py-0.5 rounded text-center ${
              isProfit ? 'bg-green-100 dark:bg-green-900/50 text-green-800 dark:text-green-300' : 
              isLoss ? 'bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-300' : 
              'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300'
            }`}>
              {formatCurrency(stats.pnl)}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 text-center mt-1">
              {stats.trade_count} trade{stats.trade_count !== 1 ? 's' : ''}
            </div>
          </div>
        )}
      </div>
    </button>
  );
}

interface DayDetailModalProps {
  date: Date | null;
  stats: DailyStats | null;
  showNetProfits: boolean;
  onClose: () => void;
}

function DayDetailModal({ date, stats, showNetProfits, onClose }: DayDetailModalProps) {
  if (!date || !stats) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-96 overflow-auto">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            {date.toLocaleDateString('en-US', { 
              weekday: 'long', 
              year: 'numeric', 
              month: 'long', 
              day: 'numeric' 
            })}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
          >
            ✕
          </button>
        </div>

        <div className="mb-4 p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-600 dark:text-gray-400">
              P&L ({showNetProfits ? 'Net' : 'Gross'}):
            </span>
            <span className={`font-semibold ${
              stats.pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
            }`}>
              {stats.pnl >= 0 ? '+' : ''}{formatCurrency(stats.pnl)}
            </span>
          </div>
          <div className="flex justify-between items-center mt-1">
            <span className="text-sm text-gray-600 dark:text-gray-400">Total Trades:</span>
            <span className="font-semibold text-gray-900 dark:text-white">{stats.trade_count}</span>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="font-medium text-gray-900 dark:text-white">Trades</h4>
          {stats.trades.map((trade) => {
            const pnl = trade.sell_price && trade.buy_price
              ? (trade.sell_price - trade.buy_price) * trade.shares 
              : 0;
            const canCalculatePnL = trade.buy_price && trade.sell_price;
            
            return (
              <div key={trade.id} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-800">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-medium text-gray-900 dark:text-white">{trade.ticker}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">
                      {formatShares(trade.shares)} shares
                      {trade.buy_price && ` @ $${trade.buy_price}`}
                      {trade.sell_price && ` → $${trade.sell_price}`}
                      {!trade.buy_price && trade.sell_price && ` @ $${trade.sell_price} (exit only)`}
                    </div>
                    <div className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full mt-1 ${
                      trade.status === 'closed' 
                        ? 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200' 
                        : 'bg-blue-100 dark:bg-blue-900/50 text-blue-800 dark:text-blue-300'
                    }`}>
                      {trade.status}
                    </div>
                  </div>
                  <div className="text-right">
                    {trade.status === 'closed' && canCalculatePnL && (
                      <div className={`font-semibold ${
                        pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                      }`}>
                        {pnl >= 0 ? '+' : ''}{formatCurrency(pnl)}
                      </div>
                    )}
                    {trade.status === 'closed' && !canCalculatePnL && (
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        Exit recorded
                      </div>
                    )}
                  </div>
                </div>
                {trade.notes && (
                  <div className="mt-2 text-sm text-gray-600 dark:text-gray-400 italic">
                    "{trade.notes}"
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function CalendarView() {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [trades, setTrades] = useState<Trade[]>([]);
  const [feesConfig, setFeesConfig] = useState<FeesConfig | null>(null);
  const [showNetProfits, setShowNetProfits] = useState(true);
  const [viewMode, setViewMode] = useState<'monthly' | 'yearly'>('monthly');
  const [loading, setLoading] = useState(true);
  const [selectedDay, setSelectedDay] = useState<{ date: Date; stats: DailyStats } | null>(null);
  const { currentUser } = useAuth();

  useEffect(() => {
    if (!currentUser) return;
    
    const fetchData = async () => {
      try {
        const [tradesResponse, feesResponse] = await Promise.all([
          getTrades(currentUser.uid),
          getFeesConfig(currentUser.uid)
        ]);
        setTrades(tradesResponse.trades);
        setFeesConfig(feesResponse.fees_config);
        // Track calendar page view
        trackPageView('/calendar');
        trackUserEngagement('calendar_view');
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [currentUser]);

  // Generate calendar data
  const generateCalendarData = () => {
    if (viewMode === 'yearly') {
      // For yearly view, show all 12 months
      const months = [];
      for (let month = 0; month < 12; month++) {
        months.push(new Date(currentDate.getFullYear(), month, 1));
      }
      return months;
    } else {
      // Monthly view - original logic
      const year = currentDate.getFullYear();
      const month = currentDate.getMonth();
      
      // Get first day of month and calculate starting date
      const firstDay = new Date(year, month, 1);
      const lastDay = new Date(year, month + 1, 0);
      const startDate = new Date(firstDay);
      startDate.setDate(startDate.getDate() - firstDay.getDay());

      // Generate 42 days (6 weeks)
      const days = [];
      const currentDateObj = new Date(startDate);
      
      for (let i = 0; i < 42; i++) {
        days.push(new Date(currentDateObj));
        currentDateObj.setDate(currentDateObj.getDate() + 1);
      }

      return days;
    }
  };

  // Group trades by date or month
  const groupTradesByDate = (): Record<string, DailyStats> => {
    const grouped: Record<string, DailyStats> = {};
    
    trades.forEach(trade => {
      // For closed trades, use exit_date if available, otherwise use entry date
      const tradeDate = trade.status === 'closed' && trade.exit_date ? trade.exit_date : trade.date;
      
      let dateKey: string;
      if (viewMode === 'yearly') {
        // Group by month for yearly view
        const date = new Date(tradeDate);
        dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
      } else {
        // Group by day for monthly view
        dateKey = tradeDate;
      }
      
      if (!grouped[dateKey]) {
        grouped[dateKey] = {
          date: dateKey,
          pnl: 0,
          trade_count: 0,
          trades: []
        };
      }
      
      grouped[dateKey].trades.push(trade);
      grouped[dateKey].trade_count++;
      
      // Calculate P&L for closed trades that have both buy and sell prices
      if (trade.status === 'closed' && trade.sell_price && trade.buy_price) {
        const grossPnl = (trade.sell_price - trade.buy_price) * trade.shares;
        const netPnl = feesConfig ? calculateNetPnL(trade, feesConfig) : grossPnl;
        const pnl = showNetProfits ? netPnl : grossPnl;
        grouped[dateKey].pnl += pnl;
      }
    });
    
    return grouped;
  };

  const goToPreviousPeriod = () => {
    if (viewMode === 'yearly') {
      setCurrentDate(new Date(currentDate.getFullYear() - 1, 0, 1));
      trackEvent('calendar_navigation', 'calendar', 'previous_year');
      trackUserEngagement('year_navigation', 'previous');
    } else {
      setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
      trackEvent('calendar_navigation', 'calendar', 'previous_month');
      trackUserEngagement('month_navigation', 'previous');
    }
  };

  const goToNextPeriod = () => {
    if (viewMode === 'yearly') {
      setCurrentDate(new Date(currentDate.getFullYear() + 1, 0, 1));
      trackEvent('calendar_navigation', 'calendar', 'next_year');
      trackUserEngagement('year_navigation', 'next');
    } else {
      setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
      trackEvent('calendar_navigation', 'calendar', 'next_month');
      trackUserEngagement('month_navigation', 'next');
    }
  };

  const handleDayClick = (date: Date, stats: DailyStats | null) => {
    if (stats && stats.trade_count > 0) {
      setSelectedDay({ date, stats });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const calendarData = generateCalendarData();
  const tradesByDate = groupTradesByDate();
  const today = new Date();

  // Calculate stats based on view mode
  const periodStats = Object.values(tradesByDate)
    .filter(stats => {
      if (viewMode === 'yearly') {
        const statsDate = new Date(stats.date + '-01'); // Add day to make it a valid date
        return statsDate.getFullYear() === currentDate.getFullYear();
      } else {
        const statsDate = new Date(stats.date);
        return statsDate.getMonth() === currentDate.getMonth() && 
               statsDate.getFullYear() === currentDate.getFullYear();
      }
    })
    .reduce((acc, stats) => ({
      totalPnl: acc.totalPnl + stats.pnl,
      totalTrades: acc.totalTrades + stats.trade_count,
      tradingDays: acc.tradingDays + (stats.trade_count > 0 ? 1 : 0)
    }), { totalPnl: 0, totalTrades: 0, tradingDays: 0 });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Trading Calendar</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {viewMode === 'yearly' ? 'View your trading activity by month' : 'View your trading activity by day'}
          </p>
        </div>
        
        {/* Toggles */}
        <div className="flex flex-col sm:flex-row gap-4">
          {/* View Mode Toggle */}
          <div className="flex items-center space-x-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
            <button
              onClick={() => {
                setViewMode('monthly');
                trackEvent('calendar_view_toggle', 'calendar', 'monthly');
              }}
              className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'monthly'
                  ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => {
                setViewMode('yearly');
                trackEvent('calendar_view_toggle', 'calendar', 'yearly');
              }}
              className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'yearly'
                  ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
            >
              Yearly
            </button>
          </div>

          {/* Fees Toggle */}
          <div className="flex items-center space-x-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
            <button
              onClick={() => {
                setShowNetProfits(false);
                trackEvent('calendar_fees_toggle', 'calendar', 'gross');
              }}
              className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                !showNetProfits
                  ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
            >
              Gross
            </button>
            <button
              onClick={() => {
                setShowNetProfits(true);
                trackEvent('calendar_fees_toggle', 'calendar', 'net');
              }}
              className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                showNetProfits
                  ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
            >
              Net
            </button>
          </div>
        </div>
      </div>

      {/* Period Stats */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
        <div className="bg-white dark:bg-gray-800 overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <TrendingUp className="h-6 w-6 text-gray-400 dark:text-gray-500" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400 truncate">
                    {viewMode === 'yearly' ? 'Year' : 'Month'} P&L ({showNetProfits ? 'Net' : 'Gross'})
                  </dt>
                  <dd className={`text-lg font-medium ${
                    periodStats.totalPnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                  }`}>
                    {formatCurrency(periodStats.totalPnl)}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <BarChart className="h-6 w-6 text-gray-400 dark:text-gray-500" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400 truncate">Total Trades</dt>
                  <dd className="text-lg font-medium text-gray-900 dark:text-white">{periodStats.totalTrades}</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Calendar className="h-6 w-6 text-gray-400 dark:text-gray-500" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400 truncate">
                    {viewMode === 'yearly' ? 'Trading Months' : 'Trading Days'}
                  </dt>
                  <dd className="text-lg font-medium text-gray-900 dark:text-white">{periodStats.tradingDays}</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Calendar */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
        {/* Calendar Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={goToPreviousPeriod}
            className="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {viewMode === 'yearly' 
              ? currentDate.getFullYear().toString()
              : currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
            }
          </h2>
          
          <button
            onClick={goToNextPeriod}
            className="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>

        {/* Calendar Grid */}
        <div className="p-6">
          {viewMode === 'yearly' ? (
            /* Yearly View - Month Grid */
            <div className="grid grid-cols-3 gap-4">
              {calendarData.map((monthDate, index) => {
                const monthKey = `${monthDate.getFullYear()}-${String(monthDate.getMonth() + 1).padStart(2, '0')}`;
                const stats = tradesByDate[monthKey] || null;
                const monthName = monthDate.toLocaleDateString('en-US', { month: 'long' });
                const isCurrentMonth = monthDate.getMonth() === new Date().getMonth() && monthDate.getFullYear() === new Date().getFullYear();
                
                return (
                  <div
                    key={index}
                    onClick={() => {
                      if (stats && stats.trade_count > 0) {
                        setSelectedDay({ date: monthDate, stats });
                        trackEvent('calendar_month_click', 'calendar', monthKey, stats?.trade_count);
                      }
                    }}
                    className={`
                      p-4 rounded-lg border-2 transition-all cursor-pointer hover:shadow-md
                      ${isCurrentMonth ? 'border-blue-500 dark:border-blue-400 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-200 dark:border-gray-700'}
                      ${stats && stats.trade_count > 0 ? 'hover:border-gray-300 dark:hover:border-gray-600' : ''}
                    `}
                  >
                    <div className="text-center">
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">{monthName}</h3>
                      {stats && stats.trade_count > 0 ? (
                        <div className="space-y-1">
                          <div className={`text-sm font-medium ${
                            stats.pnl >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                          }`}>
                            {formatCurrency(stats.pnl)}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">
                            {stats.trade_count} trade{stats.trade_count !== 1 ? 's' : ''}
                          </div>
                        </div>
                      ) : (
                        <div className="text-sm text-gray-400 dark:text-gray-500">No trades</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* Monthly View - Day Grid */
            <>
              {/* Day headers */}
              <div className="grid grid-cols-7 gap-0 mb-1">
                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                  <div key={day} className="h-8 flex items-center justify-center">
                    <span className="text-sm font-medium text-gray-500 dark:text-gray-400">{day}</span>
                  </div>
                ))}
              </div>

              {/* Calendar days */}
              <div className="grid grid-cols-7 gap-0">
                {calendarData.map((date, index) => {
                  const dateKey = date.toISOString().split('T')[0];
                  const stats = tradesByDate[dateKey] || null;
                  const isCurrentMonth = date.getMonth() === currentDate.getMonth();
                  const isToday = date.toDateString() === today.toDateString();

                  return (
                    <CalendarDay
                      key={index}
                      date={date}
                      stats={stats}
                      isCurrentMonth={isCurrentMonth}
                      isToday={isToday}
                      onClick={handleDayClick}
                    />
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Day Detail Modal */}
      <DayDetailModal
        date={selectedDay?.date || null}
        stats={selectedDay?.stats || null}
        showNetProfits={showNetProfits}
        onClose={() => setSelectedDay(null)}
      />
    </div>
  );
}
