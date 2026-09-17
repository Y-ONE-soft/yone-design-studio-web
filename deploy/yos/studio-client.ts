// 예: src/server/studio/client.ts — contents(또는 design)가 스튜디오 API 를 부르는 얇은 클라이언트.
//
// 환경변수 (Vercel):
//   STUDIO_SERVICE_URL     https://yos-studio.fly.dev
//   STUDIO_SERVICE_TOKEN   스튜디오의 SERVICE_TOKEN 과 같은 값 (yos-typeset 의 TYPESET_SERVICE_TOKEN 과 같은 규칙)
const BASE = (process.env.STUDIO_SERVICE_URL ?? "").replace(/\/$/, "");
const TOKEN = process.env.STUDIO_SERVICE_TOKEN ?? "";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  if (!BASE || !TOKEN) throw new Error("스튜디오가 설정되지 않았다 — STUDIO_SERVICE_URL · STUDIO_SERVICE_TOKEN");
  const res = await fetch(BASE + path, {
    ...init,
    headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((body as { error?: string }).error ?? `스튜디오 ${res.status}`);
  return body as T;
}

/** 틀 → 디자인 목록. 화면에서는 unstable_cache/태그 캐시로 감싸고 design.changed 웹훅에서 revalidateTag("studio-catalog"). */
export const studioCatalog = () => call<{ dirs: unknown[] }>("/api/v1/catalog");

export type RenderRequest = {
  series: string; design: string;
  book: { name: string; period: string; school?: string; title?: string };
  source: { type: "data"; data: unknown } | { type: "plan"; plan: unknown } | ({ type: "yos" } & Record<string, unknown>);
  knobs?: Record<string, unknown>; fields?: Record<string, string>;
  print?: boolean; replace?: boolean; callback?: Record<string, unknown>;
};
export const studioRender = (req: RenderRequest) =>
  call<{ job: string; book: { key: string; bid: string }; status_url: string }>("/api/v1/renders", { method: "POST", body: JSON.stringify(req) });

export type RenderStatus = {
  id: string; status: "queued" | "running" | "done" | "done_warn" | "failed" | "lost";
  log: string[]; n: number; elapsed: number; rc: number | null; error: string | null;
  result: { pdfs: string[]; main_pdf: string | null; pages: number | null; verify_ok: boolean;
            blob?: Record<string, { url: string; pathname: string; access: "private" | "public" }> };
  urls: Record<string, string>;
};
export const studioRenderStatus = (job: string, since = 0) => call<RenderStatus>(`/api/v1/renders/${job}?since=${since}`);

/** contents 화면 안 iframe 으로 작업대를 열 때 — 짧은 일회용 주소를 받는다. */
export const studioEmbedUrl = (user: { id: string; name?: string | null; role?: string | null }, next: string) =>
  call<{ url: string; expires_in: number }>("/api/v1/embed-token", {
    method: "POST", body: JSON.stringify({ next, ttl: 300, user: { sub: user.id, name: user.name, role: user.role } }),
  });
