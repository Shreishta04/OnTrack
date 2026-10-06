import { useState } from 'react'

// The product picture, or the first letter of the name if there is no
// picture (manual items) or the store refuses to show it.
export default function Thumb({ src, name }: { src: string | null; name: string }) {
  const [failed, setFailed] = useState(false)

  if (src && !failed) {
    return (
      <img
        className="thumb"
        src={src}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    )
  }
  return (
    <div className="thumb thumb-letter serif" aria-hidden="true">
      {name.trim().charAt(0).toUpperCase()}
    </div>
  )
}
