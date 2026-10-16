import { supabase } from './supabase'

const NEXT_KEY = 'after-sign-in'

/** Starts Google sign-in; the user comes back to the page they were on. */
export async function signInWithGoogle() {
  sessionStorage.setItem(NEXT_KEY, window.location.pathname)
  return supabase.auth.signInWithOAuth({
    provider: 'google',
    // the bare origin always matches the redirect allow-list
    options: { redirectTo: window.location.origin },
  })
}

/** The page to return to after Google sign-in, read once. */
export function takeAfterSignIn(): string | null {
  const next = sessionStorage.getItem(NEXT_KEY)
  sessionStorage.removeItem(NEXT_KEY)
  return next
}
