#!/bin/sh
# Runtime entrypoint for the Next.js web container.
#
# Replaces the build-time placeholder API URL with the real URL, resolved at
# CONTAINER START from runtime env. This lets one image serve any deployment
# (split-domain, tunnel, or same-origin PR preview) without a rebuild.
#
# Precedence: explicit NEXT_PUBLIC_API_BASE_URL (split-domain deploys,
# tunnels) beats the NEXT_PUBLIC_APP_URL same-origin derivation (PR previews).
# Neither set -> fail loudly; the image ships a placeholder and cannot serve
# requests without a real URL.
#
# NEXT_PUBLIC_API_BASE_URL is read on the server at render time, so the
# placeholder gets baked into every server-rendered output: client JS, server
# JS, prerendered HTML, RSC flight payloads (including .segment.rsc), and the
# required-server-files.json runtime config. All of these need patching.
set -e

PLACEHOLDER="http://preview.placeholder.buildtime/api/v1/"

# Precedence: explicit NEXT_PUBLIC_API_BASE_URL (split-domain deploys, tunnels)
# beats the NEXT_PUBLIC_APP_URL same-origin derivation (PR previews). The
# client-side URL contract requires a trailing slash — normalize it here so a
# hand-typed env value without one doesn't half-break SSE and WebSockets.
if [ -n "${NEXT_PUBLIC_API_BASE_URL:-}" ]; then
  REAL_URL="${NEXT_PUBLIC_API_BASE_URL%/}/"
elif [ -n "${NEXT_PUBLIC_APP_URL:-}" ]; then
  REAL_URL="${NEXT_PUBLIC_APP_URL%/}/api/v1/"
else
  echo "[entrypoint] FATAL: neither NEXT_PUBLIC_API_BASE_URL nor NEXT_PUBLIC_APP_URL is set." >&2
  echo "[entrypoint] The image ships a placeholder API URL and cannot serve requests without one." >&2
  exit 1
fi

if [ "${REAL_URL}" != "${PLACEHOLDER}" ]; then
  find /app/apps/web/.next -type f \
    \( -name "*.js" -o -name "*.html" -o -name "*.rsc" -o -name "*.json" \) \
    2>/dev/null \
    | xargs grep -l "${PLACEHOLDER}" 2>/dev/null \
    | xargs -r sed -i "s|${PLACEHOLDER}|${REAL_URL}|g"
fi

exec node apps/web/server.js
