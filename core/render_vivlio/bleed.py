"""도련 · TrimBox · 간지 결합 — 조판 뒤 PDF 마감.

**도련은 옮기는 게 아니라 늘리는 것이다.** 판형 148×210 에 도련 3mm 를 주면
페이지는 154×216 이 되고 재단선 원점은 (3,3) 이 된다. 본문 위치는 재단선 기준으로
그대로 두고(여백만 도련만큼 더한다), 재단선에 닿는 **색면만 3mm 더 그린다**.
요소를 페이지 끝에 붙이면 재단 후 폭이 3mm 줄어든다 — 측면 라벨에서 실제로 발생.

⚠ `set_cropbox` 를 먼저 부르면 TrimBox 가 되돌아간다. TrimBox 만, 그리고
**MediaBox 원점 기준**으로 찍는다(원점이 0 이 아닐 수 있다).
"""
import os
import re

PT = 72 / 25.4


def _fitz():
    import fitz
    return fitz


# ── TrimBox ─────────────────────────────────────────────────────────────
def stamp_trimbox(doc, bleed=3.0, trim=None, log=None):
    """전 면에 TrimBox 지정. trim=(x0,y0,x1,y1) mm 를 주면 그 값으로,
    아니면 MediaBox 에서 사방 `bleed` mm 를 들인 사각형으로."""
    fitz = _fitz()
    n = 0
    for pg in doc:
        mb = pg.mediabox
        if trim:
            r = fitz.Rect(mb.x0 + trim[0] * PT, mb.y0 + trim[1] * PT,
                          mb.x0 + trim[2] * PT, mb.y0 + trim[3] * PT)
        else:
            r = fitz.Rect(mb.x0 + bleed * PT, mb.y0 + bleed * PT,
                          mb.x1 - bleed * PT, mb.y1 - bleed * PT)
        try:
            pg.set_trimbox(r)
            n += 1
        except Exception as e:            # noqa: BLE001 — 원인을 보고 멈춘다
            (log or print)(f"[경고] TrimBox 설정 실패({n + 1}쪽): {e}")
            break
    return n


# ── 아트워크(간지·MEMO) 삽입 ─────────────────────────────────────────────
def _open_art(path):
    if not path:
        return None
    p = os.path.expanduser(path)
    return _fitz().open(p) if os.path.exists(p) else None


def body_rect(doc):
    """조판 면의 판형(가장 많은 면 크기). 아트워크가 이것과 다르면 맞춰 넣는다."""
    from collections import Counter
    c = Counter((round(p.rect.width, 2), round(p.rect.height, 2)) for p in doc)
    if not c:
        return None
    w, h = c.most_common(1)[0][0]
    return _fitz().Rect(0, 0, w, h)


def insert_page(doc, art, art_page, at, rect=None, fit=None, crop=None):
    """아트워크 한 장을 `at`(0-based) 자리에 끼운다.

    ⚠ **완성본이 도련 없이 뽑혀 있는 경우가 흔하다**(A4 210×297 vs 판형 216×303).
      그대로 끼우면 그 면만 작아지고, 뒤에 찍는 TrimBox 가 재단선을 3mm 안쪽으로
      잡아 **간지 가장자리가 잘린다.** 크기가 다르면 판형 한가운데 놓는다.

    fit="cover"  판형과 **크기가 다른** 아트워크를 비율 유지로 확대·축소해 판형을
                 덮는다(넘치는 쪽은 잘린다). 표지 원본(216×303)을 A5 내지 간지
                 (154×216)로 쓰는 것처럼 **비율이 같고 크기만 다를 때** 쓴다.
    crop=[x0,y0,x1,y1]  원본에서 이 영역(mm)만 가져온다. 펼침면 PDF 에서 뒤표지
                 절반만 떼어 오는 자리.
    """
    fitz = _fitz()
    r = art[art_page].rect
    if crop:
        r = fitz.Rect(crop[0] * PT, crop[1] * PT, crop[2] * PT, crop[3] * PT)
    if not crop and not fit and (
            rect is None or (abs(r.width - rect.width) < 0.1
                             and abs(r.height - rect.height) < 0.1)):
        doc.insert_pdf(art, from_page=art_page, to_page=art_page, start_at=at)
        return
    pg = doc.new_page(pno=at, width=rect.width, height=rect.height)
    if fit == "cover":
        s = max(rect.width / r.width, rect.height / r.height)
        w, h = r.width * s, r.height * s
    else:
        w, h = r.width, r.height
    x = (rect.width - w) / 2.0
    y = (rect.height - h) / 2.0
    pg.show_pdf_page(fitz.Rect(x, y, x + w, y + h), art, art_page,
                     clip=r if crop else None)


