import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="auth-page single">
      <div className="auth-panel">
        <h1 className="hand-title small">Nothing drawn here yet</h1>
        <p>This page doesn't exist.</p>
        <Link to="/" className="btn btn-primary">
          Go to the home page
        </Link>
      </div>
    </div>
  )
}
