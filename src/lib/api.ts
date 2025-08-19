import { Trade, TradeMetrics } from '@/types/trade';
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

// Monthly Balance Management
export async function getMonthlyBalances(userId: string): Promise<{ monthly_balances: any[] }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/monthly-balances/${userId}`, { headers });
  
  if (!response.ok) {
    throw new Error('Failed to fetch monthly balances');
  }
  
  return response.json();
}

export async function saveMonthlyBalance(monthlyBalance: {
  month: string;
  start_balance: number;
  end_balance?: number;
  is_manual?: boolean;
  notes?: string;
}): Promise<{ message: string; balance_id: string; user_id: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/monthly-balances`, {
    method: 'POST',
    headers,
    body: JSON.stringify(monthlyBalance),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to save monthly balance');
  }
  
  return response.json();
}

export async function deleteMonthlyBalance(balanceId: string): Promise<{ message: string }> {
  const headers = await getAuthHeaders();
  const response = await fetch(`${API_BASE_URL}/monthly-balances/${balanceId}`, {
    method: 'DELETE',
    headers,
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to delete monthly balance');
  }
  
  return response.json();
}
