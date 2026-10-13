// Each person sees prices in their own currency: ₹ and Indian grouping
// (1,00,000) in India, $ and 100,000 in the US.
//
// A "context" is React's way of giving every component a value without
// passing it down through each one by hand. App wraps the page in
// <MoneyProvider>, and any component calls useMoney() to get the symbol.
//
// Prices are shown as the store gave them: OnTrack doesn't convert currencies.

import { createContext, useContext, useMemo, type ReactNode } from 'react'

export interface Money {
  currency: string
  locale: string // e.g. "en-IN": decides how digits are grouped
  symbol: string // "₹", "$", "£"…
  digits: (amount: number) => string // 123456 → "1,23,456" (India) or "123,456"
}

function makeMoney(currency: string, country: string): Money {
  const locale = `en-${country}`
  let symbol = currency
  try {
    const parts = new Intl.NumberFormat(locale, { style: 'currency', currency }).formatToParts(0)
    symbol = parts.find((p) => p.type === 'currency')?.value ?? currency
  } catch {
    // an unknown currency code: show its letters, e.g. "XYZ"
  }
  // Rupees and yen are shown whole (₹1,299). Other currencies keep their
  // cents when there are some: $120.50, but $120 rather than $120.00.
  const whole = currency === 'INR' || currency === 'JPY'
  const digits = (n: number) => {
    const cents = !whole && Math.round(n * 100) % 100 !== 0
    return cents
      ? n.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : Math.round(n).toLocaleString(locale)
  }
  return { currency, locale, symbol, digits }
}

const MoneyContext = createContext<Money>(makeMoney('INR', 'IN'))

export function MoneyProvider({ currency, country, children }: { currency: string; country: string; children: ReactNode }) {
  const money = useMemo(() => makeMoney(currency, country), [currency, country]) // only rebuilt when they change
  return <MoneyContext.Provider value={money}>{children}</MoneyContext.Provider>
}

// eslint-disable-next-line react/only-export-components -- a hook next to its provider is fine
export const useMoney = () => useContext(MoneyContext)
