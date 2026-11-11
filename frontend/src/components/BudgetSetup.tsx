import BudgetEditor from './BudgetEditor'
import type { PeriodInfo } from '../types'

interface BudgetSetupProps {
  period: PeriodInfo
  name?: string
  onSaved: () => Promise<void>
  onSkip: () => void
}

// Straight after logging in, while the budget or the reset day isn't set:
// a whole page asking for both, before the list. "Skip for now" goes to the
// list, where a bar at the top keeps reminding until both are set.
export default function BudgetSetup({ period, name, onSaved, onSkip }: BudgetSetupProps) {
  const first = name?.trim().split(/\s+/)[0]
  return (
    <div className="page setup-page">
      <div className="brand">OnTrack</div>
      <div className="setup-intro">
        <h1 className="setup-title">{first ? `Hi ${first}, set up your budget` : 'Set up your budget'}</h1>
        <p className="budget-note">
          How much you want to spend each month, and the day it starts again. OnTrack shows what’s left after your
          wish list.
        </p>
      </div>
      <section className="card setup-card">
        <BudgetEditor period={period} onSaved={onSaved} saveLabel="Save and continue" />
      </section>
      <button className="link-btn setup-skip" onClick={onSkip}>Skip for now</button>
    </div>
  )
}
