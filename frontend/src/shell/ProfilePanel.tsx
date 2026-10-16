import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthProvider'
import { Icon } from '../components/Icon'
import type { Video } from '../lib/types'
import type { MyVideos } from '../lib/useMyVideos'
import { deleteVideo, setVideoPublic } from '../lib/videos'
import { PlayerModal } from './PlayerModal'
import { VideoRow } from './VideoRow'

interface Props {
  myVideos: MyVideos
  onClose: () => void
}

export function ProfilePanel({ myVideos, onClose }: Props) {
  const { user, profile, signOut } = useAuth()
  const { videos, urls, error, reload } = myVideos
  const [playing, setPlaying] = useState<Video | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !playing && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, playing])

  if (!user) return null
  const meta = user.user_metadata as { full_name?: string; avatar_url?: string }
  const name = profile?.display_name || meta.full_name || user.email || ''

  async function remove(video: Video) {
    if (!confirm(`Delete “${video.title ?? video.prompt}”? This can't be undone.`)) return
    await deleteVideo(video)
    reload()
  }

  return (
    <>
      <div className="panel-scrim" onClick={onClose} />
      <aside className="profile-panel" aria-label="Your profile and videos">
        <div className="profile-head">
          {meta.avatar_url ? (
            <img className="profile-avatar" src={meta.avatar_url} alt="" referrerPolicy="no-referrer" />
          ) : (
            <span className="profile-avatar">{name.charAt(0).toUpperCase()}</span>
          )}
          <div className="profile-name">
            <strong>{name}</strong>
            <span>{user.email}</span>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close panel">
            <Icon name="close" />
          </button>
        </div>


        <h2 className="panel-heading">Your videos</h2>
        {error && <p className="form-error">{error}</p>}
        {error ? null : videos.length === 0 ? (
          <p className="panel-empty">Videos you create show up here. Describe a topic in the box to make your first one.</p>
        ) : (
          <ul className="video-list">
            {videos.map((video) => (
              <VideoRow
                key={video.id}
                video={video}
                url={urls[video.id]}
                onPlay={() => setPlaying(video)}
                onToggleShare={() => setVideoPublic(video.id, !video.is_public).then(reload)}
                onDelete={() => remove(video)}
              />
            ))}
          </ul>
        )}

        <button className="btn btn-ghost sign-out" onClick={signOut}>
          <Icon name="logout" size={16} />
          Sign out
        </button>
      </aside>
      {playing && urls[playing.id] && (
        <PlayerModal title={playing.title ?? playing.prompt} src={urls[playing.id]} onClose={() => setPlaying(null)} />
      )}
    </>
  )
}
