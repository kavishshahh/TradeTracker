import { FeesConfig, Trade, TradeMetrics } from '@/types/trade';
import { auth } from './firebase';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

// Helper function to get auth headers
async function getAuthHeaders() {
  const user = auth.currentUser;
  if (!user) {
    throw new Error('User not authenticated');
  }
  
  const token = await user.getIdToken();
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  };
}

export async function addTrade(trade: Omit<Trade, 'id' | 'created_at' | 'updated_at'>): Promise<{ message: string; trade_id: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/add-trade`, {
    method: 'POST',
    headers,
    body: JSON.stringify(trade),
  });

  if (!response.ok) {
    throw new Error('Failed to add trade');
  }

  return response.json();
}

export async function getTrades(userId: string, fromDate?: string, toDate?: string): Promise<{ trades: Trade[] }> {
  const params = new URLSearchParams();
  if (fromDate) params.append('from_date', fromDate);
  if (toDate) params.append('to_date', toDate);
  
  const queryString = params.toString();
  const url = `${API_BASE_URL}/trades/${userId}${queryString ? `?${queryString}` : ''}`;

  const headers = await getAuthHeaders();
  const response = await fetch(url, { headers });

  if (!response.ok) {
    throw new Error('Failed to fetch trades');
  }

  return response.json();
}

export async function getMetrics(userId: string, fromDate?: string, toDate?: string): Promise<TradeMetrics> {
  const params = new URLSearchParams();
  if (fromDate) params.append('from_date', fromDate);
  if (toDate) params.append('to_date', toDate);
  
  const queryString = params.toString();
  const url = `${API_BASE_URL}/metrics/${userId}${queryString ? `?${queryString}` : ''}`;

  const headers = await getAuthHeaders();
  const response = await fetch(url, { headers });

  if (!response.ok) {
    throw new Error('Failed to fetch metrics');
  }

  return response.json();
}

export async function updateTrade(tradeId: string, updateData: {
  date?: string;
  ticker?: string;
  buy_price?: number;
  sell_price?: number;
  shares?: number;
  risk?: number;
  risk_dollars?: number;
  account_balance?: number;
  notes?: string;
  status?: 'open' | 'closed';
}): Promise<{ message: string; trade_id: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/trades/${tradeId}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ trade_id: tradeId, ...updateData }),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update trade');
  }
  
  return response.json();
}

export async function deleteTrade(tradeId: string): Promise<{ message: string; trade_id: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/trades/${tradeId}`, {
    method: 'DELETE',
    headers,
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete trade');
  }
  
  return response.json();
}

export async function exitTrade(userId: string, exitData: {
  ticker: string;
  shares_to_exit: number;
  sell_price: number;
  notes?: string;
}): Promise<{ message: string; trade_id?: string; exit_trade_id?: string; remaining_trade_id?: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/exit-trade/${userId}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(exitData),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to exit trade');
  }
  
  return response.json();
}

export async function getUserProfile(userId: string): Promise<{ profile: any }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/profile/${userId}`, { headers });
  
  if (!response.ok) {
    throw new Error('Failed to fetch profile');
  }
  
  return response.json();
}

export async function updateUserProfile(userId: string, profileData: {
  account_balance: number;
  currency?: string;
  risk_tolerance?: number;
}): Promise<{ message: string; user_id: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/profile/${userId}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(profileData),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to update profile');
  }
  
  return response.json();
}

export async function getAccountBalance(userId: string): Promise<{ account_balance: number }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/profile/${userId}/account-balance`, { headers });
  
  if (!response.ok) {
    throw new Error('Failed to fetch account balance');
  }
  
  return response.json();
}

// Monthly Returns Management
export async function getMonthlyReturns(userId: string): Promise<{ monthly_returns: any[] }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/monthly-returns/${userId}`, { headers });
  
  if (!response.ok) {
    throw new Error('Failed to fetch monthly returns');
  }
  
  return response.json();
}

export async function saveMonthlyReturn(monthlyReturn: {
  month: string;
  start_cap: number;
  close_cap?: number;
  percentage_return?: number;
  dollar_return?: number;
  inr_return?: number;
  comments?: string;
}): Promise<{ message: string; return_id: string; user_id: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/monthly-returns`, {
    method: 'POST',
    headers,
    body: JSON.stringify(monthlyReturn),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to save monthly return');
  }
  
  return response.json();
}

export async function deleteMonthlyReturn(returnId: string): Promise<{ message: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/monthly-returns/${returnId}`, {
    method: 'DELETE',
    headers,
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete monthly return');
  }
  
  return response.json();
}

// Fees Configuration Management
export async function getFeesConfig(userId: string): Promise<{ fees_config: FeesConfig }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/fees-config/${userId}`, { headers });
  
  if (!response.ok) {
    throw new Error('Failed to fetch fees configuration');
  }
  
  return response.json();
}

export async function saveFeesConfig(feesConfig: FeesConfig): Promise<{ message: string; user_id: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/fees-config`, {
    method: 'POST',
    headers,
    body: JSON.stringify(feesConfig),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to save fees configuration');
  }
  
  return response.json();
}

// Email API functions
export const sendWelcomeEmail = async (email: string, userName?: string) => {
  try {
    const headers = await getAuthHeaders();
    
    const response = await fetch(`${API_BASE_URL}/send-welcome-email`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        email,
        user_name: userName,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to send welcome email');
    }

    return await response.json();
  } catch (error) {
    console.error('Error sending welcome email:', error);
    throw new Error(`Failed to send welcome email: ${error}`);
  }
};

export const triggerWelcomeEmail = async (email: string, userName?: string, isNewUser: boolean = false) => {
  try {
    const headers = await getAuthHeaders();
    
    const response = await fetch(`${API_BASE_URL}/trigger-welcome-email`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        email,
        user_name: userName,
        is_new_user: isNewUser,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to trigger welcome email');
    }

    return await response.json();
  } catch (error) {
    console.error('Error triggering welcome email:', error);
    // Don't throw error for welcome email failure - it shouldn't block login
    console.log('Welcome email failed, but continuing with login...');
    return null;
  }
};

export const sendTradeReminder = async (email: string, userName?: string, daysInactive?: number) => {
  try {
    const headers = await getAuthHeaders();
    
    const response = await fetch(`${API_BASE_URL}/send-trade-reminder`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        email,
        user_name: userName,
        days_inactive: daysInactive || 7,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to send trade reminder');
    }

    return await response.json();
  } catch (error) {
    console.error('Error sending trade reminder:', error);
    throw new Error(`Failed to send trade reminder: ${error}`);
  }
};

export const sendWeeklySummary = async (email: string, userName?: string, summaryData?: any) => {
  try {
    const headers = await getAuthHeaders();
    
    const response = await fetch(`${API_BASE_URL}/send-weekly-summary`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        email,
        user_name: userName,
        summary_data: summaryData,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to send weekly summary');
    }

    return await response.json();
  } catch (error) {
    console.error('Error sending weekly summary:', error);
    throw new Error(`Failed to send weekly summary: ${error}`);
  }
};
