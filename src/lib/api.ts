import { Trade, TradeMetrics } from '@/types/trade';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function addTrade(trade: Omit<Trade, 'id' | 'created_at' | 'updated_at'>): Promise<{ message: string; trade_id: string }> {
  const response = await fetch(`${API_BASE_URL}/add-trade`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
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

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error('Failed to fetch trades');
  }

  return response.json();
}

export async function getMetrics(userId: string): Promise<TradeMetrics> {
  const response = await fetch(`${API_BASE_URL}/metrics/${userId}`);

  if (!response.ok) {
    throw new Error('Failed to fetch metrics');
  }

  return response.json();
}
