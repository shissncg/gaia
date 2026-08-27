import { type NextRequest, NextResponse } from "next/server";

import { getServerApiBaseUrl } from "@/lib/serverApiBaseUrl";

// The blog write credential lives ONLY on the server. It must never carry a
// NEXT_PUBLIC_ prefix — that would inline it into the client bundle.
const BLOG_BEARER_TOKEN = process.env.BLOG_BEARER_TOKEN;

/**
 * Server-side proxy for creating blog posts.
 *
 * Forwards the multipart form body to the backend `blogs` endpoint with the
 * server-only bearer token, so the write credential is never exposed to the
 * browser. The caller's session cookie is forwarded for backend auth.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!BLOG_BEARER_TOKEN) {
    return NextResponse.json(
      { error: "Blog management is not configured." },
      { status: 503 },
    );
  }

  // Fetch the API from inside the web container over the private network —
  // the browser-facing NEXT_PUBLIC_API_BASE_URL is unreachable (or has an
  // untrusted TLS cert) from here on a split-domain/container deploy.
  const apiBaseUrl = getServerApiBaseUrl();
  if (!apiBaseUrl) {
    return NextResponse.json(
      { error: "API base URL is not configured." },
      { status: 500 },
    );
  }

  // CSRF: only accept same-origin submissions. A cross-site form POST carries
  // the victim's cookie but a foreign (or absent) Origin, so reject it before
  // attaching the server write credential. Compare the Origin header's host to
  // the request Host — both are browser-provided and stay consistent behind a
  // proxy/CDN (unlike a server-derived origin).
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  let originHost: string | null = null;
  try {
    originHost = origin ? new URL(origin).host : null;
  } catch {
    originHost = null;
  }
  if (!originHost || !host || originHost !== host) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  // Require an authenticated session — unauthenticated callers carry no session
  // cookie, so reject before touching the backend or the write credential.
  const cookie = request.headers.get("cookie");
  if (!cookie) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const formData = await request.formData();

  // Build the target via the URL parser (keeps scheme/host/port/query intact),
  // appending `/blogs` regardless of whether the base has a trailing slash.
  const backendUrl = new URL(apiBaseUrl);
  backendUrl.pathname = `${backendUrl.pathname.replace(/\/+$/, "")}/blogs`;

  const backendResponse = await fetch(backendUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${BLOG_BEARER_TOKEN}`,
      cookie,
    },
    body: formData,
  });

  const contentType = backendResponse.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await backendResponse.json()
    : await backendResponse.text();

  return NextResponse.json(payload, { status: backendResponse.status });
}
