const DEFAULT_API_URL = "http://127.0.0.1:8000";

function apiUrl(path: string): string {
  const base = (process.env.RECOMMENDER_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "");
  return `${base}${path}`;
}

export async function POST(request: Request): Promise<Response> {
  try {
    const upstream = await fetch(apiUrl("/v1/recommend"), {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: await request.text(),
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json(
      {
        error: "backend_unavailable",
        message: "推荐服务尚未启动，请先启动模型服务后重试。",
      },
      { status: 503 },
    );
  }
}
