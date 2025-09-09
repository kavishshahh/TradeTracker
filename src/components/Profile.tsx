'use client';

import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { trackEvent, trackFormSubmission, trackPageView } from '@/lib/analytics';
import { getFeesConfig, getUserProfile, saveFeesConfig, updateUserProfile } from '@/lib/api';
import { FeesConfig } from '@/types/trade';
import { Calculator, DollarSign, Lock, Moon, Save, Settings, Sun, User } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'react-toastify';

interface ProfileFormData {
  account_balance: number;
  currency: string;
  risk_tolerance: number;
}

interface PasswordFormData {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}

export default function Profile() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'profile' | 'fees' | 'security'>('profile');
  const [feesConfig, setFeesConfig] = useState<FeesConfig | null>(null);
  const [isFeesSubmitting, setIsFeesSubmitting] = useState(false);
  const [feesSubmitSuccess, setFeesSubmitSuccess] = useState(false);
  const [isPasswordSubmitting, setIsPasswordSubmitting] = useState(false);
  const [passwordSubmitSuccess, setPasswordSubmitSuccess] = useState(false);
  const [showPasswords, setShowPasswords] = useState({
    current: false,
    new: false,
    confirm: false
  });
  const { currentUser, changePassword: changePasswordAuth } = useAuth();
  const { theme, toggleTheme } = useTheme();

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

  const {
    register: registerPassword,
    handleSubmit: handlePasswordSubmit,
    reset: resetPassword,
    watch: watchPassword,
    formState: { errors: passwordErrors }
  } = useForm<PasswordFormData>({
    defaultValues: {
      currentPassword: '',
      newPassword: '',
      confirmPassword: ''
    }
  });

  const accountBalance = watch('account_balance');
  const riskTolerance = watch('risk_tolerance');
  const newPassword = watchPassword('newPassword');
  const confirmPassword = watchPassword('confirmPassword');

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

  // Handle password change
  const onPasswordSubmit = async (data: PasswordFormData) => {
    if (!currentUser) return;

    try {
      setIsPasswordSubmitting(true);
      setPasswordSubmitSuccess(false);
      
      await changePasswordAuth(data.currentPassword, data.newPassword);
      
      setPasswordSubmitSuccess(true);
      toast.success('Password changed successfully!');
      
      // Track successful password change
      trackEvent('password_change', 'security', 'success');
      
      // Reset form and success state
      resetPassword();
      setTimeout(() => setPasswordSubmitSuccess(false), 3000);
    } catch (error: any) {
      console.error('Error changing password:', error);
      let errorMessage = 'Failed to change password. Please try again.';
      
      if (error.code === 'auth/wrong-password') {
        errorMessage = 'Current password is incorrect.';
      } else if (error.code === 'auth/weak-password') {
        errorMessage = 'New password is too weak. Please choose a stronger password.';
      } else if (error.code === 'auth/requires-recent-login') {
        errorMessage = 'Please log out and log back in before changing your password.';
      }
      
      if (error.message === 'INVALID_LOGIN_CREDENTIALS') {
        errorMessage = 'Invalid credential. Please try again.';
      }
      
      toast.error(errorMessage);
      trackEvent('password_change', 'security', 'error');
    } finally {
      setIsPasswordSubmitting(false);
    }
  };

  // Password strength validation
  const getPasswordStrength = (password: string) => {
    if (!password) return { score: 0, label: '', color: '' };
    
    let score = 0;
    if (password.length >= 8) score++;
    if (password.length >= 12) score++;
    if (/[a-z]/.test(password)) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    
    if (score <= 2) return { score, label: 'Weak', color: 'text-red-500' };
    if (score <= 4) return { score, label: 'Medium', color: 'text-yellow-500' };
    return { score, label: 'Strong', color: 'text-green-500' };
  };

  const passwordStrength = getPasswordStrength(newPassword || '');



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
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center">
          <User className="h-6 w-6 mr-2 text-blue-500" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Profile Settings</h1>
            <p className="text-gray-600 dark:text-gray-300 mt-1">Manage your account settings and trading preferences</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="border-b border-gray-200 dark:border-gray-700">
          <nav className="-mb-px flex">
            <button
              onClick={() => setActiveTab('profile')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'profile'
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
            >
              <User className="h-4 w-4 mr-2 inline" />
              Account Settings
            </button>
            <button
              onClick={() => setActiveTab('fees')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'fees'
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
            >
              <Calculator className="h-4 w-4 mr-2 inline" />
              Fees Configuration
            </button>
            <button
              onClick={() => setActiveTab('security')}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'security'
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
            >
              <Lock className="h-4 w-4 mr-2 inline" />
              Security
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
              theme={theme}
              toggleTheme={toggleTheme}
            />
          ) : activeTab === 'fees' ? (
            <FeesTabContent 
              feesConfig={feesConfig}
              handleFeesSubmit={handleFeesSubmit}
              handleFeesChange={handleFeesChange}
              isFeesSubmitting={isFeesSubmitting}
              feesSubmitSuccess={feesSubmitSuccess}
              getDefaultFeesConfig={getDefaultFeesConfig}
            />
          ) : (
            <SecurityTabContent 
              registerPassword={registerPassword}
              handlePasswordSubmit={handlePasswordSubmit}
              onPasswordSubmit={onPasswordSubmit}
              passwordErrors={passwordErrors}
              isPasswordSubmitting={isPasswordSubmitting} 
              passwordSubmitSuccess={passwordSubmitSuccess}
              showPasswords={showPasswords}
              setShowPasswords={setShowPasswords}
              passwordStrength={passwordStrength}
              newPassword={newPassword}
              confirmPassword={confirmPassword}
            />
          )}
        </div>
      </div>

      {/* User Info */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Account Information</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Email Address</p>
            <p className="text-gray-900 dark:text-white font-medium">{currentUser?.email}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">User ID</p>
            <p className="text-gray-900 dark:text-white font-medium font-mono text-sm">{currentUser?.uid}</p>
          </div>
        </div>
        
        <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
          <p className="text-sm text-blue-800 dark:text-blue-200">
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
  theme: 'light' | 'dark';
  toggleTheme: () => void;
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
  calculatePositionSize,
  theme,
  toggleTheme
}: ProfileTabContentProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Account Settings Form */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Account Settings</h2>
        
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label htmlFor="account_balance" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Account Balance (USD) *
            </label>
            <div className="relative">
              <DollarSign className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400 dark:text-gray-500" />
              <input
                id="account_balance"
                type="number"
                step="0.01"
                {...register('account_balance', {
                  required: 'Account balance is required',
                  min: { value: 0.01, message: 'Account balance must be greater than 0' }
                })}
                className="w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                placeholder="Enter your account balance"
              />
            </div>
            {errors.account_balance && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.account_balance.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="currency" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Currency
            </label>
            <select
              id="currency"
              {...register('currency')}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
            >
              <option value="USD">USD - US Dollar</option>
              <option value="EUR">EUR - Euro</option>
              <option value="GBP">GBP - British Pound</option>
              <option value="INR">INR - Indian Rupee</option>
            </select>
          </div>

          <div>
            <label htmlFor="risk_tolerance" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
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
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              placeholder="2.0"
            />
            {errors.risk_tolerance && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.risk_tolerance.message}</p>
            )}
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Recommended: 1-3% per trade for conservative approach
            </p>
          </div>

          {/* Theme Toggle */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Theme Preference
            </label>
            <div className="flex items-center space-x-4">
              <button
                type="button"
                onClick={() => {
                  toggleTheme();
                  trackEvent('theme_toggle', 'profile', theme === 'light' ? 'dark' : 'light');
                }}
                className="flex items-center space-x-2 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              >
                {theme === 'light' ? (
                  <>
                    <Moon className="h-4 w-4" />
                    <span>Switch to Dark Mode</span>
                  </>
                ) : (
                  <>
                    <Sun className="h-4 w-4" />
                    <span>Switch to Light Mode</span>
                  </>
                )}
              </button>
              <span className="text-sm text-gray-500 dark:text-gray-400">
                Current: {theme === 'light' ? 'Light' : 'Dark'} Mode
              </span>
            </div>
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
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Risk Calculator</h2>
        
        <div className="space-y-4">
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
            <h3 className="text-sm font-medium text-blue-900 dark:text-blue-200 mb-2">Position Size per Trade</h3>
            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              ${calculatePositionSize().toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
            <p className="text-sm text-blue-700 dark:text-blue-300 mt-1">
              Based on {riskTolerance}% risk tolerance
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <p className="text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wide">Account Balance</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">
                ${accountBalance?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
              </p>
            </div>
            
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
              <p className="text-xs text-gray-600 dark:text-gray-400 uppercase tracking-wide">Risk per Trade</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">{riskTolerance}%</p>
            </div>
          </div>

          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-2">Risk Management Tips</h4>
            <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
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
        <p className="mt-2 text-gray-500 dark:text-gray-400">Loading fees configuration...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Trading Fees Configuration</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Configure your broker's fee structure to get accurate P&L calculations. Default values are based on typical US stock trading fees.
        </p>
      </div>

      <form onSubmit={handleFeesSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Brokerage Fees */}
          <div className="space-y-4">
            <h3 className="text-md font-medium text-gray-900 dark:text-white border-b border-gray-200 dark:border-gray-700 pb-2">Brokerage Fees</h3>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Brokerage (% per transaction)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="5"
                value={feesConfig.brokerage_percentage}
                onChange={(e) => handleFeesChange('brokerage_percentage', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="0.25"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Percentage charged per transaction</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Maximum Brokerage (USD)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.brokerage_max_usd}
                onChange={(e) => handleFeesChange('brokerage_max_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="25"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Maximum brokerage fee cap</p>
            </div>
          </div>

          {/* Exchange & Regulatory Fees */}
          <div className="space-y-4">
            <h3 className="text-md font-medium text-gray-900 dark:text-white border-b border-gray-200 dark:border-gray-700 pb-2">Exchange & Regulatory Fees</h3>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Exchange Transaction Charges (%)
              </label>
              <input
                type="number"
                step="0.001"
                min="0"
                value={feesConfig.exchange_transaction_charges_percentage}
                onChange={(e) => handleFeesChange('exchange_transaction_charges_percentage', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="0.12"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Exchange charges per transaction</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                IFSCA Turnover Fees (%)
              </label>
              <input
                type="number"
                step="0.0001"
                min="0"
                value={feesConfig.ifsca_turnover_fees_percentage}
                onChange={(e) => handleFeesChange('ifsca_turnover_fees_percentage', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="0.0001"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">IFSCA regulatory fees</p>
            </div>
          </div>

          {/* Platform & Other Fees */}
          <div className="space-y-4">
            <h3 className="text-md font-medium text-gray-900 dark:text-white border-b border-gray-200 dark:border-gray-700 pb-2">Platform Fees</h3>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Platform Fee per Transaction (USD)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.platform_fee_usd}
                onChange={(e) => handleFeesChange('platform_fee_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="0"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Fixed fee per trade</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Withdrawal Fee (USD)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.withdrawal_fee_usd}
                onChange={(e) => handleFeesChange('withdrawal_fee_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="0"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Fee for withdrawing funds</p>
            </div>
          </div>

          {/* Annual & Setup Fees */}
          <div className="space-y-4">
            <h3 className="text-md font-medium text-gray-900 dark:text-white border-b border-gray-200 dark:border-gray-700 pb-2">Annual & Setup Fees</h3>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Account Maintenance (USD/year)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.amc_yearly_usd}
                onChange={(e) => handleFeesChange('amc_yearly_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="0"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Annual maintenance charges</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Account Opening Fee (USD)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={feesConfig.account_opening_fee_usd}
                onChange={(e) => handleFeesChange('account_opening_fee_usd', Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                placeholder="0"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">One-time account setup fee</p>
            </div>
          </div>
        </div>

        {/* Fees Preview */}
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Fee Calculation Preview</h4>
          <div className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
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
            className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
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

// Security Tab Component
interface SecurityTabContentProps {
  registerPassword: any;
  handlePasswordSubmit: any;
  onPasswordSubmit: any;
  passwordErrors: any;
  isPasswordSubmitting: boolean;
  passwordSubmitSuccess: boolean;
  showPasswords: {
    current: boolean;
    new: boolean;
    confirm: boolean;
  };
  setShowPasswords: (passwords: { current: boolean; new: boolean; confirm: boolean }) => void;
  passwordStrength: {
    score: number;
    label: string;
    color: string;
  };
  newPassword: string;
  confirmPassword: string;
}

function SecurityTabContent({ 
  registerPassword, 
  handlePasswordSubmit, 
  onPasswordSubmit, 
  passwordErrors, 
  isPasswordSubmitting, 
  passwordSubmitSuccess,
  showPasswords,
  setShowPasswords,
  passwordStrength,
  newPassword,
  confirmPassword
}: SecurityTabContentProps) {
  return (
    <div className="max-w-md mx-auto">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Change Password</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Update your password to keep your account secure. Make sure to use a strong password.
        </p>
      </div>

      <form onSubmit={handlePasswordSubmit(onPasswordSubmit)} className="space-y-4">
        {/* Current Password */}
        <div>
          <label htmlFor="currentPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Current Password *
          </label>
          <div className="relative">
            <input
              id="currentPassword"
              type={showPasswords.current ? 'text' : 'password'}
              {...registerPassword('currentPassword', {
                required: 'Current password is required'
              })}
              className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              placeholder="Enter your current password"
            />
            <button
              type="button"
              onClick={() => setShowPasswords({ ...showPasswords, current: !showPasswords.current })}
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              {showPasswords.current ? (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878L21 21" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
          {passwordErrors.currentPassword && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{passwordErrors.currentPassword.message}</p>
          )}
        </div>

        {/* New Password */}
        <div>
          <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            New Password *
          </label>
          <div className="relative">
            <input
              id="newPassword"
              type={showPasswords.new ? 'text' : 'password'}
              {...registerPassword('newPassword', {
                required: 'New password is required',
                minLength: { value: 8, message: 'Password must be at least 8 characters long' }
              })}
              className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              placeholder="Enter your new password"
            />
            <button
              type="button"
              onClick={() => setShowPasswords({ ...showPasswords, new: !showPasswords.new })}
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              {showPasswords.new ? (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878L21 21" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
          {passwordErrors.newPassword && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{passwordErrors.newPassword.message}</p>
          )}
          
          {/* Password Strength Indicator */}
          {newPassword && (
            <div className="mt-2">
              <div className="flex items-center space-x-2">
                <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div 
                    className={`h-2 rounded-full transition-all duration-300 ${
                      passwordStrength.score <= 2 ? 'bg-red-500' : 
                      passwordStrength.score <= 4 ? 'bg-yellow-500' : 'bg-green-500'
                    }`}
                    style={{ width: `${(passwordStrength.score / 6) * 100}%` }}
                  />
                </div>
                <span className={`text-sm font-medium ${passwordStrength.color}`}>
                  {passwordStrength.label}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Confirm Password */}
        <div>
          <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Confirm New Password *
          </label>
          <div className="relative">
            <input
              id="confirmPassword"
              type={showPasswords.confirm ? 'text' : 'password'}
              {...registerPassword('confirmPassword', {
                required: 'Please confirm your new password',
                validate: (value: string) => value === newPassword || 'Passwords do not match'
              })}
              className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              placeholder="Confirm your new password"
            />
            <button
              type="button"
              onClick={() => setShowPasswords({ ...showPasswords, confirm: !showPasswords.confirm })}
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              {showPasswords.confirm ? (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878L21 21" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
          {passwordErrors.confirmPassword && (
            <p className="mt-1 text-sm text-red-600 dark:text-red-400">{passwordErrors.confirmPassword.message}</p>
          )}
        </div>

        {/* Password Requirements */}
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
          <h4 className="text-sm font-medium text-blue-900 dark:text-blue-200 mb-2">Password Requirements</h4>
          <ul className="text-sm text-blue-800 dark:text-blue-300 space-y-1">
            <li>• At least 8 characters long</li>
            <li>• Mix of uppercase and lowercase letters</li>
            <li>• Include numbers and special characters</li>
            <li>• Avoid common words or personal information</li>
          </ul>
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isPasswordSubmitting}
          className={`w-full flex items-center justify-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white transition-colors ${
            isPasswordSubmitting
              ? 'bg-gray-400 cursor-not-allowed'
              : passwordSubmitSuccess
              ? 'bg-green-600 hover:bg-green-700'
              : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          {isPasswordSubmitting ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
              Updating Password...
            </>
          ) : passwordSubmitSuccess ? (
            <>
              <Lock className="h-4 w-4 mr-2" />
              Password Updated!
            </>
          ) : (
            <>
              <Lock className="h-4 w-4 mr-2" />
              Update Password
            </>
          )}
        </button>
      </form>
    </div>
  );
}

