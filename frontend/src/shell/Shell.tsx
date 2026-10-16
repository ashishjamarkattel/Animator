import { useCallback, useState } from 'react'
import { NavLink, Outlet, useOutletContext } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { GoogleMark, Icon } from '../components/Icon'
import { Logo } from '../components/Logo'
import { signInWithGoogle } from '../lib/auth'
import { useMyVideos, type MyVideos } from '../lib/useMyVideos'
import { GeminiKeyButton } from './GeminiKeyButton'
import { ProfilePanel } from './ProfilePanel'

export interface ShellContext {
  myVideos: MyVideos
  openPanel: () => void
  openKey: () => void
}

export function useShell() {
  return useOutletContext<ShellContext>()
}

export default function Shell() {
  const { user } = useAuth()
  const myVideos = useMyVideos()
  const [panelOpen, setPanelOpen] = useState(false)
  const openPanel = useCallback(() => setPanelOpen(true), [])
  const closePanel = useCallback(() => setPanelOpen(false), [])
  const [keyOpen, setKeyOpen] = useState(false)
  const openKey = useCallback(() => {
    setPanelOpen(false)
    setKeyOpen(true)
  }, [])
  const meta = (user?.user_metadata ?? {}) as { full_name?: string; avatar_url?: string }
  const initial = (meta.full_name || user?.email || '?').charAt(0).toUpperCase()
  const activeCount = myVideos.videos.filter((v) => v.status === 'queued' || v.status === 'generating').length

  return (
    <div className="shell">
      <nav className="rail" aria-label="Main">
        <Logo compact />
        <NavLink to="/" end className="rail-item" title="Home" onClick={closePanel}>
          <Icon name="home" size={22} />
          <span className="sr-only">Home</span>
        </NavLink>
        <NavLink to="/explore" className="rail-item" title="Explore" onClick={closePanel}>
          <Icon name="compass" size={22} />
          <span className="sr-only">Explore</span>
        </NavLink>
        {user && (
          <button className={`rail-item ${panelOpen ? 'active' : ''}`} onClick={() => setPanelOpen((open) => !open)} title="Your videos">
            <Icon name="grid" size={22} />
            {activeCount > 0 && <span className="rail-badge">{activeCount}</span>}
            <span className="sr-only">Your videos</span>
          </button>
        )}
        <div className="rail-bottom">
          {user ? (
            <button className="rail-avatar" onClick={() => setPanelOpen((open) => !open)} aria-label="Your profile" aria-expanded={panelOpen}>
              {meta.avatar_url ? <img src={meta.avatar_url} alt="" referrerPolicy="no-referrer" /> : initial}
            </button>
          ) : (
            <button className="rail-item" onClick={() => signInWithGoogle()} title="Sign in with Google">
              <Icon name="user" size={22} />
              <span className="sr-only">Sign in with Google</span>
            </button>
          )}
        </div>
      </nav>

      {panelOpen && user && <ProfilePanel myVideos={myVideos} onClose={closePanel} />}
      {user && <GeminiKeyButton open={keyOpen} onOpenChange={setKeyOpen} />}

      <div className="shell-main">
        {!user && (
          <div className="top-right">
            <button className="btn btn-outline" onClick={() => signInWithGoogle()}>
              Sign in
            </button>
            <button className="btn btn-primary" onClick={() => signInWithGoogle()}>
              <GoogleMark /> Get Animator free
            </button>
          </div>
        )}
        <Outlet context={{ myVideos, openPanel, openKey } satisfies ShellContext} />
      </div>
    </div>
  )
}
