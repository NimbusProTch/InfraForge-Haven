# Long-sprint demo gallery — 2026-04-19

Screenshots produced by `tests/e2e/specs/11-ui-full-journey.spec.ts`
when run against the live cluster after the L02–L12 PR series merges.

## How to run

```bash
cd tests/e2e
BASE_URL=https://iyziops.com npx playwright test 11-ui-full-journey
# screenshots land in this directory
```

## Expected gallery

| file | what it proves |
|---|---|
| `01-sidebar-brand.png` | Sidebar reads "iyziops" + caption "VNG Haven 15/15" (L12) |
| `02-source-tabs.png` | New-app wizard exposes GitHub / Gitea / Manual tabs (L03) |
| `03-gitea-tab.png` | Gitea tab renders the self-hosted picker (L03) |
| `04-manual-tab.png` | Manual URL input still reachable (L03) |
| `05-add-service-modal.png` | AddServiceModal Create button stays inside the 1366×768 viewport (L06) |
| `06-app-detail-live-badges.png` | LiveStatusBadge + LiveResourceBadge render on the app detail header (L05 + L10) |
| `07-signin-brand.png` | Sign-in page carries the new "iyziops" brand + VNG Haven tagline (L12) |

## What is *not* covered here

This is a **read-mostly smoke** spec — no service create / delete, no
build trigger, no GitOps writer round-trip. Stateful coverage lives in:

- `04-ui-tenant-flow.spec.ts` — tenant CRUD via UI
- `05-ui-app-flow.spec.ts` — app CRUD via UI + 9-tab navigation
- `07-ui-services.spec.ts` — service provision via the UI modal
- `09-ui-source-tabs.spec.ts` — Step-2 picker tab assertions (L03)
- `10-ui-add-service-modal.spec.ts` — Sticky-footer assertion at 1366×768 (L06)

For the **full UI-only demo rebuild** (L11) — wipe demo, sign up tenant
"demo", provision PG/Redis/RabbitMQ via the modal, connect a GitHub repo
that hard-depends on all three, watch the build logs stream, see the
LiveStatusBadge flip from Progressing → Healthy — that requires real
clicks and real cluster I/O. Drive it manually from a browser; this
smoke spec can be a sanity check after each step.
