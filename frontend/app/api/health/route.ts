const DEFAULT_API_URL = "http://127.0.0.1:8000";

export async function GET(): Promise<Response> {
  const base = (process.env.RECOMMENDER_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "");
  try {
    const upstream = await fetch(`${base}/health`, {
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json(
      { status: "degraded", model_ready: false, deepseek_configured: false },
      { status: 503 },
    );
  }
}
