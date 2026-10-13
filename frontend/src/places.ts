// Countries, currencies and time zones offered at sign-up and in Account.
// The server accepts the same currencies (CURRENCIES in backend/auth.py).

export interface Country {
  code: string // ISO two letters, e.g. "IN"
  name: string
  currency: string // suggested when you pick the country
  zone: string // suggested time zone
}

export const COUNTRIES: Country[] = [
  { code: 'IN', name: 'India', currency: 'INR', zone: 'Asia/Kolkata' },
  { code: 'US', name: 'United States', currency: 'USD', zone: 'America/New_York' },
  { code: 'GB', name: 'United Kingdom', currency: 'GBP', zone: 'Europe/London' },
  { code: 'AE', name: 'United Arab Emirates', currency: 'AED', zone: 'Asia/Dubai' },
  { code: 'SG', name: 'Singapore', currency: 'SGD', zone: 'Asia/Singapore' },
  { code: 'CA', name: 'Canada', currency: 'CAD', zone: 'America/Toronto' },
  { code: 'AU', name: 'Australia', currency: 'AUD', zone: 'Australia/Sydney' },
  { code: 'JP', name: 'Japan', currency: 'JPY', zone: 'Asia/Tokyo' },
  { code: 'DE', name: 'Germany', currency: 'EUR', zone: 'Europe/Berlin' },
  { code: 'FR', name: 'France', currency: 'EUR', zone: 'Europe/Paris' },
  { code: 'IE', name: 'Ireland', currency: 'EUR', zone: 'Europe/Dublin' },
  { code: 'NL', name: 'Netherlands', currency: 'EUR', zone: 'Europe/Amsterdam' },
]

export const CURRENCIES = ['INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD', 'CAD', 'AUD', 'JPY']

// Every time zone this browser knows ("Asia/Kolkata", "America/Chicago", …).
export function timeZones(): string[] {
  try {
    return Intl.supportedValuesOf('timeZone')
  } catch {
    return COUNTRIES.map((c) => c.zone) // very old browsers
  }
}

// The time zone this device is set to, e.g. "America/Chicago".
// Some browsers still use old names for a few zones; use today's name.
const RENAMED: Record<string, string> = { 'Asia/Calcutta': 'Asia/Kolkata', 'Asia/Saigon': 'Asia/Ho_Chi_Minh', 'Asia/Katmandu': 'Asia/Kathmandu' }

export function deviceZone(): string {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata'
  return RENAMED[zone] ?? zone
}

// A sensible first guess at sign-up: the country whose time zone matches this
// device, else whatever the browser's language says (en-US → US), else India.
export function guessCountry(): Country {
  const zone = deviceZone()
  const byZone = COUNTRIES.find((c) => c.zone === zone)
  if (byZone) return byZone
  const region = navigator.language.split('-')[1]?.toUpperCase()
  const byRegion = COUNTRIES.find((c) => c.code === region)
  if (byRegion) return byRegion
  if (zone.startsWith('America/')) return COUNTRIES[1]
  return COUNTRIES[0]
}
