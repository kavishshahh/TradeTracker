// Algo Lab > Research: strategies that were built and tested but not listed. The write-ups name each
// strategy's rules, so like the catalogue rules they are served to the owner only (GET /algos/research,
// from backend/seed_data/algo_research.json) and are never part of the page bundle.

export type ResearchStat = { label: string; value: string; tone?: 'up' | 'down' };
/** Return per year (% of model capital) with no costs, 2 points and 4.6 points of slippage and charges per trade. */
export type CostRow = { name: string; note: string; edge_points: number; gross: number; mid: number; high: number; listed?: boolean };
export type ResearchNote = {
  id: string; name: string; tag: string; source: string; researched: string; code: string;
  verdict: string; summary: string; stats: ResearchStat[]; costs: CostRow[]; findings: string[];
};
export type Research = { method: string; notes: ResearchNote[] };
