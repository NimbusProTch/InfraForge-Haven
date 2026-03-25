#!/usr/bin/env bash
# Haven Keycloak Realm Setup
# Run after Keycloak is up: ./keycloak/setup-realm.sh
set -euo pipefail

KC_URL="${KC_URL:-http://localhost:8081}"
KC_ADMIN="${KC_ADMIN:-admin}"
KC_ADMIN_PASS="${KC_ADMIN_PASS:-admin}"

echo "→ Getting admin token from $KC_URL..."
TOKEN=$(curl -sf -X POST "$KC_URL/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=admin-cli&username=$KC_ADMIN&password=$KC_ADMIN_PASS" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "→ Creating haven realm..."
curl -sf -X POST "$KC_URL/admin/realms" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "realm": "haven",
    "displayName": "Haven Platform",
    "enabled": true,
    "registrationAllowed": false,
    "loginWithEmailAllowed": true,
    "bruteForceProtected": false
  }' && echo "  realm created" || echo "  realm may already exist, continuing..."

echo "→ Creating haven-ui client..."
curl -sf -X POST "$KC_URL/admin/realms/haven/clients" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clientId": "haven-ui",
    "name": "Haven UI",
    "enabled": true,
    "publicClient": false,
    "standardFlowEnabled": true,
    "directAccessGrantsEnabled": true,
    "redirectUris": ["http://localhost:3001/*", "http://localhost:3000/*"],
    "webOrigins": ["http://localhost:3001", "http://localhost:3000"],
    "secret": "haven-ui-secret"
  }' && echo "  client created" || echo "  client may already exist"

echo "→ Creating test user admin@haven.dev..."
curl -sf -X POST "$KC_URL/admin/realms/haven/users" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@haven.dev",
    "firstName": "Haven",
    "lastName": "Admin",
    "enabled": true,
    "emailVerified": true,
    "credentials": [{"type": "password", "value": "HavenAdmin2026!", "temporary": false}]
  }' && echo "  user created" || echo "  user may already exist"

echo ""
echo "✓ Done! Keycloak haven realm configured."
echo "  Admin UI: $KC_URL/admin → admin / admin"
echo "  Test user: admin@haven.dev / HavenAdmin2026!"
echo "  OIDC discovery: $KC_URL/realms/haven/.well-known/openid-configuration"
