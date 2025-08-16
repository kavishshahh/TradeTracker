'use client';

import { useAuth } from '@/contexts/AuthContext';
import { getMetrics, getTrades } from '@/lib/api';
import { formatCurrency, formatPercentage } from '@/lib/utils';
import { Trade, TradeMetrics } from '@/types/trade';
import { BarChart, DollarSign, Target, TrendingDown, TrendingUp } from 'lucide-react';
import { useEffect, useState } from 'react';
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
  const { currentUser } = useAuth();

  useEffect(() => {
    if (!currentUser) return;
    
    const fetchData = async () => {
      try {
        const [metricsData, tradesData] = await Promise.all([
          getMetrics(currentUser.uid),
          getTrades(currentUser.uid)
        ]);
        
        setMetrics(metricsData);
        setTrades(tradesData.trades);
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [currentUser]);

  if (loading || !metrics) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  // Prepare equity curve data
  const equityCurveData = trades
    .filter(trade => trade.status === 'closed' && trade.sell_price)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
    .reduce((acc, trade, index) => {
      const pnl = (trade.sell_price! - trade.buy_price) * trade.shares;
      const prevValue = acc.length > 0 ? acc[acc.length - 1].equity : 0;
      acc.push({
        date: trade.date,
        equity: prevValue + pnl,
        pnl: pnl
      });
      return acc;
    }, [] as { date: string; equity: number; pnl: number }[]);

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
          Your trading performance at a glance
        </p>
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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Equity Curve */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Equity Curve</h3>
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
          <h3 className="text-lg font-medium text-gray-900 mb-4">Win/Loss Distribution</h3>
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
          <h3 className="text-lg font-medium text-gray-900 mb-4">Trading Score</h3>
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
          <h3 className="text-lg font-medium text-gray-900 mb-4">Performance Breakdown</h3>
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

      {/* Recent Trades */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">Recent Trades</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Date
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Ticker
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Shares
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  P&L
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {trades.slice(0, 5).map((trade) => {
                const pnl = trade.sell_price 
                  ? (trade.sell_price - trade.buy_price) * trade.shares 
                  : 0;
                return (
                  <tr key={trade.id}>
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
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {trade.status === 'closed' ? (
                        <span className={pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
                          {formatCurrency(pnl)}
                        </span>
                      ) : (
                        <span className="text-gray-500">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
