import { useState } from 'react'
import { Icon } from '../components/Icon'
import type { Video } from '../lib/types'

const STATUS_TEXT: Record<Video['status'], string> = {
  queued: 'Waiting to start',
  generating: 'Drawing…',
  ready: 'Ready',
  failed: 'Failed',
}

interface Props {
  video: Video
  url?: string
  onPlay: () => void
  onToggleShare: () => void
  onDelete: () => void
}

export function VideoRow({ video, url, onPlay, onToggleShare, onDelete }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)
  const title = video.title ?? video.prompt
  const ready = video.status === 'ready' && url

  return (
    <li className={`video-row ${menuOpen ? 'menu-open' : ''}`}>
      <button className="row-thumb" onClick={onPlay} disabled={!ready} aria-label={ready ? `Play ${title}` : title}>
        {/* skip ahead: the first frames of every video are an empty board */}
        {ready ? <video src={`${url}#t=6`} muted preload="metadata" /> : null}
        {video.status === 'generating' || video.status === 'queued' ? <span className="scribble" aria-hidden="true" /> : null}
        {video.status === 'failed' && <Icon name="close" />}
        {ready && (
          <span className="row-play">
            <Icon name="play" size={14} />
          </span>
        )}
      </button>
      <div className="row-text">
        <span className="row-title" title={title}>
          {title}
        </span>
        <span className={`row-status status-${video.status}`} title={video.error ?? undefined}>
          {video.status === 'failed' && video.error ? video.error : STATUS_TEXT[video.status]}
          {video.is_public && ' · Shared'}
        </span>
      </div>
      {ready && (
        <a className="icon-btn row-action" href={url} download={`${title.slice(0, 40)}.mp4`} title="Download">
          <Icon name="download" size={17} />
          <span className="sr-only">Download</span>
        </a>
      )}
      <div className="row-menu">
        <button className="icon-btn" onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen} aria-label="More actions">
          <Icon name="more" size={20} />
        </button>
        {menuOpen && (
          <div className="menu" role="menu" onMouseLeave={() => setMenuOpen(false)}>
            {video.status === 'ready' && (
              <button
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false)
                  onToggleShare()
                }}
              >
                <Icon name="share" size={16} />
                {video.is_public ? 'Remove from Explore' : 'Share to Explore'}
              </button>
            )}
            <button
              role="menuitem"
              className="danger-text"
              onClick={() => {
                setMenuOpen(false)
                onDelete()
              }}
            >
              <Icon name="trash" size={16} />
              Delete
            </button>
          </div>
        )}
      </div>
    </li>
  )
}
