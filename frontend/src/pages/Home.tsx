import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { PromptBox } from '../components/PromptBox'
import { Showcase } from '../components/Showcase'
import { signInWithGoogle } from '../lib/auth'
import { useGeminiKey } from '../lib/geminiKey'
import type { GenerationRequest } from '../lib/types'
import { createVideo, isServerConfigured } from '../lib/videos'
import { useShell } from '../shell/Shell'

const PENDING_KEY = 'pending-prompt'

// a prompt typed while signed out survives the trip through Google sign-in
function readPendingPrompt(): string {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY)
    return raw ? (JSON.parse(raw) as GenerationRequest).prompt : ''
  } catch {
    return ''
  }
}

export default function Home() {
  const { user } = useAuth()
  const { myVideos, openPanel, openKey } = useShell()
  const geminiKey = useGeminiKey()
  const location = useLocation()
  const authError = (location.state as { authError?: string } | null)?.authError
  const [initialPrompt] = useState(readPendingPrompt)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (user) sessionStorage.removeItem(PENDING_KEY)
  }, [user])

  async function generate(request: GenerationRequest) {
    setError(null)
    if (!user) {
      sessionStorage.setItem(PENDING_KEY, JSON.stringify(request))
      const { error } = await signInWithGoogle()
      if (error) setError(error.message)
      return
    }
    if (!geminiKey) {
      setError('Add your Gemini API key first.')
      openKey()
      return
    }
    setBusy(true)
    try {
      await createVideo(request, geminiKey)
      await myVideos.reload()
      openPanel()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the video.')
      // the unstarted row was deleted, and live updates don't report deletes, so refresh the list
      await myVideos.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="home">
      <section className={`home-hero ${user ? 'centered' : ''}`}>
        <h1 className="home-title">{user ? 'What should we explain today?' : 'Create with Animator'}</h1>
        {!user && (
          <p className="hero-sub">Type an idea and get a narrated, hand-drawn whiteboard video in about a minute.</p>
        )}
        <PromptBox key={initialPrompt} initialPrompt={initialPrompt} busy={busy} onSubmit={generate} />
        {(error || authError) && (
          <p className="form-error" role="alert">
            {error ?? `Sign-in failed: ${authError}`}
          </p>
        )}
        {user && !geminiKey && !error && (
          <p className="form-notice">
            Videos are made with your own Gemini API key.{' '}
            <button className="text-btn" onClick={openKey}>
              Add your key
            </button>{' '}
            to start creating.
          </p>
        )}
        {user && !isServerConfigured && (
          <p className="form-notice">
            No video server is connected, so new videos wait in the queue. Set <code>VITE_API_URL</code> to start generating.
          </p>
        )}
      </section>

      {!user && <Showcase onStart={() => document.getElementById('prompt')?.focus()} />}
    </div>
  )
}
