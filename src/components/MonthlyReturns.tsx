'use client';

import { useAuth } from '@/contexts/AuthContext';
import { deleteMonthlyReturn, getMonthlyReturns, saveMonthlyReturn } from '@/lib/api';
import { Calendar, DollarSign, Edit, Plus, Trash2, TrendingDown, TrendingUp } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

interface MonthlyReturn {
  id?: string;
  month: string;
  start_cap: number;
  close_cap?: number;
  percentage_return?: number;
  dollar_return?: number;
  inr_return?: number;
  comments?: string;
}

export default function MonthlyReturns() {
  const [monthlyData, setMonthlyData] = useState<MonthlyReturn[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingReturn, setEditingReturn] = useState<MonthlyReturn | null>(null);
  const [totalReturn, setTotalReturn] = useState({
    totalPercentage: 0,
    totalDollar: 0,
    totalINR: 0
  });
  const { currentUser } = useAuth();

  const fetchMonthlyReturns = async () => {
    if (!currentUser) return;
    
    try {
      setLoading(true);
      const response = await getMonthlyReturns(currentUser.uid);
      const returns = response.monthly_returns;
      setMonthlyData(returns);
      
      // Calculate totals
      const totalDollar = returns.reduce((sum, item) => sum + (item.dollar_return || 0), 0);
      const totalINR = returns.reduce((sum, item) => sum + (item.inr_return || 0), 0);
      
      // Calculate overall percentage (simple average for now)
      const returnsWithPercentage = returns.filter(item => item.percentage_return !== undefined);
      const totalPercentage = returnsWithPercentage.length > 0 
        ? returnsWithPercentage.reduce((sum, item) => sum + (item.percentage_return || 0), 0) / returnsWithPercentage.length
        : 0;

      setTotalReturn({
        totalPercentage,
        totalDollar,
        totalINR
      });
    } catch (error) {
      console.error('Error fetching monthly returns:', error);
      toast.error('Failed to fetch monthly returns');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMonthlyReturns();
  }, [currentUser]);

  const formatCurrency = (amount: number, currency: 'USD' | 'INR') => {
    const symbol = currency === 'USD' ? '$' : '₹';
    return `${symbol}${Math.abs(amount).toLocaleString('en-US', { 
      minimumFractionDigits: 2, 
      maximumFractionDigits: 2 
    })}`;
  };

  const getReturnColor = (value: number) => {
    if (value > 0) return 'text-green-600';
    if (value < 0) return 'text-red-600';
    return 'text-gray-600';
  };

  const getReturnIcon = (value: number) => {
    if (value > 0) return <TrendingUp className="h-4 w-4" />;
    if (value < 0) return <TrendingDown className="h-4 w-4" />;
    return null;
  };

  const handleAddReturn = () => {
    setEditingReturn(null);
    setShowForm(true);
  };

  const handleEditReturn = (returnData: MonthlyReturn) => {
    setEditingReturn(returnData);
    setShowForm(true);
  };

  const handleDeleteReturn = async (returnData: MonthlyReturn) => {
    if (!returnData.id) return;
    
    if (!confirm(`Are you sure you want to delete the ${returnData.month} return?`)) {
      return;
    }
    
    try {
      await deleteMonthlyReturn(returnData.id);
      toast.success('Monthly return deleted successfully');
      fetchMonthlyReturns();
    } catch (error) {
      console.error('Error deleting monthly return:', error);
      toast.error('Failed to delete monthly return');
    }
  };

  const handleSaveReturn = async (returnData: MonthlyReturn) => {
    try {
      await saveMonthlyReturn(returnData);
      toast.success('Monthly return saved successfully');
      setShowForm(false);
      setEditingReturn(null);
      fetchMonthlyReturns();
    } catch (error) {
      console.error('Error saving monthly return:', error);
      toast.error('Failed to save monthly return');
    }
  };

  // Prepare chart data
  const chartData = monthlyData
    .filter(item => item.percentage_return !== undefined)
    .map(item => ({
      month: item.month.split(' ')[0], // Get just the month name
      return: item.percentage_return || 0,
      year: item.month.split(' ')[1] || '',
    }));

  const getBarColor = (value: number) => {
    return value >= 0 ? '#10b981' : '#ef4444'; // Green for positive, red for negative
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center">
              <Calendar className="h-6 w-6 mr-2 text-blue-500" />
              Monthly Returns
            </h1>
            <p className="text-gray-600 mt-1">Track your month-wise portfolio performance</p>
          </div>
          <button
            onClick={handleAddReturn}
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Month
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total Return %</p>
              <p className={`text-2xl font-bold ${getReturnColor(totalReturn.totalPercentage)}`}>
                {totalReturn.totalPercentage.toFixed(2)}%
              </p>
            </div>
            <div className={`p-3 rounded-full ${totalReturn.totalPercentage >= 0 ? 'bg-green-100' : 'bg-red-100'}`}>
              {getReturnIcon(totalReturn.totalPercentage)}
            </div>
          </div>
        </div>
        
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total USD Return</p>
              <p className={`text-2xl font-bold ${getReturnColor(totalReturn.totalDollar)}`}>
                {totalReturn.totalDollar >= 0 ? '+' : '-'}{formatCurrency(totalReturn.totalDollar, 'USD')}
              </p>
            </div>
            <div className={`p-3 rounded-full ${totalReturn.totalDollar >= 0 ? 'bg-green-100' : 'bg-red-100'}`}>
              <DollarSign className="h-4 w-4" />
            </div>
          </div>
        </div>
        
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total INR Return</p>
              <p className={`text-2xl font-bold ${getReturnColor(totalReturn.totalINR)}`}>
                {totalReturn.totalINR >= 0 ? '+' : '-'}{formatCurrency(totalReturn.totalINR, 'INR')}
              </p>
            </div>
            <div className={`p-3 rounded-full ${totalReturn.totalINR >= 0 ? 'bg-green-100' : 'bg-red-100'}`}>
              <DollarSign className="h-4 w-4" />
            </div>
          </div>
        </div>
      </div>

      {/* Bar Chart */}
      {chartData.length > 0 && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Monthly Returns Chart</h2>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="month" 
                  tick={{ fontSize: 12 }}
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis 
                  tick={{ fontSize: 12 }}
                  label={{ value: 'Return %', angle: -90, position: 'insideLeft' }}
                />
                <Tooltip 
                  formatter={(value: number) => [`${value.toFixed(2)}%`, 'Return']}
                  labelFormatter={(label) => `${label} ${chartData.find(d => d.month === label)?.year || ''}`}
                />
                <Bar dataKey="return" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={getBarColor(entry.return)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Monthly Returns Table */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Monthly Performance</h2>
        </div>
        
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Month
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Start Capital
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Close Capital
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Return %
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  USD Return
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  INR Return
                </th>
                                 <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                   Comments
                 </th>
                 <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                   Actions
                 </th>
               </tr>
             </thead>
             <tbody className="bg-white divide-y divide-gray-200">
               {monthlyData.map((row, index) => (
                 <tr key={row.id || index} className="hover:bg-gray-50">
                   <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                     {row.month}
                   </td>
                   <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                     {formatCurrency(row.start_cap, 'USD')}
                   </td>
                   <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                     {row.close_cap ? formatCurrency(row.close_cap, 'USD') : '-'}
                   </td>
                   <td className="px-6 py-4 whitespace-nowrap text-sm">
                     {row.percentage_return !== undefined ? (
                       <div className={`flex items-center ${getReturnColor(row.percentage_return)}`}>
                         {getReturnIcon(row.percentage_return)}
                         <span className="ml-1 font-semibold">
                           {row.percentage_return >= 0 ? '+' : ''}{row.percentage_return.toFixed(2)}%
                         </span>
                       </div>
                     ) : '-'}
                   </td>
                   <td className="px-6 py-4 whitespace-nowrap text-sm">
                     {row.dollar_return !== undefined ? (
                       <span className={`font-semibold ${getReturnColor(row.dollar_return)}`}>
                         {row.dollar_return >= 0 ? '+' : '-'}{formatCurrency(row.dollar_return, 'USD')}
                       </span>
                     ) : '-'}
                   </td>
                   <td className="px-6 py-4 whitespace-nowrap text-sm">
                     {row.inr_return !== undefined ? (
                       <span className={`font-semibold ${getReturnColor(row.inr_return)}`}>
                         {row.inr_return >= 0 ? '+' : '-'}{formatCurrency(row.inr_return, 'INR')}
                       </span>
                     ) : '-'}
                   </td>
                   <td className="px-6 py-4 text-sm text-gray-600 max-w-xs">
                     {row.comments && (
                       <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">
                         {row.comments}
                       </span>
                     )}
                   </td>
                   <td className="px-6 py-4 whitespace-nowrap text-sm">
                     <div className="flex items-center space-x-2">
                       <button
                         onClick={() => handleEditReturn(row)}
                         className="text-blue-600 hover:text-blue-900 transition-colors"
                         title="Edit"
                       >
                         <Edit className="h-4 w-4" />
                       </button>
                       <button
                         onClick={() => handleDeleteReturn(row)}
                         className="text-red-600 hover:text-red-900 transition-colors"
                         title="Delete"
                       >
                         <Trash2 className="h-4 w-4" />
                       </button>
                     </div>
                   </td>
                 </tr>
               ))}
             </tbody>
          </table>
        </div>
      </div>

      {/* Add/Edit Form Modal */}
      {showForm && (
        <MonthlyReturnForm
          returnData={editingReturn}
          onSave={handleSaveReturn}
          onCancel={() => {
            setShowForm(false);
            setEditingReturn(null);
          }}
        />
      )}
    </div>
  );
}

// Form component for adding/editing monthly returns
interface MonthlyReturnFormProps {
  returnData: MonthlyReturn | null;
  onSave: (data: MonthlyReturn) => void;
  onCancel: () => void;
}

function MonthlyReturnForm({ returnData, onSave, onCancel }: MonthlyReturnFormProps) {
  const [formData, setFormData] = useState<MonthlyReturn>({
    month: returnData?.month || '',
    start_cap: returnData?.start_cap || 0,
    close_cap: returnData?.close_cap || undefined,
    percentage_return: returnData?.percentage_return || undefined,
    dollar_return: returnData?.dollar_return || undefined,
    inr_return: returnData?.inr_return || undefined,
    comments: returnData?.comments || '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(formData);
  };

  const handleChange = (field: keyof MonthlyReturn, value: string | number) => {
    // Convert string values to appropriate types for number fields
    let processedValue: any = value;
    
    if (field === 'start_cap') {
      processedValue = typeof value === 'string' ? Number(value) : value;
    } else if (field === 'close_cap' || field === 'inr_return') {
      processedValue = value === '' ? undefined : (typeof value === 'string' ? Number(value) : value);
    }
    
    const updatedData = { ...formData, [field]: processedValue };
    
    // Auto-calculate percentage and dollar return if both start_cap and close_cap are provided
    if (field === 'close_cap' || field === 'start_cap') {
      const startCap = field === 'start_cap' ? Number(value) : updatedData.start_cap;
      const closeCap = field === 'close_cap' ? (value ? Number(value) : undefined) : updatedData.close_cap;
      
      if (startCap && closeCap && startCap > 0) {
        updatedData.percentage_return = ((closeCap - startCap) / startCap) * 100;
        updatedData.dollar_return = closeCap - startCap;
      }
    }
    
    setFormData(updatedData);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900">
            {returnData ? 'Edit Monthly Return' : 'Add Monthly Return'}
          </h3>
        </div>
        
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Month *
            </label>
            <input
              type="text"
              value={formData.month}
              onChange={(e) => handleChange('month', e.target.value)}
              placeholder="e.g., December 2024"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Start Capital (USD) *
            </label>
            <input
              type="number"
              step="0.01"
              value={formData.start_cap}
              onChange={(e) => handleChange('start_cap', Number(e.target.value))}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Close Capital (USD)
            </label>
            <input
              type="number"
              step="0.01"
              value={formData.close_cap || ''}
              onChange={(e) => handleChange('close_cap', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              INR Return
            </label>
            <input
              type="number"
              step="0.01"
              value={formData.inr_return || ''}
              onChange={(e) => handleChange('inr_return', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Comments
            </label>
            <textarea
              value={formData.comments}
              onChange={(e) => handleChange('comments', e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Any additional notes..."
            />
          </div>
          
          {/* Show calculated values */}
          {formData.percentage_return !== undefined && (
            <div className="text-sm text-gray-600">
              <p>Calculated Return: {formData.percentage_return.toFixed(2)}%</p>
              <p>Dollar Return: ${formData.dollar_return?.toFixed(2)}</p>
            </div>
          )}
          
          <div className="flex justify-end space-x-3 pt-4">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              {returnData ? 'Update' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
