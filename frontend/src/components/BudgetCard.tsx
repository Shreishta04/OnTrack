import type { Summary } from '../types'
import Price from './Price'

interface BudgetCardProps {
  summary: Summary
}

export default function BudgetCard({ summary }: BudgetCardProps) {
  const { budget, spent_this_month: spent, planned_total: planned, remaining, savings_vs_mrp: savings } = summary

  // No budget set yet: nothing to measure against.
  if (budget == null || remaining == null) {
    return (
      <section className="card budget-card" aria-label="Budget summary">
        <div className="eyebrow">No budget yet</div>
        <p className="budget-note">Set a monthly budget in Settings to see what's left after your wish list.</p>
        <Stats spent={spent} planned={planned} budget={null} />
      </section>
    )
  }

  const over = remaining < 0
  const percent = (n: number) => (budget > 0 ? Math.min(100, Math.max(0, (n / budget) * 100)) : 0)
  const spentPct = percent(spent)
  const plannedPct = Math.min(100 - spentPct, percent(planned))

  return (
    <section className="card budget-card" aria-label="Budget summary">
      <div className="budget-hero">
        <div className="eyebrow">{over ? 'Over budget' : 'Left after wish list'}</div>
        <Price amount={Math.abs(remaining)} className={over ? 'hero-amount is-over' : 'hero-amount'} />
      </div>

      <div className="bar" aria-hidden="true">
        <div className="bar-seg bar-spent" style={{ width: `${spentPct}%` }} />
        <div className="bar-seg bar-planned" style={{ width: `${plannedPct}%` }} />
      </div>

      <Stats spent={spent} planned={planned} budget={budget} />

      <p className="budget-note budget-foot">
        {savings > 0 ? (
          <>
            Your wish list is <Price amount={savings} /> below MRP.
          </>
        ) : (
          'Prices are what you would pay today.'
        )}
      </p>
    </section>
  )
}

// The three small numbers under the bar. A separate component because
// both versions of the card above use it.
function Stats({ spent, planned, budget }: { spent: number; planned: number; budget: number | null }) {
  return (
    <div className="stats">
      <div className="stat">
        <span className="eyebrow"><i className="dot dot-spent" />Spent</span>
        <Price amount={spent} className="stat-amount" />
      </div>
      <div className="stat">
        <span className="eyebrow"><i className="dot dot-planned" />Planned</span>
        <Price amount={planned} className="stat-amount" />
      </div>
      <div className="stat">
        <span className="eyebrow"><i className="dot dot-budget" />Budget</span>
        <Price amount={budget} className="stat-amount" />
      </div>
    </div>
  )
}
