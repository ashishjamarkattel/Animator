# Animator web app

React + Vite frontend for Animator, with Supabase for accounts, the video list and file storage.

- **/**: the home page and dashboard in one: the prompt box and examples for everyone. Signed in, the avatar
  in the left rail opens a panel with your Gemini API key and every video you've made (play, download, share, delete).
  Signed out, the rail shows a Google sign-in button, and pressing Create starts the sign-in, keeping the prompt.
- **/explore**: featured examples plus videos people have shared

## Setup

1. Create a Supabase project.
2. In the SQL editor, run [`supabase/schema.sql`](supabase/schema.sql). It creates `profiles` (with credits),
   `videos`, row-level security, a private `videos` storage bucket, and turns on realtime for `videos`.
3. In **Authentication → URL configuration**, add `http://localhost:5173` to the redirect URLs.
   Enable the Google provider under **Authentication → Providers** (it needs a Google OAuth client ID
   and secret; add Supabase's callback URL to that client's authorized redirect URIs).
4. Configure and run:

```bash
cd frontend
cp .env.example .env      # fill in VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY
npm install
npm run dev               # http://localhost:5173
```

## How generation works

The browser never runs the pipeline. It only records the request:

1. **Create video** inserts a row into `videos` with `status = 'queued'`.
2. If `VITE_API_URL` is set, it then calls the generation server:

   ```
   POST {VITE_API_URL}/api/generate
   Authorization: Bearer <supabase access token>
   {"video_id": "<uuid>", "gemini_api_key": "<the user's key>"}
   ```

3. The server, [`animator/api`](../animator/api/README.md), checks the token and the key, renders the video,
   uploads it to the `videos` bucket and marks the row `ready` (or `failed` with a reason). Start it with
   `python -m animator.api` from the repo root.

The studio updates on its own as the row changes, through Supabase Realtime.

Without `VITE_API_URL`, videos stay in the queue and the Create page says so.

Each user brings their own Gemini API key, added in the profile panel. It is kept in that browser's
`localStorage` ([`src/lib/geminiKey.ts`](src/lib/geminiKey.ts)) and sent only with the generate request.
Until a key is added, Create opens the panel instead of starting a video.

## Design notes

The design is meant to feel like a whiteboard: a cool board background with a faint grid, and a graphite "marker tray" sidebar. There are three marker colours, each with one meaning: blue for actions, green for finished, red for problems. Kalam, a handwritten face, is used only for display text. Everything else uses Instrument Sans. The only motion that plays without user input is the hero headline writing itself out, which mirrors what the product does.
