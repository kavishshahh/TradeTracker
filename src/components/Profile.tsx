'use client';

import { useAuth } from '@/contexts/AuthContext';
import { getUserProfile, updateUserProfile } from '@/lib/api';
import { formatCurrency } from '@/lib/utils';
import { DollarSign, Save, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';

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
      } finally {
        setLoading(false);
      }
    };

    fetchProfile();
  }, [currentUser, reset]);

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
    <div className="max-w-2xl mx-auto">
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
          {/* Account Balance */}
          <div>
            <label htmlFor="account_balance" className="block text-sm font-medium text-gray-700">
              Account Balance *
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

          {/* Risk Calculation Preview */}
          {accountBalance && riskTolerance && (
            <div className="bg-blue-50 rounded-md p-4">
              <h4 className="text-sm font-medium text-blue-900 mb-2">Risk Calculation Preview</h4>
              <div className="space-y-1 text-sm text-blue-800">
                <div className="flex justify-between">
                  <span>Account Balance:</span>
                  <span className="font-medium">{formatCurrency(accountBalance)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Risk Tolerance:</span>
                  <span className="font-medium">{riskTolerance}%</span>
                </div>
                <div className="flex justify-between border-t border-blue-200 pt-1">
                  <span>Risk per Trade:</span>
                  <span className="font-bold">{formatCurrency(riskInDollars)}</span>
                </div>
              </div>
            </div>
          )}

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

        {/* Info Section */}
        <div className="mt-8 border-t pt-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">How This Works</h3>
          <div className="space-y-3 text-sm text-gray-600">
            <div className="flex items-start space-x-3">
              <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
              <p>
                <strong>Account Balance:</strong> Your total trading account size. This is used to calculate risk in dollars when you enter risk as a percentage.
              </p>
            </div>
            <div className="flex items-start space-x-3">
              <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
              <p>
                <strong>Risk Tolerance:</strong> Your default risk percentage per trade. You can override this when adding individual trades.
              </p>
            </div>
            <div className="flex items-start space-x-3">
              <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
              <p>
                <strong>Automatic Calculation:</strong> When adding trades, if you provide risk percentage, we'll calculate the dollar amount automatically using your account balance.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
