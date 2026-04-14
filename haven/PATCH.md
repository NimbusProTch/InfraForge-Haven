# iyziops fork patch — HAVEN_RELEASES_URL env var

## Why this fork exists

Upstream VNG Haven CLI v12.8.0 hardcodes the release manifest URL in
`haven/cli/pkg/compliancy/checker.go`:

```go
res, err := http.Get("https://gitlab.com/commonground/haven/haven/-/raw/main/docs/public/releases.json?ref_type=heads")
```

Since August 2025 Cloudflare returns an interactive bot-challenge page
for requests made with Go's default `User-Agent: Go-http-client/2.0`,
so `haven check` fails on startup with:

```
[F] Could not initialize checker: Could not parse latest Haven releases:
    'invalid character '<' looking for beginning of value'
```

The `<` is the opening of `<!DOCTYPE html>` from Cloudflare's challenge
page. `curl` with its own User-Agent still works; only Go http.Client
from inside the haven binary trips the WAF rule. This hits **every**
network — the root cause is the User-Agent, not the source IP.

## The patch

One function, five lines added. Default behaviour is **identical** to
upstream when the env var is unset.

```diff
--- a/haven/cli/pkg/compliancy/checker.go
+++ b/haven/cli/pkg/compliancy/checker.go
@@ -225,8 +225,13 @@ func NewChecker(ctx context.Context, ...
 func FetchHavenReleases() (HavenReleases, error) {
        var havenReleases HavenReleases

-       // please change to main at release
-       res, err := http.Get("https://gitlab.com/commonground/haven/haven/-/raw/main/docs/public/releases.json?ref_type=heads")
+       // iyziops fork: honour HAVEN_RELEASES_URL so operators can mirror the
+       // release manifest when gitlab.com is unreachable (corporate proxies,
+       // Cloudflare bot challenges, air-gapped clusters).
+       url := os.Getenv("HAVEN_RELEASES_URL")
+       if url == "" {
+               url = "https://gitlab.com/commonground/haven/haven/-/raw/main/docs/public/releases.json?ref_type=heads"
+       }
+       res, err := http.Get(url)
        if err != nil {
                return havenReleases, fmt.Errorf("Could not fetch latest Haven releases: '%s'", err.Error())
        }
```

`os` is already imported in that file — no new dependencies.

## Build recipe

```bash
# 1. Clone upstream at the pinned tag
git clone https://gitlab.com/commonground/haven/haven.git /tmp/haven
cd /tmp/haven
git checkout tags/v12.8.0      # commit 87047a70

# 2. Apply the patch (contents above)
cd haven/cli
# (edit pkg/compliancy/checker.go as shown)

# 3. Cross-compile three platforms
go mod edit -go=1.26            # requires Go ≥ 1.25
for target in linux/amd64 darwin/amd64 darwin/arm64; do
    os="${target%/*}"; arch="${target#*/}"
    GOOS=$os GOARCH=$arch CGO_ENABLED=0 \
        go build -ldflags="-X main.version=v12.8.0-infraforge" \
        -o "haven-${os}-${arch}" ./cmd/cli/
done

# 4. Compute sha256sums and publish as a GitHub release
sha256sum haven-*
gh release create v12.8.0-infraforge haven-linux-amd64 haven-darwin-amd64 haven-darwin-arm64 \
    --title "Haven CLI v12.8.0 iyziops fork" \
    --notes "5-line patch: HAVEN_RELEASES_URL env var. See haven/PATCH.md."
```

## How to bump the version

1. Wait for an upstream Haven release (e.g. v12.9.0).
2. Re-run the build recipe with the new tag.
3. Update `haven/VERSION` to `v12.9.0-infraforge`.
4. Update `haven/releases.json` with the three new SHA256 hashes.
5. `make haven-install` will pick up the new binary automatically.

## Upstream status

We should upstream this patch. Tracking:

- Upstream issue: **TODO — open after first in-house validation**
- Upstream MR: **TODO**

Once upstream ships `HAVEN_RELEASES_URL` support officially, this
fork goes away and `haven/install.sh` switches back to gitlab.com.
