import type { CostEstimate } from '../types/quest'

// One budget vocabulary everywhere: the builder pills say Cheap / Mid /
// Splurge, so every chip does too — with ₹ marks, since MoodyEat is
// India-only.
const BUDGET_LABELS: Record<CostEstimate, string> = {
  cheap: '₹ Cheap',
  mid: '₹₹ Mid',
  splurge: '₹₹₹ Splurge',
}

export function budgetLabel(cost: CostEstimate | string): string {
  return BUDGET_LABELS[cost as CostEstimate] ?? cost
}
