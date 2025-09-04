'use client';

import { Calendar } from '@/components/ui/calendar';
import { useAuth } from '@/contexts/AuthContext';
import { trackEvent, trackPageView, trackUserEngagement } from '@/lib/analytics';
import { deleteTrade, getFeesConfig, getTrades, updateTrade } from '@/lib/api';
import { calculateCompleteTradeFees, calculateNetPnL, formatCurrency } from '@/lib/utils';
import { FeesConfig, Trade } from '@/types/trade';
import { BarChart3, Calculator, Calendar as CalendarIcon, DollarSign, Download, Edit, Filter, Search, Target, Trash2, TrendingDown, TrendingUp, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { DateRange } from 'react-day-picker';
import { toast } from 'react-toastify';

interface MonthShortcut {
  label: string;
  range: DateRange;
}

interface TradeDetailModalProps {
  trade: Trade | null;
  feesConfig: FeesConfig | null;
  showNetProfits: boolean;
  onClose: () => void;
}

interface EditModalProps {
  trade: Trade | null;
  onClose: () => void;
  onSave: (updatedTrade: Trade) => void;
}

interface DeleteTradeModalProps {
  trade: Trade | null;
  onClose: () => void;
  onDelete: (tradeId: string) => void;
}

function TradeDetailModal({ trade, feesConfig, showNetProfits, onClose }: TradeDetailModalProps) {
  if (!trade) return null;

  const grossPnl = trade.sell_price && trade.buy_price
    ? (trade.sell_price - trade.buy_price) * trade.shares 
    : 0;
  
  const netPnl = feesConfig ? calculateNetPnL(trade, feesConfig) : grossPnl;
  const pnl = showNetProfits ? netPnl : grossPnl;
  
  const fees = feesConfig ? calculateCompleteTradeFees(trade, feesConfig) : null;
  
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
          <div className={`grid gap-4 ${fees && trade.status === 'closed' ? 'grid-cols-2 lg:grid-cols-5' : 'grid-cols-2 lg:grid-cols-4'}`}>
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
                    P&L ({showNetProfits ? 'Net' : 'Gross'})
                  </p>
                  <p className={`text-lg font-semibold ${pnl >= 0 ? 'text-green-900' : 'text-red-900'}`}>
                    {trade.status === 'closed' ? formatCurrency(pnl) : 'Open'}
                  </p>
                </div>
              </div>
            </div>

            {/* Fees Card */}
            {fees && trade.status === 'closed' && (
              <div className="bg-orange-50 rounded-lg p-4">
                <div className="flex items-center">
                  <Calculator className="h-5 w-5 text-orange-500 mr-2" />
                  <div>
                    <p className="text-xs font-medium text-orange-600">Trading Fees</p>
                    <p className="text-lg font-semibold text-orange-900">
                      {formatCurrency(fees.totalFees)}
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="bg-yellow-50 rounded-lg p-4">
              <div className="flex items-center">
                <Target className="h-5 w-5 text-yellow-600 mr-2" />
                <div>
                  <p className="text-xs font-medium text-yellow-700">Risk Amount</p>
                  <p className="text-lg font-semibold text-yellow-900">
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
                  <span className="text-gray-500">{showNetProfits ? 'Net' : 'Gross'} P&L:</span>
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
              
              {/* Fees Breakdown */}
              {fees && feesConfig && (
                <div className="border-t border-gray-200 pt-3">
                  <h4 className="text-sm font-medium text-gray-900 mb-2">Fees Breakdown</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                    <div>
                      <span className="text-gray-500">Brokerage:</span>
                      <p className="font-medium text-orange-600">
                        -{formatCurrency(fees.breakdown.buyBrokerage + fees.breakdown.sellBrokerage)}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">Exchange Charges:</span>
                      <p className="font-medium text-orange-600">
                        -{formatCurrency(fees.breakdown.buyExchangeCharges + fees.breakdown.sellExchangeCharges)}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">IFSCA Fees:</span>
                      <p className="font-medium text-orange-600">
                        -{formatCurrency(fees.breakdown.buyIfscaFees + fees.breakdown.sellIfscaFees)}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">Platform Fees:</span>
                      <p className="font-medium text-orange-600">
                        -{formatCurrency(fees.breakdown.platformFees)}
                      </p>
                    </div>
                  </div>
                  
                  {showNetProfits && grossPnl !== netPnl && (
                    <div className="mt-3 pt-2 border-t border-gray-200">
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">Gross P&L:</span>
                        <span className={`font-medium ${grossPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {formatCurrency(grossPnl)}
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">Total Fees:</span>
                        <span className="font-medium text-orange-600">
                          -{formatCurrency(fees.totalFees)}
                        </span>
                      </div>
                      <div className="flex justify-between text-sm border-t border-gray-200 pt-1 mt-1">
                        <span className="text-gray-900 font-medium">Net P&L:</span>
                        <span className={`font-semibold ${netPnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {formatCurrency(netPnl)}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}
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

function EditModal({ trade, onClose, onSave }: EditModalProps) {
  const [formData, setFormData] = useState({
    date: '',
    ticker: '',
    buy_price: '',
    sell_price: '',
    shares: '',
    risk: '',
    risk_dollars: '',
    notes: '',
    status: 'open' as 'open' | 'closed'
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (trade) {
      setFormData({
        date: trade.date,
        ticker: trade.ticker,
        buy_price: trade.buy_price?.toString() || '',
        sell_price: trade.sell_price?.toString() || '',
        shares: trade.shares?.toString() || '',
        risk: trade.risk?.toString() || '',
        risk_dollars: trade.risk_dollars?.toString() || '',
        notes: trade.notes || '',
        status: trade.status as 'open' | 'closed'
      });
    }
  }, [trade]);

  if (!trade) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      // Prepare update data - only include changed fields
      const updateData: any = {};
      
      if (formData.date !== trade.date) updateData.date = formData.date;
      if (formData.ticker !== trade.ticker) updateData.ticker = formData.ticker;
      if (formData.buy_price && parseFloat(formData.buy_price) !== trade.buy_price) {
        updateData.buy_price = parseFloat(formData.buy_price);
      }
      if (formData.sell_price && parseFloat(formData.sell_price) !== trade.sell_price) {
        updateData.sell_price = parseFloat(formData.sell_price);
      }
      if (formData.shares && parseFloat(formData.shares) !== trade.shares) {
        updateData.shares = parseFloat(formData.shares);
      }
      if (formData.risk && parseFloat(formData.risk) !== trade.risk) {
        updateData.risk = parseFloat(formData.risk);
      }
      if (formData.risk_dollars && parseFloat(formData.risk_dollars) !== trade.risk_dollars) {
        updateData.risk_dollars = parseFloat(formData.risk_dollars);
      }
      if (formData.notes !== trade.notes) updateData.notes = formData.notes;
      if (formData.status !== trade.status) updateData.status = formData.status;

      // Only proceed if there are changes
      if (Object.keys(updateData).length === 0) {
        toast.success('No changes to save');
        onClose();
        return;
      }

      await updateTrade(trade.id!, updateData);
      
      // Update the local trade object with new data
      const updatedTrade = { ...trade, ...updateData };
      onSave(updatedTrade);
      
      toast.success('Trade updated successfully!');
      onClose();
    } catch (error: any) {
      toast.error(error.message || 'Failed to update trade');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-4xl w-full mx-4 max-h-[90vh] overflow-auto">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-xl font-semibold">Edit Trade - {trade.ticker}</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic Trade Information */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Date
              </label>
              <input
                type="date"
                value={formData.date}
                onChange={(e) => handleInputChange('date', e.target.value)}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Ticker
              </label>
              <input
                type="text"
                value={formData.ticker}
                onChange={(e) => handleInputChange('ticker', e.target.value.toUpperCase())}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="AAPL"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Shares
              </label>
              <input
                type="number"
                step="0.01"
                value={formData.shares}
                onChange={(e) => handleInputChange('shares', e.target.value)}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="100"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Status
              </label>
              <select
                value={formData.status}
                onChange={(e) => handleInputChange('status', e.target.value)}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="open">Open</option>
                <option value="closed">Closed</option>
              </select>
            </div>
          </div>

          {/* Price Information */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Buy Price ($)
              </label>
              <input
                type="number"
                step="0.01"
                value={formData.buy_price}
                onChange={(e) => handleInputChange('buy_price', e.target.value)}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="150.00"
                required={formData.status === 'open'}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Sell Price ($)
              </label>
              <input
                type="number"
                step="0.01"
                value={formData.sell_price}
                onChange={(e) => handleInputChange('sell_price', e.target.value)}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="165.00"
                required={formData.status === 'closed'}
              />
            </div>
          </div>

          {/* Risk Information */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Risk (%)
              </label>
              <input
                type="number"
                step="0.01"
                value={formData.risk}
                onChange={(e) => handleInputChange('risk', e.target.value)}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="2.0"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Risk ($)
              </label>
              <input
                type="number"
                step="0.01"
                value={formData.risk_dollars}
                onChange={(e) => handleInputChange('risk_dollars', e.target.value)}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="200.00"
              />
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Trade Notes
            </label>
            <textarea
              value={formData.notes}
              onChange={(e) => handleInputChange('notes', e.target.value)}
              rows={6}
              placeholder="Enter your thoughts about this trade...

• Why did you take this trade?
• What was your confidence level?
• What went right or wrong?
• What lessons did you learn?
• How can you improve next time?"
              className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Action Buttons */}
          <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? 'Saving...' : 'Save Changes'}
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
      <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-red-600">Delete Trade</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Trade Info */}
        <div className="mb-4 p-3 bg-red-50 rounded-lg text-sm">
          <div className="grid grid-cols-2 gap-2">
            <div>Ticker: <span className="font-medium">{trade.ticker}</span></div>
            <div>Shares: <span className="font-medium">{trade.shares}</span></div>
            <div>Entry: <span className="font-medium">${trade.buy_price}</span></div>
            <div>Date: <span className="font-medium">{new Date(trade.date).toLocaleDateString()}</span></div>
            <div>Status: <span className="font-medium capitalize">{trade.status}</span></div>
            <div>P&L: <span className="font-medium">
              {trade.status === 'closed' && trade.sell_price && trade.buy_price 
                ? `${((trade.sell_price - trade.buy_price) * trade.shares) >= 0 ? '+' : ''}$${((trade.sell_price - trade.buy_price) * trade.shares).toFixed(2)}`
                : 'Open'
              }
            </span></div>
          </div>
        </div>

        <div className="mb-6">
          <p className="text-gray-700 mb-2">
            Are you sure you want to delete this trade? This action cannot be undone.
          </p>
          <p className="text-sm text-red-600 font-medium">
            ⚠️ This will permanently remove the trade from your records.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex space-x-3 pt-4">
          <button
            onClick={onClose}
            className="flex-1 py-2 px-4 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
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

export default function TradesView() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [filteredTrades, setFilteredTrades] = useState<Trade[]>([]);
  const [feesConfig, setFeesConfig] = useState<FeesConfig | null>(null);
  const [showNetProfits, setShowNetProfits] = useState(true);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'closed'>('all');
  const [dateRange, setDateRange] = useState<DateRange | undefined>();
  const [selectedDateRange, setSelectedDateRange] = useState<DateRange | undefined>();
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const [sortField, setSortField] = useState<'date' | 'ticker' | 'pnl'>('date');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [editingTrade, setEditingTrade] = useState<Trade | null>(null);
  const [deletingTrade, setDeletingTrade] = useState<Trade | null>(null);
  const calendarRef = useRef<HTMLDivElement>(null);
  const { currentUser } = useAuth();

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
      
      const [tradesResponse, feesResponse] = await Promise.all([
        getTrades(
          currentUser.uid,
          dateRangeParams?.startDate,
          dateRangeParams?.endDate
        ),
        getFeesConfig(currentUser.uid).catch(() => ({ fees_config: getDefaultFeesConfig() }))
      ]);
      
      const sortedTrades = tradesResponse.trades.sort((a, b) => 
        new Date(b.date).getTime() - new Date(a.date).getTime()
      );
      
      setTrades(sortedTrades);
      setFeesConfig(feesResponse.fees_config);
      
      // Track trades page view
      trackPageView('/trades');
      trackUserEngagement('trades_view', `trades_${sortedTrades.length}`);
    } catch (error) {
      console.error('Error fetching trades:', error);
    } finally {
      setLoading(false);
    }
  }, [currentUser, selectedDateRange, getDateRange]);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  // Handle trade editing
  const handleSaveTrade = async (updatedTrade: Trade) => {
    // Update local state with the updated trade
    const updatedTrades = trades.map(trade =>
      trade.id === updatedTrade.id ? updatedTrade : trade
    );
    setTrades(updatedTrades);
    
    // Refresh trades from server to ensure consistency
    try {
      await fetchTrades();
    } catch (error) {
      console.error('Error refreshing trades after update:', error);
    }
  };

  // Handle trade deletion
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
          const aGrossPnl = a.sell_price && a.buy_price ? (a.sell_price - a.buy_price) * a.shares : 0;
          const bGrossPnl = b.sell_price && b.buy_price ? (b.sell_price - b.buy_price) * b.shares : 0;
          const aNetPnl = feesConfig ? calculateNetPnL(a, feesConfig) : aGrossPnl;
          const bNetPnl = feesConfig ? calculateNetPnL(b, feesConfig) : bGrossPnl;
          aVal = showNetProfits ? aNetPnl : aGrossPnl;
          bVal = showNetProfits ? bNetPnl : bGrossPnl;
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
        if (showNetProfits && feesConfig) {
          return sum + calculateNetPnL(trade, feesConfig);
        } else {
          return sum + (trade.sell_price - trade.buy_price) * trade.shares;
        }
      }
      return sum;
    }, 0);

    const winningTrades = closedTrades.filter(trade => {
      if (trade.sell_price && trade.buy_price) {
        const pnl = showNetProfits && feesConfig 
          ? calculateNetPnL(trade, feesConfig)
          : (trade.sell_price - trade.buy_price) * trade.shares;
        return pnl > 0;
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">All Trades</h1>
          <p className="mt-1 text-sm text-gray-500">
            View and filter all your trades for {formatDateRange(selectedDateRange)}
          </p>
        </div>
        
        {/* Profit Type Toggle */}
        {feesConfig && (
          <div className="flex items-center space-x-2 bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setShowNetProfits(false)}
              className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
                !showNetProfits 
                  ? 'bg-white text-gray-900 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Gross P&L
            </button>
            <button
              onClick={() => setShowNetProfits(true)}
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
          <div className="text-sm font-medium text-gray-500">
            Total P&L {showNetProfits ? '(Net)' : '(Gross)'}
          </div>
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
                  onChange={(e) => {
                    setSearchTerm(e.target.value);
                    if (e.target.value.length > 2) {
                      trackEvent('trades_search', 'trades', e.target.value.length.toString());
                      trackUserEngagement('search_usage', 'trades');
                    }
                  }}
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
                onChange={(e) => {
                  const newFilter = e.target.value as 'all' | 'open' | 'closed';
                  setStatusFilter(newFilter);
                  trackEvent('trades_filter', 'trades', newFilter);
                  trackUserEngagement('filter_change', `status_${newFilter}`);
                }}
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
                    P&L {showNetProfits ? '(Net)' : '(Gross)'} {sortField === 'pnl' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Risk
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Notes
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredTrades.map((trade) => {
                  const grossPnl = trade.sell_price && trade.buy_price
                    ? (trade.sell_price - trade.buy_price) * trade.shares 
                    : 0;
                  const netPnl = feesConfig ? calculateNetPnL(trade, feesConfig) : grossPnl;
                  const pnl = showNetProfits ? netPnl : grossPnl;
                  
                  return (
                    <tr 
                      key={trade.id} 
                      className="hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => {
                        setSelectedTrade(trade);
                        trackEvent('trade_detail_view', 'trades', trade.ticker);
                        trackUserEngagement('trade_interaction', trade.status);
                      }}
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
                        {(() => {
                          const riskDollars = trade.risk_dollars || (trade.risk && trade.buy_price ? (trade.risk / 100) * trade.buy_price * trade.shares : 0);
                          const riskPercent = trade.risk ? trade.risk.toFixed(2) : '0.00';
                          return riskDollars > 0 
                            ? `${formatCurrency(riskDollars)} (${riskPercent}%)`
                            : 'N/A';
                        })()}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900 max-w-xs truncate">
                        {trade.notes || '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        <div className="flex space-x-2">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingTrade(trade);
                              trackEvent('trade_edit', 'trades', trade.ticker);
                              trackUserEngagement('edit_action', trade.status);
                            }}
                            className="text-blue-600 hover:text-blue-800 transition-colors p-1"
                            title="Edit trade"
                          >
                            <Edit className="h-4 w-4" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeletingTrade(trade);
                              trackEvent('trade_delete_click', 'trades', trade.ticker);
                              trackUserEngagement('delete_action', trade.status);
                            }}
                            className="text-red-600 hover:text-red-800 transition-colors p-1"
                            title="Delete trade"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
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
        feesConfig={feesConfig}
        showNetProfits={showNetProfits}
        onClose={() => setSelectedTrade(null)} 
      />

      {/* Edit Trade Modal */}
      <EditModal 
        trade={editingTrade}
        onClose={() => setEditingTrade(null)}
        onSave={handleSaveTrade}
      />

      {/* Delete Trade Modal */}
      <DeleteTradeModal 
        trade={deletingTrade}
        onClose={() => setDeletingTrade(null)}
        onDelete={handleDeleteTrade}
      />
    </div>
  );
}
