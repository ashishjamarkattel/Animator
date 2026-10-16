import { useEffect, useState } from 'react'

// The user's own Gemini API key. It stays in this browser and is sent to the video server
// only with a Create request; the server uses it for that one video and never stores it.
const STORAGE_KEY = 'gemini-api-key'
const CHANGED = 'gemini-api-key-changed'

// used when storage is blocked (some private windows): the key then lasts until the tab closes
let memoryKey = ''

export function getGeminiKey(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return memoryKey
  }
}

export function setGeminiKey(key: string) {
  memoryKey = key
  try {
    if (key) localStorage.setItem(STORAGE_KEY, key)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // storage blocked: memoryKey holds it instead
  }
  window.dispatchEvent(new Event(CHANGED))
}

/** The saved key, kept in sync across components and tabs. */
export function useGeminiKey(): string {
  const [key, setKey] = useState(getGeminiKey)
  useEffect(() => {
    const update = () => setKey(getGeminiKey())
    window.addEventListener(CHANGED, update)
    window.addEventListener('storage', update)
    return () => {
      window.removeEventListener(CHANGED, update)
      window.removeEventListener('storage', update)
    }
  }, [])
  return key
}
