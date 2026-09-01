import assert from "node:assert/strict";
import test from "node:test";

import {
  calculateBreakEvenWinRate,
  calculateExpectancy,
  calculateMaximumDrawdown,
  calculatePositionSize,
  calculateProfitFactor,
  calculateRiskReward,
  calculateTradingRoi,
  calculateWinRate,
} from "../src/lib/calculators.ts";

function assertClose(actual: number, expected: number, tolerance = 1e-10): void {
  assert.ok(
    Math.abs(actual - expected) <= tolerance,
    `Expected ${actual} to be within ${tolerance} of ${expected}.`,
  );
}

test("calculateWinRate includes breakevens in total-trade rates", () => {
  const result = calculateWinRate({ wins: 5, losses: 3, breakevens: 2 });

  assert.equal(result.totalTrades, 10);
  assert.equal(result.winRatePercent, 50);
  assert.equal(result.lossRatePercent, 30);
  assert.equal(result.breakevenRatePercent, 20);
  assert.equal(result.decisiveWinRatePercent, 62.5);
});

test("calculateWinRate reports an undefined decisive rate for all-breakeven samples", () => {
  const result = calculateWinRate({ wins: 0, losses: 0, breakevens: 4 });

  assert.equal(result.winRatePercent, 0);
  assert.equal(result.breakevenRatePercent, 100);
  assert.equal(result.decisiveWinRate, null);
  assert.equal(result.decisiveWinRatePercent, null);
});

test("calculateWinRate rejects empty, fractional, negative, and non-finite counts", () => {
  assert.throws(
    () => calculateWinRate({ wins: 0, losses: 0 }),
    /At least one trade is required/,
  );
  assert.throws(
    () => calculateWinRate({ wins: 1.5, losses: 1 }),
    /wins must be a whole number/,
  );
  assert.throws(
    () => calculateWinRate({ wins: -1, losses: 1 }),
    /wins must be greater than or equal to 0/,
  );
  assert.throws(
    () => calculateWinRate({ wins: Number.NaN, losses: 1 }),
    /wins must be a finite number/,
  );
});

test("calculateExpectancy derives payoff, profit factor, and scenario projection", () => {
  const result = calculateExpectancy({
    wins: 4,
    losses: 6,
    averageWin: 200,
    averageLoss: 100,
    scenarioTrades: 50,
  });

  assert.equal(result.expectancyPerTrade, 20);
  assert.equal(result.payoffRatio, 2);
  assert.equal(result.payoffRatioStatus, "finite");
  assertClose(result.profitFactor ?? Number.NaN, 4 / 3);
  assert.equal(result.profitFactorStatus, "finite");
  assert.equal(result.grossProfit, 800);
  assert.equal(result.grossLoss, 600);
  assert.equal(result.scenarioProjection, 1_000);
});

test("calculateExpectancy gives breakevens zero weight and handles no-loss samples", () => {
  const result = calculateExpectancy({
    wins: 3,
    losses: 0,
    breakevens: 2,
    averageWin: 100,
    averageLoss: 0,
    scenarioTrades: 10,
  });

  assert.equal(result.expectancyPerTrade, 60);
  assert.equal(result.scenarioProjection, 600);
  assert.equal(result.payoffRatio, Number.POSITIVE_INFINITY);
  assert.equal(result.payoffRatioStatus, "infinite");
  assert.equal(result.profitFactor, Number.POSITIVE_INFINITY);
  assert.equal(result.profitFactorStatus, "infinite");
});

test("calculateExpectancy rejects inconsistent averages and invalid scenarios", () => {
  assert.throws(
    () => calculateExpectancy({ wins: 0, losses: 2, averageWin: 50, averageLoss: 25 }),
    /averageWin must be 0 when wins is 0/,
  );
  assert.throws(
    () => calculateExpectancy({ wins: 2, losses: 0, averageWin: 50, averageLoss: 25 }),
    /averageLoss must be 0 when losses is 0/,
  );
  assert.throws(
    () => calculateExpectancy({
      wins: 1,
      losses: 1,
      averageWin: 50,
      averageLoss: 25,
      scenarioTrades: Number.POSITIVE_INFINITY,
    }),
    /scenarioTrades must be a finite number/,
  );
});

