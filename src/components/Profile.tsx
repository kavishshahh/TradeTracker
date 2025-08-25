'use client';

import { useAuth } from '@/contexts/AuthContext';
import { getUserProfile, updateUserProfile } from '@/lib/api';
import { DollarSign, Save, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'react-toastify';

interface ProfileFormData {
  account_balance: number;
  currency: string;
  risk_tolerance: number;
}

export default function Profile() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [loading, setLoading] = useState(true);
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
    
    const fetchProfile = async () => {
      try {
        const response = await getUserProfile(currentUser.uid);
        reset({
          account_balance: response.profile.account_balance || 10000,
          currency: response.profile.currency || 'USD',
          risk_tolerance: response.profile.risk_tolerance || 2.0
        });
      } catch (error) {
        console.error('Error fetching profile:', error);
        toast.error('Failed to load profile data');
      } finally {
        setLoading(false);
      }
    };

    fetchProfile();
  }, [currentUser, reset]);

  const onSubmit = async (data: ProfileFormData) => {
    if (!currentUser) return;

    try {
      setIsSubmitting(true);
      setSubmitSuccess(false);
      
      await updateUserProfile(currentUser.uid, data);
      
      setSubmitSuccess(true);
      toast.success('Profile updated successfully!');
      
      // Reset success state after 3 seconds
      setTimeout(() => setSubmitSuccess(false), 3000);
    } catch (error) {
      console.error('Error updating profile:', error);
      toast.error('Failed to update profile. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Calculate position size based on risk
  const calculatePositionSize = () => {
    if (!accountBalance || !riskTolerance) return 0;
    return (accountBalance * riskTolerance) / 100;
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
        <div className="flex items-center">
          <User className="h-6 w-6 mr-2 text-blue-500" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Profile Settings</h1>
            <p className="text-gray-600 mt-1">Manage your account settings and trading preferences</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Account Settings Form */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Account Settings</h2>
          
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label htmlFor="account_balance" className="block text-sm font-medium text-gray-700 mb-1">
                Account Balance (USD) *
              </label>
              <div className="relative">
                <DollarSign className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  id="account_balance"
                  type="number"
                  step="0.01"
                  {...register('account_balance', {
                    required: 'Account balance is required',
                    min: { value: 0.01, message: 'Account balance must be greater than 0' }
                  })}
                  className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="Enter your account balance"
                />
              </div>
              {errors.account_balance && (
                <p className="mt-1 text-sm text-red-600">{errors.account_balance.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="currency" className="block text-sm font-medium text-gray-700 mb-1">
                Currency
              </label>
              <select
                id="currency"
                {...register('currency')}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="USD">USD - US Dollar</option>
                <option value="EUR">EUR - Euro</option>
                <option value="GBP">GBP - British Pound</option>
                <option value="INR">INR - Indian Rupee</option>
              </select>
            </div>

            <div>
              <label htmlFor="risk_tolerance" className="block text-sm font-medium text-gray-700 mb-1">
                Risk Tolerance (% per trade) *
              </label>
              <input
                id="risk_tolerance"
                type="number"
                step="0.1"
                min="0.1"
                max="10"
                {...register('risk_tolerance', {
                  required: 'Risk tolerance is required',
                  min: { value: 0.1, message: 'Risk tolerance must be at least 0.1%' },
                  max: { value: 10, message: 'Risk tolerance cannot exceed 10%' }
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="2.0"
              />
              {errors.risk_tolerance && (
                <p className="mt-1 text-sm text-red-600">{errors.risk_tolerance.message}</p>
              )}
              <p className="mt-1 text-sm text-gray-500">
                Recommended: 1-3% per trade for conservative approach
              </p>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className={`w-full flex items-center justify-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white transition-colors ${
                isSubmitting
                  ? 'bg-gray-400 cursor-not-allowed'
                  : submitSuccess
                  ? 'bg-green-600 hover:bg-green-700'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {isSubmitting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Saving...
                </>
              ) : submitSuccess ? (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  Saved!
                </>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  Save Changes
                </>
              )}
            </button>
          </form>
        </div>

        {/* Risk Calculator */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Risk Calculator</h2>
          
          <div className="space-y-4">
            <div className="bg-blue-50 rounded-lg p-4">
              <h3 className="text-sm font-medium text-blue-900 mb-2">Position Size per Trade</h3>
              <p className="text-2xl font-bold text-blue-600">
                ${calculatePositionSize().toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
              <p className="text-sm text-blue-700 mt-1">
                Based on {riskTolerance}% risk tolerance
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-600 uppercase tracking-wide">Account Balance</p>
                <p className="text-lg font-semibold text-gray-900">
                  ${accountBalance?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
                </p>
              </div>
              
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-600 uppercase tracking-wide">Risk per Trade</p>
                <p className="text-lg font-semibold text-gray-900">{riskTolerance}%</p>
              </div>
            </div>

            <div className="border-t pt-4">
              <h4 className="text-sm font-medium text-gray-900 mb-2">Risk Management Tips</h4>
              <ul className="text-sm text-gray-600 space-y-1">
                <li>• Never risk more than 1-3% of your account per trade</li>
                <li>• Use stop-losses to limit downside risk</li>
                <li>• Diversify across different stocks/sectors</li>
                <li>• Review and adjust risk tolerance regularly</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* User Info */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Account Information</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-600">Email Address</p>
            <p className="text-gray-900 font-medium">{currentUser?.email}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">User ID</p>
            <p className="text-gray-900 font-medium font-mono text-sm">{currentUser?.uid}</p>
          </div>
        </div>
        
        <div className="mt-4 p-4 bg-blue-50 rounded-lg">
          <p className="text-sm text-blue-800">
            💡 <strong>Tip:</strong> For monthly performance tracking, use the <strong>Monthly Returns</strong> tab to add your month-wise portfolio data including start/end capital, returns, and notes.
          </p>
        </div>
      </div>
    </div>
  );
}