import { useEffect, useState, type ReactNode } from 'react'
import { getPeriods } from '../api'
import type { Item, Me, PeriodRow, Summary } from '../types'
import { useMoney } from '../money'
import { useEdgeBack } from '../hooks/useEdgeBack'
import { dayMonth, storeName } from '../format'
import Price from './Price'
import { BackIcon } from './Icons'

interface AnalyticsPageProps {
  me: Me
  summary: Summary | null
  notes: ReactNode // offline / new version lines, as on the list
  onBack: () => void
}

// /analytics: how this period is going, past periods against their budgets,
// and which stores the money goes to.
export default function AnalyticsPage({ me, summary, notes, onBack }: AnalyticsPageProps) {
  const [periods, setPeriods] = useState<PeriodRow[] | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const edgeBack = useEdgeBack(onBack)

  useEffect(() => {
    getPeriods()
      .then(setPeriods)
      .catch((e: Error) => setProblem(e.message))
  }, [summary])

  const period = summary?.period
  const past = periods?.filter((p) => !p.current) ?? []

  return (
    <div className="page settings-page analytics-page" {...edgeBack}>
      <div className="settings-top">
        <button className="icon-btn" aria-label="Back to your list" onClick={onBack}>
          <BackIcon />
        </button>
      </div>
      <h1 className="settings-title">Analytics</h1>
      {notes}

      {!summary && <p className="notice">Loading…</p>}
      {summary && !period && (
        <p className="notice">Analytics needs the newest server. It appears once the server is updated.</p>
      )}
      {summary && period && <ThisPeriod summary={summary} />}

      <h2 className="set-heading">Past periods</h2>
      {problem && <p className="notice notice-error">{problem}</p>}
      {!problem && !periods && <p className="notice">Loading…</p>}
      {periods && periods.length > 0 && <PeriodChart periods={periods.slice(0, 6).reverse()} />}
      {periods && past.length === 0 && (
        <p className="set-note">Your first period is still going. Past periods show up here once it ends.</p>
      )}
      {past.length > 0 && <PastList periods={past} defaultBudget={period?.default_budget ?? null} />}

      {summary && periods && <Stores items={summary.items} periods={periods.slice(0, 3)} zone={me.timezone} />}
    </div>
  )
}

// ---------------------------------------------------------------- this period

// The dark card: what's left after the wish list, how much that is a day,
// and how far through the period we are.
function ThisPeriod({ summary }: { summary: Summary }) {
  const period = summary.period!
  const left = summary.remaining
  const gone = period.days_total - period.days_left
  const perDay = left != null && left > 0 ? Math.floor(left / Math.max(1, period.days_left)) : null
  const daysLeft = `${period.days_left} ${period.days_left === 1 ? 'day' : 'days'} left`

  return (
    <section className="hero-card stat-card">
      <span className="stat-top">
        <span>This period · {dayMonth(period.starts_on)} – {dayMonth(period.ends_on)}</span>
        <span>{daysLeft}</span>
      </span>
      {left == null ? (
        <span className="hero-empty">Set a budget to see what’s left each day.</span>
      ) : (
        <>
          <span className="stat-amount">
            <Price amount={Math.abs(left)} className="stat-big" />
            <span className="stat-word">{left < 0 ? 'over' : 'left'}</span>
          </span>
          <span className="stat-line">
            {perDay != null ? (
              <>About <b><Price amount={perDay} /> a day</b> after your wish list, until your next budget</>
            ) : (
              'Your wish list is more than what’s left this period'
            )}
          </span>
        </>
      )}
      <span className="stat-bar" role="img" aria-label={`${gone} of ${period.days_total} days gone`}>
        <span style={{ width: `${(gone / period.days_total) * 100}%` }} />
      </span>
      <span className="stat-small">{gone} of {period.days_total} days gone</span>
    </section>
  )
}

// ---------------------------------------------------------------- the chart

