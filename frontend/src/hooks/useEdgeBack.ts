import { useRef, type TouchEvent } from 'react'

// The iPhone's home-screen app has no back swipe of its own, so pages give
// it one: swipe in from the left edge to go back, like native iPhone apps.
// Only there: Safari and Android already have their own Back.
//
// Spread what this returns onto the page: <div {...useEdgeBack(onBack)}>
export function useEdgeBack(onBack: () => void) {
  const edge = useRef<{ x: number; y: number; t: number } | null>(null)
  const installedIPhone = (navigator as Navigator & { standalone?: boolean }).standalone === true

  return {
    onTouchStart(e: TouchEvent) {
      const touch = e.touches[0]
      edge.current = installedIPhone && touch.clientX <= 24 ? { x: touch.clientX, y: touch.clientY, t: Date.now() } : null
    },
    onTouchEnd(e: TouchEvent) {
      const from = edge.current
      edge.current = null
      if (!from) return
      const touch = e.changedTouches[0]
      const across = touch.clientX - from.x
      // far enough, mostly sideways, and quick
      if (across > 70 && across > Math.abs(touch.clientY - from.y) * 1.5 && Date.now() - from.t < 800) onBack()
    },
  }
}
