import { useEffect, useState } from 'react'
import { ExamplePlayer } from '../components/ExamplePlayer'
import { VideoCard } from '../components/VideoCard'
import { EXAMPLES } from '../lib/examples'
import type { Video } from '../lib/types'
import { listPublicVideos, signedUrls } from '../lib/videos'

export default function Explore() {
  const [videos, setVideos] = useState<Video[]>([])
  const [urls, setUrls] = useState<Record<string, string>>({})

  useEffect(() => {
    listPublicVideos()
      .then(async (list) => {
        setVideos(list)
        setUrls(await signedUrls(list))
      })
      .catch(() => setVideos([]))
  }, [])

  return (
    <div className="explore">
      <h1>Explore</h1>
      <section>
        <h2>Featured</h2>
        <div className="video-grid">
          {EXAMPLES.map((example) => (
            <ExamplePlayer key={example.title} example={example} />
          ))}
        </div>
      </section>
      <section>
        <h2>Shared by the community</h2>
        {videos.length === 0 ? (
          <p className="empty">Nothing shared yet. Open your videos, choose ⋯ on a finished one, then Share to Explore.</p>
        ) : (
          <div className="video-grid">
            {videos.map((video) => (
              <VideoCard key={video.id} video={video} url={urls[video.id]} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
