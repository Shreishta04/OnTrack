// Small line icons, drawn with SVG so they take the text colour.

const common = {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
}

export function SunIcon() {
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  )
}

export function MoonIcon() {
  return (
    <svg {...common}>
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
    </svg>
  )
}

// "Auto" in Settings: follow the phone's own light/dark setting.
export function PhoneIcon() {
  return (
    <svg {...common}>
      <rect x="6" y="2.5" width="12" height="19" rx="3" />
      <path d="M11 18h2" />
    </svg>
  )
}

export function SearchIcon() {
  return (
    <svg {...common} strokeWidth={1.8}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M20 20l-4.2-4.2" />
    </svg>
  )
}

// The settings gear (Tabler's outline gear).
export function GearIcon() {
  return (
    <svg {...common} width={19} height={19} strokeWidth={1.7}>
      <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37c1 .608 2.296.07 2.572-1.065z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

export function BackIcon() {
  return (
    <svg {...common} width={20} height={20} strokeWidth={2}>
      <path d="M15 18l-6-6 6-6" />
    </svg>
  )
}

// The ">" at the end of a Settings row.
export function ChevronRightIcon() {
  return (
    <svg {...common} width={16} height={16} strokeWidth={2}>
      <path d="M9 6l6 6-6 6" />
    </svg>
  )
}

export function WalletIcon() {
  return (
    <svg {...common} width={17} height={17} strokeWidth={1.8}>
      <path d="M4 7h15a1 1 0 0 1 1 1v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7z" />
      <path d="M4 7V6a2 2 0 0 1 2-2h10" />
      <circle cx="16" cy="13.5" r="1" />
    </svg>
  )
}

export function GlobeIcon() {
  return (
    <svg {...common} width={17} height={17} strokeWidth={1.8}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z" />
    </svg>
  )
}

export function ClockIcon() {
  return (
    <svg {...common} width={17} height={17} strokeWidth={1.8}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  )
}

export function LockIcon() {
  return (
    <svg {...common} width={17} height={17} strokeWidth={1.8}>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  )
}

export function KeyIcon() {
  return (
    <svg {...common} width={17} height={17} strokeWidth={1.8}>
      <circle cx="8" cy="15" r="4" />
      <path d="M11 12l8-8M16 7l2 2" />
    </svg>
  )
}

export function PeopleIcon() {
  return (
    <svg {...common} width={17} height={17} strokeWidth={1.8}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 4.5a3.5 3.5 0 0 1 0 7M18 14c2 .8 3 2.8 3 6" />
    </svg>
  )
}

export function LogOutIcon() {
  return (
    <svg {...common} strokeWidth={1.8}>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l-5-5 5-5M5 12h11" />
    </svg>
  )
}

export function CloseIcon() {
  return (
    <svg {...common}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}


export function RefreshIcon() {
  return (
    <svg {...common}>
      <path d="M20 11a8 8 0 1 0-2.3 5.7" />
      <path d="M20 4v7h-7" />
    </svg>
  )
}

export function PlusIcon() {
  return (
    <svg {...common} width={24} height={24} strokeWidth={1.8}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

// The little "v" on the sort button (it turns over while the menu is open).
export function ChevronIcon() {
  return (
    <svg {...common} width={14} height={14} strokeWidth={2}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

// The tick beside the chosen sort.
export function CheckIcon() {
  return (
    <svg {...common} width={16} height={16} strokeWidth={2}>
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  )
}
