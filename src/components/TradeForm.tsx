'use client';

import { addTrade } from '@/lib/api';
import { Trade } from '@/types/trade';
import { CalendarIcon, DollarSign } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

interface TradeFormData {
  date: string;
  ticker: string;
  buy_price: number;
  sell_price?: number;
  shares: number;
  risk: number;
  notes?: string;
  status: 'open' | 'closed';
}

export default function TradeForm() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  
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
      const tradeData: Omit<Trade, 'id' | 'created_at' | 'updated_at'> = {
        user_id: 'user123', // In a real app, this would come from auth
        date: data.date,
        ticker: data.ticker.toUpperCase(),
        buy_price: data.buy_price,
        sell_price: data.status === 'closed' ? data.sell_price : undefined,
        shares: data.shares,
        risk: data.risk,
        notes: data.notes || '',
        status: data.status,
      };

      await addTrade(tradeData);
      setSubmitSuccess(true);
      reset();
      
      // Auto-hide success message after 3 seconds
      setTimeout(() => setSubmitSuccess(false), 3000);
    } catch (error) {
      console.error('Error adding trade:', error);
      alert('Failed to add trade. Please try again.');
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
          <h2 className="text-2xl font-bold text-gray-900">Add New Trade</h2>
          <p className="mt-1 text-sm text-gray-600">
            Enter the details of your trade to track performance
          </p>
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
            <div>
              <label htmlFor="buy_price" className="block text-sm font-medium text-gray-700">
                Buy Price
              </label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <DollarSign className="h-5 w-5 text-gray-400" />
                </div>
                <input
                  type="number"
                  step="0.01"
                  {...register('buy_price', { 
                    required: 'Buy price is required',
                    min: { value: 0.01, message: 'Price must be greater than 0' }
                  })}
                  placeholder="150.00"
                  className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              {errors.buy_price && (
                <p className="mt-1 text-sm text-red-600">{errors.buy_price.message}</p>
              )}
            </div>

            {status === 'closed' && (
              <div>
                <label htmlFor="sell_price" className="block text-sm font-medium text-gray-700">
                  Sell Price
                </label>
                <div className="mt-1 relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <DollarSign className="h-5 w-5 text-gray-400" />
                  </div>
                  <input
                    type="number"
                    step="0.01"
                    {...register('sell_price', { 
                      required: status === 'closed' ? 'Sell price is required for closed trades' : false,
                      min: { value: 0.01, message: 'Price must be greater than 0' }
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
                  {...register('shares', { 
                    required: 'Number of shares is required',
                    min: { value: 1, message: 'Must have at least 1 share' }
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

          {/* Risk Percentage */}
          <div>
            <label htmlFor="risk" className="block text-sm font-medium text-gray-700">
              Risk Percentage
            </label>
            <div className="mt-1">
              <input
                type="number"
                step="0.1"
                {...register('risk', { 
                  required: 'Risk percentage is required',
                  min: { value: 0.1, message: 'Risk must be at least 0.1%' },
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
