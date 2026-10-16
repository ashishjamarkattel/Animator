import { supabase } from './supabase'
import type { GenerationRequest, Profile, Video } from './types'

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''
export const isServerConfigured = Boolean(API_URL)

export const VOICES = ['Kore', 'Puck', 'Charon', 'Fenrir', 'Aoede', 'Leda', 'Orus', 'Zephyr']

export async function fetchProfile(userId: string): Promise<Profile | null> {
  const { data, error } = await supabase.from('profiles').select('*').eq('id', userId).maybeSingle()
  if (error) throw error
  return data
}

export async function updateDisplayName(userId: string, displayName: string) {
  const { error } = await supabase.from('profiles').update({ display_name: displayName }).eq('id', userId)
  if (error) throw error
}

export async function listMyVideos(userId: string): Promise<Video[]> {
  const { data, error } = await supabase
    .from('videos')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
  if (error) throw error
  return data
}

export async function listPublicVideos(): Promise<Video[]> {
  const { data, error } = await supabase
    .from('videos')
    .select('*')
    .eq('is_public', true)
    .eq('status', 'ready')
    .order('created_at', { ascending: false })
    .limit(30)
  if (error) throw error
  return data
}

/** Queues a video row, then asks the generation server to start on it with the user's Gemini key. */
export async function createVideo(request: GenerationRequest, geminiKey: string): Promise<Video> {
  const { data, error } = await supabase.from('videos').insert(request).select().single()
  if (error) throw error
  if (isServerConfigured) {
    try {
      await startGeneration(data.id, geminiKey)
    } catch (e) {
      // the server never started it, so don't leave it in the list as "Waiting to start" forever
      await supabase.from('videos').delete().eq('id', data.id)
      throw e
    }
  }
  return data
}

async function startGeneration(videoId: string, geminiKey: string) {
  const { data } = await supabase.auth.getSession()
  const response = await fetch(`${API_URL}/api/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${data.session?.access_token ?? ''}`,
    },
    body: JSON.stringify({ video_id: videoId, gemini_api_key: geminiKey }),
  }).catch(() => {
    throw new Error("Can't reach the video server. Check that it's running, then try again.")
  })
  if (!response.ok) {
    // the API answers errors as {"detail": "<message for the user>"}
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
    const detail = typeof body?.detail === 'string' ? body.detail : `The video server returned ${response.status}.`
    throw new Error(detail)
  }
}

export async function setVideoPublic(videoId: string, isPublic: boolean) {
  const { error } = await supabase.from('videos').update({ is_public: isPublic }).eq('id', videoId)
  if (error) throw error
}

export async function deleteVideo(video: Video) {
  if (video.storage_path) await supabase.storage.from('videos').remove([video.storage_path])
  const { error } = await supabase.from('videos').delete().eq('id', video.id)
  if (error) throw error
}

/** Signed playback URLs for every finished video, keyed by video id. */
export async function signedUrls(videos: Video[]): Promise<Record<string, string>> {
  const paths = videos.flatMap((v) => (v.storage_path ? [v.storage_path] : []))
  if (paths.length === 0) return {}
  const { data, error } = await supabase.storage.from('videos').createSignedUrls(paths, 60 * 60)
  if (error) throw error
  const byPath = Object.fromEntries(data.flatMap((d) => (d.signedUrl && d.path ? [[d.path, d.signedUrl]] : [])))
  return Object.fromEntries(
    videos.flatMap((v) => (v.storage_path && byPath[v.storage_path] ? [[v.id, byPath[v.storage_path]]] : [])),
  )
}

/** Calls onChange whenever one of the user's videos is inserted, updated or deleted. */
export function subscribeToMyVideos(userId: string, onChange: () => void) {
  const channel = supabase
    .channel(`videos:${userId}`)
    .on('postgres_changes', { event: '*', schema: 'public', table: 'videos', filter: `user_id=eq.${userId}` }, onChange)
    .subscribe()
  return () => {
    supabase.removeChannel(channel)
  }
}
