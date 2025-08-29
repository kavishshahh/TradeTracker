'use client';

import { useAuth } from '@/contexts/AuthContext';
import { trackEvent, trackPageView, trackUserEngagement } from '@/lib/analytics';
import { getTrades, updateTrade } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { Trade } from '@/types/trade';
import { Calendar, Edit, Eye, Filter, Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'react-toastify';

interface JournalEntryProps {
  trade: Trade;
  onEdit: (trade: Trade) => void;
}

function JournalEntry({ trade, onEdit }: JournalEntryProps) {
  const pnl = trade.sell_price && trade.buy_price
    ? (trade.sell_price - trade.buy_price) * trade.shares 
    : 0;

  const getPnLStatus = () => {
    if (trade.status === 'open') return 'open';
    return pnl >= 0 ? 'profit' : 'loss';
  };

  const pnlStatus = getPnLStatus();

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 p-6 hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start mb-4">
        <div className="flex items-center space-x-3">
          <div className={`w-3 h-3 rounded-full ${
            pnlStatus === 'profit' ? 'bg-green-500' :
            pnlStatus === 'loss' ? 'bg-red-500' : 'bg-blue-500'
          }`} />
          <div>
            <h3 className="text-lg font-semibold text-gray-900">{trade.ticker}</h3>
            <p className="text-sm text-gray-500">
              {new Date(trade.date).toLocaleDateString('en-US', { 
                weekday: 'long', 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric' 
              })}
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
            trade.status === 'closed' 
              ? 'bg-gray-100 text-gray-800' 
              : 'bg-blue-100 text-blue-800'
          }`}>
            {trade.status}
          </span>
          <button
            onClick={() => onEdit(trade)}
            className="p-1 text-gray-400 hover:text-gray-600"
          >
            <Edit className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
        <div>
          <span className="text-gray-500">Buy Price:</span>
          <div className="font-medium">${trade.buy_price}</div>
        </div>
        {trade.sell_price && (
          <div>
            <span className="text-gray-500">Sell Price:</span>
            <div className="font-medium">${trade.sell_price}</div>
          </div>
        )}
        <div>
          <span className="text-gray-500">Shares:</span>
          <div className="font-medium">{trade.shares}</div>
        </div>
        {trade.status === 'closed' && (
          <div>
            <span className="text-gray-500">P&L:</span>
            <div className={`font-medium ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {formatCurrency(pnl)}
            </div>
          </div>
        )}
      </div>

      {trade.notes && (
        <div className="border-t border-gray-200 pt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">Notes</h4>
          <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">
            {trade.notes}
          </div>
        </div>
      )}

      <div className="mt-4 text-xs text-gray-400">
        Risk: {trade.risk}% | 
        Created: {new Date(trade.created_at || trade.date).toLocaleDateString()}
      </div>
    </div>
  );
}

interface EditModalProps {
  trade: Trade | null;
  onClose: () => void;
  onSave: (updatedTrade: Trade) => void;
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

export default function Journal() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [filteredTrades, setFilteredTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'closed'>('all');
  const [editingTrade, setEditingTrade] = useState<Trade | null>(null);
  const { currentUser } = useAuth();

  useEffect(() => {
    if (!currentUser) return;
    
    const fetchTrades = async () => {
      try {
        const response = await getTrades(currentUser.uid);
        const sortedTrades = response.trades.sort((a, b) => 
          new Date(b.date).getTime() - new Date(a.date).getTime()
        );
        setTrades(sortedTrades);
        setFilteredTrades(sortedTrades);
        // Track journal page view
        trackPageView('/journal');
        trackUserEngagement('journal_view', `trades_${sortedTrades.length}`);
      } catch (error) {
        console.error('Error fetching trades:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchTrades();
  }, [currentUser]);

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

    setFilteredTrades(filtered);
  }, [trades, searchTerm, statusFilter]);

  const handleEditTrade = (trade: Trade) => {
    setEditingTrade(trade);
    trackEvent('journal_edit', 'journal', trade.ticker);
    trackUserEngagement('trade_edit', trade.status);
  };

  const handleSaveTrade = async (updatedTrade: Trade) => {
    // Update local state with the updated trade
    const updatedTrades = trades.map(trade =>
      trade.id === updatedTrade.id ? updatedTrade : trade
    );
    setTrades(updatedTrades);
    
    // Refresh trades from server to ensure consistency
    try {
      const response = await getTrades(currentUser!.uid);
      const sortedTrades = response.trades.sort((a, b) => 
        new Date(b.date).getTime() - new Date(a.date).getTime()
      );
      setTrades(sortedTrades);
    } catch (error) {
      console.error('Error refreshing trades after update:', error);
    }
  };

  const stats = {
    total: trades.length,
    withNotes: trades.filter(trade => trade.notes && trade.notes.trim()).length,
    open: trades.filter(trade => trade.status === 'open').length,
    closed: trades.filter(trade => trade.status === 'closed').length,
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
        <h1 className="text-2xl font-bold text-gray-900">Trading Journal</h1>
        <p className="mt-1 text-sm text-gray-500">
          Review and analyze your trading decisions
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-4">
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Calendar className="h-6 w-6 text-gray-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Total Trades</dt>
                  <dd className="text-lg font-medium text-gray-900">{stats.total}</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Edit className="h-6 w-6 text-blue-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">With Notes</dt>
                  <dd className="text-lg font-medium text-gray-900">
                    {stats.withNotes} ({((stats.withNotes / stats.total) * 100).toFixed(0)}%)
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
                <Eye className="h-6 w-6 text-green-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Closed</dt>
                  <dd className="text-lg font-medium text-gray-900">{stats.closed}</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="h-6 w-6 rounded-full bg-blue-500" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Open</dt>
                  <dd className="text-lg font-medium text-gray-900">{stats.open}</dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-3 sm:space-y-0 sm:space-x-4">
          <div className="flex-1">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search by ticker or notes..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            <Filter className="h-4 w-4 text-gray-400" />
            <select
              value={statusFilter}
              onChange={(e) => {
                const newFilter = e.target.value as 'all' | 'open' | 'closed';
                setStatusFilter(newFilter);
                trackEvent('journal_filter', 'journal', newFilter);
                trackUserEngagement('filter_change', newFilter);
              }}
              className="border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="all">All Trades</option>
              <option value="open">Open Positions</option>
              <option value="closed">Closed Positions</option>
            </select>
          </div>
        </div>
      </div>

      {/* Trade Entries */}
      <div className="space-y-4">
        {filteredTrades.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500">No trades found matching your criteria.</p>
          </div>
        ) : (
          filteredTrades.map((trade) => (
            <JournalEntry
              key={trade.id}
              trade={trade}
              onEdit={handleEditTrade}
            />
          ))
        )}
      </div>

      {/* Edit Modal */}
      <EditModal
        trade={editingTrade}
        onClose={() => setEditingTrade(null)}
        onSave={handleSaveTrade}
      />
    </div>
  );
}
