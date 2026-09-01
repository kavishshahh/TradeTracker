"use client";

import {
  calculateBreakEvenWinRate,
  calculateExpectancy,
  calculateMaximumDrawdown,
  calculatePositionSize,
  calculateProfitFactor,
  calculateRiskReward,
  calculateTradingRoi,
  calculateWinRate,
  type TradeDirection,
} from "@/lib/calculators";
import { trackPublicEvent } from "@/lib/analytics";
import type { ToolDefinition } from "@/content/tools";
import Link from "next/link";
import { useState, type FormEvent } from "react";

type FormValue = string | number;
type FormState = Record<string, FormValue>;

const defaults: Record<string, FormState> = {
  "profit-factor-calculator": { grossProfit: "8400", grossLoss: "4000" },
  "trading-expectancy-calculator": {
    wins: "18",
    losses: "22",
    breakevens: "0",
    averageWin: "180",
    averageLoss: "100",
    scenarioTrades: "40",
  },
  "win-rate-calculator": { wins: "24", losses: "14", breakevens: "2" },
  "risk-reward-calculator": {
    direction: "long",
    entryPrice: "50",
    stopPrice: "48",
    targetPrice: "56",
  },
  "break-even-win-rate-calculator": { averageWin: "200", averageLoss: "100" },
  "position-size-calculator": {
    direction: "long",
    accountEquity: "25000",
    riskPercent: "0.5",
    entryPrice: "50",
    stopPrice: "48.75",
    unitMode: "whole",
  },
  "maximum-drawdown-calculator": { equitySeries: "10000, 11500, 10800, 9200, 10400" },
  "trading-roi-calculator": { initialCapital: "20000", netProfit: "1500" },
};

function numberValue(values: FormState, key: string): number {
  const value = values[key];
  return typeof value === "number" ? value : Number(value);
}

function formatNumber(value: number | null, digits = 2): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (value === Number.POSITIVE_INFINITY) return "∞";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatSigned(value: number | null, digits = 2): string {
  if (value === null || Number.isNaN(value)) return "—";
  if (value === Number.POSITIVE_INFINITY) return "∞";
  return `${value > 0 ? "+" : ""}${formatNumber(value, digits)}`;
}

function Field({
  label,
  name,
  value,
  onChange,
  help,
  step = "any",
  min,
}: {
  label: string;
  name: string;
  value: FormValue;
  onChange: (name: string, value: string) => void;
  help?: string;
  step?: string;
  min?: string;
}) {
  return (
    <label className="calculator-field">
      <span>{label}</span>
      <input
        name={name}
        type="number"
        inputMode="decimal"
        value={value}
        onChange={(event) => onChange(name, event.target.value)}
        step={step}
        min={min}
        required
      />
      {help && <small>{help}</small>}
    </label>
  );
}

function DirectionField({
  value,
  onChange,
}: {
  value: FormValue;
  onChange: (name: string, value: string) => void;
}) {
  return (
    <label className="calculator-field">
      <span>Trade direction</span>
      <select value={value} onChange={(event) => onChange("direction", event.target.value)}>
        <option value="long">Long</option>
        <option value="short">Short</option>
      </select>
      <small>Used to validate which side of entry the stop and target sit on.</small>
    </label>
  );
}

