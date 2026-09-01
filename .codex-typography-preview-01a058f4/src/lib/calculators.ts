export type TradeDirection = "long" | "short";
export type PositionUnitMode = "fractional" | "whole";
export type RatioStatus = "finite" | "infinite" | "undefined";

export interface RatioResult {
  value: number | null;
  status: RatioStatus;
}

export interface WinRateInput {
  wins: number;
  losses: number;
  breakevens?: number;
}

export interface WinRateResult {
  wins: number;
  losses: number;
  breakevens: number;
  totalTrades: number;
  winRate: number;
  lossRate: number;
  breakevenRate: number;
  winRatePercent: number;
  lossRatePercent: number;
  breakevenRatePercent: number;
  decisiveWinRate: number | null;
  decisiveWinRatePercent: number | null;
}

export interface ProfitFactorInput {
  grossProfit: number;
  grossLoss: number;
}

export interface ProfitFactorResult {
  grossProfit: number;
  grossLoss: number;
  netProfit: number;
  profitFactor: number | null;
  status: RatioStatus;
}

export interface ExpectancyInput extends WinRateInput {
  averageWin: number;
  averageLoss: number;
  scenarioTrades?: number;
}

export interface ExpectancyResult extends WinRateResult {
  averageWin: number;
  averageLoss: number;
  expectancyPerTrade: number;
  payoffRatio: number | null;
  payoffRatioStatus: RatioStatus;
  grossProfit: number;
  grossLoss: number;
  profitFactor: number | null;
  profitFactorStatus: RatioStatus;
  scenarioTrades: number;
  scenarioProjection: number;
}

export interface RiskRewardInput {
  direction: TradeDirection;
  entryPrice: number;
  stopPrice: number;
  targetPrice: number;
}

export interface RiskRewardResult extends RiskRewardInput {
  riskPerUnit: number;
  rewardPerUnit: number;
  rewardToRiskRatio: number;
  riskToRewardRatio: number;
  breakEvenWinRate: number;
  breakEvenWinRatePercent: number;
}

export interface BreakEvenWinRateInput {
  averageWin: number;
  averageLoss: number;
}

export interface BreakEvenWinRateResult extends BreakEvenWinRateInput {
  payoffRatio: number;
  breakEvenWinRate: number;
  breakEvenWinRatePercent: number;
}

export interface PositionSizeInput {
  direction: TradeDirection;
  accountEquity: number;
  riskPercent: number;
  entryPrice: number;
  stopPrice: number;
  unitMode?: PositionUnitMode;
}

export interface PositionSizeResult {
  direction: TradeDirection;
  unitMode: PositionUnitMode;
  accountEquity: number;
  riskPercent: number;
  requestedRiskAmount: number;
  riskPerUnit: number;
  exactUnits: number;
  units: number;
  actualRiskAmount: number;
  unusedRiskAmount: number;
  notionalValue: number;
}

export interface MaximumDrawdownResult {
  maxDrawdownAbsolute: number;
  maxDrawdownPercent: number;
  peakIndex: number;
  troughIndex: number;
  peakEquity: number;
  troughEquity: number;
}

export interface TradingRoiInput {
  initialCapital: number;
  netProfit: number;
}

export interface TradingRoiResult extends TradingRoiInput {
  endingCapital: number;
  roi: number;
  roiPercent: number;
}

function assertFiniteNumber(value: number, name: string): void {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new TypeError(`${name} must be a finite number.`);
  }
}

function assertNonNegativeNumber(value: number, name: string): void {
  assertFiniteNumber(value, name);
  if (value < 0) {
    throw new RangeError(`${name} must be greater than or equal to 0.`);
  }
}

function assertPositiveNumber(value: number, name: string): void {
  assertFiniteNumber(value, name);
  if (value <= 0) {
    throw new RangeError(`${name} must be greater than 0.`);
  }
}

function assertNonNegativeInteger(value: number, name: string): void {
  assertNonNegativeNumber(value, name);
  if (!Number.isInteger(value)) {
    throw new RangeError(`${name} must be a whole number.`);
  }
}

function assertDirection(direction: TradeDirection): void {
  if (direction !== "long" && direction !== "short") {
    throw new RangeError('direction must be either "long" or "short".');
  }
}

function divideAsRatio(numerator: number, denominator: number): RatioResult {
  if (denominator === 0) {
    if (numerator === 0) {
      return { value: null, status: "undefined" };
    }

    return { value: Number.POSITIVE_INFINITY, status: "infinite" };
  }

  return { value: numerator / denominator, status: "finite" };
}

