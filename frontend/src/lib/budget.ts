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

// "≈₹400–800" (or "≈₹400" when the range collapses). Null when unknown so
// callers can skip rendering — never show a made-up number.
export function formatInrEstimate(
  min?: number | null,
  max?: number | null,
): string | null {
  if (min == null && max == null) return null
  const lo = min ?? max!
  const hi = max ?? min!
  const fmt = (n: number) => n.toLocaleString('en-IN')
  return lo === hi ? `≈₹${fmt(lo)}` : `≈₹${fmt(lo)}–${fmt(hi)}`
}
