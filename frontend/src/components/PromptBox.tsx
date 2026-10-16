import { useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'
import { PROMPT_IDEAS } from '../lib/examples'
import type { GenerationRequest, Quality } from '../lib/types'
import { VOICES } from '../lib/videos'
import { Icon, type IconName } from './Icon'
import { useTypingPlaceholder } from './useTypingPlaceholder'


interface Props {
  initialPrompt?: string
  busy?: boolean
  onSubmit: (request: GenerationRequest) => void
}

const QUALITIES: { value: Quality; label: string }[] = [
  { value: 'low', label: 'Draft' },
  { value: 'medium', label: 'Standard' },
  { value: 'high', label: 'Crisp' },
]

/** A pill-shaped native select: icon, current value, chevron. */
function PillSelect({ icon, label, children, ...select }: { icon: IconName; label: string; children: ReactNode } & React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <label className="pill" title={label}>
      <Icon name={icon} size={16} />
      <span className="sr-only">{label}</span>
      <select {...select}>{children}</select>
      <Icon name="chevron" size={14} />
    </label>
  )
}

export function PromptBox({ initialPrompt = '', busy = false, onSubmit }: Props) {
  const [prompt, setPrompt] = useState(initialPrompt)
  const [scenes, setScenes] = useState<number | null>(null)
  const [voice, setVoice] = useState('Kore')
  const [quality, setQuality] = useState<Quality>('medium')
  // the hint keeps cycling until something is typed; Tab takes the one showing
  const suggestion = useTypingPlaceholder(PROMPT_IDEAS, !prompt)
  const trimmed = prompt.trim()
  const canSubmit = trimmed.length >= 3 && !busy

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (canSubmit) onSubmit({ prompt: trimmed, scenes, voice, quality })
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Tab' && !prompt && !event.shiftKey) {
      event.preventDefault()
      setPrompt(suggestion.phrase)
      return
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="prompt">
      <form className="prompt-box" onSubmit={submit}>
        <label htmlFor="prompt" className="sr-only">
          What should the video explain?
        </label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={suggestion.text}
          aria-describedby={prompt ? undefined : 'tab-hint'}
          rows={2}
          maxLength={500}
        />
        <div className="prompt-controls">
          <PillSelect icon="layers" label="Number of scenes" value={scenes ?? ''} onChange={(e) => setScenes(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Auto scenes</option>
            {[3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n} scenes
              </option>
            ))}
          </PillSelect>
          <PillSelect icon="mic" label="Narrator voice" value={voice} onChange={(e) => setVoice(e.target.value)}>
            {VOICES.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </PillSelect>
          <PillSelect icon="spark" label="Video quality" value={quality} onChange={(e) => setQuality(e.target.value as Quality)}>
            {QUALITIES.map((q) => (
              <option key={q.value} value={q.value}>
                {q.label}
              </option>
            ))}
          </PillSelect>
          {!prompt && (
            <button type="button" id="tab-hint" className="tab-hint" onClick={() => setPrompt(suggestion.phrase)}>
              <span className="hint-keys">
                <kbd>Tab</kbd> to use
              </span>
              <span className="hint-touch">Use this idea</span>
            </button>
          )}
          <button type="submit" className="prompt-submit" disabled={!canSubmit} aria-label={busy ? 'Starting video' : 'Create video'}>
            {busy ? <span className="spinner" aria-hidden="true" /> : <Icon name="arrowRight" size={20} />}
          </button>
        </div>
      </form>
    </div>
  )
}