function riskPerUnitForTrade(
  direction: TradeDirection,
  entryPrice: number,
  stopPrice: number,
): number {
  assertDirection(direction);
  assertPositiveNumber(entryPrice, "entryPrice");
  assertPositiveNumber(stopPrice, "stopPrice");

  if (direction === "long") {
    if (stopPrice >= entryPrice) {
      throw new RangeError("stopPrice must be below entryPrice for a long trade.");
    }

    return entryPrice - stopPrice;
  }

  if (stopPrice <= entryPrice) {
    throw new RangeError("stopPrice must be above entryPrice for a short trade.");
  }

  return stopPrice - entryPrice;
}

export function calculateWinRate(input: WinRateInput): WinRateResult {
  const breakevens = input.breakevens ?? 0;

  assertNonNegativeInteger(input.wins, "wins");
  assertNonNegativeInteger(input.losses, "losses");
  assertNonNegativeInteger(breakevens, "breakevens");

  const totalTrades = input.wins + input.losses + breakevens;
  if (totalTrades === 0) {
    throw new RangeError("At least one trade is required to calculate win rate.");
  }

  const decisiveTrades = input.wins + input.losses;
  const winRate = input.wins / totalTrades;
  const lossRate = input.losses / totalTrades;
  const breakevenRate = breakevens / totalTrades;
  const decisiveWinRate = decisiveTrades === 0 ? null : input.wins / decisiveTrades;

  return {
    wins: input.wins,
    losses: input.losses,
    breakevens,
    totalTrades,
    winRate,
    lossRate,
    breakevenRate,
    winRatePercent: winRate * 100,
    lossRatePercent: lossRate * 100,
    breakevenRatePercent: breakevenRate * 100,
    decisiveWinRate,
    decisiveWinRatePercent: decisiveWinRate === null ? null : decisiveWinRate * 100,
  };
}

export function calculateProfitFactor(input: ProfitFactorInput): ProfitFactorResult {
  assertNonNegativeNumber(input.grossProfit, "grossProfit");
  assertNonNegativeNumber(input.grossLoss, "grossLoss");

  const ratio = divideAsRatio(input.grossProfit, input.grossLoss);

  return {
    grossProfit: input.grossProfit,
    grossLoss: input.grossLoss,
    netProfit: input.grossProfit - input.grossLoss,
    profitFactor: ratio.value,
    status: ratio.status,
  };
}

export function calculateExpectancy(input: ExpectancyInput): ExpectancyResult {
  const rates = calculateWinRate(input);
  const scenarioTrades = input.scenarioTrades ?? rates.totalTrades;

  assertNonNegativeNumber(input.averageWin, "averageWin");
  assertNonNegativeNumber(input.averageLoss, "averageLoss");
  assertNonNegativeInteger(scenarioTrades, "scenarioTrades");

  if (input.wins === 0 && input.averageWin !== 0) {
    throw new RangeError("averageWin must be 0 when wins is 0.");
  }
  if (input.wins > 0 && input.averageWin === 0) {
    throw new RangeError("averageWin must be greater than 0 when wins is greater than 0.");
  }
  if (input.losses === 0 && input.averageLoss !== 0) {
    throw new RangeError("averageLoss must be 0 when losses is 0.");
  }
  if (input.losses > 0 && input.averageLoss === 0) {
    throw new RangeError("averageLoss must be greater than 0 when losses is greater than 0.");
  }

  const expectancyPerTrade =
    rates.winRate * input.averageWin - rates.lossRate * input.averageLoss;
  const grossProfit = input.wins * input.averageWin;
  const grossLoss = input.losses * input.averageLoss;
  const payoffRatio = divideAsRatio(input.averageWin, input.averageLoss);
  const profitFactor = calculateProfitFactor({ grossProfit, grossLoss });

  return {
    ...rates,
    averageWin: input.averageWin,
    averageLoss: input.averageLoss,
    expectancyPerTrade,
    payoffRatio: payoffRatio.value,
    payoffRatioStatus: payoffRatio.status,
    grossProfit,
    grossLoss,
    profitFactor: profitFactor.profitFactor,
    profitFactorStatus: profitFactor.status,
    scenarioTrades,
    scenarioProjection: expectancyPerTrade * scenarioTrades,
  };
}