def replace_page(doc, art, art_page, at, rect=None, fit=None, crop=None):
    """`at`(0-based) 자리를 아트워크 한 장으로 교체."""
    insert_page(doc, art, art_page, at, rect, fit=fit, crop=crop)
    doc.delete_page(at + 1)


def marker_pages(doc, marker):
    """마커 텍스트가 있는 쪽 인덱스(0-based) 목록."""
    return [i for i, pg in enumerate(doc) if marker in pg.get_text()]


def blank_page_indices(doc, ignore_chars=""):
    rx = re.compile(f"[{re.escape(ignore_chars)}]") if ignore_chars else None
    out = []
    for i, pg in enumerate(doc):
        s = re.sub(r"\s", "", pg.get_text())
        if rx:
            s = rx.sub("", s)
        if s == "":
            out.append(i)
    return out


def fill_blanks(doc, art, art_page, ignore_chars="", rect=None):
    """파리티로 생긴 빈 면을 MEMO 면 아트워크로 채운다(뒤에서부터)."""
    idx = blank_page_indices(doc, ignore_chars)
    for i in reversed(idx):
        replace_page(doc, art, art_page, i, rect)
    return [i + 1 for i in idx]


def redact(page, rect_mm, color=(1, 1, 1)):
    """원본 아트워크에 남은 찌꺼기를 흰 상자로 가린다(원본 자체의 결함 대응)."""
    fitz = _fitz()
    x0, y0, x1, y1 = rect_mm
    page.draw_rect(fitz.Rect(x0 * PT, y0 * PT, x1 * PT, y1 * PT),
                   color=None, fill=color, overlay=True)


