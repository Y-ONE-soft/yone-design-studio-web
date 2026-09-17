// Y.OS 앱(core · contents · design 중 스튜디오 진입을 맡을 곳)에 넣는 파일 — 예: src/server/studio/link.ts
//
// 스튜디오(yos-studio.fly.dev)는 로그인 화면이 없다. 이 앱이 Auth.js 세션으로 사람을 알고 있으니
// 공유 비밀로 서명한 "표"를 건네고 스튜디오는 서명만 확인한다 — core 의 위젯 표(src/server/widget/token.ts)와 같은 꼴.
//
// 환경변수 (Vercel):
//   STUDIO_URL            https://yos-studio.fly.dev
//   STUDIO_LINK_SECRET    스튜디오의 YOS_LINK_SECRET 과 같은 값
import { createHmac } from "node:crypto";

const SECRET = process.env.STUDIO_LINK_SECRET ?? "";
const STUDIO_URL = (process.env.STUDIO_URL ?? "").replace(/\/$/, "");
const TTL_MS = 10 * 60 * 1000; // 한 번 쓰고 스튜디오 세션 쿠키(12h)로 바뀐다 — 길 필요가 없다

export const studioEnabled = () => !!SECRET && !!STUDIO_URL;

export type StudioUser = { id: string; name?: string | null; email?: string | null; role?: string | null };

/** 스튜디오가 읽는 표: base64url(JSON{u,e,n,m,r}) . base64url(HMAC-SHA256) */
export function signStudioToken(user: StudioUser): string {
  if (!SECRET) throw new Error("STUDIO_LINK_SECRET 미설정");
  const payload = Buffer.from(
    JSON.stringify({ u: user.id, e: Date.now() + TTL_MS, n: user.name ?? undefined, m: user.email ?? undefined, r: user.role ?? undefined }),
  ).toString("base64url");
  const mac = createHmac("sha256", SECRET).update(payload).digest("base64url");
  return `${payload}.${mac}`;
}

/** 스튜디오로 들어가는 주소. next 는 스튜디오 안 경로(/catalog, /book-studio?b=…). */
export function studioEntryUrl(user: StudioUser, next = "/catalog"): string {
  const u = new URL("/auth/callback", STUDIO_URL);
  u.searchParams.set("token", signStudioToken(user));
  u.searchParams.set("next", next.startsWith("/") ? next : "/catalog");
  return u.toString();
}
