// Draws a rupee amount the OnTrack way: a small, soft ₹ and clear digits.
// Every price in the app goes through this, so they all look the same.

interface PriceProps {
  amount: number | null
  className?: string
}

export default function Price({ amount, className = '' }: PriceProps) {
  if (amount == null) return <span className={`num ${className}`}>—</span>

  return (
    <span className={`num ${className}`}>
      <span className="cur">₹</span>
      {Math.round(amount).toLocaleString('en-IN')}
    </span>
  )
}
