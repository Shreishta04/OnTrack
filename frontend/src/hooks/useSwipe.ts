import { useRef } from 'react'
import type { TouchEvent } from 'react'

// A flick left or right on the list moves to the next or previous tab.
// Returns two touch handlers to put on the element that should listen.
//
// What counts as a flick:
//   - one finger, mostly sideways: at least 60px across, and clearly more
//     across than up or down (so scrolling the list never changes tab)
//   - lifted within 0.8 s (a slow drag is someone reading, not swiping)
//   - NOT started at the very edge of the screen: iPhone Safari and Android
//     use edge swipes for "Back", and we mustn't fight them
//   - NOT started on the sort menu or a text box
const MIN_ACROSS = 60
const MAX_TIME = 800
const EDGE = 24

export function useSwipe(onLeft: () => void, onRight: () => void) {
  const start = useRef<{ x: number; y: number; t: number } | null>(null)

  function onTouchStart(e: TouchEvent) {
    const touch = e.touches[0]
    const target = e.target as HTMLElement
    const nearEdge = touch.clientX < EDGE || touch.clientX > window.innerWidth - EDGE
    if (e.touches.length > 1 || nearEdge || target.closest('.sort-menu, input, textarea')) {
      start.current = null
      return
    }
    start.current = { x: touch.clientX, y: touch.clientY, t: Date.now() }
  }

  function onTouchEnd(e: TouchEvent) {
    const from = start.current
    start.current = null
    if (!from) return
    const touch = e.changedTouches[0]
    const across = touch.clientX - from.x
    const down = touch.clientY - from.y
    const quick = Date.now() - from.t < MAX_TIME
    if (!quick || Math.abs(across) < MIN_ACROSS || Math.abs(across) < Math.abs(down) * 1.5) return
    if (across < 0) onLeft() // finger moved left: show the tab to the right
    else onRight()
  }

  return { onTouchStart, onTouchEnd }
}