// Up to six periods, oldest on the left: a bar for what was spent, a dashed
// line for the budget. Over budget bars are clay; the current one is lighter.
function PeriodChart({ periods }: { periods: PeriodRow[] }) {
  const money = useMoney()
  const top = Math.max(1, ...periods.map((p) => Math.max(p.spent, p.budget ?? 0))) * 1.12
  const pct = (n: number) => `${Math.round((n / top) * 100)}%`
  const month = (p: PeriodRow) => dayMonth(p.starts_on).split(' ')[1]
  const words = periods
    .map((p) => `${dayMonth(p.starts_on)}: ${money.symbol + money.digits(p.spent)} spent${p.budget != null ? ` of ${money.symbol + money.digits(p.budget)}` : ''}`)
    .join('; ')

  return (
    <section className="set-group chart-card">
      <div className="chart" role="img" aria-label={`Spent against budget. ${words}`}>
        {periods.map((p) => {
          const over = p.budget != null && p.spent > p.budget
          return (
            <div key={p.starts_on} className="chart-col">
              {p.budget != null && <div className="chart-budget" style={{ bottom: pct(p.budget) }} />}
              <div
                className={p.current ? 'chart-bar is-current' : over ? 'chart-bar is-over' : 'chart-bar'}
                style={{ height: p.spent > 0 ? pct(p.spent) : '2px' }}
              />
            </div>
          )
        })}
      </div>
      <div className="chart-labels" aria-hidden="true">
        {periods.map((p) => <span key={p.starts_on}>{month(p)}</span>)}
      </div>
      <div className="chart-key" aria-hidden="true">
        <span><i className="key-box" />Spent</span>
        <span><i className="key-box is-over" />Over budget</span>
        <span><i className="key-line" />Budget</span>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------- the list

function PastList({ periods, defaultBudget }: { periods: PeriodRow[]; defaultBudget: number | null }) {
  return (
    <section className="set-group past-list">
      {periods.map((p) => {
        const over = p.budget != null && p.spent > p.budget
        return (
          <div key={p.starts_on} className="past-row">
            <div className="past-text">
              <span className="past-dates">{dayMonth(p.starts_on)} – {dayMonth(p.ends_on)}</span>
              <span className="budget-note">
                <Price amount={p.spent} />
                {p.budget != null && <> of <Price amount={p.budget} /></>}
                {p.custom && p.budget !== defaultBudget && ' (set just for this period)'}
              </span>
            </div>
            {p.budget != null && (
              <span className={over ? 'pill pill-warn' : 'pill pill-good'}>
                <Price amount={Math.abs(p.budget - p.spent)} /> {over ? 'over' : 'under'}
              </span>
            )}
          </div>
        )
      })}
    </section>
  )
}

// ---------------------------------------------------------------- stores

// What was bought in the last three periods, added up by store. The date of
// a purchase is read on the person's own calendar (their time zone), the
// same way the server decides which period it belongs to.
function Stores({ items, periods, zone }: { items: Item[]; periods: PeriodRow[]; zone: string }) {
  if (periods.length === 0) return null
  const from = periods[periods.length - 1].starts_on
  const to = periods[0].ends_on
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: zone }) // en-CA writes dates as YYYY-MM-DD

  const totals = new Map<string, number>()
  for (const i of items) {
    if (i.status !== 'purchased' || !i.purchased_at) continue
    const d = day.format(new Date(i.purchased_at))
    if (d < from || d > to) continue
    totals.set(storeName(i), (totals.get(storeName(i)) ?? 0) + (i.purchased_price ?? 0))
  }
  const rows = [...totals].filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1])
  const most = rows[0]?.[1] ?? 1
  const label = periods.length === 1 ? 'this period' : `last ${periods.length} periods`

  return (
    <>
      <h2 className="set-heading">Where it goes · {label}</h2>
      <section className="set-group store-card">
        {rows.length === 0 && <p className="budget-note">Nothing marked as bought yet. Stores show up here once you buy things.</p>}
        {rows.map(([name, n]) => (
          <div key={name} className="store-row">
            <div className="store-top">
              <span className="store-name">{name}</span>
              <Price amount={n} />
            </div>
            <div className="store-track">
              <span style={{ width: `${(n / most) * 100}%` }} />
            </div>
          </div>
        ))}
        <p className="budget-note">Spend by type (clothes, beauty, tech…) comes once items have categories.</p>
      </section>
    </>
  )
}
