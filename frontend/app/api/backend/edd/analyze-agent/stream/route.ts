import { NextRequest } from "next/server";

// Streaming proxy for /api/edd/analyze-agent/stream — returns SSE so the
// browser can render live tool activity without waiting 60–90s for the
// whole agent loop to finish.
//
// We pass the upstream ReadableStream straight through; no buffering, no
// JSON parsing in the proxy. The 3-minute AbortSignal is a safety cap on
// the upstream connection, not on the browser's event consumption.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const backendUrl = process.env.BACKEND_URL || "http://localhost:8001";

  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl}/api/edd/analyze-agent/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(600_000), // 10-minute hard cap
    });
  } catch {
    return new Response(
      JSON.stringify({ detail: "proxy_error", message: "Backend unreachable or timed out." }),
      { status: 502, headers: { "Content-Type": "application/json" } }
    );
  }

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    return new Response(text || "Upstream error", { status: upstream.status });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