test("calculateProfitFactor calculates finite, infinite, and undefined ratios", () => {
  assert.deepEqual(calculateProfitFactor({ grossProfit: 4_000, grossLoss: 2_500 }), {
    grossProfit: 4_000,
    grossLoss: 2_500,
    netProfit: 1_500,
    profitFactor: 1.6,
    status: "finite",
  });

  const noLosses = calculateProfitFactor({ grossProfit: 500, grossLoss: 0 });
  assert.equal(noLosses.profitFactor, Number.POSITIVE_INFINITY);
  assert.equal(noLosses.status, "infinite");

  const noOutcomes = calculateProfitFactor({ grossProfit: 0, grossLoss: 0 });
  assert.equal(noOutcomes.profitFactor, null);
  assert.equal(noOutcomes.status, "undefined");
});

test("calculateProfitFactor rejects negative magnitudes and non-finite inputs", () => {
  assert.throws(
    () => calculateProfitFactor({ grossProfit: 10, grossLoss: -1 }),
    /grossLoss must be greater than or equal to 0/,
  );
  assert.throws(
    () => calculateProfitFactor({ grossProfit: Number.POSITIVE_INFINITY, grossLoss: 1 }),
    /grossProfit must be a finite number/,
  );
});

test("calculateRiskReward calculates a long trade", () => {
  const result = calculateRiskReward({
    direction: "long",
    entryPrice: 100,
    stopPrice: 95,
    targetPrice: 115,
  });

  assert.equal(result.riskPerUnit, 5);
  assert.equal(result.rewardPerUnit, 15);
  assert.equal(result.rewardToRiskRatio, 3);
  assertClose(result.riskToRewardRatio, 1 / 3);
  assert.equal(result.breakEvenWinRatePercent, 25);
});

test("calculateRiskReward calculates a short trade", () => {
  const result = calculateRiskReward({
    direction: "short",
    entryPrice: 100,
    stopPrice: 104,
    targetPrice: 88,
  });

  assert.equal(result.riskPerUnit, 4);
  assert.equal(result.rewardPerUnit, 12);
  assert.equal(result.rewardToRiskRatio, 3);
  assert.equal(result.breakEvenWinRatePercent, 25);
});

test("calculateRiskReward rejects stops and targets on the wrong side", () => {
  assert.throws(
    () => calculateRiskReward({
      direction: "long",
      entryPrice: 100,
      stopPrice: 101,
      targetPrice: 110,
    }),
    /stopPrice must be below entryPrice for a long trade/,
  );
  assert.throws(
    () => calculateRiskReward({
      direction: "short",
      entryPrice: 100,
      stopPrice: 105,
      targetPrice: 101,
    }),
    /targetPrice must be below entryPrice for a short trade/,
  );
});

test("calculateBreakEvenWinRate derives the payoff ratio and required rate", () => {
  const result = calculateBreakEvenWinRate({ averageWin: 200, averageLoss: 100 });

  assert.equal(result.payoffRatio, 2);
  assertClose(result.breakEvenWinRate, 1 / 3);
  assertClose(result.breakEvenWinRatePercent, 100 / 3);
});

test("calculateBreakEvenWinRate rejects zero and non-finite averages", () => {
  assert.throws(
    () => calculateBreakEvenWinRate({ averageWin: 0, averageLoss: 100 }),
    /averageWin must be greater than 0/,
  );
  assert.throws(
    () => calculateBreakEvenWinRate({ averageWin: 100, averageLoss: Number.NaN }),
    /averageLoss must be a finite number/,
  );
});

test("calculatePositionSize returns fractional long units, risk, and notional", () => {
  const result = calculatePositionSize({
    direction: "long",
    accountEquity: 10_000,
    riskPercent: 1,
    entryPrice: 50,
    stopPrice: 47,
  });

  assert.equal(result.unitMode, "fractional");
  assert.equal(result.requestedRiskAmount, 100);
  assert.equal(result.riskPerUnit, 3);
  assertClose(result.exactUnits, 100 / 3);
  assertClose(result.units, 100 / 3);
  assertClose(result.actualRiskAmount, 100);
  assertClose(result.unusedRiskAmount, 0);
  assertClose(result.notionalValue, 5_000 / 3);
});

test("calculatePositionSize rounds whole short units down without exceeding risk", () => {
  const result = calculatePositionSize({
    direction: "short",
    accountEquity: 10_000,
    riskPercent: 1,
    entryPrice: 50,
    stopPrice: 53,
    unitMode: "whole",
  });

  assert.equal(result.exactUnits, 100 / 3);
  assert.equal(result.units, 33);
  assert.equal(result.actualRiskAmount, 99);
  assert.equal(result.unusedRiskAmount, 1);
  assert.equal(result.notionalValue, 1_650);
});

