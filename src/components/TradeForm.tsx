'use client';

import { useAuth } from '@/contexts/AuthContext';
import { addTrade } from '@/lib/api';
import { CalendarIcon, DollarSign } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'react-toastify';

interface TradeFormData {
  date: string;
  ticker: string;
  buy_price?: number;
  sell_price?: number;
  shares: number;
  risk?: number; // Risk percentage
  risk_dollars?: number; // Risk in dollars
  notes?: string;
  status: 'open' | 'closed';
}

export default function TradeForm() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [tradeType, setTradeType] = useState<'entry' | 'exit'>('entry');
  const { currentUser } = useAuth();
  
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors }
  } = useForm<TradeFormData>({
    defaultValues: {
      status: 'closed',
      date: new Date().toISOString().split('T')[0],
    }
  });

  const status = watch('status');
  const buyPrice = watch('buy_price');
  const sellPrice = watch('sell_price');
  const shares = watch('shares');

  const onSubmit = async (data: TradeFormData) => {
    setIsSubmitting(true);
    setSubmitSuccess(false);

    try {
      const tradeData: any = {
        user_id: currentUser!.uid, // Use authenticated user's ID
        date: data.date,
        ticker: data.ticker.toUpperCase(),
        shares: data.shares,
        notes: data.notes || '',
        status: tradeType === 'exit' ? 'closed' : data.status,
      };

      // Include risk fields
      if (data.risk) tradeData.risk = data.risk;
      if (data.risk_dollars) tradeData.risk_dollars = data.risk_dollars;

      // Only include buy_price if it's provided (for entry trades or complete trades)
      if (data.buy_price && data.buy_price > 0) {
        tradeData.buy_price = data.buy_price;
      }

      // Include sell_price for closed trades or exits
      if ((data.status === 'closed' || tradeType === 'exit') && data.sell_price) {
        tradeData.sell_price = data.sell_price;
      }

      await addTrade(tradeData);
      setSubmitSuccess(true);
      reset();
      
      // Show success toast
      toast.success('🚀 Trade added successfully!', {
        className: '!bg-gradient-to-r !from-green-400 !to-green-600 !text-white',
        progressClassName: '!bg-white !bg-opacity-50'
      });
      
      // Auto-hide success message after 3 seconds
      setTimeout(() => setSubmitSuccess(false), 3000);
    } catch (error) {
      console.error('Error adding trade:', error);
      toast.error('❌ Failed to add trade. Please try again!', {
        className: '!bg-gradient-to-r !from-red-400 !to-red-600 !text-white',
        progressClassName: '!bg-white !bg-opacity-50'
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Calculate potential P&L
  const calculatePnL = () => {
    if (buyPrice && sellPrice && shares) {
      return (sellPrice - buyPrice) * shares;
    }
    return 0;
  };

  const pnl = calculatePnL();

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white rounded-lg shadow-lg p-6">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900">
            {tradeType === 'entry' ? 'Add New Trade' : 'Exit Trade'}
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            {tradeType === 'entry' 
              ? 'Enter the details of your trade to track performance'
              : 'Record your trade exit to close the position'
            }
          </p>
        </div>

        {/* Trade Type Toggle */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">Trade Type</label>
          <div className="flex rounded-md shadow-sm">
            <button
              type="button"
              onClick={() => {
                setTradeType('entry');
                reset({ 
                  status: 'closed',
                  date: new Date().toISOString().split('T')[0],
                });
              }}
              className={`flex-1 py-2 px-4 text-sm font-medium rounded-l-md border ${
                tradeType === 'entry'
                  ? 'bg-blue-50 border-blue-500 text-blue-700'
                  : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              New Entry
            </button>
            <button
              type="button"
              onClick={() => {
                setTradeType('exit');
                reset({ 
                  status: 'closed',
                  date: new Date().toISOString().split('T')[0],
                });
              }}
              className={`flex-1 py-2 px-4 text-sm font-medium rounded-r-md border-t border-r border-b ${
                tradeType === 'exit'
                  ? 'bg-blue-50 border-blue-500 text-blue-700'
                  : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              Exit Trade
            </button>
          </div>
        </div>

        {submitSuccess && (
          <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-md">
            <p className="text-green-800">Trade added successfully!</p>
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Date and Ticker */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div>
              <label htmlFor="date" className="block text-sm font-medium text-gray-700">
                Trade Date
              </label>
                             <div className="mt-1 relative">
                 <input
                   type="date"
                   {...register('date', { required: 'Date is required' })}
                   className="appearance-none block w-full px-3 py-2 pr-10 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                   style={{ colorScheme: 'light' }}
                 />
                 <CalendarIcon className="absolute right-3 top-2.5 h-5 w-5 text-gray-700 pointer-events-none" />
               </div>
              {errors.date && (
                <p className="mt-1 text-sm text-red-600">{errors.date.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="ticker" className="block text-sm font-medium text-gray-700">
                Ticker Symbol
              </label>
              <div className="mt-1">
                                 <input
                   type="text"
                   {...register('ticker', { 
                     required: 'Ticker is required',
                     pattern: {
                       value: /^[A-Za-z]+$/,
                       message: 'Ticker should only contain letters'
                     }
                   })}
                   placeholder="AAPL"
                   className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 uppercase text-gray-900 bg-white"
                 />
              </div>
              {errors.ticker && (
                <p className="mt-1 text-sm text-red-600">{errors.ticker.message}</p>
              )}
            </div>
          </div>

          {/* Status Toggle */}
          <div>
            <label className="block text-sm font-medium text-gray-700">Trade Status</label>
            <div className="mt-1 flex rounded-md shadow-sm">
              <button
                type="button"
                onClick={() => reset({ ...watch(), status: 'open' })}
                className={`flex-1 py-2 px-4 text-sm font-medium rounded-l-md border ${
                  status === 'open'
                    ? 'bg-blue-50 border-blue-500 text-blue-700'
                    : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
              >
                Open Position
              </button>
              <button
                type="button"
                onClick={() => reset({ ...watch(), status: 'closed' })}
                className={`flex-1 py-2 px-4 text-sm font-medium rounded-r-md border-t border-r border-b ${
                  status === 'closed'
                    ? 'bg-blue-50 border-blue-500 text-blue-700'
                    : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
              >
                Closed Position
              </button>
            </div>
          </div>

          {/* Prices and Shares */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
            {tradeType === 'entry' && (
              <div>
                <label htmlFor="buy_price" className="block text-sm font-medium text-gray-700">
                  Buy Price *
                </label>
                <div className="mt-1 relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <DollarSign className="h-5 w-5 text-gray-600" />
                  </div>
                  <input
                    type="number"
                    step="0.0001"
                    {...register('buy_price', { 
                      required: tradeType === 'entry' ? 'Buy price is required' : false,
                      min: { value: 0.0001, message: 'Price must be greater than 0' }
                    })}
                    placeholder="150.00"
                    className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                  />
                </div>
                {errors.buy_price && (
                  <p className="mt-1 text-sm text-red-600">{errors.buy_price.message}</p>
                )}
              </div>
            )}

            {(status === 'closed' || tradeType === 'exit') && (
              <div>
                <label htmlFor="sell_price" className="block text-sm font-medium text-gray-700">
                  {tradeType === 'exit' ? 'Exit Price *' : 'Sell Price *'}
                </label>
                <div className="mt-1 relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <DollarSign className="h-5 w-5 text-gray-600" />
                  </div>
                  <input
                    type="number"
                    step="0.0001"
                    {...register('sell_price', { 
                      required: (status === 'closed' || tradeType === 'exit') ? 'Exit price is required' : false,
                      min: { value: 0.0001, message: 'Price must be greater than 0' }
                    })}
                    placeholder="165.00"
                    className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                  />
                </div>
                {errors.sell_price && (
                  <p className="mt-1 text-sm text-red-600">{errors.sell_price.message}</p>
                )}
              </div>
            )}

            <div>
              <label htmlFor="shares" className="block text-sm font-medium text-gray-700">
                Shares
              </label>
              <div className="mt-1">
                <input
                  type="number"
                  step="0.0001"
                  {...register('shares', { 
                    required: 'Number of shares is required',
                    min: { value: 0.0001, message: 'Must have at least 0.0001 shares' }
                  })}
                  placeholder="100"
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                />
              </div>
              {errors.shares && (
                <p className="mt-1 text-sm text-red-600">{errors.shares.message}</p>
              )}
            </div>
          </div>



          {/* Risk Fields */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {/* Risk Percentage */}
            <div>
              <label htmlFor="risk" className="block text-sm font-medium text-gray-700">
                Risk Percentage (%)
              </label>
              <div className="mt-1">
                <input
                  type="number"
                  step="0.01"
                  {...register('risk', { 
                    min: { value: 0.01, message: 'Risk must be at least 0.01%' },
                    max: { value: 100, message: 'Risk cannot exceed 100%' }
                  })}
                  placeholder="2.0"
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                />
              </div>
              {errors.risk && (
                <p className="mt-1 text-sm text-red-600">{errors.risk.message}</p>
              )}
            </div>

            {/* Risk in Dollars */}
            <div>
              <label htmlFor="risk_dollars" className="block text-sm font-medium text-gray-700">
                Risk in Dollars ($)
              </label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <DollarSign className="h-5 w-5 text-gray-600" />
                </div>
                <input
                  type="number"
                  step="0.01"
                  {...register('risk_dollars', {
                    min: { value: 0.01, message: 'Risk amount must be greater than 0' }
                  })}
                  placeholder="200.00"
                  className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
                />
              </div>
              {errors.risk_dollars && (
                <p className="mt-1 text-sm text-red-600">{errors.risk_dollars.message}</p>
              )}
            </div>
          </div>

          <div className="text-sm text-gray-600">
            <p>💡 <strong>Risk Fields:</strong> Provide either risk percentage OR risk in dollars. The other field will be calculated automatically based on your profile's account balance.</p>
          </div>

          {/* Notes */}
          <div>
            <label htmlFor="notes" className="block text-sm font-medium text-gray-700">
              Trade Notes
            </label>
            <div className="mt-1">
              <textarea
                {...register('notes')}
                rows={3}
                placeholder="Reason for trade, confidence level, strategy used..."
                                   className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
              />
            </div>
          </div>

          {/* P&L Preview for closed trades */}
          {status === 'closed' && buyPrice && sellPrice && shares && (
            <div className="bg-gray-50 rounded-md p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Estimated P&L:</span>
                <span className={`text-lg font-bold ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                </span>
              </div>
              <div className="mt-1 text-xs text-gray-500">
                ({sellPrice} - {buyPrice}) × {shares} shares
              </div>
            </div>
          )}

          {/* Submit Button */}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isSubmitting}
              className="bg-blue-600 py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? 'Adding Trade...' : 'Add Trade'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
