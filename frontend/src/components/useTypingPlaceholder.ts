import { useEffect, useState } from 'react'

const TYPE_MS = 45
const DELETE_MS = 22
const HOLD_MS = 2200

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * Cycles through `phrases` while `active`, typing each one out and deleting it.
 * Returns the visible text and the full phrase it belongs to.
 */
export function useTypingPlaceholder(phrases: string[], active: boolean) {
  const [state, setState] = useState({ text: phrases[0] ?? '', phrase: phrases[0] ?? '' })

  useEffect(() => {
    if (!active || reducedMotion()) return
    let index = 0
    let length = 0
    let deleting = false
    let timer: number

    const tick = () => {
      const target = phrases[index]
      length += deleting ? -1 : 1
      setState({ text: target.slice(0, length), phrase: target })
      if (!deleting && length === target.length) {
        deleting = true
        timer = window.setTimeout(tick, HOLD_MS)
        return
      }
      if (deleting && length === 0) {
        deleting = false
        index = (index + 1) % phrases.length
      }
      timer = window.setTimeout(tick, deleting ? DELETE_MS : TYPE_MS)
    }
    timer = window.setTimeout(tick, 400)
    return () => window.clearTimeout(timer)
  }, [phrases, active])

  return state
}
