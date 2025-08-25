import { FeesConfig, Trade } from "@/types/trade";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatPercentage(value: number): string {
  return `${value.toFixed(2)}%`;
}

// Calculate fees for a single trade
export function calculateTradeFees(trade: Trade, feesConfig: FeesConfig): {
  totalFees: number;
  breakdown: {
    brokerage: number;
    exchangeCharges: number;
    ifscaFees: number;
    platformFee: number;
  };
} {
  const tradeValue = (trade.buy_price || 0) * trade.shares;
  
  // Calculate brokerage (percentage with max cap)
  const brokerageUncapped = tradeValue * (feesConfig.brokerage_percentage / 100);
  const brokerage = Math.min(brokerageUncapped, feesConfig.brokerage_max_usd);
  
  // Calculate exchange transaction charges
  const exchangeCharges = tradeValue * (feesConfig.exchange_transaction_charges_percentage / 100);
  
  // Calculate IFSCA turnover fees
  const ifscaFees = tradeValue * (feesConfig.ifsca_turnover_fees_percentage / 100);
  
  // Platform fee per transaction
  const platformFee = feesConfig.platform_fee_usd;
  
  const totalFees = brokerage + exchangeCharges + ifscaFees + platformFee;
  
  return {
    totalFees,
    breakdown: {
      brokerage,
      exchangeCharges,
      ifscaFees,
      platformFee
    }
  };
}

// Calculate total fees for a complete trade (buy + sell)
export function calculateCompleteTradeFees(trade: Trade, feesConfig: FeesConfig): {
  totalFees: number;
  buyFees: number;
  sellFees: number;
  breakdown: {
    buyBrokerage: number;
    sellBrokerage: number;
    buyExchangeCharges: number;
    sellExchangeCharges: number;
    buyIfscaFees: number;
    sellIfscaFees: number;
    platformFees: number;
  };
} {
  if (trade.status !== 'closed' || !trade.sell_price) {
    // For open trades, only calculate buy fees
    const buyFeesCalc = calculateTradeFees(trade, feesConfig);
    return {
      totalFees: buyFeesCalc.totalFees,
      buyFees: buyFeesCalc.totalFees,
      sellFees: 0,
      breakdown: {
        buyBrokerage: buyFeesCalc.breakdown.brokerage,
        sellBrokerage: 0,
        buyExchangeCharges: buyFeesCalc.breakdown.exchangeCharges,
        sellExchangeCharges: 0,
        buyIfscaFees: buyFeesCalc.breakdown.ifscaFees,
        sellIfscaFees: 0,
        platformFees: buyFeesCalc.breakdown.platformFee,
      }
    };
  }

  // For closed trades, calculate both buy and sell fees
  const buyTradeValue = (trade.buy_price || 0) * trade.shares;
  const sellTradeValue = (trade.sell_price || 0) * trade.shares;
  
  // Buy fees
  const buyBrokerageUncapped = buyTradeValue * (feesConfig.brokerage_percentage / 100);
  const buyBrokerage = Math.min(buyBrokerageUncapped, feesConfig.brokerage_max_usd);
  const buyExchangeCharges = buyTradeValue * (feesConfig.exchange_transaction_charges_percentage / 100);
  const buyIfscaFees = buyTradeValue * (feesConfig.ifsca_turnover_fees_percentage / 100);
  
  // Sell fees
  const sellBrokerageUncapped = sellTradeValue * (feesConfig.brokerage_percentage / 100);
  const sellBrokerage = Math.min(sellBrokerageUncapped, feesConfig.brokerage_max_usd);
  const sellExchangeCharges = sellTradeValue * (feesConfig.exchange_transaction_charges_percentage / 100);
  const sellIfscaFees = sellTradeValue * (feesConfig.ifsca_turnover_fees_percentage / 100);
  
  // Platform fees (2x for buy + sell)
  const platformFees = feesConfig.platform_fee_usd * 2;
  
  const buyFees = buyBrokerage + buyExchangeCharges + buyIfscaFees + feesConfig.platform_fee_usd;
  const sellFees = sellBrokerage + sellExchangeCharges + sellIfscaFees + feesConfig.platform_fee_usd;
  const totalFees = buyFees + sellFees;
  
  return {
    totalFees,
    buyFees,
    sellFees,
    breakdown: {
      buyBrokerage,
      sellBrokerage,
      buyExchangeCharges,
      sellExchangeCharges,
      buyIfscaFees,
      sellIfscaFees,
      platformFees,
    }
  };
}

// Calculate net P&L after fees
export function calculateNetPnL(trade: Trade, feesConfig: FeesConfig): number {
  if (trade.status !== 'closed' || !trade.sell_price || !trade.buy_price) {
    return 0;
  }
  
  const grossPnL = (trade.sell_price - trade.buy_price) * trade.shares;
  const fees = calculateCompleteTradeFees(trade, feesConfig);
  
  return grossPnL - fees.totalFees;
}
