export type ToolFaq = {
  question: string;
  answer: string;
};

export type ToolDefinition = {
  slug: string;
  title: string;
  seoTitle: string;
  description: string;
  summary: string;
  formula: string;
  formulaNote: string;
  example: string;
  interpretation: string[];
  mistakes: string[];
  faq: ToolFaq[];
  relatedGlossary?: string;
  relatedArticle?: string;
  updated: string;
};

export const tools: ToolDefinition[] = [
  {
    slug: "profit-factor-calculator",
    title: "Profit factor calculator",
    seoTitle: "Profit Factor Calculator (Free)",
    description:
      "Calculate trading profit factor from gross winning and losing results, inspect net P&L, and understand zero-loss and small-sample edge cases.",
    summary:
      "Profit factor compares all winning value with the absolute value of all losing value in the same sample. It describes the balance of gains and losses; it does not show timing, drawdown, or whether one outlier produced most of the result.",
    formula: "Profit factor = gross profit ÷ gross loss",
    formulaNote:
      "Enter gross loss as a positive magnitude. When gross loss is zero and gross profit is positive, the ratio is mathematically unbounded and is shown as ∞ rather than an invented number.",
    example:
      "If winning trades total $8,400 and losing trades total $4,000 in absolute terms, profit factor is 8,400 ÷ 4,000 = 2.10. Net P&L before any omitted costs is $4,400.",
    interpretation: [
      "A value above 1 means gross winning value exceeded gross losing value in the selected sample.",
      "A value below 1 means gross losses exceeded gross wins.",
      "Compare the ratio across consistent time periods and setups, then inspect the trades behind it.",
    ],
    mistakes: [
      "Entering losses as a negative number instead of a positive magnitude.",
      "Mixing gross winners with fee-adjusted losers.",
      "Treating an infinite value from a no-loss sample as proof that risk is absent.",
      "Ignoring whether one unusually large winner dominates a small sample.",
    ],
    faq: [
      {
        question: "What does a profit factor of 1 mean?",
        answer:
          "It means gross winning value equals the absolute gross losing value for the sample. Any costs not already included would make the net result negative.",
      },
      {
        question: "Should fees be included?",
        answer:
          "For a net view, calculate each trade after the costs you intend to measure, then total the net winners and absolute net losers consistently.",
      },
      {
        question: "Can profit factor predict future performance?",
        answer:
          "No. It describes a historical or hypothetical sample. Market conditions, execution, costs, and the underlying process can change.",
      },
    ],
    relatedGlossary: "profit-factor",
    relatedArticle: "trading-journal-metrics-that-matter",
    updated: "2026-08-31",
  },
  {
    slug: "trading-expectancy-calculator",
    title: "Trading expectancy calculator",
    seoTitle: "Trading Expectancy Calculator (Free)",
    description:
      "Calculate expectancy per trade from wins, losses, breakevens, average win, and average loss, with payoff ratio and scenario projection.",
    summary:
      "Trading expectancy estimates the average result per trade in a recorded sample. This calculator uses trade counts so breakeven trades remain in the denominator instead of being silently classified as losses.",
    formula:
      "Expectancy = (win probability × average win) − (loss probability × average loss)",
    formulaNote:
      "Win and loss probabilities are each calculated over all entered trades, including breakevens. Average loss is entered as a positive magnitude. The result uses the same unit as the average outcomes.",
    example:
      "For 18 wins, 22 losses, 0 breakevens, a $180 average win, and a $100 average loss: (18/40 × 180) − (22/40 × 100) = $26 per trade.",
    interpretation: [
      "A positive result means the sample produced a positive average outcome per entered trade.",
      "The scenario projection multiplies historical expectancy by a chosen number of trades; it is not a forecast or confidence interval.",
      "Use the payoff ratio and profit factor to understand how the same expectancy was produced.",
    ],
    mistakes: [
      "Using gross wins with net losses or mixing currencies and units of risk.",
      "Excluding breakeven trades from total trades without documenting that rule.",
      "Treating a few trades or one outlier as a stable estimate.",
      "Assuming historical expectancy guarantees the next trade or future period.",
    ],
    faq: [
      {
        question: "What unit does expectancy use?",
        answer:
          "It uses the same unit as average win and average loss. Enter dollars for dollars per trade, percentage points for percentage points per trade, or R-multiples for R per trade.",
      },
      {
        question: "How are breakeven trades handled?",
        answer:
          "They add to total trades but not to winning or losing value, so both win and loss probabilities can sum to less than 100%.",
      },
      {
        question: "How many trades are enough?",
        answer:
          "There is no universal number. Stability depends on the process and outcome distribution. Inspect rolling samples, outliers, and whether the strategy or market conditions changed.",
      },
    ],
    relatedGlossary: "trading-expectancy",
    relatedArticle: "how-to-calculate-trading-expectancy",
    updated: "2026-08-31",
  },
  {
    slug: "win-rate-calculator",
    title: "Trading win rate calculator",
    seoTitle: "Trading Win Rate Calculator (Free)",
    description:
      "Calculate overall and decisive-trade win rate from winning, losing, and breakeven trades, with transparent denominator rules.",
    summary:
      "Win rate is the share of all closed trades classified as winners. Breakevens matter because including them in total trades produces a different result from calculating wins only against decisive wins and losses.",
    formula: "Win rate = winning trades ÷ total closed trades × 100",
    formulaNote:
      "This tool reports both overall win rate, where breakevens remain in the denominator, and decisive win rate, where breakevens are excluded. Label the convention whenever you compare results.",
    example:
      "With 24 winners, 14 losers, and 2 breakevens, overall win rate is 24 ÷ 40 = 60%. Decisive win rate is 24 ÷ 38 = 63.16%.",
    interpretation: [
      "Win rate measures frequency, not the size of wins and losses.",
      "A higher win rate can still produce a negative result when average losses are sufficiently larger than average wins.",
      "Use expectancy or profit factor alongside win rate before judging a sample.",
    ],
    mistakes: [
      "Changing how breakevens are classified between periods.",
      "Counting open trades or partial positions as final outcomes.",
      "Comparing win rates across unrelated setups without checking payoff size.",
      "Optimizing for win frequency while ignoring loss magnitude and costs.",
    ],
    faq: [
      {
        question: "Are breakeven trades losses?",
        answer:
          "Not automatically. This calculator keeps them as a separate category and shows both common denominator conventions.",
      },
      {
        question: "What is a good trading win rate?",
        answer:
          "There is no universal target. The relevant rate depends on average win, average loss, costs, and how consistently the same process was applied.",
      },
    ],
    relatedGlossary: "win-rate",
    relatedArticle: "trading-journal-metrics-that-matter",
    updated: "2026-08-31",
  },
  {
    slug: "risk-reward-calculator",
    title: "Risk/reward calculator",
    seoTitle: "Risk/Reward Ratio Calculator (Free)",
    description:
      "Calculate price risk, potential reward, reward-to-risk ratio, and break-even win rate for a direct-price long or short trade plan.",
    summary:
      "A planned reward-to-risk ratio compares the distance from entry to target with the distance from entry to stop. It describes the plan before costs and does not estimate the probability of reaching either level.",
    formula: "Reward-to-risk ratio = potential reward per unit ÷ risk per unit",
    formulaNote:
      "For a long plan the stop must be below entry and target above it. For a short plan the stop must be above entry and target below it. Fees, slippage, gaps, and partial exits are not included.",
    example:
      "A long entry at $50, stop at $48, and target at $56 risks $2 per unit for $6 potential reward. The reward-to-risk ratio is 3:1 and the theoretical break-even win rate before costs is 25%.",
    interpretation: [
      "The ratio describes payoff geometry, not trade quality or likelihood.",
      "The break-even rate assumes every win and loss reaches the entered levels and ignores costs.",
      "Compare planned levels with actual exits in your journal to measure execution drift.",
    ],
    mistakes: [
      "Reversing risk/reward and reward/risk without labeling the convention.",
      "Entering a stop or target on the wrong side of the entry.",
      "Assuming a larger target is equally likely to be reached.",
      "Ignoring fees, slippage, gaps, and partial exits.",
    ],
    faq: [
      {
        question: "Does a 3:1 ratio mean the trade is good?",
        answer:
          "No. It only means planned reward is three times planned risk. The setup still needs a defensible probability, execution plan, and realistic costs.",
      },
      {
        question: "What is the break-even win rate for 2:1?",
        answer:
          "Before costs and assuming full wins and losses, it is 1 ÷ (1 + 2) = 33.33%.",
      },
    ],
    relatedGlossary: "risk-reward-ratio",
    updated: "2026-08-31",
  },
  {
    slug: "break-even-win-rate-calculator",
    title: "Break-even win rate calculator",
    seoTitle: "Break-Even Win Rate Calculator",
    description:
      "Calculate the win rate required for zero expectancy from average net win and average net loss, plus payoff ratio.",
    summary:
      "Break-even win rate is the win frequency at which average expectancy equals zero for the entered payoff sizes. It is a mathematical threshold, not a recommended target or safety margin.",
    formula: "Break-even win rate = average loss ÷ (average win + average loss) × 100",
    formulaNote:
      "Use average net win and average net loss after the costs you want included. Enter average loss as a positive magnitude.",
    example:
      "If average net win is $200 and average net loss is $100, break-even win rate is 100 ÷ (200 + 100) = 33.33%.",
    interpretation: [
      "A historical win rate above the threshold implies positive expectancy only if the entered average outcomes remain representative.",
      "A historical win rate below the threshold implies negative expectancy under those same assumptions.",
      "Use a margin for estimation error rather than treating the threshold as precise evidence about the future.",
    ],
    mistakes: [
      "Using gross average wins and fee-adjusted average losses.",
      "Entering average loss as a negative number.",
      "Assuming payoff size remains constant as market conditions or execution changes.",
      "Ignoring breakevens and partial exits when constructing the averages.",
    ],
    faq: [
      {
        question: "Is break-even win rate the same as actual win rate?",
        answer:
          "No. One is a threshold implied by payoff size; the other is the observed frequency of winners in a sample.",
      },
      {
        question: "Where do costs belong?",
        answer:
          "Include them in the net outcome of each trade before calculating average win and average loss.",
      },
    ],
    relatedGlossary: "average-win-vs-average-loss",
    updated: "2026-08-31",
  },
  {
    slug: "position-size-calculator",
    title: "Position size calculator",
    seoTitle: "Position Size Calculator for Stocks & Crypto",
    description:
      "Calculate risk-based units or shares from account size, risk percentage, entry price, and stop price for direct-price stocks and crypto.",
    summary:
      "Risk-based position sizing divides the amount you are prepared to lose by the price distance between entry and stop. This version is for direct-price units such as shares or spot crypto—not forex lots, options contracts, or futures tick values.",
    formula: "Position size = (account size × risk %) ÷ |entry price − stop price|",
    formulaNote:
      "The fractional result is mathematical size; the whole-unit result rounds down so price risk does not exceed the entered amount before costs. Fees, slippage, gaps, leverage, and contract multipliers are excluded.",
    example:
      "For a $25,000 account risking 0.5%, the risk amount is $125. With entry at $50 and stop at $48.75, risk per unit is $1.25, producing 100 whole units and $5,000 notional value.",
    interpretation: [
      "Whole-unit rounding down keeps planned price risk at or below the input before costs.",
      "The notional value shows capital exposure; it can exceed cash balance when leverage is used, but this tool does not assess margin rules.",
      "A stop is not guaranteed to fill at its exact price, so actual loss can be larger.",
    ],
    mistakes: [
      "Using this direct-price formula for forex lots or futures/options contracts.",
      "Forgetting fees, slippage, gaps, or a contract multiplier.",
      "Rounding units up and unintentionally exceeding the risk amount.",
      "Treating account risk percentage as a recommendation rather than a personal input.",
    ],
    faq: [
      {
        question: "Does this work for forex or futures?",
        answer:
          "No. Those instruments require pip value, contract multiplier, tick value, currency conversion, and broker-specific lot rules that this calculator deliberately does not model.",
      },
      {
        question: "Why show fractional and whole units?",
        answer:
          "Some assets support fractional units while many shares or contracts do not. The whole-unit result rounds down rather than increasing planned price risk.",
      },
    ],
    updated: "2026-08-31",
  },
  {
    slug: "maximum-drawdown-calculator",
    title: "Maximum drawdown calculator",
    seoTitle: "Maximum Drawdown Calculator (Free)",
    description:
      "Paste an equity series to calculate the largest peak-to-trough decline in amount and percentage, with peak and trough positions.",
    summary:
      "Maximum drawdown is the largest observed decline from a prior equity peak to a later trough in the entered sequence. Order matters: sorting the values by size instead of time destroys the measurement.",
    formula: "Drawdown % = (peak equity − later trough equity) ÷ peak equity × 100",
    formulaNote:
      "Enter positive equity values in chronological order, separated by commas, spaces, or new lines. The calculation does not infer dates, deposits, withdrawals, or cash flows.",
    example:
      "For 10,000 → 11,500 → 10,800 → 9,200 → 10,400, the largest decline is 11,500 − 9,200 = $2,300, or 20%, from the second observation to the fourth.",
    interpretation: [
      "Maximum drawdown measures the worst observed peak-to-trough path in the supplied sample.",
      "It does not show how long recovery took unless dates are analyzed separately.",
      "Deposits and withdrawals can create false drawdowns or recoveries unless the series is adjusted for cash flows.",
    ],
    mistakes: [
      "Entering unordered balances rather than a chronological sequence.",
      "Mixing account deposits or withdrawals with trading performance.",
      "Calculating from individual trade P&L without a starting equity baseline.",
      "Treating historical maximum drawdown as a worst-case guarantee.",
    ],
    faq: [
      {
        question: "Can maximum drawdown be zero?",
        answer:
          "Yes. A sequence that never falls below a prior peak has zero observed drawdown.",
      },
      {
        question: "Does maximum drawdown predict future loss?",
        answer:
          "No. It describes the entered history. Future paths can produce a larger or differently timed decline.",
      },
    ],
    relatedGlossary: "maximum-drawdown",
    relatedArticle: "trading-journal-metrics-that-matter",
    updated: "2026-08-31",
  },
  {
    slug: "trading-roi-calculator",
    title: "Trading ROI calculator",
    seoTitle: "Trading ROI Calculator (Free)",
    description:
      "Calculate simple trading return on investment and ending capital from starting capital and net profit or loss.",
    summary:
      "Simple ROI expresses net profit or loss as a percentage of starting capital. It is easy to compare but does not account for the timing of cash flows, compounding, changing exposure, or risk taken.",
    formula: "ROI = net profit or loss ÷ starting capital × 100",
    formulaNote:
      "Use net P&L after the fees and costs you intend to measure. For deposits, withdrawals, or irregular cash flows, a time-weighted or money-weighted return may be more appropriate.",
    example:
      "Starting with $20,000 and recording $1,500 net profit gives ROI of 1,500 ÷ 20,000 = 7.5% and ending capital of $21,500 before external cash flows.",
    interpretation: [
      "Positive ROI means entered net P&L is positive relative to starting capital; negative ROI means it is negative.",
      "Two samples with the same ROI can have very different drawdown, variability, and duration.",
      "Do not average periodic ROI percentages to calculate a multi-period compounded return.",
    ],
    mistakes: [
      "Using gross P&L while describing the result as net.",
      "Ignoring deposits and withdrawals during the measurement period.",
      "Averaging monthly percentages instead of compounding linked returns.",
      "Comparing periods of different length without making the duration clear.",
    ],
    faq: [
      {
        question: "Is ROI the same as annualized return?",
        answer:
          "No. This tool calculates simple period ROI and does not annualize it.",
      },
      {
        question: "Can I enter a loss?",
        answer:
          "Yes. Enter net P&L as a negative number and the calculator will return a negative ROI and reduced ending capital.",
      },
    ],
    updated: "2026-08-31",
  },
];

export function getTool(slug: string) {
  return tools.find((tool) => tool.slug === slug);
}
