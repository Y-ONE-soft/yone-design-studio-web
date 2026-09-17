// 예: src/app/studio/route.ts — 로그인한 사람을 스튜디오로 보내는 진입 라우트.
//
// 스튜디오의 YOS_LOGIN_URL 을 이 주소(https://<이 앱>/studio)로 두면, 미인증 브라우저가
// 스튜디오에 오면 여기로 튕겨 오고 → (로그인 페이지 →) 표를 들고 스튜디오로 돌아간다.
// 스튜디오가 `?next=<돌아올 스튜디오 절대 URL>` 을 붙여 보내므로 그 경로만 뽑아 넘긴다.
import { NextResponse } from "next/server";
import { auth } from "@/server/auth"; // 이 앱의 Auth.js 진입점 (core 기준 경로)
import { studioEnabled, studioEntryUrl } from "@/server/studio/link";

export async function GET(req: Request) {
  if (!studioEnabled()) return NextResponse.json({ error: "스튜디오 연동이 꺼져 있다 (STUDIO_URL · STUDIO_LINK_SECRET)" }, { status: 503 });
  const session = await auth();
  const url = new URL(req.url);
  if (!session?.user?.id) {
    const login = new URL("/login", url.origin);
    login.searchParams.set("callbackUrl", url.pathname + url.search);
    return NextResponse.redirect(login);
  }
  // next 는 스튜디오 절대 URL 로 온다 → 경로만 (다른 도메인은 버린다)
  let next = "/catalog";
  const raw = url.searchParams.get("next");
  if (raw) {
    try {
      const n = new URL(raw);
      if (n.origin === (process.env.STUDIO_URL ?? "").replace(/\/$/, "")) next = n.pathname + n.search;
    } catch { if (raw.startsWith("/")) next = raw; }
  }
  return NextResponse.redirect(studioEntryUrl(
    { id: session.user.id, name: session.user.name, email: session.user.email, role: (session.user as { role?: string }).role },
    next,
  ));
}
