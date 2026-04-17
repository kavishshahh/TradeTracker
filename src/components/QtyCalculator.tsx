'use client';

import { trackPageView, trackUserEngagement } from '@/lib/analytics';
import { getUsdtFxRates, UsdtFxRates } from '@/lib/api';
import { Calculator, RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

type RiskCurrency = 'USDT' | 'INR' | 'EUR' | 'SGD';
type InstrumentKey = 'BTC' | 'ETH' | 'XAU' | 'GOLD' | 'SILVER' | 'CRUDE_OIL' | 'USDT' | 'INR';

const INSTRUMENT_OPTIONS: Array<{ key: InstrumentKey; label: string; unit: string }> = [
  { key: 'BTC', label: 'Bitcoin (BTC)', unit: 'BTC' },
  { key: 'ETH', label: 'Ethereum (ETH)', unit: 'ETH' },
  { key: 'XAU', label: 'Gold Spot (XAU)', unit: 'XAU' },
  { key: 'GOLD', label: 'Gold', unit: 'GOLD' },
  { key: 'SILVER', label: 'Silver', unit: 'SILVER' },
  { key: 'CRUDE_OIL', label: 'Crude Oil', unit: 'CRUDE' },
  { key: 'USDT', label: 'USDT', unit: 'USDT' },
  { key: 'INR', label: 'INR', unit: 'INR' },
];

const FX_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

const defaultRates: UsdtFxRates = {
  usd: 1,
  inr: 0,
  eur: 0,
  sgd: 0,
};

function formatNumber(value: number, digits = 4): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

export default function QtyCalculator() {
  const [instrument, setInstrument] = useState<InstrumentKey>('BTC');
  const [slPoints, setSlPoints] = useState<string>('250');
  const [riskAmount, setRiskAmount] = useState<string>('500');
  const [riskCurrency, setRiskCurrency] = useState<RiskCurrency>('INR');
  const [rates, setRates] = useState<UsdtFxRates>(defaultRates);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refreshMarketData = async (forceFxRefresh = false) => {
    try {
      setIsRefreshing(true);
      setError(null);

      const fxRates = await getUsdtFxRates({ forceRefresh: forceFxRefresh });

      setRates(fxRates);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to refresh market data:', err);
      setError('Could not fetch live FX rates. Please try again.');
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    trackPageView('/qty-calculator');
    trackUserEngagement('qty_calculator_view');
  }, []);

  useEffect(() => {
    refreshMarketData();
    const fxIntervalId = window.setInterval(() => {
      refreshMarketData(true);
    }, FX_REFRESH_INTERVAL_MS);

    return () => {
      window.clearInterval(fxIntervalId);
    };
  }, []);

  const selectedInstrument = useMemo(() => {
    return INSTRUMENT_OPTIONS.find((item) => item.key === instrument) ?? INSTRUMENT_OPTIONS[0];
  }, [instrument]);

  const calculations = useMemo(() => {
    const sl = Number(slPoints);
    const risk = Number(riskAmount);

    if (
      !sl ||
      sl <= 0 ||
      Number.isNaN(sl) ||
      Number.isNaN(risk) ||
      risk <= 0
    ) {
      return {
        riskInUsdt: 0,
        qty: 0,
      };
    }

    let riskInUsdt = risk;

    if (riskCurrency === 'INR' && rates.inr > 0) {
      riskInUsdt = risk / rates.inr;
    } else if (riskCurrency === 'EUR' && rates.eur > 0) {
      riskInUsdt = risk / rates.eur;
    } else if (riskCurrency === 'SGD' && rates.sgd > 0) {
      riskInUsdt = risk / rates.sgd;
    }

    const qty = riskInUsdt / sl;

    return {
      riskInUsdt,
      qty,
    };
  }, [riskAmount, riskCurrency, rates, slPoints]);

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center">
              <Calculator className="h-6 w-6 mr-2 text-blue-500" />
              Live Qty Calculator
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mt-1">
              Enter SL points and risk amount to get instant position quantity.
            </p>
          </div>
          <button
            onClick={() => refreshMarketData(false)}
            className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-60"
            disabled={isRefreshing}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh Live Data
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Inputs</h2>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Instrument
            </label>
            <select
              value={instrument}
              onChange={(e) => setInstrument(e.target.value as InstrumentKey)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
            >
              {INSTRUMENT_OPTIONS.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Stop Loss (Points / $ Move)
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={slPoints}
              onChange={(e) => setSlPoints(e.target.value)}
              placeholder="250"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Risk Amount
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={riskAmount}
                onChange={(e) => setRiskAmount(e.target.value)}
                placeholder="500"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Currency
              </label>
              <select
                value={riskCurrency}
                onChange={(e) => setRiskCurrency(e.target.value as RiskCurrency)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
              >
                <option value="USDT">USDT</option>
                <option value="INR">INR</option>
                <option value="EUR">EUR</option>
                <option value="SGD">SGD</option>
              </select>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 space-y-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Results</h2>

          <div className="rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-900 p-4">
            <p className="text-sm text-blue-700 dark:text-blue-300">Position Quantity</p>
            <p className="text-3xl font-bold text-blue-900 dark:text-blue-100">
              {formatNumber(calculations.qty, 6)} {selectedInstrument.unit}
            </p>
          </div>

          <div className="rounded-md bg-gray-50 dark:bg-gray-700 p-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">Risk In USDT</p>
            <p className="text-lg font-semibold text-gray-900 dark:text-white">
              {formatNumber(calculations.riskInUsdt, 4)} USDT
            </p>
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-300 space-y-1">
            <p>USDT/INR: {rates.inr ? formatNumber(rates.inr, 4) : 'Loading...'}</p>
            <p>USDT/EUR: {rates.eur ? formatNumber(rates.eur, 4) : 'Loading...'}</p>
            <p>USDT/SGD: {rates.sgd ? formatNumber(rates.sgd, 4) : 'Loading...'}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Last updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : 'Waiting for live feed...'}
            </p>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-md font-semibold text-gray-900 dark:text-white mb-2">Formula</h3>
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Qty = Risk (in USDT) / SL Points. Example: risk is 5.2 USDT and SL is 30 points, Qty = 5.2 / 30 = 0.1733 {selectedInstrument.unit}.
        </p>
        {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>
    </div>
  );
}