# ── 마감 오케스트레이션 ──────────────────────────────────────────────────
def finish(pdf, spec, log=None, out=None):
    """config 의 `finish` 스펙대로 PDF 를 마감한다.

    spec 키(전부 선택):
      art_pdf        아트워크 원본 PDF (간지·MEMO 면이 들어 있는 인디자인 완성본)
      inserts        [{marker|at, pdf?, page, mode:"replace"|"insert",
                       fit?, crop?}]
                     marker = 렌더러가 심어둔 자리표시 텍스트(§DIV1§ 등)
                     at     = 1-based 쪽번호(마커 없이 위치로 지정)
                     fit    = "cover" 면 판형에 맞춰 비율 유지 확대·축소
                     crop   = [x0,y0,x1,y1] mm, 원본에서 그 영역만
      blank_fill     {"pdf"?, "page", "ignore"?}  빈 면 → MEMO 면
      end_on_left    {"pdf"?, "page"}  마지막 면이 왼쪽(짝수)이 되도록 한 장 보충
      append         [{"pdf"?, "page", "redact"?, "fit"?, "crop"?}]  맨 뒤에 붙일 면
      trim           {"bleed": 3}  또는 {"rect": [x0,y0,x1,y1]}
      suffix         산출 파일명 접미사(예: "_최종"). 없으면 제자리 갱신.
    Returns: {"pdf": 경로, "pages": n, "marks": {...}}
    """
    log = log or print
    doc = _fitz().open(pdf)
    body = body_rect(doc)          # 아트워크를 맞춰 넣을 판형
    default_art = _open_art(spec.get("art_pdf"))
    opened = [default_art] if default_art else []
    marks = {}

    def art_of(item):
        if item.get("pdf"):
            a = _open_art(item["pdf"])
            if a:
                opened.append(a)
            return a
        return default_art

    # ① 간지 — 마커/위치 자리를 아트워크로 교체(뒤에서부터 해야 인덱스가 안 밀린다)
    ins = sorted(spec.get("inserts") or [],
                 key=lambda it: -(it.get("at") or 0))
    resolved = []
    for it in ins:
        if it.get("marker"):
            hits = marker_pages(doc, it["marker"])
            for h in hits:
                resolved.append((h, it))
        elif it.get("at"):
            resolved.append((it["at"] - 1, it))
    for at, it in sorted(resolved, key=lambda x: -x[0]):
        art = art_of(it)
        if art is None:
            log(f"[경고] 간지 원본 없음 — 건너뜀: {it}")
            continue
        fn = (insert_page if it.get("mode", "replace") == "insert"
              else replace_page)
        fn(doc, art, it.get("page", 0), at, body,
           fit=it.get("fit"), crop=it.get("crop"))
        marks[it.get("marker") or f"@{at + 1}"] = at + 1

    # ② 빈 면 → MEMO
    bf = spec.get("blank_fill")
    if bf:
        art = art_of(bf)
        if art is not None:
            marks["MEMO"] = fill_blanks(doc, art, bf.get("page", 0),
                                        bf.get("ignore", ""), body)

    # ③ 마지막 면은 언제나 왼쪽(짝수) — 뒤 간지를 붙였을 때 기준
    eol = spec.get("end_on_left")
    if eol:
        art = art_of(eol)
        if (doc.page_count + 1) % 2:
            if art is not None:
                insert_page(doc, art, eol.get("page", 0), doc.page_count, body)
            else:
                # 아트워크가 없는 책(간지를 안 쓰는 계열)은 **빈 면**으로 맞춘다.
                # 예전에는 조용히 아무것도 안 해서 홀수로 끝나는 판이 나갔다.
                r = doc[doc.page_count - 1].rect
                doc.new_page(width=r.width, height=r.height)
            marks["parity"] = doc.page_count

    # ④ 뒤 간지
    for ap in spec.get("append") or []:
        art = art_of(ap)
        if art is None:
            log(f"[경고] 뒤 간지 원본 없음 — 건너뜀: {ap}")
            continue
        insert_page(doc, art, ap.get("page", 0), doc.page_count, body,
                    fit=ap.get("fit"), crop=ap.get("crop"))
        if ap.get("redact"):
            redact(doc[-1], ap["redact"])
        marks["back"] = doc.page_count

    # ⑤ TrimBox — 반드시 마지막에(면 구성이 다 끝난 뒤 전 면에 같은 값으로)
    trim = spec.get("trim")
    if trim:
        stamp_trimbox(doc, bleed=trim.get("bleed", 3.0),
                      trim=trim.get("rect"), log=log)

    target = out or (pdf.replace(".pdf", spec["suffix"] + ".pdf")
                     if spec.get("suffix") else pdf)
    # 항상 임시 파일에 쓰고 바꿔치운다. 교재 폴더는 클라우드 동기화 경로라
    # 큰 파일 저장이 `Operation timed out` 으로 끊길 수 있는데, 목적지에 직접
    # 쓰면 **납품본이 반쪽짜리로 덮인다**. 실패하면 목적지는 손대지 않은 채 남는다.
    tmp = target + ".tmp"
    try:
        doc.save(tmp, garbage=3, deflate=True)
        n = doc.page_count
        doc.close()
        os.replace(tmp, target)
    except Exception:
        try:
            doc.close()
        except Exception:
            pass
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    for a in opened:
        try:
            a.close()
        except Exception:
            pass
    log(f"[마감] {n}p · {marks} → {os.path.basename(target)}")
    return {"pdf": target, "pages": n, "marks": marks}
