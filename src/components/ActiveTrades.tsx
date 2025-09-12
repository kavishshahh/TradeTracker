'use client';

import { useAuth } from '@/contexts/AuthContext';
import { deleteTrade, exitTrade, getTrades } from '@/lib/api';
import { formatCurrency, formatShares, normalizeShares } from '@/lib/utils';
import { Trade } from '@/types/trade';
import { DollarSign, MoreVertical, Trash2, TrendingDown, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'react-toastify';

interface ExitTradeFormData {
  sell_price: number;
  shares_to_exit: number;
  notes?: string;
}

interface ExitTradeModalProps {
  trade: Trade | null;
  onClose: () => void;
  onExit: (tradeId: string, exitData: ExitTradeFormData) => void;
}

interface DeleteTradeModalProps {
  trade: Trade | null;
  onClose: () => void;
  onDelete: (tradeId: string) => void;
}

function ExitTradeModal({ trade, onClose, onExit }: ExitTradeModalProps) {
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors }
  } = useForm<ExitTradeFormData>();

  const watchedShares = watch('shares_to_exit');
  const watchedPrice = watch('sell_price');

  useEffect(() => {
    if (trade) {
      // Handle floating-point precision issues - normalize very small numbers to 0
      const normalizedShares = Math.abs(trade.shares) < 1e-10 ? 0 : trade.shares;
      setValue('shares_to_exit', normalizedShares);
      reset({
        shares_to_exit: normalizedShares,
        sell_price: 0,
        notes: ''
      });
    }
  }, [trade, setValue, reset]);

  if (!trade) return null;

  const onSubmit = (data: ExitTradeFormData) => {
    onExit(trade.id!, data);
    onClose();
  };

  const setPartialExit = (fraction: number) => {
    // Use proper decimal arithmetic to avoid floating-point precision issues
    const normalizedShares = Math.abs(trade.shares) < 1e-10 ? 0 : trade.shares;
    const sharesToExit = Math.round((normalizedShares * fraction) * 10000) / 10000; // Round to 4 decimal places
    setValue('shares_to_exit', parseFloat(sharesToExit.toFixed(4)));
  };

  const estimatedPnL = watchedPrice && watchedShares && trade.buy_price
    ? (watchedPrice - trade.buy_price) * watchedShares 
    : 0;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Exit Trade - {trade.ticker}</h3>
          <button
            onClick={onClose}
            className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Trade Info */}
        <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-700 rounded-lg text-sm">
          <div className="grid grid-cols-2 gap-2">
            <div className="text-gray-700 dark:text-gray-300">Position: <span className="font-medium text-gray-900 dark:text-white">{formatShares(trade.shares)} shares</span></div>
            <div className="text-gray-700 dark:text-gray-300">Entry: <span className="font-medium text-gray-900 dark:text-white">${trade.buy_price}</span></div>
            <div className="text-gray-700 dark:text-gray-300">Date: <span className="font-medium text-gray-900 dark:text-white">{new Date(trade.date).toLocaleDateString()}</span></div>
            <div className="text-gray-700 dark:text-gray-300">Risk: <span className="font-medium text-gray-900 dark:text-white">{trade.risk}%</span></div>
          </div>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Exit Price */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Exit Price *
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <DollarSign className="h-5 w-5 text-gray-600 dark:text-gray-400" />
              </div>
              <input
                type="number"
                step="0.01"
                {...register('sell_price', { 
                  required: 'Exit price is required',
                  min: { value: 0.01, message: 'Price must be greater than 0' }
                })}
                placeholder="165.00"
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 dark:text-white bg-white dark:bg-gray-700"
              />
            </div>
            {errors.sell_price && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.sell_price.message}</p>
            )}
          </div>

          {/* Shares to Exit */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Shares to Exit *
            </label>
            <input
              type="number"
              step="0.0001"
              {...register('shares_to_exit', { 
                required: 'Number of shares is required',
                min: { value: 0.0001, message: 'Must exit at least 0.0001 share' },
                max: { value: Math.abs(trade.shares) < 1e-10 ? 0 : trade.shares, message: `Cannot exit more than ${formatShares(trade.shares)} shares` }
              })}
              className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 dark:text-white bg-white dark:bg-gray-700"
            />
            {errors.shares_to_exit && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.shares_to_exit.message}</p>
            )}
          </div>

          {/* Quick Exit Shortcuts */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Quick Exit
            </label>
            <div className="flex space-x-2">
              <button
                type="button"
                onClick={() => setPartialExit(1/3)}
                className="flex-1 py-2 px-3 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                1/3 ({Math.round((trade.shares / 3) * 100) / 100})
              </button>
              <button
                type="button"
                onClick={() => setPartialExit(1/2)}
                className="flex-1 py-2 px-3 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                1/2 ({Math.round((trade.shares / 2) * 100) / 100})
              </button>
              <button
                type="button"
                onClick={() => setValue('shares_to_exit', trade.shares)}
                className="flex-1 py-2 px-3 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
              >
                All ({trade.shares})
              </button>
            </div>
          </div>

          {/* Exit Notes */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Exit Notes (Optional)
            </label>
            <textarea
              {...register('notes')}
              rows={2}
              placeholder="Reason for exit, profit taking, stop loss..."
              className="block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 dark:text-white bg-white dark:bg-gray-700"
            />
          </div>

          {/* P&L Preview */}
          {watchedPrice && watchedShares && (
            <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-3">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Estimated P&L:</span>
                <span className={`text-lg font-bold ${estimatedPnL >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {estimatedPnL >= 0 ? '+' : ''}{formatCurrency(estimatedPnL)}
                </span>
              </div>
              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                ({watchedPrice} - {trade.buy_price}) × {watchedShares} shares
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex space-x-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 px-4 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 py-2 px-4 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700"
            >
              Exit Trade
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DeleteTradeModal({ trade, onClose, onDelete }: DeleteTradeModalProps) {
  if (!trade) return null;

  const handleDelete = () => {
    onDelete(trade.id!);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-red-600 dark:text-red-400">Delete Trade</h3>
          <button
            onClick={onClose}
            className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Trade Info */}
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg text-sm">
          <div className="grid grid-cols-2 gap-2">
            <div className="text-gray-700 dark:text-gray-300">Ticker: <span className="font-medium text-gray-900 dark:text-white">{trade.ticker}</span></div>
            <div className="text-gray-700 dark:text-gray-300">Shares: <span className="font-medium text-gray-900 dark:text-white">{formatShares(trade.shares)}</span></div>
            <div className="text-gray-700 dark:text-gray-300">Entry: <span className="font-medium text-gray-900 dark:text-white">${trade.buy_price}</span></div>
            <div className="text-gray-700 dark:text-gray-300">Date: <span className="font-medium text-gray-900 dark:text-white">{new Date(trade.date).toLocaleDateString()}</span></div>
          </div>
        </div>

        <div className="mb-6">
          <p className="text-gray-700 dark:text-gray-300 mb-2">
            Are you sure you want to delete this trade? This action cannot be undone.
          </p>
          <p className="text-sm text-red-600 dark:text-red-400 font-medium">
            ⚠️ This will permanently remove the trade from your records.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex space-x-3 pt-4">
          <button
            onClick={onClose}
            className="flex-1 py-2 px-4 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={handleDelete}
            className="flex-1 py-2 px-4 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700"
          >
            Delete Trade
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ActiveTrades() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [exitingTrade, setExitingTrade] = useState<Trade | null>(null);
  const [deletingTrade, setDeletingTrade] = useState<Trade | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const { currentUser } = useAuth();

  useEffect(() => {
    if (!currentUser) return;
    
    const fetchTrades = async () => {
      try {
        const response = await getTrades(currentUser.uid);
        const activeTrades = response.trades.filter(trade => 
          trade.status === 'open' && Math.abs(trade.shares) >= 1e-10 // Filter out trades with effectively 0 shares
        );
        setTrades(activeTrades);
      } catch (error) {
        console.error('Error fetching trades:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchTrades();
  }, [currentUser]);

  const handleExitTrade = async (tradeId: string, exitData: ExitTradeFormData) => {
    try {
      const trade = trades.find(t => t.id === tradeId);
      if (!trade) {
        throw new Error('Trade not found');
      }

      // Check if trade effectively has 0 shares
      const normalizedShares = Math.abs(trade.shares) < 1e-10 ? 0 : trade.shares;
      if (normalizedShares === 0) {
        toast.error('❌ Cannot exit trade with 0 shares', {
          className: '!bg-gradient-to-r !from-red-400 !to-red-600 !text-white',
          progressClassName: '!bg-white !bg-opacity-50'
        });
        return;
      }

      // Call the proper exit trade API
      const result = await exitTrade(currentUser!.uid, {
        ticker: trade.ticker,
        shares_to_exit: normalizeShares(exitData.shares_to_exit), // Normalize to avoid floating-point precision issues
        sell_price: exitData.sell_price,
        notes: exitData.notes || ''
      });
      
      // Calculate P&L
      const pnl = trade.buy_price 
        ? (exitData.sell_price - trade.buy_price) * normalizeShares(exitData.shares_to_exit)
        : 0;
      
      // Refresh the trades list to reflect the changes
      const response = await getTrades(currentUser!.uid);
      const activeTrades = response.trades.filter(trade => 
        trade.status === 'open' && Math.abs(trade.shares) >= 1e-10 // Filter out trades with effectively 0 shares
      );
      setTrades(activeTrades);
      
      // Show success toast
      toast.success(`🎯 ${result.message}${pnl !== 0 ? ` P&L: ${formatCurrency(pnl)}` : ''}`, {
        className: pnl >= 0 
          ? '!bg-gradient-to-r !from-green-400 !to-green-600 !text-white'
          : '!bg-gradient-to-r !from-orange-400 !to-red-500 !text-white',
        progressClassName: '!bg-white !bg-opacity-50',
        autoClose: 4000
      });
    } catch (error) {
      console.error('Error exiting trade:', error);
      toast.error(`❌ Failed to exit trade: ${error instanceof Error ? error.message : 'Unknown error'}`, {
        className: '!bg-gradient-to-r !from-red-400 !to-red-600 !text-white',
        progressClassName: '!bg-white !bg-opacity-50'
      });
    }
  };

  const handleDeleteTrade = async (tradeId: string) => {
    try {
      await deleteTrade(tradeId);
      
      // Remove the trade from local state
      setTrades(prevTrades => prevTrades.filter(trade => trade.id !== tradeId));
      
      // Show success toast
      toast.success('🗑️ Trade deleted successfully', {
        className: '!bg-gradient-to-r !from-red-400 !to-red-600 !text-white',
        progressClassName: '!bg-white !bg-opacity-50',
        autoClose: 3000
      });
    } catch (error) {
      console.error('Error deleting trade:', error);
      toast.error(`❌ Failed to delete trade: ${error instanceof Error ? error.message : 'Unknown error'}`, {
        className: '!bg-gradient-to-r !from-red-400 !to-red-600 !text-white',
        progressClassName: '!bg-white !bg-opacity-50'
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (trades.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Active Trades</h3>
        <div className="text-center py-12">
          <div className="mx-auto w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-4">
            <TrendingDown className="h-8 w-8 text-gray-400 dark:text-gray-500" />
          </div>
          <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No Active Trades</h4>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            You don't have any open positions at the moment.
          </p>
          <p className="text-sm text-gray-400 dark:text-gray-500">
            Add a new trade to start tracking your positions.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-medium text-gray-900 dark:text-white">Active Trades ({trades.length})</h3>
      </div>
      
      <div className="divide-y divide-gray-200 dark:divide-gray-700">
        {trades.map((trade) => {
          const currentValue = (trade.buy_price ?? 0) * trade.shares; // Placeholder for current market value
          const unrealizedPnL = 0; // Would calculate with real-time prices
          
          return (
            <div key={trade.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3">
                    <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                    <div>
                      <h4 className="text-sm font-medium text-gray-900 dark:text-white">{trade.ticker}</h4>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {formatShares(trade.shares)} shares @ ${trade.buy_price}
                      </p>
                    </div>
                  </div>
                </div>
                
                <div className="text-right">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {formatCurrency(currentValue)}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Risk: {trade.risk}%
                  </p>
                </div>
                
                <div className="ml-4 relative">
                  <button
                    onClick={() => setOpenMenuId(openMenuId === trade.id ? null : (trade.id ?? null))}
                    className="p-1 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 rounded"
                  >
                    <MoreVertical className="h-4 w-4" />
                  </button>
                  
                  {openMenuId === trade.id && (
                    <div className="absolute right-0 mt-1 w-40 bg-white dark:bg-gray-800 rounded-md shadow-lg border border-gray-200 dark:border-gray-700 z-10">
                      <button
                        onClick={() => {
                          setExitingTrade(trade);
                          setOpenMenuId(null);
                        }}
                        className="w-full px-3 py-2 text-left text-sm text-orange-600 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-900/20 flex items-center"
                      >
                        <TrendingDown className="h-4 w-4 mr-2" />
                        Exit Trade
                      </button>
                      <button
                        onClick={() => {
                          setDeletingTrade(trade);
                          setOpenMenuId(null);
                        }}
                        className="w-full px-3 py-2 text-left text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 flex items-center"
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Delete Trade
                      </button>
                    </div>
                  )}
                </div>
              </div>
              
              {trade.notes && (
                <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
                  "{trade.notes}"
                </div>
              )}
            </div>
          );
        })}
      </div>

      <ExitTradeModal
        trade={exitingTrade}
        onClose={() => setExitingTrade(null)}
        onExit={handleExitTrade}
      />

      <DeleteTradeModal
        trade={deletingTrade}
        onClose={() => setDeletingTrade(null)}
        onDelete={handleDeleteTrade}
      />
    </div>
  );
}