export function calculateRiskReward(input: RiskRewardInput): RiskRewardResult {
  const riskPerUnit = riskPerUnitForTrade(
    input.direction,
    input.entryPrice,
    input.stopPrice,
  );
  assertPositiveNumber(input.targetPrice, "targetPrice");

  let rewardPerUnit: number;
  if (input.direction === "long") {
    if (input.targetPrice <= input.entryPrice) {
      throw new RangeError("targetPrice must be above entryPrice for a long trade.");
    }
    rewardPerUnit = input.targetPrice - input.entryPrice;
  } else {
    if (input.targetPrice >= input.entryPrice) {
      throw new RangeError("targetPrice must be below entryPrice for a short trade.");
    }
    rewardPerUnit = input.entryPrice - input.targetPrice;
  }

  const rewardToRiskRatio = rewardPerUnit / riskPerUnit;
  const riskToRewardRatio = riskPerUnit / rewardPerUnit;
  const breakEvenWinRate = riskPerUnit / (riskPerUnit + rewardPerUnit);

  return {
    ...input,
    riskPerUnit,
    rewardPerUnit,
    rewardToRiskRatio,
    riskToRewardRatio,
    breakEvenWinRate,
    breakEvenWinRatePercent: breakEvenWinRate * 100,
  };
}

export function calculateBreakEvenWinRate(
  input: BreakEvenWinRateInput,
): BreakEvenWinRateResult {
  assertPositiveNumber(input.averageWin, "averageWin");
  assertPositiveNumber(input.averageLoss, "averageLoss");

  const breakEvenWinRate = input.averageLoss / (input.averageWin + input.averageLoss);

  return {
    ...input,
    payoffRatio: input.averageWin / input.averageLoss,
    breakEvenWinRate,
    breakEvenWinRatePercent: breakEvenWinRate * 100,
  };
}

export function calculatePositionSize(input: PositionSizeInput): PositionSizeResult {
  const unitMode = input.unitMode ?? "fractional";

  assertPositiveNumber(input.accountEquity, "accountEquity");
  assertPositiveNumber(input.riskPercent, "riskPercent");
  if (input.riskPercent > 100) {
    throw new RangeError("riskPercent must be less than or equal to 100.");
  }
  if (unitMode !== "fractional" && unitMode !== "whole") {
    throw new RangeError('unitMode must be either "fractional" or "whole".');
  }

  const riskPerUnit = riskPerUnitForTrade(
    input.direction,
    input.entryPrice,
    input.stopPrice,
  );
  const requestedRiskAmount = input.accountEquity * (input.riskPercent / 100);
  const exactUnits = requestedRiskAmount / riskPerUnit;
  const units = unitMode === "whole" ? Math.floor(exactUnits) : exactUnits;
  const actualRiskAmount = units * riskPerUnit;

  return {
    direction: input.direction,
    unitMode,
    accountEquity: input.accountEquity,
    riskPercent: input.riskPercent,
    requestedRiskAmount,
    riskPerUnit,
    exactUnits,
    units,
    actualRiskAmount,
    unusedRiskAmount: requestedRiskAmount - actualRiskAmount,
    notionalValue: units * input.entryPrice,
  };
}

export function calculateMaximumDrawdown(
  equitySeries: readonly number[],
): MaximumDrawdownResult {
  if (!Array.isArray(equitySeries) || equitySeries.length === 0) {
    throw new RangeError("equitySeries must contain at least one equity value.");
  }

  equitySeries.forEach((equity, index) => {
    assertPositiveNumber(equity, `equitySeries[${index}]`);
  });

  let runningPeak = equitySeries[0];
  let runningPeakIndex = 0;
  let maxDrawdownAbsolute = 0;
  let maxDrawdownPercent = 0;
  let peakIndex = 0;
  let troughIndex = 0;

  for (let index = 1; index < equitySeries.length; index += 1) {
    const equity = equitySeries[index];

    if (equity > runningPeak) {
      runningPeak = equity;
      runningPeakIndex = index;
      continue;
    }

    const drawdownAbsolute = runningPeak - equity;
    const drawdownPercent = (drawdownAbsolute / runningPeak) * 100;

    // Maximum drawdown is conventionally selected by percentage decline.
    // Absolute drawdown is reported for that same peak-to-trough episode.
    if (drawdownPercent > maxDrawdownPercent) {
      maxDrawdownAbsolute = drawdownAbsolute;
      maxDrawdownPercent = drawdownPercent;
      peakIndex = runningPeakIndex;
      troughIndex = index;
    }
  }

  return {
    maxDrawdownAbsolute,
    maxDrawdownPercent,
    peakIndex,
    troughIndex,
    peakEquity: equitySeries[peakIndex],
    troughEquity: equitySeries[troughIndex],
  };
}

export function calculateTradingRoi(input: TradingRoiInput): TradingRoiResult {
  assertPositiveNumber(input.initialCapital, "initialCapital");
  assertFiniteNumber(input.netProfit, "netProfit");

  const roi = input.netProfit / input.initialCapital;

  return {
    ...input,
    endingCapital: input.initialCapital + input.netProfit,
    roi,
    roiPercent: roi * 100,
  };
}
