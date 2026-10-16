import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

/** True for a secret or service-role key, which must never be shipped to a browser. */
function isSecretKey(key: string) {
  if (key.startsWith('sb_secret_')) return true
  try {
    return JSON.parse(atob(key.split('.')[1])).role === 'service_role'
  } catch {
    return false
  }
}

export const usesSecretKey = Boolean(anonKey && isSecretKey(anonKey))
export const isSupabaseConfigured = Boolean(url && anonKey) && !usesSecretKey

// The placeholder values only keep createClient from throwing; the app shows a
// setup screen instead of making requests when Supabase isn't configured.
export const supabase = createClient(
  url || 'http://localhost',
  isSupabaseConfigured ? anonKey! : 'missing-anon-key',
)