test("calculatePositionSize can safely return zero whole units", () => {
  const result = calculatePositionSize({
    direction: "long",
    accountEquity: 100,
    riskPercent: 1,
    entryPrice: 100,
    stopPrice: 90,
    unitMode: "whole",
  });

  assert.equal(result.exactUnits, 0.1);
  assert.equal(result.units, 0);
  assert.equal(result.actualRiskAmount, 0);
  assert.equal(result.notionalValue, 0);
});

test("calculatePositionSize validates equity, risk, prices, and unit mode", () => {
  assert.throws(
    () => calculatePositionSize({
      direction: "long",
      accountEquity: -1,
      riskPercent: 1,
      entryPrice: 100,
      stopPrice: 90,
    }),
    /accountEquity must be greater than 0/,
  );
  assert.throws(
    () => calculatePositionSize({
      direction: "long",
      accountEquity: 1_000,
      riskPercent: 101,
      entryPrice: 100,
      stopPrice: 90,
    }),
    /riskPercent must be less than or equal to 100/,
  );
  assert.throws(
    () => calculatePositionSize({
      direction: "short",
      accountEquity: 1_000,
      riskPercent: 1,
      entryPrice: 100,
      stopPrice: 90,
    }),
    /stopPrice must be above entryPrice for a short trade/,
  );
  assert.throws(
    () => calculatePositionSize({
      direction: "long",
      accountEquity: 1_000,
      riskPercent: 1,
      entryPrice: Number.NaN,
      stopPrice: 90,
    }),
    /entryPrice must be a finite number/,
  );
});

test("calculateMaximumDrawdown returns the maximum percentage episode", () => {
  const result = calculateMaximumDrawdown([100, 120, 90, 130, 104, 140]);

  assert.equal(result.maxDrawdownAbsolute, 30);
  assert.equal(result.maxDrawdownPercent, 25);
  assert.equal(result.peakIndex, 1);
  assert.equal(result.troughIndex, 2);
  assert.equal(result.peakEquity, 120);
  assert.equal(result.troughEquity, 90);
});

test("calculateMaximumDrawdown reports zero for a rising or one-point series", () => {
  assert.deepEqual(calculateMaximumDrawdown([100, 110, 120]), {
    maxDrawdownAbsolute: 0,
    maxDrawdownPercent: 0,
    peakIndex: 0,
    troughIndex: 0,
    peakEquity: 100,
    troughEquity: 100,
  });
  assert.deepEqual(calculateMaximumDrawdown([50]), {
    maxDrawdownAbsolute: 0,
    maxDrawdownPercent: 0,
    peakIndex: 0,
    troughIndex: 0,
    peakEquity: 50,
    troughEquity: 50,
  });
});

test("calculateMaximumDrawdown rejects empty, zero, negative, and non-finite equity", () => {
  assert.throws(() => calculateMaximumDrawdown([]), /at least one equity value/);
  assert.throws(() => calculateMaximumDrawdown([100, 0]), /equitySeries\[1\] must be greater than 0/);
  assert.throws(() => calculateMaximumDrawdown([100, -1]), /equitySeries\[1\] must be greater than 0/);
  assert.throws(
    () => calculateMaximumDrawdown([100, Number.POSITIVE_INFINITY]),
    /equitySeries\[1\] must be a finite number/,
  );
});

test("calculateTradingRoi calculates gains and losses", () => {
  assert.deepEqual(calculateTradingRoi({ initialCapital: 10_000, netProfit: 1_500 }), {
    initialCapital: 10_000,
    netProfit: 1_500,
    endingCapital: 11_500,
    roi: 0.15,
    roiPercent: 15,
  });

  assert.deepEqual(calculateTradingRoi({ initialCapital: 10_000, netProfit: -2_500 }), {
    initialCapital: 10_000,
    netProfit: -2_500,
    endingCapital: 7_500,
    roi: -0.25,
    roiPercent: -25,
  });
});

test("calculateTradingRoi rejects invalid capital and non-finite profit", () => {
  assert.throws(
    () => calculateTradingRoi({ initialCapital: 0, netProfit: 100 }),
    /initialCapital must be greater than 0/,
  );
  assert.throws(
    () => calculateTradingRoi({ initialCapital: 1_000, netProfit: Number.NaN }),
    /netProfit must be a finite number/,
  );
});
