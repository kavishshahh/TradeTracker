'use client';

import { useAuth } from '@/contexts/AuthContext';
import { trackEvent, trackPageView, trackUserEngagement } from '@/lib/analytics';
import { getTrades } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { DailyStats, Trade } from '@/types/trade';
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
        h-20 w-full p-1 text-left hover:bg-gray-50 border border-gray-200 transition-colors
        ${!isCurrentMonth ? 'text-gray-300 bg-gray-50' : 'text-gray-900'}
        ${isToday ? 'ring-2 ring-blue-500' : ''}
        ${hasData ? 'cursor-pointer' : ''}
      `}
    >
      <div className="flex flex-col h-full">
        <span className={`text-sm font-medium ${isToday ? 'text-blue-600' : ''}`}>
          {date.getDate()}
        </span>
        
        {hasData && (
          <div className="flex-1 flex flex-col justify-end">
            <div className={`text-xs px-1 py-0.5 rounded text-center ${
              isProfit ? 'bg-green-100 text-green-800' : 
              isLoss ? 'bg-red-100 text-red-800' : 
              'bg-gray-100 text-gray-800'
            }`}>
              {formatCurrency(stats.pnl)}
            </div>
            <div className="text-xs text-gray-500 text-center mt-1">
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
  onClose: () => void;
}

function DayDetailModal({ date, stats, onClose }: DayDetailModalProps) {
  if (!date || !stats) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-96 overflow-auto">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">
            {date.toLocaleDateString('en-US', { 
              weekday: 'long', 
              year: 'numeric', 
              month: 'long', 
              day: 'numeric' 
            })}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        <div className="mb-4 p-4 bg-gray-50 rounded-lg">
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-600">Daily P&L:</span>
            <span className={`font-semibold ${
              stats.pnl >= 0 ? 'text-green-600' : 'text-red-600'
            }`}>
              {stats.pnl >= 0 ? '+' : ''}{formatCurrency(stats.pnl)}
            </span>
          </div>
          <div className="flex justify-between items-center mt-1">
            <span className="text-sm text-gray-600">Total Trades:</span>
            <span className="font-semibold">{stats.trade_count}</span>
          </div>
        </div>

        <div className="space-y-3">
          <h4 className="font-medium text-gray-900">Trades</h4>
          {stats.trades.map((trade) => {
            const pnl = trade.sell_price && trade.buy_price
              ? (trade.sell_price - trade.buy_price) * trade.shares 
              : 0;
            const canCalculatePnL = trade.buy_price && trade.sell_price;
            
            return (
              <div key={trade.id} className="border border-gray-200 rounded-lg p-3">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-medium">{trade.ticker}</div>
                    <div className="text-sm text-gray-600">
                      {trade.shares} shares
                      {trade.buy_price && ` @ $${trade.buy_price}`}
                      {trade.sell_price && ` → $${trade.sell_price}`}
                      {!trade.buy_price && trade.sell_price && ` @ $${trade.sell_price} (exit only)`}
                    </div>
                    <div className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full mt-1 ${
                      trade.status === 'closed' 
                        ? 'bg-gray-100 text-gray-800' 
                        : 'bg-blue-100 text-blue-800'
                    }`}>
                      {trade.status}
                    </div>
                  </div>
                  <div className="text-right">
                    {trade.status === 'closed' && canCalculatePnL && (
                      <div className={`font-semibold ${
                        pnl >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {pnl >= 0 ? '+' : ''}{formatCurrency(pnl)}
                      </div>
                    )}
                    {trade.status === 'closed' && !canCalculatePnL && (
                      <div className="text-xs text-gray-500">
                        Exit recorded
                      </div>
                    )}
                  </div>
                </div>
                {trade.notes && (
                  <div className="mt-2 text-sm text-gray-600 italic">
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
  const [loading, setLoading] = useState(true);
  const [selectedDay, setSelectedDay] = useState<{ date: Date; stats: DailyStats } | null>(null);
  const { currentUser } = useAuth();

  useEffect(() => {
    if (!currentUser) return;
    
    const fetchTrades = async () => {
      try {
        const response = await getTrades(currentUser.uid);
        setTrades(response.trades);
        // Track calendar page view
        trackPageView('/calendar');
        trackUserEngagement('calendar_view');
      } catch (error) {
        console.error('Error fetching trades:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchTrades();
  }, [currentUser]);

  // Generate calendar data
  const generateCalendarData = () => {
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
  };

  // Group trades by date
  const groupTradesByDate = (): Record<string, DailyStats> => {
    const grouped: Record<string, DailyStats> = {};
    
    trades.forEach(trade => {
      const dateKey = trade.date;
      
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
        const pnl = (trade.sell_price - trade.buy_price) * trade.shares;
        grouped[dateKey].pnl += pnl;
      }
    });
    
    return grouped;
  };

  const goToPreviousMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
    trackEvent('calendar_navigation', 'calendar', 'previous_month');
    trackUserEngagement('month_navigation', 'previous');
  };

  const goToNextMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
    trackEvent('calendar_navigation', 'calendar', 'next_month');
    trackUserEngagement('month_navigation', 'next');
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

  const calendarDays = generateCalendarData();
  const tradesByDate = groupTradesByDate();
  const today = new Date();

  const monthStats = Object.values(tradesByDate)
    .filter(stats => {
      const statsDate = new Date(stats.date);
      return statsDate.getMonth() === currentDate.getMonth() && 
             statsDate.getFullYear() === currentDate.getFullYear();
    })
    .reduce((acc, stats) => ({
      totalPnl: acc.totalPnl + stats.pnl,
      totalTrades: acc.totalTrades + stats.trade_count,
      tradingDays: acc.tradingDays + (stats.trade_count > 0 ? 1 : 0)
    }), { totalPnl: 0, totalTrades: 0, tradingDays: 0 });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Trading Calendar</h1>
        <p className="mt-1 text-sm text-gray-500">
          View your trading activity by day
        </p>
      </div>

      {/* Month Stats */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <TrendingUp className="h-6 w-6 text-gray-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Month P&L</dt>
                  <dd className={`text-lg font-medium ${
                    monthStats.totalPnl >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {formatCurrency(monthStats.totalPnl)}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <BarChart className="h-6 w-6 text-gray-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Total Trades</dt>
                  <dd className="text-lg font-medium text-gray-900">{monthStats.totalTrades}</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Calendar className="h-6 w-6 text-gray-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Trading Days</dt>
                  <dd className="text-lg font-medium text-gray-900">{monthStats.tradingDays}</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Calendar */}
      <div className="bg-white shadow rounded-lg">
        {/* Calendar Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <button
            onClick={goToPreviousMonth}
            className="p-2 rounded-md hover:bg-gray-100"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          
          <h2 className="text-lg font-semibold text-gray-900">
            {currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
          </h2>
          
          <button
            onClick={goToNextMonth}
            className="p-2 rounded-md hover:bg-gray-100"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>

        {/* Calendar Grid */}
        <div className="p-6">
          {/* Day headers */}
          <div className="grid grid-cols-7 gap-0 mb-1">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
              <div key={day} className="h-8 flex items-center justify-center">
                <span className="text-sm font-medium text-gray-500">{day}</span>
              </div>
            ))}
          </div>

          {/* Calendar days */}
          <div className="grid grid-cols-7 gap-0">
            {calendarDays.map((date, index) => {
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
        </div>
      </div>

      {/* Day Detail Modal */}
      <DayDetailModal
        date={selectedDay?.date || null}
        stats={selectedDay?.stats || null}
        onClose={() => setSelectedDay(null)}
      />
    </div>
  );
}
