# demo-ui

Next.js 14 UI backing `https://demo.iyziops.com`. Talks to demo-api directly via
CORS. NO AUTH (this is a demo — the platform is the story, not auth).

## Features

- Notes list + create form + delete button
- Live stats bar (Redis hit ratio, RabbitMQ msg counts) via 3s polling
- Footer: "Deployed via iyziops platform"
- Tailwind dark theme

## Env

| Var | When | Default |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | **build-time ARG** | `https://demo-api.iyziops.com` |

`NEXT_PUBLIC_*` variables are baked into the Next.js bundle at build time. When
deploying via iyziops, set `NEXT_PUBLIC_API_URL` as a docker build ARG (the
iyziops build pipeline picks it up from the app's env_vars).

## Deploy via iyziops UI

```
Repo URL:      https://github.com/NimbusProTch/InfraForge-Haven.git
Branch:        main
Build context: demo/ui
Dockerfile:    demo/ui/Dockerfile
Port:          3000
Custom domain: demo.iyziops.com
Health path:   /
Services:      (none — UI talks only to demo-api over CORS)
Env vars:
  NEXT_PUBLIC_API_URL=https://demo-api.iyziops.com
```

## Local dev

```bash
cd demo/ui
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
# opens on localhost:3000
```

## Not included on purpose

- **No NextAuth / Keycloak**: demo is public. Adding auth would complicate the "15-minute deploy" story without adding customer value.
- **No SSR fetching**: client-side react-query keeps things simple and live.
- **No per-tenant branding**: single demo, one tenant (`demo`).
