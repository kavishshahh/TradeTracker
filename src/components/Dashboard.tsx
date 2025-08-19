'use client';

import { Calendar } from '@/components/ui/calendar';
import { useAuth } from '@/contexts/AuthContext';
import { getMetrics, getTrades } from '@/lib/api';
import { formatCurrency, formatPercentage } from '@/lib/utils';
import { Trade, TradeMetrics } from '@/types/trade';
import { BarChart, Calendar as CalendarIcon, DollarSign, Target, TrendingDown, TrendingUp } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { DateRange } from 'react-day-picker';
import {
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
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState<DateRange | undefined>({
    from: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
    to: new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0)
  });
  const [selectedDateRange, setSelectedDateRange] = useState<DateRange | undefined>({
    from: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
    to: new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0)
  });
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const calendarRef = useRef<HTMLDivElement>(null);
  const { currentUser } = useAuth();

  // Helper function to get date range start and end dates
  const getDateRange = useCallback((range: DateRange | undefined) => {
    if (!range?.from || !range?.to) {
      // Default to current month if no range is selected
      const now = new Date();
      const startDate = new Date(now.getFullYear(), now.getMonth(), 1);
      const endDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);
      
      const formatDate = (date: Date) => {
        return date.toISOString().split('T')[0];
      };
      
      return {
        startDate: formatDate(startDate),
        endDate: formatDate(endDate)
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

  // Fetch data for selected date range
  const fetchData = useCallback(async () => {
    if (!currentUser) return;
    
    try {
      setLoading(true);
      const { startDate, endDate } = getDateRange(selectedDateRange);
      
      const [metricsData, tradesData] = await Promise.all([
        getMetrics(currentUser.uid, startDate, endDate),
        getTrades(currentUser.uid, startDate, endDate)
      ]);
      
      setMetrics(metricsData);
      setTrades(tradesData.trades);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  }, [currentUser, selectedDateRange, getDateRange]);

  useEffect(() => {
    fetchData();
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
  };

  // Toggle calendar open/close
  const toggleCalendar = () => {
    setIsCalendarOpen(!isCalendarOpen);
  };

  // Close calendar explicitly
  const closeCalendar = () => {
    setIsCalendarOpen(false);
  };

  // Helper function to format date range for display
  const formatDateRange = (range: DateRange | undefined) => {
    if (!range?.from || !range?.to) {
      const now = new Date();
      return now.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
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

  // Prepare equity curve data (simplified without fund flows)
  const equityCurveData = trades
    .filter(trade => trade.status === 'closed' && trade.sell_price && trade.buy_price)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
    .reduce((acc, trade, index) => {
      const pnl = (trade.sell_price! - trade.buy_price!) * trade.shares;
      const prevValue = acc.length > 0 ? acc[acc.length - 1].equity : 0;
      acc.push({
        date: trade.date,
        equity: prevValue + pnl,
        pnl: pnl
      });
      return acc;
    }, [] as { date: string; equity: number; pnl: number }[]);

  // Check if we have enough data for charts
  const hasChartData = equityCurveData.length > 0;

  // Prepare win/loss pie chart data
  const pieData = [
    { name: 'Winning Trades', value: metrics.winning_trades, color: '#10B981' },
    { name: 'Losing Trades', value: metrics.losing_trades, color: '#EF4444' }
  ];

  // Prepare radar chart data for trading score
  const radarData = [
    { subject: 'Win Rate', A: metrics.win_percentage, fullMark: 100 },
    { subject: 'Risk Management', A: 75, fullMark: 100 },
    { subject: 'Discipline', A: 80, fullMark: 100 },
    { subject: 'Consistency', A: 70, fullMark: 100 },
    { subject: 'Resilience', A: 85, fullMark: 100 },
  ];

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

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Net P&L"
          value={formatCurrency(metrics.net_pnl)}
          icon={DollarSign}
          trend={metrics.net_pnl >= 0 ? 'up' : 'down'}
          trendValue={formatCurrency(Math.abs(metrics.net_pnl))}
        />
        <MetricCard
          title="Win Rate"
          value={formatPercentage(metrics.win_percentage)}
          icon={Target}
          trend={metrics.win_percentage >= 50 ? 'up' : 'down'}
          trendValue={`${metrics.winning_trades}/${metrics.total_trades}`}
        />
        <MetricCard
          title="Profit Factor"
          value={metrics.profit_factor.toFixed(2)}
          icon={BarChart}
          trend={metrics.profit_factor >= 1 ? 'up' : 'down'}
          trendValue={`${metrics.profit_factor >= 1 ? 'Profitable' : 'Unprofitable'}`}
        />
        <MetricCard
          title="Expectancy"
          value={formatCurrency(metrics.trade_expectancy)}
          icon={TrendingUp}
          trend={metrics.trade_expectancy >= 0 ? 'up' : 'down'}
          trendValue={`Per Trade`}
        />
      </div>

      {/* Charts Grid */}
      {hasChartData ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Equity Curve */}
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Profit Curve - {formatDateRange(selectedDateRange)}</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={equityCurveData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip formatter={(value) => formatCurrency(value as number)} />
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
          <h3 className="text-lg font-medium text-gray-900 mb-4">Performance Breakdown - {formatDateRange(selectedDateRange)}</h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">Average Win</span>
              <span className="text-sm font-medium text-green-600">
                {formatCurrency(metrics.avg_win)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">Average Loss</span>
              <span className="text-sm font-medium text-red-600">
                -{formatCurrency(metrics.avg_loss)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">Total Trades</span>
              <span className="text-sm font-medium text-gray-900">
                {metrics.total_trades}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">Win/Loss Ratio</span>
              <span className="text-sm font-medium text-gray-900">
                {metrics.losing_trades > 0 
                  ? (metrics.winning_trades / metrics.losing_trades).toFixed(2)
                  : 'N/A'
                }
              </span>
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


    </div>
  );
}
