# GitHub OAuth App — operator notes

The "Connect GitHub" wizard in the iyziops UI calls
`POST /api/v1/github/auth/url`, which returns a `https://github.com/login/oauth/authorize?...`
URL. The OAuth App that backs this URL is registered under the
**NimbusProTch** organization (canonical owner of the `iyziops` brand).

## Credentials

The live `client_id` / `client_secret` are stored in the
`iyziops-api-secrets` K8s Secret in the `haven-system` namespace under
the keys `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`. The Secret is
**not** in git — it is created out-of-band by the operator after they
register the OAuth App. The `Settings.github_client_id_placeholder_values`
guard rejects any well-known placeholder literal at startup and at request
time so a half-bootstrapped Secret cannot leak into prod again.

To rotate:

1. github.com → Settings → Developer settings → OAuth Apps → iyziops
   Platform → "Generate a new client secret".
2. `kubectl -n haven-system patch secret iyziops-api-secrets --type=merge -p
   '{"stringData":{"GITHUB_CLIENT_SECRET":"<new>"}}'`
3. `kubectl -n haven-system rollout restart deploy/iyziops-api`

## Why org repos sometimes "do not show up"

When a tenant connects GitHub via the wizard and selects a repo, the
wizard pulls the list from `GET /api/v1/github/repos`. That endpoint
calls both `GET /user/repos?affiliation=owner,collaborator,organization_member`
and `GET /user/orgs` followed by `GET /orgs/<login>/repos` for every org
the user belongs to.

Repos owned by an organization will only show up in that list if the
**OAuth App has been approved for the org** by an org owner. Until then,
GitHub silently returns an empty repo list for the org even when the user
has push access. There is nothing the platform can do server-side to
override this — it is a GitHub-side policy enforced on the
`/orgs/<login>/repos` endpoint.

The wizard surfaces a one-line hint
(`github-org-approval-hint` test id) explaining this, with a link to
the canonical settings page:

```
github.com/organizations/<org>/settings/oauth_application_policy
```

An org owner clicks "Request" → "Approve" against the **iyziops Platform**
entry and the next refresh of the wizard will list the org's repos.

## Self-hosted Gitea fallback

For tenants that do not want to involve github.com at all (e.g. air-gapped
municipal environments later), the wizard now exposes a second source
tab — **Gitea (self-hosted)** — that lists repos under
`tenant-{slug}` in the in-cluster Gitea. Selecting a repo there sets the
clone URL to the Gitea HTTP URL and the rest of the build/deploy flow
works unchanged.
