import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthProvider'
import type { Video } from './types'
import { listMyVideos, signedUrls, subscribeToMyVideos } from './videos'

/** The signed-in user's videos, kept live via Supabase Realtime. Empty when signed out. */
export function useMyVideos() {
  const { user } = useAuth()
  const [videos, setVideos] = useState<Video[]>([])
  const [urls, setUrls] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (!user) {
      setVideos([])
      setUrls({})
      return
    }
    try {
      const next = await listMyVideos(user.id)
      setVideos(next)
      setUrls(await signedUrls(next.filter((v) => v.status === 'ready')))
      setError(null)
    } catch (e) {
      // Supabase errors are plain objects, not Error instances, but carry a message
      const message = (e as { message?: string } | null)?.message
      setError(message ? `Could not load your videos: ${message}` : 'Could not load your videos.')
    }
  }, [user])

  useEffect(() => {
    reload()
    if (user) return subscribeToMyVideos(user.id, reload)
  }, [user, reload])

  return { videos, urls, error, reload }
}

export type MyVideos = ReturnType<typeof useMyVideos>
