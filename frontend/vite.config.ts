import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // the example videos live in ../examples and are imported directly
  server: { fs: { allow: ['..'] } },
})
