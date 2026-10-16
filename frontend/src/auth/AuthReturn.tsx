import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { takeAfterSignIn } from '../lib/auth'
import { supabase } from '../lib/supabase'
import { useAuth } from './AuthProvider'

/**
 * Finishes a Google sign-in: reports a failure (Supabase puts it in the URL, or the
 * session exchange fails) on the home page, otherwise returns to the saved page.
 */
export function AuthReturn() {
  const navigate = useNavigate()
  const { user } = useAuth()

  useEffect(() => {
    const params = new URLSearchParams(window.location.search + '&' + window.location.hash.replace(/^#/, ''))
    const description = params.get('error_description')
    if (description) {
      navigate('/', { replace: true, state: { authError: description } })
      return
    }
    supabase.auth.initialize().then(({ error }) => {
      if (error) navigate('/', { replace: true, state: { authError: error.message } })
    })
  }, [navigate])

  useEffect(() => {
    if (!user) return
    const next = takeAfterSignIn()
    if (next && next !== window.location.pathname) navigate(next, { replace: true })
  }, [user, navigate])

  return null
}