function ResultCard({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="calculator-result-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

export default function CalculatorForm({ tool }: { tool: ToolDefinition }) {
  const [values, setValues] = useState<FormState>(defaults[tool.slug] ?? {});
  const [result, setResult] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const updateValue = (name: string, value: string) => {
    setValues((current) => ({ ...current, [name]: value }));
    setError(null);
  };

  const calculate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    try {
      let nextResult: Record<string, string>;

      switch (tool.slug) {
        case "profit-factor-calculator": {
          const calculated = calculateProfitFactor({
            grossProfit: numberValue(values, "grossProfit"),
            grossLoss: numberValue(values, "grossLoss"),
          });
          nextResult = {
            primary: formatNumber(calculated.profitFactor),
            primaryLabel: calculated.status === "infinite" ? "Profit factor (unbounded)" : "Profit factor",
            secondary: formatSigned(calculated.netProfit),
            secondaryLabel: "Net result before omitted costs",
            note:
              calculated.status === "undefined"
                ? "No winning or losing value was entered."
                : calculated.status === "infinite"
                  ? "Gross loss is zero; this is not evidence that future loss is impossible."
                  : "Use the same cost convention for gross profit and gross loss.",
          };
          break;
        }
        case "trading-expectancy-calculator": {
          const calculated = calculateExpectancy({
            wins: numberValue(values, "wins"),
            losses: numberValue(values, "losses"),
            breakevens: numberValue(values, "breakevens"),
            averageWin: numberValue(values, "averageWin"),
            averageLoss: numberValue(values, "averageLoss"),
            scenarioTrades: numberValue(values, "scenarioTrades"),
          });
          nextResult = {
            primary: formatSigned(calculated.expectancyPerTrade),
            primaryLabel: "Expectancy per trade",
            secondary: formatSigned(calculated.scenarioProjection),
            secondaryLabel: `Projection for ${formatNumber(calculated.scenarioTrades, 0)} trades`,
            tertiary: formatNumber(calculated.payoffRatio),
            tertiaryLabel: "Payoff ratio",
            note: `Win rate ${formatNumber(calculated.winRatePercent)}% · loss rate ${formatNumber(calculated.lossRatePercent)}% · profit factor ${formatNumber(calculated.profitFactor)}`,
          };
          break;
        }
        case "win-rate-calculator": {
          const calculated = calculateWinRate({
            wins: numberValue(values, "wins"),
            losses: numberValue(values, "losses"),
            breakevens: numberValue(values, "breakevens"),
          });
          nextResult = {
            primary: `${formatNumber(calculated.winRatePercent)}%`,
            primaryLabel: "Overall win rate",
            secondary: calculated.decisiveWinRatePercent === null ? "—" : `${formatNumber(calculated.decisiveWinRatePercent)}%`,
            secondaryLabel: "Decisive-trade win rate",
            tertiary: `${formatNumber(calculated.breakevenRatePercent)}%`,
            tertiaryLabel: "Breakeven rate",
            note: `${calculated.totalTrades} total trades · ${calculated.wins} wins · ${calculated.losses} losses · ${calculated.breakevens} breakevens`,
          };
          break;
        }
        case "risk-reward-calculator": {
          const calculated = calculateRiskReward({
            direction: values.direction as TradeDirection,
            entryPrice: numberValue(values, "entryPrice"),
            stopPrice: numberValue(values, "stopPrice"),
            targetPrice: numberValue(values, "targetPrice"),
          });
          nextResult = {
            primary: `${formatNumber(calculated.rewardToRiskRatio)}:1`,
            primaryLabel: "Reward-to-risk ratio",
            secondary: formatNumber(calculated.riskPerUnit),
            secondaryLabel: "Risk per unit",
            tertiary: `${formatNumber(calculated.breakEvenWinRatePercent)}%`,
            tertiaryLabel: "Theoretical break-even win rate",
            note: `Potential reward per unit: ${formatNumber(calculated.rewardPerUnit)}. Costs, slippage, gaps, and probability are not modeled.`,
          };
          break;
        }
        case "break-even-win-rate-calculator": {
          const calculated = calculateBreakEvenWinRate({
            averageWin: numberValue(values, "averageWin"),
            averageLoss: numberValue(values, "averageLoss"),
          });
          nextResult = {
            primary: `${formatNumber(calculated.breakEvenWinRatePercent)}%`,
            primaryLabel: "Break-even win rate",
            secondary: formatNumber(calculated.payoffRatio),
            secondaryLabel: "Payoff ratio",
            note: "This threshold assumes the entered average net outcomes remain representative.",
          };
          break;
        }
        case "position-size-calculator": {
          const calculated = calculatePositionSize({
            direction: values.direction as TradeDirection,
            accountEquity: numberValue(values, "accountEquity"),
            riskPercent: numberValue(values, "riskPercent"),
            entryPrice: numberValue(values, "entryPrice"),
            stopPrice: numberValue(values, "stopPrice"),
            unitMode: values.unitMode as "fractional" | "whole",
          });
          nextResult = {
            primary: formatNumber(calculated.units, calculated.unitMode === "whole" ? 0 : 4),
            primaryLabel: calculated.unitMode === "whole" ? "Whole units" : "Position units",
            secondary: formatNumber(calculated.requestedRiskAmount),
            secondaryLabel: "Requested risk amount",
            tertiary: formatNumber(calculated.notionalValue),
            tertiaryLabel: "Notional value",
            note: `Exact mathematical size: ${formatNumber(calculated.exactUnits, 4)} · actual price risk: ${formatNumber(calculated.actualRiskAmount)} · unused risk after rounding: ${formatNumber(calculated.unusedRiskAmount)}`,
          };
          break;
        }
        case "maximum-drawdown-calculator": {
          const series = String(values.equitySeries)
            .split(/[\s,]+/)
            .filter(Boolean)
            .map(Number);
          const calculated = calculateMaximumDrawdown(series);
          nextResult = {
            primary: formatNumber(calculated.maxDrawdownAbsolute),
            primaryLabel: "Maximum drawdown",
            secondary: `${formatNumber(calculated.maxDrawdownPercent)}%`,
            secondaryLabel: "Peak-to-trough drawdown",
            note: `Peak ${formatNumber(calculated.peakEquity)} at observation ${calculated.peakIndex + 1} → trough ${formatNumber(calculated.troughEquity)} at observation ${calculated.troughIndex + 1}.`,
          };
          break;
        }
        case "trading-roi-calculator": {
          const calculated = calculateTradingRoi({
            initialCapital: numberValue(values, "initialCapital"),
            netProfit: numberValue(values, "netProfit"),
          });
          nextResult = {
            primary: `${formatSigned(calculated.roiPercent)}%`,
            primaryLabel: "Simple ROI",
            secondary: formatSigned(calculated.endingCapital),
            secondaryLabel: "Ending capital",
            note: "This is simple period ROI; it does not annualize or adjust for deposits and withdrawals.",
          };
          break;
        }
        default:
          throw new Error("This calculator is not available yet.");
      }

      setResult(nextResult);
      trackPublicEvent("calculator_completed", tool.slug);
    } catch (calculationError) {
      setResult(null);
      setError(calculationError instanceof Error ? calculationError.message : "Check the values and try again.");
    }
  };

  const renderFields = () => {
    switch (tool.slug) {
      case "profit-factor-calculator":
        return <><Field label="Gross profit" name="grossProfit" value={values.grossProfit} onChange={updateValue} min="0" /><Field label="Gross loss (positive magnitude)" name="grossLoss" value={values.grossLoss} onChange={updateValue} min="0" /></>;
      case "trading-expectancy-calculator":
        return <>
          <Field label="Winning trades" name="wins" value={values.wins} onChange={updateValue} step="1" min="0" />
          <Field label="Losing trades" name="losses" value={values.losses} onChange={updateValue} step="1" min="0" />
          <Field label="Breakeven trades" name="breakevens" value={values.breakevens} onChange={updateValue} step="1" min="0" />
          <Field label="Average win" name="averageWin" value={values.averageWin} onChange={updateValue} min="0" />
          <Field label="Average loss (positive magnitude)" name="averageLoss" value={values.averageLoss} onChange={updateValue} min="0" />
          <Field label="Scenario trades" name="scenarioTrades" value={values.scenarioTrades} onChange={updateValue} step="1" min="0" />
        </>;
      case "win-rate-calculator":
        return <><Field label="Winning trades" name="wins" value={values.wins} onChange={updateValue} step="1" min="0" /><Field label="Losing trades" name="losses" value={values.losses} onChange={updateValue} step="1" min="0" /><Field label="Breakeven trades" name="breakevens" value={values.breakevens} onChange={updateValue} step="1" min="0" /></>;
      case "risk-reward-calculator":
        return <><DirectionField value={values.direction} onChange={updateValue} /><Field label="Entry price" name="entryPrice" value={values.entryPrice} onChange={updateValue} min="0" /><Field label="Stop price" name="stopPrice" value={values.stopPrice} onChange={updateValue} min="0" /><Field label="Target price" name="targetPrice" value={values.targetPrice} onChange={updateValue} min="0" /></>;
      case "break-even-win-rate-calculator":
        return <><Field label="Average net win" name="averageWin" value={values.averageWin} onChange={updateValue} min="0" /><Field label="Average net loss (positive magnitude)" name="averageLoss" value={values.averageLoss} onChange={updateValue} min="0" /></>;
      case "position-size-calculator":
        return <><DirectionField value={values.direction} onChange={updateValue} /><Field label="Account equity" name="accountEquity" value={values.accountEquity} onChange={updateValue} min="0.0001" /><Field label="Risk per trade (%)" name="riskPercent" value={values.riskPercent} onChange={updateValue} min="0.0001" /><Field label="Entry price" name="entryPrice" value={values.entryPrice} onChange={updateValue} min="0.0001" /><Field label="Stop price" name="stopPrice" value={values.stopPrice} onChange={updateValue} min="0.0001" /><label className="calculator-field"><span>Unit rounding</span><select value={values.unitMode} onChange={(event) => updateValue("unitMode", event.target.value)}><option value="whole">Whole units</option><option value="fractional">Fractional units</option></select><small>Whole units round down; fractional units preserve the exact mathematical size.</small></label></>;
      case "maximum-drawdown-calculator":
        return <label className="calculator-field calculator-field-wide"><span>Equity values in chronological order</span><textarea name="equitySeries" value={values.equitySeries} onChange={(event) => updateValue("equitySeries", event.target.value)} rows={4} required /><small>Separate positive values with commas, spaces, or new lines. Keep deposits and withdrawals out or adjust for them first.</small></label>;
      case "trading-roi-calculator":
        return <><Field label="Starting capital" name="initialCapital" value={values.initialCapital} onChange={updateValue} min="0" /><Field label="Net profit or loss" name="netProfit" value={values.netProfit} onChange={updateValue} /></>;
      default:
        return null;
    }
  };

  return (
    <section className="calculator-shell" aria-label={`${tool.title} inputs and result`}>
      <div className="calculator-panel">
        <form onSubmit={calculate}>
          <div className="calculator-fields">{renderFields()}</div>
          {error && <p className="calculator-error" role="alert">{error}</p>}
          <button className="button button-large calculator-submit" type="submit">Calculate {tool.title.replace(/ calculator.*/, "")}</button>
        </form>
      </div>

      {result && (
        <div className="calculator-results" aria-live="polite">
          <p className="kicker">YOUR RESULT</p>
          <div className="calculator-result-grid">
            <ResultCard label={result.primaryLabel} value={result.primary} />
            {result.secondary && <ResultCard label={result.secondaryLabel} value={result.secondary} />}
            {result.tertiary && <ResultCard label={result.tertiaryLabel} value={result.tertiary} />}
          </div>
          {result.note && <p className="calculator-result-note">{result.note}</p>}
          <div className="calculator-next-step">
            <strong>Want this calculated automatically for every trade?</strong>
            <p>Record your history in TradeBud, then review the same metrics across a consistent sample.</p>
            <Link href="/free-trading-journal">See the free trading journal <span aria-hidden="true">→</span></Link>
          </div>
        </div>
      )}
    </section>
  );
}
