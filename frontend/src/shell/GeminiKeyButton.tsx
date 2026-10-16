import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Icon } from '../components/Icon'
import { setGeminiKey, useGeminiKey } from '../lib/geminiKey'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Bottom-right key button; its popover adds, replaces or removes the user's Gemini API key. */
export function GeminiKeyButton({ open, onOpenChange }: Props) {
  const savedKey = useGeminiKey()
  const [replacing, setReplacing] = useState(false)
  const [draft, setDraft] = useState('')
  const dockRef = useRef<HTMLDivElement>(null)
  const showForm = !savedKey || replacing

  function close() {
    setReplacing(false)
    setDraft('')
    onOpenChange(false)
  }

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    const onPointer = (e: PointerEvent) => {
      if (!dockRef.current?.contains(e.target as Node)) close()
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
    }
  })

  function save(e: FormEvent) {
    e.preventDefault()
    const key = draft.trim()
    if (!key) return
    setGeminiKey(key)
    close()
  }

  return (
    <div className="key-dock" ref={dockRef}>
      {open && (
        <div className="key-popover" role="dialog" aria-label="Gemini API key">
          {showForm ? (
            <form onSubmit={save}>
              <h2>{savedKey ? 'Replace your Gemini API key' : 'Add your Gemini API key'}</h2>
              <p>
                Videos are made with your own key. Create one in{' '}
                <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">
                  Google AI Studio
                </a>
                .
              </p>
              <div className="key-field">
                <input
                  type="password"
                  aria-label="Gemini API key"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="Paste your key"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  autoFocus
                />
                <button className="btn btn-primary btn-sm" type="submit" disabled={!draft.trim()}>
                  Save
                </button>
              </div>
              <p className="key-note">
                Kept only in this browser, and sent only when you create a video.
                {replacing && (
                  <>
                    {' '}
                    <button className="text-btn" type="button" onClick={() => setReplacing(false)}>
                      Keep current key
                    </button>
                  </>
                )}
              </p>
            </form>
          ) : (
            <>
              <h2>Gemini API key</h2>
              <p>
                Ending in <code>{savedKey.slice(-4)}</code>, saved in this browser.
              </p>
              <div className="key-actions">
                <button className="btn btn-outline btn-sm" onClick={() => setReplacing(true)}>
                  Replace key
                </button>
                <button className="btn btn-ghost btn-sm danger-text" onClick={() => setGeminiKey('')}>
                  Remove
                </button>
              </div>
            </>
          )}
        </div>
      )}

      <button
        className={`key-trigger ${savedKey ? '' : 'missing'}`}
        onClick={() => (open ? close() : onOpenChange(true))}
        aria-expanded={open}
        aria-label={savedKey ? 'Gemini API key (saved)' : undefined}
        title={savedKey ? `Gemini API key ending in ${savedKey.slice(-4)}` : undefined}
      >
        <Icon name="key" size={20} />
        {savedKey ? <span className="key-dot" /> : 'Add Gemini key'}
      </button>
    </div>
  )
}
