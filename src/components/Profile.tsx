'use client';

import { useAuth } from '@/contexts/AuthContext';
import { deleteMonthlyBalance, getMonthlyBalances, getUserProfile, saveMonthlyBalance, updateUserProfile } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { Calendar, DollarSign, Edit2, Minus, Plus, Save, Trash2, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';

interface ProfileFormData {
  account_balance: number;
  currency: string;
  risk_tolerance: number;
}

interface FundFlow {
  id: string;
  date: string;
  type: 'deposit' | 'withdrawal';
  amount: number;
  description: string;
}

interface MonthBalance {
  id?: string;
  month: string; // Format: "YYYY-MM"
  start_balance: number;
  end_balance?: number;
  is_manual: boolean; // Whether this month's start balance was manually set
  notes?: string;
  created_at?: string;
  updated_at?: string;
}

export default function Profile() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [loading, setLoading] = useState(true);
  const [fundFlows, setFundFlows] = useState<FundFlow[]>([]);
  const [showFundFlowForm, setShowFundFlowForm] = useState(false);
  const [newFundFlow, setNewFundFlow] = useState<Omit<FundFlow, 'id'>>({
    date: new Date().toISOString().split('T')[0],
    type: 'deposit',
    amount: 0,
    description: ''
  });
  const [monthBalances, setMonthBalances] = useState<MonthBalance[]>([]);
  const [editingMonth, setEditingMonth] = useState<string | null>(null);
  const [editBalance, setEditBalance] = useState<number>(0);
  const [showAddMonthForm, setShowAddMonthForm] = useState(false);
  const [newMonthData, setNewMonthData] = useState({
    month: new Date().toISOString().substring(0, 7), // Current month YYYY-MM
    start_balance: 0,
    notes: ''
  });
  const { currentUser } = useAuth();

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors }
  } = useForm<ProfileFormData>({
    defaultValues: {
      account_balance: 10000,
      currency: 'USD',
      risk_tolerance: 2.0
    }
  });

  const accountBalance = watch('account_balance');
  const riskTolerance = watch('risk_tolerance');

  useEffect(() => {
    if (!currentUser) return;
    
    const fetchData = async () => {
      try {
        const [profileResponse, balancesResponse] = await Promise.all([
          getUserProfile(currentUser.uid),
          getMonthlyBalances(currentUser.uid)
        ]);
        
        reset({
          account_balance: profileResponse.profile.account_balance || 10000,
          currency: profileResponse.profile.currency || 'USD',
          risk_tolerance: profileResponse.profile.risk_tolerance || 2.0
        });
        
        setMonthBalances(balancesResponse.monthly_balances || []);
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [currentUser, reset]);

  // Initialize month balances with default values
  useEffect(() => {
    if (fundFlows.length > 0) {
      calculateMonthBalances();
    }
  }, [fundFlows]);

  // Calculate month balances automatically
  const calculateMonthBalances = () => {
    const balances: MonthBalance[] = [];
    let currentBalance = 10000; // Default starting balance
    
    // Group fund flows by month
    const monthlyFlows = new Map<string, FundFlow[]>();
    
    fundFlows.forEach(flow => {
      const monthKey = flow.date.substring(0, 7); // YYYY-MM
      if (!monthlyFlows.has(monthKey)) {
        monthlyFlows.set(monthKey, []);
      }
      monthlyFlows.get(monthKey)!.push(flow);
    });
    
    // Sort months chronologically
    const sortedMonths = Array.from(monthlyFlows.keys()).sort();
    
    sortedMonths.forEach(month => {
      const monthFlows = monthlyFlows.get(month)!;
      const netFlow = monthFlows.reduce((sum, flow) => {
        return sum + (flow.type === 'deposit' ? flow.amount : -flow.amount);
      }, 0);
      
      const endBalance = currentBalance + netFlow;
      
      // Check if this month already has a manual balance
      const existingBalance = monthBalances.find(b => b.month === month);
      const startBalance = existingBalance?.is_manual ? existingBalance.start_balance : currentBalance;
      
      balances.push({
        month,
        start_balance: startBalance,
        end_balance: endBalance,
        is_manual: existingBalance?.is_manual || false
      });
      
      currentBalance = endBalance;
    });
    
    setMonthBalances(balances);
  };

  // Get current month's start balance
  const getCurrentMonthStartBalance = () => {
    const currentMonth = new Date().toISOString().substring(0, 7);
    const currentMonthBalance = monthBalances.find(b => b.month === currentMonth);
    
    if (currentMonthBalance) {
      return currentMonthBalance.start_balance;
    }
    
    // If no current month, use the last month's end balance or default
    if (monthBalances.length > 0) {
      return monthBalances[monthBalances.length - 1].end_balance || 0;
    }
    
    return 10000; // Default
  };

  // Get current month's net fund flows
  const getCurrentMonthNetFlows = () => {
    const currentMonth = new Date().toISOString().substring(0, 7);
    const currentMonthFlows = fundFlows.filter(flow => 
      flow.date.substring(0, 7) === currentMonth
    );
    
    return currentMonthFlows.reduce((sum, flow) => {
      return sum + (flow.type === 'deposit' ? flow.amount : -flow.amount);
    }, 0);
  };

  // Calculate current account balance
  const currentMonthStartBalance = getCurrentMonthStartBalance();
  const netFundFlows = getCurrentMonthNetFlows();
  const currentAccountBalance = currentMonthStartBalance + netFundFlows;

  // Edit month balance
  const startEditingMonth = (month: string, currentBalance: number) => {
    setEditingMonth(month);
    setEditBalance(currentBalance);
  };

  // Save month balance edit
  const saveMonthBalance = async () => {
    if (editingMonth && editBalance > 0) {
      try {
        await saveMonthlyBalance({
          month: editingMonth,
          start_balance: editBalance,
          is_manual: true
        });
        
        // Update local state
        setMonthBalances(prev => prev.map(balance => 
          balance.month === editingMonth 
            ? { ...balance, start_balance: editBalance, is_manual: true }
            : balance
        ));
        
        setEditingMonth(null);
        setEditBalance(0);
      } catch (error) {
        console.error('Error saving monthly balance:', error);
        alert('Failed to save monthly balance. Please try again.');
      }
    }
  };

  // Cancel month balance edit
  const cancelMonthBalanceEdit = () => {
    setEditingMonth(null);
    setEditBalance(0);
  };

  // Add new month balance
  const addMonthBalance = async () => {
    if (!newMonthData.month || newMonthData.start_balance <= 0) {
      alert('Please enter a valid month and start balance');
      return;
    }

    try {
      await saveMonthlyBalance({
        month: newMonthData.month,
        start_balance: newMonthData.start_balance,
        is_manual: true,
        notes: newMonthData.notes
      });

      // Refresh monthly balances
      const balancesResponse = await getMonthlyBalances(currentUser!.uid);
      setMonthBalances(balancesResponse.monthly_balances || []);

      // Reset form
      setNewMonthData({
        month: new Date().toISOString().substring(0, 7),
        start_balance: 0,
        notes: ''
      });
      setShowAddMonthForm(false);
    } catch (error) {
      console.error('Error adding monthly balance:', error);
      alert('Failed to add monthly balance. Please try again.');
    }
  };

  // Delete month balance
  const handleDeleteMonthBalance = async (balanceId: string) => {
    if (!confirm('Are you sure you want to delete this monthly balance?')) {
      return;
    }

    try {
      await deleteMonthlyBalance(balanceId);
      
      // Update local state
      setMonthBalances(prev => prev.filter(balance => balance.id !== balanceId));
    } catch (error) {
      console.error('Error deleting monthly balance:', error);
      alert('Failed to delete monthly balance. Please try again.');
    }
  };

  const onSubmit = async (data: ProfileFormData) => {
    setIsSubmitting(true);
    setSubmitSuccess(false);

    try {
      await updateUserProfile(currentUser!.uid, data);
      setSubmitSuccess(true);
      setTimeout(() => setSubmitSuccess(false), 3000);
    } catch (error) {
      console.error('Error updating profile:', error);
      alert('Failed to update profile. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Add fund flow
  const addFundFlow = () => {
    if (newFundFlow.amount <= 0 || !newFundFlow.description.trim()) return;
    
    const fundFlow: FundFlow = {
      ...newFundFlow,
      id: Date.now().toString()
    };
    
    setFundFlows(prev => [...prev, fundFlow]);
    setNewFundFlow({
      date: new Date().toISOString().split('T')[0],
      type: 'deposit',
      amount: 0,
      description: ''
    });
    setShowFundFlowForm(false);
  };

  // Remove fund flow
  const removeFundFlow = (id: string) => {
    setFundFlows(prev => prev.filter(flow => flow.id !== id));
  };

  // Calculate risk in dollars based on current values
  const riskInDollars = accountBalance && riskTolerance 
    ? (riskTolerance / 100) * accountBalance 
    : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Profile Settings */}
      <div className="bg-white rounded-lg shadow-lg p-6">
        <div className="mb-6">
          <div className="flex items-center space-x-3">
            <User className="h-8 w-8 text-blue-600" />
            <div>
              <h2 className="text-2xl font-bold text-gray-900">Profile Settings</h2>
              <p className="mt-1 text-sm text-gray-600">
                Manage your account settings and trading preferences
              </p>
            </div>
          </div>
        </div>

        {submitSuccess && (
          <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-md">
            <p className="text-green-800">Profile updated successfully!</p>
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* Current Account Balance */}
          <div>
            <label htmlFor="account_balance" className="block text-sm font-medium text-gray-700">
              Current Account Balance *
            </label>
            <div className="mt-1 relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <DollarSign className="h-5 w-5 text-gray-600" />
              </div>
              <input
                type="number"
                step="0.01"
                {...register('account_balance', {
                  required: 'Account balance is required',
                  min: { value: 0.01, message: 'Account balance must be greater than 0' }
                })}
                placeholder="10000.00"
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
              />
            </div>
            {errors.account_balance && (
              <p className="mt-1 text-sm text-red-600">{errors.account_balance.message}</p>
            )}
          </div>

          {/* Currency */}
          <div>
            <label htmlFor="currency" className="block text-sm font-medium text-gray-700">
              Currency
            </label>
            <div className="mt-1">
              <select
                {...register('currency')}
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
              >
                <option value="USD">USD - US Dollar</option>
                <option value="EUR">EUR - Euro</option>
                <option value="GBP">GBP - British Pound</option>
                <option value="JPY">JPY - Japanese Yen</option>
                <option value="CAD">CAD - Canadian Dollar</option>
                <option value="AUD">AUD - Australian Dollar</option>
              </select>
            </div>
          </div>

          {/* Default Risk Tolerance */}
          <div>
            <label htmlFor="risk_tolerance" className="block text-sm font-medium text-gray-700">
              Default Risk Tolerance (%)
            </label>
            <div className="mt-1">
              <input
                type="number"
                step="0.01"
                {...register('risk_tolerance', {
                  min: { value: 0.01, message: 'Risk tolerance must be at least 0.01%' },
                  max: { value: 100, message: 'Risk tolerance cannot exceed 100%' }
                })}
                placeholder="2.0"
                className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-gray-900 bg-white"
              />
            </div>
            <p className="mt-1 text-xs text-gray-500">
              This will be used as the default risk percentage for new trades
            </p>
            {errors.risk_tolerance && (
              <p className="mt-1 text-sm text-red-600">{errors.risk_tolerance.message}</p>
            )}
          </div>

          {/* Balance Summary */}
          <div className="bg-blue-50 rounded-md p-4">
            <h4 className="text-sm font-medium text-blue-900 mb-3">Balance Summary</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2 text-sm text-blue-800">
                <div className="flex justify-between">
                  <span>Month Start Balance:</span>
                  <span className="font-medium">{formatCurrency(currentMonthStartBalance)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Net Fund Flows:</span>
                  <span className={`font-medium ${netFundFlows >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {netFundFlows >= 0 ? '+' : ''}{formatCurrency(netFundFlows)}
                  </span>
                </div>
                <div className="flex justify-between border-t border-blue-200 pt-2">
                  <span className="font-medium">Current Balance:</span>
                  <span className="font-bold">{formatCurrency(currentAccountBalance)}</span>
                </div>
              </div>
              <div className="space-y-2 text-sm text-blue-800">
                <div className="flex justify-between">
                  <span>Account Balance:</span>
                  <span className="font-medium">{formatCurrency(accountBalance)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Risk Tolerance:</span>
                  <span className="font-medium">{riskTolerance}%</span>
                </div>
                <div className="flex justify-between border-t border-blue-200 pt-2">
                  <span>Risk per Trade:</span>
                  <span className="font-bold">{formatCurrency(riskInDollars)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Submit Button */}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center space-x-2 py-2 px-4 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save className="h-4 w-4" />
              <span>{isSubmitting ? 'Saving...' : 'Save Profile'}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Month Balance Management */}
      <div className="bg-white rounded-lg shadow-lg p-6">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-xl font-bold text-gray-900">Monthly Balance Tracking</h3>
            <p className="mt-1 text-sm text-gray-600">
              Set starting balances for each month. If not set, the system carries forward from the previous month.
            </p>
          </div>
          <button
            onClick={() => setShowAddMonthForm(!showAddMonthForm)}
            className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
            type="button"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Month
          </button>
        </div>

        {showAddMonthForm && (
          <div className="mb-6 p-4 border border-gray-200 rounded-lg">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <input
                type="month"
                value={newMonthData.month}
                onChange={(e) => setNewMonthData(prev => ({ ...prev, month: e.target.value }))}
                className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="number"
                step="0.01"
                placeholder="Start Balance"
                value={newMonthData.start_balance || ''}
                onChange={(e) => setNewMonthData(prev => ({ ...prev, start_balance: parseFloat(e.target.value) || 0 }))}
                className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="text"
                placeholder="Notes (optional)"
                value={newMonthData.notes}
                onChange={(e) => setNewMonthData(prev => ({ ...prev, notes: e.target.value }))}
                className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="mt-3 flex space-x-2">
              <button
                onClick={addMonthBalance}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                type="button"
              >
                Add Month
              </button>
              <button
                onClick={() => setShowAddMonthForm(false)}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-500"
                type="button"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {monthBalances.length > 0 ? (
          <div className="space-y-3">
            {monthBalances.map((balance) => (
              <div key={balance.month} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center space-x-3">
                  <Calendar className="h-4 w-4 text-gray-500" />
                  <div>
                    <span className="text-sm font-medium text-gray-900">
                      {new Date(balance.month + '-01').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
                    </span>
                    {balance.notes && (
                      <div className="text-xs text-gray-500 mt-1">{balance.notes}</div>
                    )}
                  </div>
                  {balance.is_manual && (
                    <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">
                      Manual
                    </span>
                  )}
                </div>
                <div className="flex items-center space-x-4">
                  <div className="text-right">
                    <div className="text-sm text-gray-500">Start: {formatCurrency(balance.start_balance)}</div>
                    {balance.end_balance && (
                      <div className="text-sm font-medium text-gray-900">End: {formatCurrency(balance.end_balance)}</div>
                    )}
                  </div>
                  <div className="flex space-x-1">
                    <button
                      onClick={() => startEditingMonth(balance.month, balance.start_balance)}
                      className="p-1 text-gray-400 hover:text-gray-600"
                      type="button"
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                    {balance.id && (
                      <button
                        onClick={() => handleDeleteMonthBalance(balance.id!)}
                        className="p-1 text-red-400 hover:text-red-600"
                        type="button"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <p>No monthly balances set yet.</p>
            <p className="text-sm">Add monthly starting balances to track your account growth over time.</p>
          </div>
        )}

        {/* Month Balance Edit Modal */}
        {editingMonth && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
              <h3 className="text-lg font-semibold mb-4">
                Edit {new Date(editingMonth + '-01').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })} Start Balance
              </h3>
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Start Balance
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={editBalance}
                  onChange={(e) => setEditBalance(parseFloat(e.target.value) || 0)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="flex space-x-3">
                <button
                  onClick={saveMonthBalance}
                  className="flex-1 py-2 px-4 bg-blue-600 text-white rounded-md hover:bg-blue-700"
                  type="button"
                >
                  Save
                </button>
                <button
                  onClick={cancelMonthBalanceEdit}
                  className="flex-1 py-2 px-4 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400"
                  type="button"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Fund Flows Management */}
      <div className="bg-white rounded-lg shadow-lg p-6">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-xl font-bold text-gray-900">Fund Flows Management</h3>
            <p className="mt-1 text-sm text-gray-600">
              Track deposits and withdrawals for accurate equity curve calculation
            </p>
          </div>
          <button
            onClick={() => setShowFundFlowForm(!showFundFlowForm)}
            className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
            type="button"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Fund Flow
          </button>
        </div>

        {showFundFlowForm && (
          <div className="mb-6 p-4 border border-gray-200 rounded-lg">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <input
                type="date"
                value={newFundFlow.date}
                onChange={(e) => setNewFundFlow(prev => ({ ...prev, date: e.target.value }))}
                className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <select
                value={newFundFlow.type}
                onChange={(e) => setNewFundFlow(prev => ({ ...prev, type: e.target.value as 'deposit' | 'withdrawal' }))}
                className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="deposit">Deposit</option>
                <option value="withdrawal">Withdrawal</option>
              </select>
              <input
                type="number"
                step="0.01"
                placeholder="Amount"
                value={newFundFlow.amount || ''}
                onChange={(e) => setNewFundFlow(prev => ({ ...prev, amount: parseFloat(e.target.value) || 0 }))}
                className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="text"
                placeholder="Description"
                value={newFundFlow.description}
                onChange={(e) => setNewFundFlow(prev => ({ ...prev, description: e.target.value }))}
                className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="mt-3 flex space-x-2">
              <button
                onClick={addFundFlow}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                type="button"
              >
                Add
              </button>
              <button
                onClick={() => setShowFundFlowForm(false)}
                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-500"
                type="button"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {fundFlows.length > 0 ? (
          <div className="space-y-2">
            {fundFlows.map((flow) => (
              <div key={flow.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center space-x-3">
                  <span className={`p-1 rounded-full ${flow.type === 'deposit' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                    {flow.type === 'deposit' ? <Plus className="h-4 w-4" /> : <Minus className="h-4 w-4" />}
                  </span>
                  <span className="text-sm text-gray-600">{flow.date}</span>
                  <span className="text-sm font-medium text-gray-900">{flow.description}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className={`text-sm font-medium ${flow.type === 'deposit' ? 'text-green-600' : 'text-red-600'}`}>
                    {flow.type === 'deposit' ? '+' : '-'}{formatCurrency(flow.amount)}
                  </span>
                  <button
                    onClick={() => removeFundFlow(flow.id)}
                    className="text-red-500 hover:text-red-700"
                    type="button"
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <p>No fund flows recorded yet.</p>
            <p className="text-sm">Add deposits and withdrawals to track your account balance changes.</p>
          </div>
        )}
      </div>

      {/* Info Section */}
      <div className="bg-white rounded-lg shadow-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">How This Works</h3>
        <div className="space-y-3 text-sm text-gray-600">
          <div className="flex items-start space-x-3">
            <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
            <p>
              <strong>Automatic Month Balances:</strong> Month start balances automatically continue from the previous month's ending balance. No need to manually set them each month.
            </p>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
            <p>
              <strong>Manual Adjustments:</strong> You can manually adjust past month start balances if needed (e.g., if you had external account changes not captured in fund flows).
            </p>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
            <p>
              <strong>Fund Flows:</strong> Track all deposits and withdrawals throughout each month. These automatically update your month ending balances.
            </p>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
            <p>
              <strong>Current Balance:</strong> Automatically calculated as Month Start Balance + Net Fund Flows for the current month.
            </p>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
            <p>
              <strong>Risk Tolerance:</strong> Your default risk percentage per trade. When adding trades, if you provide risk percentage, we'll calculate the dollar amount automatically.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
