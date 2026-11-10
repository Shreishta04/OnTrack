import type { CSSProperties } from 'react'
import type { Summary } from '../types'
import { useMoney } from '../money'
import Price from './Price'

// Big numbers shrink to fit their space instead of breaking onto a second
// line: the CSS divides the space available by the number of characters
// (--chars), so "₹3,605" stays large and "₹12,34,45,394" gets smaller.
function useFit() {
  const money = useMoney()
  return (amount: number | null): CSSProperties =>
    ({ '--chars': amount == null ? 1 : money.digits(Math.abs(amount)).length }) as CSSProperties
}

interface BudgetCardProps {
  summary: Summary
  onEdit: () => void // tap the card: change the budget
}

// The dark espresso card at the top: what's left after the wish list, a ring
// showing where the budget goes, and the three totals. The whole card is a
// button that opens the budget editor.
export default function BudgetCard({ summary, onEdit }: BudgetCardProps) {
  const { budget, spent_this_month: spent, planned_total: planned, remaining } = summary
  const fit = useFit()

  // No budget set yet: nothing to measure against.
  if (budget == null || remaining == null) {
    return (
      <button className="hero-card" onClick={onEdit}>
        <span className="hero-label">No budget yet</span>
        <span className="hero-empty">Set a monthly budget to see what's left after your wish list.</span>
        <span className="hero-cta">Set a budget</span>
        <Stats spent={spent} planned={planned} budget={null} />
      </button>
    )
  }

  // Each part's share of the budget, so the ring's three parts add up to the
  // whole circle. Over budget: spent and planned fill it, nothing is left.
  const share = (n: number) => (budget > 0 ? Math.max(0, n / budget) : 0)
  const spentShare = Math.min(1, share(spent))
  const plannedShare = Math.min(1 - spentShare, share(planned))
  const leftShare = Math.max(0, 1 - spentShare - plannedShare)
  const over = remaining < 0

  return (
    <button className={over ? 'hero-card is-over' : 'hero-card'} onClick={onEdit}>
      <span className="hero-top">
        <span className="hero-text">
          <span className="hero-label">{over ? 'Over budget' : 'Left this month'}</span>
          <span className="hero-amount-box" style={fit(remaining)}>
            <Price amount={Math.abs(remaining)} className="hero-amount" />
          </span>
          <span className="hero-sub">{over ? 'your wish list is more than what’s left' : 'after your wish list'}</span>
        </span>
        <Ring
          parts={[
            { share: spentShare, kind: 'spent' },
            { share: plannedShare, kind: 'planned' },
            { share: leftShare, kind: 'left' },
          ]}
          centre={over ? 'Over' : `${Math.round(leftShare * 100)}%`}
          under={over ? '' : 'left'}
          label={`Budget: ${Math.round(spentShare * 100)}% spent, ${Math.round(plannedShare * 100)}% planned, ${Math.round(leftShare * 100)}% left`}
        />
      </span>
      <Stats spent={spent} planned={planned} budget={budget} />
      <span className="sr-only">Tap to change your budget</span>
    </button>
  )
}

// The ring: up to three arcs (spent, planned, left) around one circle, with
// a small gap between them and rounded ends.
//
// How the arcs are drawn: an SVG circle's outline can be dashed. A dash as
// long as the arc, followed by a gap as long as the rest of the circle,
// draws one arc; the dash offset says where on the circle it starts.
// Rounded ends stick out by half the line's thickness at each end, so each
// dash is drawn that much shorter to keep the arcs their true size.
const R = 40
const CIRCLE = 2 * Math.PI * R
const THICK = 12
const GAP = 4

type Part = { share: number; kind: 'spent' | 'planned' | 'left' }

// Where each arc starts on the circle and how long its dash is.
function arcsFor(parts: Part[]) {
  const shown = parts.filter((p) => p.share > 0.005)
  const room = CIRCLE - (shown.length > 1 ? GAP * shown.length : 0)
  const arcs = []
  let at = 0
  for (const p of shown) {
    const length = p.share * room
    arcs.push({ kind: p.kind, full: shown.length === 1, dash: Math.max(length - THICK, 0.01), start: at + THICK / 2 })
    at += length + GAP
  }
  return arcs
}

function Ring({ parts, centre, under, label }: { parts: Part[]; centre: string; under: string; label: string }) {
  const arcs = arcsFor(parts)

  return (
    <span className="ring">
      <svg width="104" height="104" viewBox="0 0 104 104" role="img" aria-label={label}>
        <circle className="ring-base" cx="52" cy="52" r={R} fill="none" strokeWidth={THICK} />
        {arcs.map((a) =>
          a.full ? (
            <circle key={a.kind} className={`ring-${a.kind}`} cx="52" cy="52" r={R} fill="none" strokeWidth={THICK} />
          ) : (
            <circle
              key={a.kind}
              className={`ring-${a.kind}`}
              cx="52"
              cy="52"
              r={R}
              fill="none"
              strokeWidth={THICK}
              strokeLinecap="round"
              strokeDasharray={`${a.dash} ${CIRCLE - a.dash}`}
              strokeDashoffset={-a.start}
              transform="rotate(-90 52 52)"
            />
          ),
        )}
      </svg>
      <span className="ring-centre" aria-hidden="true">
        <span className="ring-big">{centre}</span>
        {under && <span className="ring-small">{under}</span>}
      </span>
    </span>
  )
}

// The three small numbers along the bottom of the card.
function Stats({ spent, planned, budget }: { spent: number; planned: number; budget: number | null }) {
  const fit = useFit()
  return (
    <span className="hero-stats">
      <span className="hero-stat" style={fit(spent)}>
        <span className="hero-stat-label"><i className="dot ring-dot-spent" />Spent</span>
        <Price amount={spent} className="hero-stat-amount" />
      </span>
      <span className="hero-stat" style={fit(planned)}>
        <span className="hero-stat-label"><i className="dot ring-dot-planned" />Planned</span>
        <Price amount={planned} className="hero-stat-amount" />
      </span>
      <span className="hero-stat" style={fit(budget)}>
        <span className="hero-stat-label"><i className="dot ring-dot-budget" />Budget</span>
        <Price amount={budget} className="hero-stat-amount" />
      </span>
    </span>
  )
}
