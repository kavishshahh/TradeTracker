export type ArticleSection = {
  heading: string;
  paragraphs: string[];
  bullets?: string[];
};

export type Article = {
  slug: string;
  title: string;
  seoTitle: string;
  description: string;
  category: "Journaling" | "Performance" | "Process" | "Costs";
  published: string;
  updated: string;
  readTime: string;
  intro: string;
  sections: ArticleSection[];
  takeaway: string;
  sources?: { label: string; url: string }[];
};

export const articles: Article[] = [
  {
    slug: "why-use-a-trading-journal",
    title: "Why use a trading journal?",
    seoTitle: "Why Use a Trading Journal? 7 Practical Reasons",
    description: "Learn why traders use journals, what a journal reveals that a broker statement cannot, and how to turn trade history into a repeatable review process.",
    category: "Journaling",
    published: "2026-08-14",
    updated: "2026-08-14",
    readTime: "3 min read",
    intro: "A broker statement can tell you what happened. A trading journal is meant to help explain why it happened—and whether the decision deserves to be repeated. The value is not the act of logging trades; it is the quality of the review that the record makes possible.",
    sections: [
      {
        heading: "A journal separates process from outcome",
        paragraphs: [
          "A profitable trade can come from a poor decision, and a losing trade can follow a reasonable plan. If you judge every decision only by its P&L, luck and skill become difficult to distinguish. A journal preserves the setup, intended risk, entry logic, exit plan, and execution notes that existed before the outcome was known.",
          "During review, compare the decision with the plan instead of asking only whether it made money. Over a meaningful sample, that distinction helps reveal which behaviors are repeatable and which results were accidental.",
        ],
      },
      {
        heading: "It makes patterns measurable",
        paragraphs: [
          "Memory is selective. Traders tend to remember unusually large winners, painful losses, and recent events while overlooking ordinary trades. A structured record creates a more complete sample.",
          "Consistent fields let you compare performance by setup, direction, holding period, day, risk level, or market condition. The point is not to create dozens of labels. Start with the smallest set that corresponds to decisions you can actually change.",
        ],
        bullets: ["Which setups have positive expectancy?", "Do losses cluster after a specific mistake?", "Does position size change the quality of execution?", "Are fees erasing the edge in frequent, smaller trades?"],
      },
      {
        heading: "It creates a review habit",
        paragraphs: [
          "Without a journal, review often happens only after a painful loss. A journal gives review a regular home. A short review after each trade captures context while it is fresh; a weekly review finds repeated behavior; a monthly review evaluates the broader sample.",
          "The best review ends with one specific action. For example: require a written invalidation level before entry, reduce risk after two rule violations, or stop taking a setup whose net expectancy remains negative after enough examples.",
        ],
      },
      {
        heading: "What a useful trading journal should contain",
        paragraphs: ["A useful journal combines objective fields with concise context. Too little detail makes analysis weak; too much detail makes the habit difficult to maintain."],
        bullets: ["Instrument, date, direction, entry, exit, and quantity", "Planned and actual risk", "Setup and reason for entry", "Exit reason and execution notes", "Fees and other trading costs", "One lesson or process adjustment"],
      },
      {
        heading: "What a journal cannot do",
        paragraphs: [
          "A journal does not create an edge, remove market risk, or guarantee improvement. It only makes evidence easier to inspect. The quality of the output depends on accurate inputs, honest notes, a sufficiently representative sample, and a willingness to change behavior when the record disagrees with a belief.",
          "Used that way, a journal becomes a feedback system rather than an archive.",
        ],
      },
    ],
    takeaway: "Use a trading journal to evaluate decisions independently from outcomes, find repeatable patterns, and turn review into one concrete process improvement at a time.",
  },
  {
    slug: "trading-journal-vs-spreadsheet",
    title: "Trading journal app vs spreadsheet",
    seoTitle: "Trading Journal App vs Spreadsheet: Which Should You Use?",
    description: "Compare a dedicated trading journal with Excel or Google Sheets across setup time, flexibility, analytics, review workflow, portability, and cost.",
    category: "Journaling",
    published: "2026-08-14",
    updated: "2026-08-14",
    readTime: "3 min read",
    intro: "A spreadsheet and a dedicated trading journal can store many of the same numbers. The real difference is not where rows live—it is how much work is required to keep the record consistent and turn it into a useful review.",
    sections: [
      {
        heading: "The short answer",
        paragraphs: [
          "Use a spreadsheet when you need a highly customized model, enjoy maintaining formulas, or want full control over the file. Use a journal app when you want a consistent workflow, built-in calculations, and less setup before you can review performance.",
          "Neither format fixes inaccurate entries or weak review habits. The better choice is the one you will keep current and can audit confidently.",
        ],
      },
      {
        heading: "Where spreadsheets are stronger",
        paragraphs: ["Spreadsheets are flexible. You can create unusual fields, custom formulas, scenario models, and layouts that match a specialized process. They are also easy to export and inspect cell by cell."],
        bullets: ["Complete control over formulas and columns", "Easy one-off calculations and custom models", "Familiar offline file formats", "Straightforward raw-data portability"],
      },
      {
        heading: "Where spreadsheets become expensive",
        paragraphs: [
          "A free spreadsheet still has a maintenance cost. Formulas can break, date formats can drift, rows can be skipped, and dashboards need to be rebuilt when the data structure changes. Manual formatting also makes it easy for two similar trades to be recorded differently.",
          "These problems matter because analysis depends on consistency. A win-rate formula can be mathematically correct while the underlying rows are incomplete or classified differently.",
        ],
      },
      {
        heading: "Where a dedicated journal is stronger",
        paragraphs: ["A dedicated journal gives every trade the same structure and connects entries directly to analytics, calendar views, notes, and review screens. That reduces administrative work between recording and reviewing."],
        bullets: ["Consistent trade-entry fields", "Metrics calculated from one data model", "Calendar and journal views without extra formulas", "Lower setup cost for a repeatable review routine"],
      },
      {
        heading: "A practical comparison",
        paragraphs: [
          "For most traders, the decision comes down to flexibility versus friction. A spreadsheet offers maximum flexibility but asks you to design and maintain the system. A journal app limits the data to a defined structure but makes the common workflow faster.",
          "A hybrid can work: keep the journal as the daily record and periodically export or summarize data for specialized research. Avoid maintaining two competing sources of truth.",
        ],
        bullets: ["Choose a spreadsheet for custom research and modeling", "Choose an app for consistent daily logging and review", "Choose a hybrid only when each tool has a clearly separate role"],
      },
    ],
    takeaway: "Choose the system with the lowest long-term friction. Flexibility matters, but a journal that stays current is more useful than a perfect spreadsheet that is rarely reviewed.",
  },
  {
    slug: "how-to-start-a-trading-journal",
    title: "How to start a trading journal",
    seoTitle: "How to Start a Trading Journal: A Practical Setup Guide",
    description: "Set up a trading journal with the right fields, a simple review schedule, and a process that stays useful without becoming a second job.",
    category: "Journaling",
    published: "2026-08-14",
    updated: "2026-08-14",
    readTime: "3 min read",
    intro: "The easiest journal to maintain is small enough to complete after every trade and structured enough to answer a real question later. Start with a minimum useful record, then add fields only when a review decision requires them.",
    sections: [
      {
        heading: "Step 1: decide what the journal must help you answer",
        paragraphs: [
          "Do not begin by copying every column from someone else’s template. Begin with the review question. You might need to know whether a setup is profitable after fees, whether losses increase after rule violations, or whether actual risk differs from planned risk.",
          "A field belongs in the journal only when it supports a decision, calculation, or review you expect to perform.",
        ],
      },
      {
        heading: "Step 2: record the minimum objective data",
        paragraphs: ["Objective fields create the base for calculations and comparisons. Use consistent formats and record the trade as soon as practical."],
        bullets: ["Date and instrument", "Long or short direction", "Entry price, exit price, and quantity", "Open or closed status", "Planned risk and invalidation level", "Commissions, exchange charges, and relevant fees"],
      },
      {
        heading: "Step 3: preserve decision context",
        paragraphs: [
          "Add a short setup label and one or two sentences explaining the trade. Record what you expected, what would prove the idea wrong, and why the position size was appropriate. After exit, note whether execution followed the plan.",
          "Avoid writing a market essay after every trade. A concise, repeatable note is easier to compare than a page of unstructured emotion.",
        ],
      },
      {
        heading: "Step 4: use three review intervals",
        paragraphs: ["Different review intervals answer different questions. Keep each one narrow."],
        bullets: ["After the trade: Was the plan followed? What changed?", "Weekly: Which behavior repeated? Which trade deserves a deeper review?", "Monthly: What does the larger sample say about setups, risk, costs, and consistency?"],
      },
      {
        heading: "Step 5: change one thing at a time",
        paragraphs: [
          "A journal becomes useful when review changes behavior. Choose one testable adjustment and define how you will measure it. Changing position size, entry criteria, exit logic, and schedule simultaneously makes it difficult to know what caused a difference.",
          "Keep the original record intact. Add the new rule and evaluate it on future examples rather than rewriting old trades to fit a new explanation.",
        ],
      },
    ],
    takeaway: "Start with objective trade data, short decision notes, and a weekly review. Add complexity only when it answers a question you can act on.",
  },
  {
    slug: "trading-journal-metrics-that-matter",
    title: "Trading journal metrics that matter",
    seoTitle: "Trading Journal Metrics: Win Rate, Expectancy, Profit Factor and More",
    description: "Understand the core trading journal metrics, what each one measures, and why no single number can describe a trading process.",
    category: "Performance",
    published: "2026-08-14",
    updated: "2026-08-14",
    readTime: "4 min read",
    intro: "A good dashboard is not the one with the most numbers. It is the one that helps you ask better questions. Win rate, average win and loss, expectancy, profit factor, drawdown, and costs describe different parts of the same record.",
    sections: [
      { heading: "Net profit and loss", paragraphs: ["Net P&L is the result after the costs included in your calculation. It answers whether the recorded sample gained or lost money, but not how consistently, how much risk was taken, or whether the result depended on one unusual trade.", "Always make clear which costs are included. A broker statement remains the authoritative record for actual account results." ] },
      { heading: "Win rate", paragraphs: ["Win rate is winning closed trades divided by total closed trades. It is easy to understand and easy to misuse. A high win rate can still lose money when average losses are much larger than average wins; a lower win rate can be viable when wins are sufficiently larger."], bullets: ["Compare win rate with average win and average loss", "Use a meaningful sample", "Do not treat breakeven trades inconsistently"] },
      { heading: "Average win, average loss, and payoff ratio", paragraphs: ["Average win and average loss describe the typical magnitude of outcomes. Their relationship is often summarized as a payoff ratio. Together with win rate, they help explain how a result was produced.", "Averages can be distorted by outliers, so review the distribution and largest trades rather than relying on one ratio." ] },
      { heading: "Expectancy", paragraphs: ["Expectancy estimates the average outcome per trade in the recorded sample: win probability multiplied by average win, minus loss probability multiplied by average loss. It combines frequency and magnitude into one figure.", "Historical expectancy is descriptive, not a promise. Market conditions, execution, sample size, and strategy changes can make future results different." ] },
      { heading: "Profit factor", paragraphs: ["Profit factor is gross winning value divided by gross losing value. Above 1 means gross wins exceeded gross losses in the sample; below 1 means the opposite. It can be inflated by a small sample or one large winner." ] },
      { heading: "Drawdown, fees, and rule adherence", paragraphs: ["Outcome metrics are incomplete without a view of risk and process. Drawdown shows the decline from a prior equity peak. Fees show how much activity costs. Rule adherence shows whether the result came from the intended process.", "Review these metrics together. The goal is not to maximize every number but to understand the trade-offs in the process you actually followed." ] },
    ],
    takeaway: "Use a small metric set as a connected system: net P&L, win rate, average outcomes, expectancy, profit factor, drawdown, costs, and process adherence.",
  },
  {
    slug: "how-to-calculate-trading-expectancy",
    title: "How to calculate trading expectancy",
    seoTitle: "How to Calculate Trading Expectancy (With Example)",
    description: "Learn the trading expectancy formula, walk through a simple example, and understand the sample-size and cost limitations behind the result.",
    category: "Performance",
    published: "2026-08-14",
    updated: "2026-08-14",
    readTime: "3 min read",
    intro: "Trading expectancy estimates the average result per trade across a recorded sample. It is useful because it combines how often trades win with the average size of wins and losses. It does not predict the outcome of the next trade.",
    sections: [
      { heading: "The expectancy formula", paragraphs: ["Expectancy = (win rate × average win) − (loss rate × average loss). Use average loss as a positive magnitude in the subtraction. The output uses the same unit as your win and loss values: dollars, percentage points, or units of risk."], bullets: ["Win rate = winning trades ÷ closed trades", "Loss rate = losing trades ÷ closed trades", "Average win = total winning value ÷ winning trades", "Average loss = absolute total losing value ÷ losing trades"] },
      { heading: "A simple example", paragraphs: ["Suppose a sample contains 40 closed trades: 18 winners and 22 losers. The win rate is 45% and the loss rate is 55%. Average win is $180 and average loss is $100.", "Expectancy = (0.45 × $180) − (0.55 × $100) = $81 − $55 = $26 per trade. That describes this historical sample before any costs not already included." ] },
      { heading: "Calculate net expectancy", paragraphs: ["For a more realistic view, calculate each trade after applicable commissions, exchange charges, and other transaction costs before deriving the averages. Subtracting an average fee later can be a rough shortcut, but trade-by-trade net results are clearer when costs vary." ] },
      { heading: "Sample size and stability", paragraphs: ["A positive expectancy based on a few trades can be dominated by chance or one outlier. There is no universal sample size that guarantees reliability. Compare rolling windows, inspect the range of outcomes, and note whether the strategy or market conditions changed during the sample." ] },
      { heading: "Common expectancy mistakes", paragraphs: ["Do not mix gross winners with net losers, combine unrelated setups without checking them separately, ignore breakeven-trade treatment, or assume the historical average will persist. Expectancy is a review tool, not a forecast." ] },
    ],
    takeaway: "Calculate expectancy from consistent net trade results, interpret it alongside sample size and distribution, and never treat it as a guarantee of future performance.",
  },
  {
    slug: "post-trade-review-checklist",
    title: "A practical post-trade review checklist",
    seoTitle: "Post-Trade Review Checklist: What to Record After Every Trade",
    description: "Use a concise post-trade review checklist to evaluate planning, execution, risk, exit quality, costs, and the next process improvement.",
    category: "Process",
    published: "2026-08-14",
    updated: "2026-08-14",
    readTime: "3 min read",
    intro: "A post-trade review should be short enough to complete consistently and specific enough to change future behavior. Its purpose is not to explain away the result. It is to compare the trade that happened with the plan that existed before it.",
    sections: [
      { heading: "1. Reconstruct the original plan", paragraphs: ["Record the setup, entry condition, invalidation level, intended exit, position size, and maximum planned risk. Use notes made before or during the trade where possible; hindsight tends to make the original idea look clearer than it was." ] },
      { heading: "2. Compare execution with the plan", paragraphs: ["Identify any difference between planned and actual entry, size, stop, or exit. A difference is not automatically a mistake—new information can justify a change—but the reason should be explicit."], bullets: ["Was the entry condition present?", "Was actual size within the risk limit?", "Was the exit rule followed?", "Did any unplanned action materially affect the result?"] },
      { heading: "3. Record costs and final result", paragraphs: ["Use the net result when possible and record the costs included. Mark the trade closed only when the journal has the information needed for the calculation. Reconcile important differences with your broker record." ] },
      { heading: "4. Classify the decision", paragraphs: ["A simple four-way classification can be useful: good process/good outcome, good process/bad outcome, poor process/good outcome, or poor process/bad outcome. The two mixed cases are especially valuable because they prevent outcome bias." ] },
      { heading: "5. End with one lesson", paragraphs: ["Write one sentence that can affect a future decision. Prefer an observable rule over a general feeling. “Wait for the closing confirmation” is testable; “be more disciplined” is not." ] },
    ],
    takeaway: "A strong post-trade review reconstructs the plan, audits execution, records the net result, separates process from outcome, and ends with one testable lesson.",
  },
  {
    slug: "why-track-trading-fees",
    title: "Why trading fees belong in your journal",
    seoTitle: "Why Track Trading Fees? Gross vs Net Trading Performance",
    description: "See how commissions, transaction costs, platform charges, and other fees change trading results—and how to keep gross and net performance clear.",
    category: "Costs",
    published: "2026-08-14",
    updated: "2026-08-14",
    readTime: "3 min read",
    intro: "Gross P&L describes price movement captured by recorded trades. Net P&L attempts to describe what remains after included costs. If a journal ignores costs, it can overstate the result and make frequent, small-edge activity look stronger than it was.",
    sections: [
      { heading: "Costs change the hurdle", paragraphs: ["Every included cost increases the amount a trade must earn before it contributes to net performance. The effect is especially visible when average profits are small relative to the number of transactions.", "Investor.gov and FINRA both emphasize that fees and commissions reduce investment returns and that investors should understand the full set of charges attached to an account or transaction." ] },
      { heading: "Costs are broader than commission", paragraphs: ["The relevant fields depend on the broker, account, market, and product. A journal should reflect the charges that actually apply rather than using a universal assumption."], bullets: ["Brokerage commission", "Exchange or transaction charges", "Platform and data fees", "Regulatory charges where applicable", "Margin interest or financing costs", "Account, transfer, or withdrawal fees when relevant to the review"] },
      { heading: "Keep gross and net views separate", paragraphs: ["Gross results can help evaluate the trade idea before costs. Net results help evaluate the practical result after included costs. Label both clearly and document what the net figure contains.", "Do not use journal estimates as a substitute for broker confirmations, account statements, or tax records." ] },
      { heading: "Review costs as a behavior signal", paragraphs: ["Costs are not only an accounting adjustment. They can reveal whether overtrading, small average profit, or unnecessary turnover is weakening the process. Compare fees with gross profit, average trade result, and trading frequency." ] },
      { heading: "Reconcile and update fee settings", paragraphs: ["Fee schedules change and may vary by product. Periodically compare estimated journal costs with actual broker records, correct configuration differences, and preserve the effective period when a fee structure changes." ] },
    ],
    takeaway: "Track costs trade by trade, label gross and net results clearly, and reconcile estimates with official broker records so performance is not overstated.",
    sources: [
      { label: "Investor.gov: How Fees and Expenses Affect Your Investment Portfolio", url: "https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/updated" },
      { label: "FINRA: Fees and Commissions", url: "https://www.finra.org/investors/investing/investing-basics/fees-commissions" },
    ],
  },
  {
    slug: "common-trading-journal-mistakes",
    title: "Common trading journal mistakes",
    seoTitle: "9 Trading Journal Mistakes That Make Reviews Less Useful",
    description: "Avoid inconsistent entries, hindsight notes, missing fees, outcome bias, over-tagging, and other mistakes that weaken trading journal analysis.",
    category: "Process",
    published: "2026-08-14",
    updated: "2026-08-14",
    readTime: "4 min read",
    intro: "A trading journal can contain hundreds of entries and still produce weak conclusions. Most problems come from inconsistent inputs, hindsight, or collecting information without a defined review decision.",
    sections: [
      { heading: "1. Recording only memorable trades", paragraphs: ["Logging unusually large wins and losses creates a biased sample. Use the same inclusion rule for every trade in the process you intend to evaluate." ] },
      { heading: "2. Writing the reason after the outcome", paragraphs: ["Notes written only after exit can reshape the original thesis. Capture the planned setup, invalidation, and risk before or near entry, then keep the post-trade review separate." ] },
      { heading: "3. Changing definitions", paragraphs: ["If “breakeven,” “rule violation,” or a setup label means something different each week, comparisons become unreliable. Define the important fields and apply them consistently." ] },
      { heading: "4. Ignoring costs", paragraphs: ["Gross performance can conceal how commissions and other charges affect frequent trading. Track what is included and keep net estimates distinct from official account records." ] },
      { heading: "5. Using too many tags", paragraphs: ["Dozens of overlapping tags create tiny groups and invite selective interpretation. Keep tags tied to a specific question and retire fields that never affect review." ] },
      { heading: "6. Optimizing from a tiny sample", paragraphs: ["A few outcomes can look decisive by chance. Note sample size, outliers, and strategy changes before treating a pattern as stable." ] },
      { heading: "7. Reviewing only P&L", paragraphs: ["Outcome metrics do not show whether the plan was followed. Include a process measure such as rule adherence, planned versus actual risk, or execution quality." ] },
      { heading: "8. Making several changes together", paragraphs: ["Simultaneous changes make cause and effect hard to identify. Choose one adjustment, define the evidence you expect, and review a future sample." ] },
      { heading: "9. Treating the journal as proof", paragraphs: ["A journal describes the data entered. It does not prove that a strategy will work in the future. Use it to challenge beliefs, not confirm them automatically." ] },
    ],
    takeaway: "Consistency matters more than complexity. Record the complete sample, preserve pre-trade context, include costs, and connect every field to a real review decision.",
  },
];

export function getArticle(slug: string) {
  return articles.find((article) => article.slug === slug);
}

export function formatArticleDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}
