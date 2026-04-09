# Keycloak `tenant_memberships` JWT claim — operator setup

> **Status:** Optional optimization. The Haven API works without this mapper —
> it just falls back to a DB lookup on every authenticated request to determine
> tenant membership. Activating the mapper eliminates that DB hop on the hot path.
>
> **Sprint:** H2 P12 (#23). PR #96 ships the Python helpers (`extract_tenant_memberships`,
> `check_tenant_membership_in_claim`) that consume the claim. This file is the
> operator-side activation runbook.

## What the claim looks like

After activation, every Keycloak access token issued from the `haven` realm
will carry a `tenant_memberships` claim:

```json
{
  "sub": "abc123",
  "preferred_username": "alice",
  "tenant_memberships": [
    {"slug": "rotterdam", "role": "owner"},
    {"slug": "amsterdam", "role": "viewer"}
  ]
}
```

The simpler "slug-only" shape is also accepted by the API:

```json
{
  "tenant_memberships": ["rotterdam", "amsterdam"]
}
```

When the claim uses the slug-only shape, role-based checks
(`require_role("owner")`, etc.) **cannot** be enforced from the claim alone —
the API will fall back to the DB lookup for those calls. The rich shape is
recommended once the data is available.

## Two ways to populate the claim

Pick **one** based on how Haven manages tenant→user mapping in Keycloak:

### Option A — User attribute (recommended for the rich shape)

Each Keycloak user gets a `tenant_memberships` user attribute whose value is
a JSON-encoded list of `{slug, role}` dicts. The mapper emits the attribute
verbatim into the JWT.

1. Per user, set the attribute (via the Keycloak admin REST API or the UI):

   ```bash
   curl -X PUT "$KC/admin/realms/haven/users/$USER_ID" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "attributes": {
         "tenant_memberships": ["[{\"slug\":\"rotterdam\",\"role\":\"owner\"}]"]
       }
     }'
   ```

2. Add a protocol mapper to the `haven-ui` client (and `haven-kubectl`,
   once it exists — see `HAVEN_COMPLIANCE_PLAN.md` H1a-2). Insert the
   following into the `clients[].protocolMappers` array of `haven-realm.json`:

   ```json
   {
     "name": "tenant-memberships",
     "protocol": "openid-connect",
     "protocolMapper": "oidc-usermodel-attribute-mapper",
     "consentRequired": false,
     "config": {
       "user.attribute": "tenant_memberships",
       "claim.name": "tenant_memberships",
       "jsonType.label": "JSON",
       "id.token.claim": "false",
       "access.token.claim": "true",
       "userinfo.token.claim": "false",
       "multivalued": "false"
     }
   }
   ```

3. Reimport the realm: `./keycloak/bootstrap-realm.sh --apply` (PR #91).

4. Have a user log out + back in to mint a new token, then verify with
   `jwt.io` or `jq` that the `tenant_memberships` claim is present.

### Option B — Group membership (slug-only shape)

Map Keycloak groups onto tenant slugs. Each group named `tenant-{slug}` →
the user is a member of `{slug}`. No role info in the claim, but no
user-attribute bookkeeping either.

1. Create groups in the `haven` realm: `tenant-rotterdam`, `tenant-amsterdam`, …

2. Assign users to the appropriate groups via the Keycloak admin API or UI.

3. Add this protocol mapper to `clients[].protocolMappers` for `haven-ui`:

   ```json
   {
     "name": "tenant-group-memberships",
     "protocol": "openid-connect",
     "protocolMapper": "oidc-group-membership-mapper",
     "consentRequired": false,
     "config": {
       "claim.name": "tenant_memberships",
       "full.path": "false",
       "id.token.claim": "false",
       "access.token.claim": "true",
       "userinfo.token.claim": "false"
     }
   }
   ```

4. Optionally add a script mapper that strips the `tenant-` prefix from group
   names so the claim contains `["rotterdam", "amsterdam"]` instead of
   `["tenant-rotterdam", "tenant-amsterdam"]`. Without this, the API still
   works — just adapt `extract_tenant_memberships()` or rename your tenant
   slugs to include the prefix.

5. Reimport the realm: `./keycloak/bootstrap-realm.sh --apply`.

## Verification

After re-import + a fresh login:

```bash
# 1. Get a token
TOKEN=$(curl -s -X POST "$KC/realms/haven/protocol/openid-connect/token" \
  -d "client_id=haven-ui" \
  -d "client_secret=$HAVEN_UI_CLIENT_SECRET" \
  -d "grant_type=password" \
  -d "username=alice" \
  -d "password=..." | jq -r .access_token)

# 2. Decode and inspect (no signature check)
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq .tenant_memberships
# Expected:
#   ["rotterdam", "amsterdam"]
# OR
#   [{"slug": "rotterdam", "role": "owner"}, ...]
```

Then hit a tenant endpoint with the token. Watch the API logs — once the
claim is present, the `db_lookup` log line for `check_tenant_membership_in_claim`
should disappear and be replaced by a `claim_hit` line (instrumentation lands
in a follow-up PR; for now you can grep for `tenant_memberships` in the
debug logs).

## Rollback

The Python side is **completely backwards-compatible**. If the mapper turns out
to be wrong (typo, missing users, etc.), simply remove the `protocolMappers`
entry from `haven-realm.json` and re-run `bootstrap-realm.sh --apply`. The API
will silently fall back to the DB lookup — no API redeploy needed, no user
impact beyond the temporary extra DB query per request.

## Migration window

Existing tokens issued **before** the mapper activation will not have the
claim. They will fall back to the DB lookup until they expire. With the
default `ssoSessionMaxLifespan = 8h` (see `haven-realm.json` line 13), the
transition window is bounded at 8 hours after re-import — no force-logout
required.
