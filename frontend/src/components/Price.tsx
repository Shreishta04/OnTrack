// Draws an amount the OnTrack way: a small, soft currency sign and clear digits.
// Every price in the app goes through this, so they all look the same.
// The sign and digit grouping follow the person's own currency (see money.tsx).

import { useMoney } from '../money'

interface PriceProps {
  amount: number | null
  className?: string
}

export default function Price({ amount, className = '' }: PriceProps) {
  const money = useMoney()
  if (amount == null) return <span className={`num ${className}`}>—</span>

  return (
    <span className={`num ${className}`}>
      <span className="cur">{money.symbol}</span>
      {money.digits(amount)}
    </span>
  )
}
