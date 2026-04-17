import { NextRequest, NextResponse } from "next/server";

// Bypass the rewrite proxy for /analyze — it can take 60-90s (full EDD memo via Claude)
// and Next.js's http-proxy times out after ~60s of socket inactivity.
// A Route Handler uses node-fetch directly with no idle-socket timeout.
export async function POST(request: NextRequest) {
  const body = await request.json();

  let response: Response;
  try {
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8001";
    response = await fetch(`${backendUrl}/api/edd/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(180_000), // 3-minute hard cap
    });
  } catch (err) {
    return NextResponse.json(
      { detail: "proxy_error", message: "Backend unreachable or timed out." },
      { status: 502 }
    );
  }

  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
