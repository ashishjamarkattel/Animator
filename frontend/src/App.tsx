import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { AuthReturn } from './auth/AuthReturn'
import { isSupabaseConfigured } from './lib/supabase'
import Explore from './pages/Explore'
import Home from './pages/Home'
import NotFound from './pages/NotFound'
import SetupNeeded from './pages/SetupNeeded'
import Shell from './shell/Shell'

export default function App() {
  if (!isSupabaseConfigured) return <SetupNeeded />

  return (
    <AuthProvider>
      <BrowserRouter>
        <AuthReturn />
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Home />} />
            <Route path="explore" element={<Explore />} />
          </Route>
          {/* older links */}
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/app/*" element={<Navigate to="/" replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
