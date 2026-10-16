export type VideoStatus = 'queued' | 'generating' | 'ready' | 'failed'
export type Quality = 'low' | 'medium' | 'high'

export interface Video {
  id: string
  user_id: string
  prompt: string
  scenes: number | null
  voice: string
  quality: Quality
  status: VideoStatus
  title: string | null
  storage_path: string | null
  duration_seconds: number | null
  error: string | null
  is_public: boolean
  created_at: string
}

export interface Profile {
  id: string
  display_name: string | null
  credits: number
}

export interface GenerationRequest {
  prompt: string
  scenes: number | null
  voice: string
  quality: Quality
}
