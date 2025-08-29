'use client';

import { useAuth } from '@/contexts/AuthContext';
import { trackEvent, trackFormSubmission, trackPageView } from '@/lib/analytics';
import { getFeesConfig, getUserProfile, saveFeesConfig, updateUserProfile } from '@/lib/api';
import { FeesConfig } from '@/types/trade';
import { Calculator, DollarSign, Save, Settings, User } from 'lucide-react';
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
  const [activeTab, setActiveTab] = useState<'profile' | 'fees'>('profile');
  const [feesConfig, setFeesConfig] = useState<FeesConfig | null>(null);
  const [isFeesSubmitting, setIsFeesSubmitting] = useState(false);
  const [feesSubmitSuccess, setFeesSubmitSuccess] = useState(false);
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
        const [profileResponse, feesResponse] = await Promise.all([
          getUserProfile(currentUser.uid),
          getFeesConfig(currentUser.uid).catch(() => ({ fees_config: getDefaultFeesConfig() }))
        ]);
        
        reset({
          account_balance: profileResponse.profile.account_balance || 10000,
          currency: profileResponse.profile.currency || 'USD',
          risk_tolerance: profileResponse.profile.risk_tolerance || 2.0
        });
        
        setFeesConfig(feesResponse.fees_config);
        // Track profile page view
        trackPageView('/profile');
      } catch (error) {
        console.error('Error fetching profile:', error);
        toast.error('Failed to load profile data');
      } finally {
        setLoading(false);
      }
    };

    fetchProfile();
  }, [currentUser, reset]);

  // Default fees configuration based on your broker info
  const getDefaultFeesConfig = (): FeesConfig => ({
    brokerage_percentage: 0.25, // 0.25% per transaction
    brokerage_max_usd: 25, // Max $25 excl GST
    exchange_transaction_charges_percentage: 0.12, // 0.12% exchange charges
    ifsca_turnover_fees_percentage: 0.0001, // 0.0001% IFSCA fees
    platform_fee_usd: 0, // Zero platform fee as mentioned
    withdrawal_fee_usd: 0, // Zero withdrawal fee
    amc_yearly_usd: 0, // Zero AMC
    account_opening_fee_usd: 0, // Zero account opening fee
    tracking_charges_usd: 0, // Zero tracking charges
    profile_verification_fee_usd: 0, // Zero KYC fee
  });

  const onSubmit = async (data: ProfileFormData) => {
    if (!currentUser) return;

    try {
      setIsSubmitting(true);
      setSubmitSuccess(false);
      
      await updateUserProfile(currentUser.uid, data);
      
      setSubmitSuccess(true);
      toast.success('Profile updated successfully!');
      
      // Track successful profile update
      trackFormSubmission('profile_form', true);
      trackEvent('profile_update', 'profile', 'success');
      
      // Reset success state after 3 seconds
      setTimeout(() => setSubmitSuccess(false), 3000);
    } catch (error) {
      console.error('Error updating profile:', error);
      toast.error('Failed to update profile. Please try again.');
      // Track failed profile update
      trackFormSubmission('profile_form', false);
      trackEvent('profile_update', 'profile', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Calculate position size based on risk
  const calculatePositionSize = () => {
    if (!accountBalance || !riskTolerance) return 0;
    return (accountBalance * riskTolerance) / 100;
  };

  // Handle fees configuration save
  const handleFeesSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentUser || !feesConfig) return;

    try {
      setIsFeesSubmitting(true);
      setFeesSubmitSuccess(false);
      
      await saveFeesConfig(feesConfig);
      
      setFeesSubmitSuccess(true);
      toast.success('Fees configuration updated successfully!');
      
      // Reset success state after 3 seconds
      setTimeout(() => setFeesSubmitSuccess(false), 3000);
    } catch (error) {
      console.error('Error updating fees config:', error);
      toast.error('Failed to update fees configuration. Please try again.');
    } finally {
      setIsFeesSubmitting(false);
    }
  };

  // Handle fees config field changes
  const handleFeesChange = (field: keyof FeesConfig, value: number) => {
    if (!feesConfig) return;
    setFeesConfig({ ...feesConfig, [field]: value });
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

      {/* Tabs */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <div className="border-b border-gray-200">
          <nav className="-mb-px flex">
            <button
              onClick={() => setActiveTab('profile')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'profile'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <User className="h-4 w-4 mr-2 inline" />
              Account Settings
            </button>
            <button
              onClick={() => setActiveTab('fees')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'fees'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <Calculator className="h-4 w-4 mr-2 inline" />
              Fees Configuration
            </button>
          </nav>
        </div>

        <div className="p-6">
          {activeTab === 'profile' ? (
            <ProfileTabContent 
              register={register}
              handleSubmit={handleSubmit}
              onSubmit={onSubmit}
              errors={errors}
              isSubmitting={isSubmitting}
              submitSuccess={submitSuccess}
              accountBalance={accountBalance}
              riskTolerance={riskTolerance}
              calculatePositionSize={calculatePositionSize}
            />
          ) : (
            <FeesTabContent 
              feesConfig={feesConfig}
              handleFeesSubmit={handleFeesSubmit}
              handleFeesChange={handleFeesChange}
              isFeesSubmitting={isFeesSubmitting}
              feesSubmitSuccess={feesSubmitSuccess}
              getDefaultFeesConfig={getDefaultFeesConfig}
            />
          )}
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

// Profile Tab Component
interface ProfileTabContentProps {
  register: any;
  handleSubmit: any;
  onSubmit: any;
  errors: any;
  isSubmitting: boolean;
  submitSuccess: boolean;
  accountBalance: number;
  riskTolerance: number;
  calculatePositionSize: () => number;
}

function ProfileTabContent({ 
  register, 
  handleSubmit, 
  onSubmit, 
  errors, 
  isSubmitting, 
  submitSuccess, 
  accountBalance, 
  riskTolerance, 
  calculatePositionSize 
}: ProfileTabContentProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Account Settings Form */}
      <div>
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
      <div>
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
  );
}

// Fees Tab Component
interface FeesTabContentProps {
  feesConfig: FeesConfig | null;
  handleFeesSubmit: (e: React.FormEvent) => void;
  handleFeesChange: (field: keyof FeesConfig, value: number) => void;
  isFeesSubmitting: boolean;
  feesSubmitSuccess: boolean;
  getDefaultFeesConfig: () => FeesConfig;
}

function FeesTabContent({ 
  feesConfig, 
  handleFeesSubmit, 
  handleFeesChange, 
  isFeesSubmitting, 
  feesSubmitSuccess,
  getDefaultFeesConfig 
}: FeesTabContentProps) {
  if (!feesConfig) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
        <p className="mt-2 text-gray-500">Loading fees configuration...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Trading Fees Configuration</h2>
        <p className="text-sm text-gray-600">
          Configure your broker's fee structure to get accurate P&L calculations. Default values are based on typical US stock trading fees.
        </p>
      </div>

      <form onSubmit={handleFeesSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Brokerage Fees */}
          <div className="space-y-4">
            <h3 className="text-md font-medium text-gray-900 border-b pb-2">Brokerage Fees</h3>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Brokerage (% per transaction)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="5"
                value={feesConfig.brokerage_percentage}
                onChange={(e) => handleFeesChange('brokerage_percentage', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0.25"
              />
              <p className="mt-1 text-xs text-gray-500">Percentage charged per transaction</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Maximum Brokerage (USD)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.brokerage_max_usd}
                onChange={(e) => handleFeesChange('brokerage_max_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="25"
              />
              <p className="mt-1 text-xs text-gray-500">Maximum brokerage fee cap</p>
            </div>
          </div>

          {/* Exchange & Regulatory Fees */}
          <div className="space-y-4">
            <h3 className="text-md font-medium text-gray-900 border-b pb-2">Exchange & Regulatory Fees</h3>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Exchange Transaction Charges (%)
              </label>
              <input
                type="number"
                step="0.001"
                min="0"
                value={feesConfig.exchange_transaction_charges_percentage}
                onChange={(e) => handleFeesChange('exchange_transaction_charges_percentage', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0.12"
              />
              <p className="mt-1 text-xs text-gray-500">Exchange charges per transaction</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                IFSCA Turnover Fees (%)
              </label>
              <input
                type="number"
                step="0.0001"
                min="0"
                value={feesConfig.ifsca_turnover_fees_percentage}
                onChange={(e) => handleFeesChange('ifsca_turnover_fees_percentage', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0.0001"
              />
              <p className="mt-1 text-xs text-gray-500">IFSCA regulatory fees</p>
            </div>
          </div>

          {/* Platform & Other Fees */}
          <div className="space-y-4">
            <h3 className="text-md font-medium text-gray-900 border-b pb-2">Platform Fees</h3>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Platform Fee per Transaction (USD)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.platform_fee_usd}
                onChange={(e) => handleFeesChange('platform_fee_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0"
              />
              <p className="mt-1 text-xs text-gray-500">Fixed fee per trade</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Withdrawal Fee (USD)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.withdrawal_fee_usd}
                onChange={(e) => handleFeesChange('withdrawal_fee_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0"
              />
              <p className="mt-1 text-xs text-gray-500">Fee for withdrawing funds</p>
            </div>
          </div>

          {/* Annual & Setup Fees */}
          <div className="space-y-4">
            <h3 className="text-md font-medium text-gray-900 border-b pb-2">Annual & Setup Fees</h3>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Account Maintenance (USD/year)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.amc_yearly_usd}
                onChange={(e) => handleFeesChange('amc_yearly_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0"
              />
              <p className="mt-1 text-xs text-gray-500">Annual maintenance charges</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Account Opening Fee (USD)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.account_opening_fee_usd}
                onChange={(e) => handleFeesChange('account_opening_fee_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0"
              />
              <p className="mt-1 text-xs text-gray-500">One-time account setup fee</p>
            </div>
          </div>
        </div>

        {/* Fees Preview */}
        <div className="bg-gray-50 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-900 mb-3">Fee Calculation Preview</h4>
          <div className="text-sm text-gray-600 space-y-1">
            <p>For a $1,000 trade:</p>
            <ul className="list-disc ml-5 space-y-1">
              <li>Brokerage: ${Math.min(1000 * feesConfig.brokerage_percentage / 100, feesConfig.brokerage_max_usd).toFixed(2)}</li>
              <li>Exchange charges: ${(1000 * feesConfig.exchange_transaction_charges_percentage / 100).toFixed(4)}</li>
              <li>IFSCA fees: ${(1000 * feesConfig.ifsca_turnover_fees_percentage / 100).toFixed(4)}</li>
              <li>Platform fee: ${feesConfig.platform_fee_usd.toFixed(2)}</li>
              <li><strong>Total per trade: ${(Math.min(1000 * feesConfig.brokerage_percentage / 100, feesConfig.brokerage_max_usd) + 
                                                1000 * feesConfig.exchange_transaction_charges_percentage / 100 + 
                                                1000 * feesConfig.ifsca_turnover_fees_percentage / 100 + 
                                                feesConfig.platform_fee_usd).toFixed(2)}</strong></li>
            </ul>
            <p className="text-xs text-gray-500 mt-2">
              * Complete trade (buy + sell) will have 2x these fees
            </p>
          </div>
        </div>

        <div className="flex justify-between items-center">
          <button
            type="button"
            onClick={() => {
              const defaultConfig = getDefaultFeesConfig();
              Object.keys(defaultConfig).forEach(key => {
                handleFeesChange(key as keyof FeesConfig, defaultConfig[key as keyof FeesConfig]);
              });
            }}
            className="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            <Settings className="h-4 w-4 mr-2 inline" />
            Reset to Defaults
          </button>

          <button
            type="submit"
            disabled={isFeesSubmitting}
            className={`flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white transition-colors ${
              isFeesSubmitting
                ? 'bg-gray-400 cursor-not-allowed'
                : feesSubmitSuccess
                ? 'bg-green-600 hover:bg-green-700'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {isFeesSubmitting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Saving...
              </>
            ) : feesSubmitSuccess ? (
              <>
                <Save className="h-4 w-4 mr-2" />
                Saved!
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Save Fees Configuration
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}