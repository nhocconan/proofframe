import { apiFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

const SHA256_RE = /^[a-f0-9]{64}$/;
const RESPONSE_HEADERS = [
  "content-type",
  "content-length",
  "accept-ranges",
  "content-range",
] as const;

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!SHA256_RE.test(id)) {
    return new Response("Invalid media id\n", {
      status: 400,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const range = request.headers.get("range");
  let upstream: Response;
  try {
    upstream = await apiFetch(`/v1/media/${id}`, {
      headers: range ? { Range: range } : {},
    });
  } catch {
    return new Response("Media upstream unavailable\n", {
      status: 502,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  if (!upstream.ok) {
    return new Response(`Media upstream returned HTTP ${upstream.status}\n`, {
      status: upstream.status,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const headers = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value !== null) headers.set(name, value);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers,
  });
}
