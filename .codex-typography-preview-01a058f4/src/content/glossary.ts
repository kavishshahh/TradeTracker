export type GlossaryEntry = {
  slug: string;
  term: string;
  seoTitle: string;
  description: string;
  definition: string;
  formula: string;
  example: string;
  interpretation: string[];
  mistakes: string[];
  relatedTool: string;
  relatedArticle?: string;
  updated: string;
};

export const glossary: GlossaryEntry[] = [
  {
    slug: "trading-expectancy",
    term: "Trading expectancy",
    seoTitle: "Trading Expectancy: Definition, Formula, and Example",
    description: "Trading expectancy is the average result per trade implied by win frequency and average win and loss size.",
    definition: "Trading expectancy estimates the average outcome per trade across a defined sample. A positive historical expectancy means the entered sample produced a positive average result; it is descriptive, not a guarantee about the next trade.",
    formula: "Expectancy = (win probability × average win) − (loss probability × average loss)",
    example: "If 18 of 40 trades win at $180 on average and 22 lose $100 on average, expectancy is (18/40 × 180) − (22/40 × 100) = $26 per trade.",
    interpretation: ["Use the same unit for average wins and losses, such as dollars, percentage points, or R.", "Keep breakeven trades in the total-trade denominator when that is how your journal defines win rate.", "Review sample size, outcome distribution, fees, and setup consistency alongside the average."],
    mistakes: ["Mixing gross and net outcomes.", "Treating expectancy from a handful of trades as stable evidence.", "Assuming positive historical expectancy predicts a future return."],
    relatedTool: "trading-expectancy-calculator",
    relatedArticle: "how-to-calculate-trading-expectancy",
    updated: "2026-08-31",
  },
  {
    slug: "profit-factor",
    term: "Profit factor",
    seoTitle: "Profit Factor: Definition, Formula, and Example",
    description: "Profit factor compares gross winning value with the absolute value of gross losing value in a trading sample.",
    definition: "Profit factor is the total value of winning trades divided by the absolute total value of losing trades. It summarizes the balance between gains and losses but does not describe timing, drawdown, or the number of trades.",
    formula: "Profit factor = gross profit ÷ gross loss",
    example: "Gross wins of $8,400 divided by gross losses of $4,000 produce a profit factor of 2.10. Net result before omitted costs is $4,400.",
    interpretation: ["A value above 1 means gross wins exceeded gross losses in the sample.", "A value below 1 means gross losses exceeded gross wins.", "When gross loss is zero, the ratio is unbounded; that edge case should be labeled rather than replaced with a made-up finite value."],
    mistakes: ["Entering gross loss as a negative number when the formula expects a positive magnitude.", "Comparing ratios built with different fee conventions.", "Ignoring outlier dependence and sample size."],
    relatedTool: "profit-factor-calculator",
    relatedArticle: "trading-journal-metrics-that-matter",
    updated: "2026-08-31",
  },
  {
    slug: "win-rate",
    term: "Trading win rate",
    seoTitle: "Trading Win Rate: Definition, Formula, and Example",
    description: "Trading win rate is the percentage of closed trades classified as winners under a stated denominator convention.",
    definition: "Win rate measures how frequently trades finish profitably in a defined sample. It says nothing by itself about the size of wins, losses, fees, or risk taken.",
    formula: "Win rate = winning trades ÷ total closed trades × 100",
    example: "With 24 winners, 14 losers, and 2 breakevens, overall win rate is 24 ÷ 40 = 60%. If breakevens are excluded, decisive win rate is 24 ÷ 38 = 63.16%.",
    interpretation: ["State whether breakevens remain in the denominator.", "Pair win rate with average win, average loss, expectancy, and costs.", "Compare consistent samples and avoid treating an arbitrary target as universal."],
    mistakes: ["Counting open trades as outcomes.", "Changing breakeven treatment between periods.", "Optimizing win frequency while ignoring loss magnitude."],
    relatedTool: "win-rate-calculator",
    relatedArticle: "trading-journal-metrics-that-matter",
    updated: "2026-08-31",
  },
  {
    slug: "average-win-vs-average-loss",
    term: "Average win vs average loss",
    seoTitle: "Average Win vs Average Loss in Trading",
    description: "Average win and average loss describe the typical magnitude of profitable and losing closed trades.",
    definition: "Average win is total winning value divided by winning trades. Average loss is the absolute total losing value divided by losing trades. Their relationship is often called the payoff ratio.",
    formula: "Payoff ratio = average win ÷ average loss",
    example: "Average wins of $200 and average losses of $100 produce a 2.00 payoff ratio. The break-even win rate before costs is 100 ÷ (200 + 100) = 33.33%.",
    interpretation: ["Use net outcomes when you want costs reflected in the comparison.", "Averages can hide skew and outliers, so inspect the distribution and largest trades.", "Payoff size and win frequency work together; neither is a complete performance measure."],
    mistakes: ["Entering average loss as a negative magnitude in a formula that expects positive loss size.", "Combining unrelated setups or instruments.", "Assuming the average stays constant as execution or market conditions change."],
    relatedTool: "break-even-win-rate-calculator",
    relatedArticle: "trading-journal-metrics-that-matter",
    updated: "2026-08-31",
  },
  {
    slug: "maximum-drawdown",
    term: "Maximum drawdown",
    seoTitle: "Maximum Drawdown: Definition, Formula, and Example",
    description: "Maximum drawdown is the largest observed decline from a prior equity peak to a later trough.",
    definition: "Maximum drawdown describes the worst peak-to-trough decline in an equity sequence. It is path-dependent: the order of values matters, and deposits or withdrawals should be separated from trading performance when possible.",
    formula: "Drawdown % = (peak equity − later trough equity) ÷ peak equity × 100",
    example: "For an equity path of $10,000 → $11,500 → $10,800 → $9,200 → $10,400, maximum drawdown is $2,300, or 20%, from $11,500 to $9,200.",
    interpretation: ["Report both the absolute decline and the percentage relative to the peak.", "Recovery time requires dates and is a separate measurement.", "Historical maximum drawdown is not a ceiling on a future loss."],
    mistakes: ["Sorting balances instead of preserving chronological order.", "Including cash deposits or withdrawals as if they were trading returns.", "Starting from cumulative P&L without a meaningful equity baseline."],
    relatedTool: "maximum-drawdown-calculator",
    relatedArticle: "trading-journal-metrics-that-matter",
    updated: "2026-08-31",
  },
  {
    slug: "risk-reward-ratio",
    term: "Risk/reward ratio",
    seoTitle: "Risk/Reward Ratio: Definition, Formula, and Example",
    description: "A risk/reward plan compares the price distance to a stop with the potential price distance to a target.",
    definition: "The reward-to-risk ratio compares potential reward per unit with planned risk per unit between an entry, stop, and target. It describes payoff geometry, not the probability that either level will be reached.",
    formula: "Reward-to-risk ratio = potential reward per unit ÷ risk per unit",
    example: "A long entry at $50, stop at $48, and target at $56 risks $2 for a potential $6 reward, a 3:1 reward-to-risk ratio.",
    interpretation: ["Validate that the stop and target are on the correct side of entry for the trade direction.", "The theoretical break-even win rate is risk ÷ (risk + reward) before costs.", "Actual exits, slippage, gaps, partial fills, and fees can differ from the plan."],
    mistakes: ["Calling risk-to-reward and reward-to-risk the same ratio without labeling it.", "Treating a distant target as equally probable.", "Ignoring execution and transaction costs."],
    relatedTool: "risk-reward-calculator",
    updated: "2026-08-31",
  },
];

export function getGlossaryEntry(slug: string) {
  return glossary.find((entry) => entry.slug === slug);
}
