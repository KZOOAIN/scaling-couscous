# Health Dashboard — Build State

## Task
Build a standalone Bun HTTP server that serves a real-time health dashboard for the full AI stack (OpenClaw, sentinels, PM2, Ollama, Telegram, Gateway).

## Phases

| # | Phase | Status |
|---|-------|--------|
| 0 | STATE.md written | ✅ done |
| 1 | Create `~/.openclaw/dashboard/server.ts` | ✅ done |
| 2 | Update `~/.openclaw/ecosystem.config.cjs` (add dashboard-server) | ✅ done |
| 3 | Register with PM2 + smoke-test | ✅ done — online, 57 MB, HTTP 200 |
| 4 | Verify end-to-end (API + HTML + graceful degradation) | ✅ done |

## Key Design Decisions
- Bun HTTP server on `127.0.0.1:18790` (no public bind until Caddy Phase 2)
- Single-file `server.ts` — no build step, no bundler
- Incident dir has ~24k files: read dir, sort descending, slice top 50, parse only those
- `pm2 jlist` emits ANSI banner before JSON — strip ANSI, find first `[`, then parse
- Telegram status read from incidents (sentinel source of truth), never probed live
- All collectors fault-isolated: never throws, always returns typed fallback

## Files
- Created: `~/.openclaw/dashboard/server.ts`
- Modified: `~/.openclaw/ecosystem.config.cjs` (additive: dashboard-server entry)
- State: `~/STATE.md` (this file)

## Next Step (if resuming)
Check STATUS column above. If Phase 2 is pending, add dashboard-server entry to ecosystem.config.cjs then run `pm2 reload ~/.openclaw/ecosystem.config.cjs --only dashboard-server && pm2 save`.
