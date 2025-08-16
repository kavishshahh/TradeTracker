'use client';

import { useAuth } from '@/contexts/AuthContext';
import { getMetrics, getTrades } from '@/lib/api';
import { formatCurrency, formatPercentage } from '@/lib/utils';
import { Trade, TradeMetrics } from '@/types/trade';
import { Calendar, DollarSign, Target, TrendingUp } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
    Area,
    AreaChart,
    Bar,
    BarChart,
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis
} from 'recharts';

interface PeriodStats {
  period: string;
  pnl: number;
  winRate: number;
  expectancy: number;
  trades: number;
  runningBalance: number;
}

export default function ProgressTracker() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [metrics, setMetrics] = useState<TradeMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedPeriod, setSelectedPeriod] = useState<'weekly' | 'monthly'>('weekly');
  const { currentUser } = useAuth();

  useEffect(() => {
    if (!currentUser) return;
    
    const fetchData = async () => {
      try {
        const [tradesData, metricsData] = await Promise.all([
          getTrades(currentUser.uid),
          getMetrics(currentUser.uid)
        ]);
        
        setTrades(tradesData.trades);
        setMetrics(metricsData);
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [currentUser]);

  const generatePeriodStats = (): PeriodStats[] => {
    if (!trades.length) return [];

    const closedTrades = trades
      .filter(trade => trade.status === 'closed' && trade.sell_price)
      .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

    const periods = new Map<string, Trade[]>();
    
    closedTrades.forEach(trade => {
      const date = new Date(trade.date);
      let periodKey: string;
      
      if (selectedPeriod === 'weekly') {
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
        const pnlValues = periodTrades.map(trade => 
          (trade.sell_price! - trade.buy_price) * trade.shares
        );
        
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
        if (selectedPeriod === 'weekly') {
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

  if (loading || !metrics) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const periodStats = generatePeriodStats();
  const latestPeriod = periodStats[periodStats.length - 1];
  const previousPeriod = periodStats[periodStats.length - 2];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Progress Tracker</h1>
          <p className="mt-1 text-sm text-gray-500">
            Track your trading performance over time
          </p>
        </div>

        {/* Period Toggle */}
        <div className="flex rounded-md shadow-sm">
          <button
            onClick={() => setSelectedPeriod('weekly')}
            className={`px-4 py-2 text-sm font-medium rounded-l-md border ${
              selectedPeriod === 'weekly'
                ? 'bg-blue-50 border-blue-500 text-blue-700'
                : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
            }`}
          >
            Weekly
          </button>
          <button
            onClick={() => setSelectedPeriod('monthly')}
            className={`px-4 py-2 text-sm font-medium rounded-r-md border-t border-r border-b ${
              selectedPeriod === 'monthly'
                ? 'bg-blue-50 border-blue-500 text-blue-700'
                : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
            }`}
          >
            Monthly
          </button>
        </div>
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
                    Current {selectedPeriod === 'weekly' ? 'Week' : 'Month'} P&L
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
                <Calendar className="h-8 w-8 text-orange-500" />
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

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Account Balance Over Time */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Account Balance ({selectedPeriod === 'weekly' ? 'Weekly' : 'Monthly'})
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
            {selectedPeriod === 'weekly' ? 'Weekly' : 'Monthly'} P&L
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
                fill={(entry) => entry >= 0 ? '#10B981' : '#EF4444'}
                radius={[2, 2, 0, 0]}
              >
                {periodStats.map((entry, index) => (
                  <Bar key={index} fill={entry.pnl >= 0 ? '#10B981' : '#EF4444'} />
                ))}
              </Bar>
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

      {/* Performance Summary Table */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">
            {selectedPeriod === 'weekly' ? 'Weekly' : 'Monthly'} Performance Summary
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Period
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  P&L
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Win Rate
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Trades
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Expectancy
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Balance
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {periodStats.slice(-8).reverse().map((period, index) => (
                <tr key={index}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {period.period}
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-sm font-medium ${
                    period.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {formatCurrency(period.pnl)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {formatPercentage(period.winRate)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {period.trades}
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-sm ${
                    period.expectancy >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {formatCurrency(period.expectancy)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {formatCurrency(period.runningBalance)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
