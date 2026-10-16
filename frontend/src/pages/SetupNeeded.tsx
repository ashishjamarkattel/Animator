import { Logo } from '../components/Logo'
import { usesSecretKey } from '../lib/supabase'

export default function SetupNeeded() {
  return (
    <div className="auth-page single">
      <div className="auth-panel">
        <Logo />
        <h1>Connect Supabase to continue</h1>
        {usesSecretKey ? (
          <p className="form-error">
            <code>VITE_SUPABASE_ANON_KEY</code> is a secret key. Browsers must use the publishable (anon) key: it starts
            with <code>sb_publishable_</code>, or is the legacy key labelled <code>anon</code>. Replace it, then rotate the
            secret key in Supabase.
          </p>
        ) : (
          <p>The app needs your Supabase project URL and anon key.</p>
        )}
        <ol className="setup-steps">
          <li>
            Copy <code>frontend/.env.example</code> to <code>frontend/.env</code>.
          </li>
          <li>
            Fill in <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code> from your project's API settings.
          </li>
          <li>
            Run <code>supabase/schema.sql</code> in the Supabase SQL editor.
          </li>
          <li>Restart the dev server.</li>
        </ol>
      </div>
    </div>
  )
}
