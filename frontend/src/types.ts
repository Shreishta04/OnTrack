// The shapes of the data the backend sends back.
// They mirror item_view() and summary() in backend/services.py.

export type Status = 'planned' | 'later' | 'purchased'

export interface Link {
  id: number
  url: string
  title: string | null
  price: number | null
  mrp: number | null
  image: string | null
  last_checked: string | null
  last_error: string | null
  price_when_saved: number | null
  previous_price: number | null
  lowest_price_seen: number | null
}

export interface Item {
  id: number
  name: string
  status: Status
  purchased_price: number | null
  purchased_at: string | null
  priority: number
  note: string | null
  manual_price: number | null
  price: number | null
  mrp: number | null
  best_link_id: number | null
  image: string | null
  needs_price: boolean
  links: Link[]
  created_at: string
  fits_budget?: boolean | null // only present in /summary
}

export interface Summary {
  budget: number | null
  planned_total: number
  spent_this_month: number
  remaining: number | null
  mrp_total: number
  savings_vs_mrp: number
  planned_count: number
  needs_price_count: number
  items: Item[]
  period?: PeriodInfo // missing only from a server older than budget periods
}

// The budget period today falls in ("25 Oct – 24 Nov").
export interface PeriodInfo {
  starts_on: string // YYYY-MM-DD, on the person's own calendar
  ends_on: string // the last day, included
  budget: number | null // this period's budget
  custom: boolean // set "just for this period"
  default_budget: number | null // what every new period starts with
  reset_day: number | null // 1–31; null: not chosen yet
  days_left: number // today included
  days_total: number
}

// One row of GET /periods (newest first).
export interface PeriodRow {
  starts_on: string
  ends_on: string
  budget: number | null
  custom: boolean
  spent: number
  current: boolean
}

// What POST /refresh sends back.
export interface RefreshResult {
  checked: number        // pages the server downloaded just now
  skipped_recent: number // checked in the last hour, so left alone
  phone_only: number     // Amazon links: the iPhone refreshes those
  changed: { link_id: number; old_price: number; new_price: number }[]
  failed: { link_id: number; error: string | null }[]
}
// ------------------------------------------------------------- accounts
// They mirror public_user(), list_tokens() and friends in backend/auth.py.

export interface Me {
  id: number
  email: string
  name: string
  currency: string // "INR", "USD"…
  country: string // "IN", "US"…
  timezone: string // "Asia/Kolkata"…
  is_admin: boolean // the owner: can invite people
  created_at: string
}

export interface AuthResult {
  user: Me
  token: string
}

// A login or a device key, as listed in Settings (never the key itself).
export interface TokenInfo {
  id: number
  kind: 'session' | 'device'
  name: string
  created_at: string
  last_used_at: string | null
  current: boolean // the one this browser is using
}

export interface DeviceToken {
  name: string
  token: string // shown once
}

export interface Invite {
  id: number
  note: string | null
  for_email: string | null // set: a password-reset link for this person
  created_at: string
  expires_at: string
  used_at: string | null
}

export interface NewCode {
  id: number
  code: string
  expires_at: string
}

export interface Person {
  id: number
  email: string
  name: string
  is_admin: boolean
  created_at: string
  items: number
  removed_at?: string | null // the owner switched this account off (an older server doesn't send it)
}

// GET /setup: the Shortcuts' iCloud links (set on Railway; null until then)
export interface SetupLinks {
  add_shortcut_url: string | null
  refresh_shortcut_url: string | null
}

// Settings → Notifications
export type AlertKind = 'price_drop' | 'budget_reset' | 'waiting' | 'back_in_stock'

export interface NotifySettings {
  settings: Record<AlertKind, boolean>
  devices: number // phones that get alerts
  configured: boolean // the server can send (Firebase set up on Railway)
  web: { config: Record<string, string>; vapid_key: string } | null // what a phone needs to sign up
}

export interface TestResult {
  sent: number
  failed: number
  devices: number
}
