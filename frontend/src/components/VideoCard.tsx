import type { Video } from '../lib/types'
import { Icon } from './Icon'

const STATUS_TEXT: Record<Video['status'], string> = {
  queued: 'Waiting to start',
  generating: 'Drawing…',
  ready: 'Ready',
  failed: 'Failed',
}

interface Props {
  video: Video
  url?: string
}

function formatDuration(seconds: number | null) {
  if (!seconds) return null
  const s = Math.round(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function VideoCard({ video, url }: Props) {
  const duration = formatDuration(video.duration_seconds)
  const date = new Date(video.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

  return (
    <article className="video-card">
      <div className={`video-frame status-${video.status}`}>
        {video.status === 'ready' && url ? (
          <video src={url} controls preload="metadata" />
        ) : (
          <div className="video-placeholder">
            {video.status === 'generating' && <span className="scribble" aria-hidden="true" />}
            <span>{video.status === 'failed' ? (video.error ?? 'Generation failed. Try again with a shorter prompt.') : STATUS_TEXT[video.status]}</span>
          </div>
        )}
      </div>
      <div className="video-meta">
        <h3>{video.title ?? video.prompt}</h3>
        <p>
          <span className={`status-dot status-${video.status}`}>{STATUS_TEXT[video.status]}</span>
          <span>{date}</span>
          {duration && <span>{duration}</span>}
        </p>
      </div>
      {url && (
        <div className="video-actions">
          <a className="icon-btn" href={url} download={`${video.prompt.slice(0, 40)}.mp4`} title="Download">
            <Icon name="download" />
            <span className="sr-only">Download</span>
          </a>
        </div>
      )}
    </article>
  )
}
