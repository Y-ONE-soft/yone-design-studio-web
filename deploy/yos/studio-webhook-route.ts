// 예: src/app/api/hooks/studio/route.ts — 스튜디오 웹훅 수신 (render.finished · design.changed).
//
// 서명 규칙은 core 의 CHAT 연동(src/server/chat/link.ts)과 같다: x-studio-signature = hex HMAC-SHA256(비밀, 본문).
// 환경변수: STUDIO_LINK_SECRET (스튜디오 YOS_LINK_SECRET 과 같은 값 — 웹훅도 이 비밀로 서명된다)
import { createHmac, timingSafeEqual } from "node:crypto";
import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";

const SECRET = process.env.STUDIO_LINK_SECRET ?? "";

function verify(body: string, sig: string | null): boolean {
  if (!SECRET || !sig) return false;
  const want = createHmac("sha256", SECRET).update(body).digest("hex");
  return sig.length === want.length && timingSafeEqual(Buffer.from(sig), Buffer.from(want));
}

type RenderFinished = {
  event: "render.finished";
  render: { id: string; status: string; book: { key: string; bid: string }; series: string; design: string; design_version: string;
            result: { pdfs: string[]; main_pdf: string | null; pages: number | null; verify_ok: boolean;
                      blob?: Record<string, { url: string; pathname: string; access: string }> };
            files: Record<string, string>; status_url: string; callback?: Record<string, unknown> | null };
};
type DesignChanged = { event: "design.changed"; series: string; design: string; action: "added" | "deleted" };

export async function POST(req: Request) {
  const body = await req.text();
  if (!verify(body, req.headers.get("x-studio-signature"))) return NextResponse.json({ error: "bad signature" }, { status: 401 });
  const ev = JSON.parse(body) as RenderFinished | DesignChanged;
  if (ev.event === "design.changed") {
    revalidateTag("studio-catalog"); // 디자인 고르기 화면이 다음 조회에 새 디자인을 본다
  } else if (ev.event === "render.finished") {
    // ev.render.callback 에 조판을 걸 때 넣어 둔 값(예: bookId)이 그대로 온다.
    // PDF 는 Blob 에 private 로 올라가 있다(ev.render.result.blob["…pdf"].pathname) → presignUrl 로 열어 준다.
    // TODO: 책 레코드에 status · pathname · pages 저장
  }
  return NextResponse.json({ ok: true });
}
