"""시각 검수 1층 — 산출물(.pdf/.indd)을 페이지 PNG로 렌더해 기계 검사 (W29).

텍스트 덤프 게이트(core.inspect)가 못 보는 시각 결함을 잡는다:
  V1 NEAR_BLANK      거의 빈 페이지 (본문 흐름 페이지가 비어 있음 — 사이클 잔존 등)
  V2 OVERDENSE       과밀 페이지 (잉크 비율 이상 — 겹침/이중 조판 의심)
  V3 RED_MARK        비정상 적색 마크 (양품 캘리브레이션 초과의 순적색 덩어리)
  V4 OVERSET         오버셋 스토리의 페이지 지목 (덤프 overflow → fp/pg 매핑)
  V5 GEOM_OOB        텍스트 프레임 페이지 경계 이탈 (덤프 fb/페이지 b 지오메트리)
  V6 GEOM_OVERLAP    서로 다른 스토리 프레임 겹침 (덤프 지오메트리)
  V7 LAYOUT_OUTLIER  같은 (마스터,좌우) 그룹 내 콘텐츠 박스 급변 (구조 어긋남 의심)

렌더 경로 (실측 2026-07-18): pdftoppm(poppler, 34p/2.4s@72dpi) → 폴백 pypdfium2.
PDF가 없는 흐름(.indd만)은 core/jsx/export_pages_png.jsx 로 InDesign PNG export.

판정 철학 (알람 피로 방지 — 리스크분석 A8 준용):
  critical: 사람이 반드시 봐야 함 (OVERSET, 심한 GEOM_OOB) → ok=False
  review:   2층(검수 에이전트)이 눈으로 볼 후보 — ok에 영향 없음
캘리브레이션: scripts/calibrate_visual_inspect.py 가 양품 코퍼스로 임계 실측.
양품 critical 0 이 합격선. 임계 기본값은 THRESHOLDS (2026-07-18 실측 기반).

이 모듈은 전부 fail-open으로 호출된다 — 예외는 위로 던지고 호출부가 삼킨다.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

_DIR = os.path.dirname(os.path.abspath(__file__))
_JSX_TEMPLATE = os.path.join(os.path.dirname(_DIR), "jsx", "export_pages_png.jsx")

DEFAULT_DPI = 72

# 임계 기본값 — scripts/calibrate_visual_inspect.py 실측으로 조정.
# (숫자 근거는 docs/workbook_v2_로드맵.md W29 기록 참조)
THRESHOLDS = {
    "ink_luma": 240,          # 이 밝기 미만 픽셀 = 잉크
    "content_luma": 200,      # 콘텐츠 박스(진한 잉크) 임계
    "near_blank_ink": 0.005,  # 잉크 비율 < 0.5% → NEAR_BLANK(review)
    "overdense_ink": 0.42,    # 잉크 비율 > 42% → OVERDENSE(review)
    "fullbleed_ink": 0.95,    # 이 초과는 전면 간지(정상 디자인) — OVERDENSE 제외
    "layout_min_ink": 0.02,   # 이 미만 페이지는 여백 통계에서 제외(잔여 마크 왜곡)
    "red_r_min": 190,         # 순적색 마스크: R>=190, G<=90, B<=90
    "red_gb_max": 90,
    "red_px_frac": 0.0030,    # 순적색 픽셀 비율 > 0.30% → RED_MARK(review)
    "layout_margin_tol": 0.10,  # 그룹 중앙값 대비 여백 편차(페이지 비율) > 10%
    "layout_min_group": 4,      # 이 미만 페이지 그룹은 outlier 판정 안 함
    "oob_review_frac": 0.01,    # 프레임이 페이지 밖으로 나간 깊이(페이지 비율)
    "oob_critical_frac": 0.05,  # > 5% 이탈은 critical
    "overlap_review_frac": 0.30,  # 교차면적/작은프레임면적 > 30% → review
}


class VisualInspectError(RuntimeError):
    pass


# ── 렌더 ──────────────────────────────────────────────────────────────────────

def _pdftoppm_bin():
    p = shutil.which("pdftoppm")
    if p:
        return p
    # launchd-spawn Flask는 PATH에 homebrew가 없을 수 있음 — 관용 경로 직접 탐색
    for cand in ("/opt/homebrew/bin/pdftoppm", "/usr/local/bin/pdftoppm"):
        if os.path.isfile(cand):
            return cand
    return None


def render_pdf_pages(pdf_path, out_dir, dpi=DEFAULT_DPI, log=None):
    """PDF → 페이지별 PNG. 반환 (png_paths, backend). 실패 시 예외."""
    pdf_path = os.path.abspath(pdf_path)
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    bin_ = _pdftoppm_bin()
    if bin_:
        prefix = os.path.join(out_dir, "page")
        cp = subprocess.run([bin_, "-png", "-r", str(dpi), pdf_path, prefix],
                            capture_output=True, text=True, timeout=1800)
        if cp.returncode == 0:
            pngs = sorted(
                os.path.join(out_dir, f) for f in os.listdir(out_dir)
                if f.startswith("page") and f.endswith(".png"))
            if pngs:
                return pngs, "pdftoppm"
        if log:
            log(f"[시각검수] pdftoppm 실패({cp.returncode}) — pypdfium2 폴백")
    # 폴백: pypdfium2 (순수 파이썬 wheel — 양 인터프리터 확인)
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf_path)
    pngs = []
    try:
        for i in range(len(doc)):
            bmp = doc[i].render(scale=dpi / 72.0)
            png = os.path.join(out_dir, f"page-{i + 1:04d}.png")
            bmp.to_pil().save(png)
            pngs.append(png)
    finally:
        doc.close()
    if not pngs:
        raise VisualInspectError(f"PDF 렌더 실패: {pdf_path}")
    return pngs, "pypdfium2"


def render_indd_pages(indd_path, out_dir, log, dpi=DEFAULT_DPI, timeout=900):
    """PDF가 없는 흐름용 — InDesign PNG export (읽기 전용 열기, 사용자 문서 무접촉).

    core/jsx/export_pages_png.jsx 템플릿을 치환해 run_jsx 로 전달 (블로킹 폴링).
    반환 (png_paths, "indesign_png").
    """
    from core.indesign.runner import run_jsx
    indd_path = os.path.abspath(indd_path)
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    export_log = os.path.join(out_dir, "png_export.log")
    try:
        os.remove(export_log)
    except OSError:
        pass
    with open(_JSX_TEMPLATE, encoding="utf-8") as f:
        src = f.read()
    src = (src.replace("__INDD_PATH__", indd_path.replace("\\", "\\\\").replace('"', '\\"'))
              .replace("__OUT_DIR__", out_dir.replace("\\", "\\\\").replace('"', '\\"'))
              .replace("__LOG_PATH__", export_log)
              .replace("__DPI__", str(int(dpi))))
    fd, jsx_path = tempfile.mkstemp(suffix=".jsx", prefix="export_pages_png_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        run_jsx(jsx_path, log, poll_log_path=export_log, timeout=timeout,
                completion_marker="PNG 내보내기 완료")
    finally:
        try:
            os.remove(jsx_path)
        except OSError:
            pass
    pngs = sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir)
        if re.match(r"^page-\d+\.png$", f))
    if not pngs:
        raise VisualInspectError(f"InDesign PNG export 산출물 없음: {out_dir}")
    return pngs, "indesign_png"


# ── 페이지 픽셀 측정 (PIL) ────────────────────────────────────────────────────

def page_metrics(png_path, th=None):
    """PNG 1장 → 픽셀 측정치 dict. (numpy 불사용 — PIL 히스토그램/포인트 연산)"""
    from PIL import Image, ImageChops
    th = th or THRESHOLDS
    im = Image.open(png_path).convert("RGB")
    w, h = im.size
    total = float(w * h)
    g = im.convert("L")
    hist = g.histogram()
    ink = sum(hist[:th["ink_luma"]]) / total

    content_luma = th["content_luma"]
    mask = g.point(lambda v: 255 if v < content_luma else 0)
    bbox = mask.getbbox()   # (l, t, r, b) 픽셀
    margins = None
    if bbox:
        l, t, r, b = bbox
        margins = {
            "left": l / w, "top": t / h,
            "right": (w - r) / w, "bottom": (h - b) / h,
        }

    r_ch, g_ch, b_ch = im.split()
    rmin, gbmax = th["red_r_min"], th["red_gb_max"]
    rm = r_ch.point(lambda v: 255 if v >= rmin else 0)
    gm = g_ch.point(lambda v: 255 if v <= gbmax else 0)
    bm = b_ch.point(lambda v: 255 if v <= gbmax else 0)
    red = ImageChops.multiply(ImageChops.multiply(rm, gm), bm)
    red_px = red.histogram()[255]
    red_bbox = red.getbbox() if red_px else None

    return {
        "size": [w, h],
        "ink_ratio": round(ink, 5),
        "content_bbox": list(bbox) if bbox else None,
        "margins": {k: round(v, 4) for k, v in margins.items()} if margins else None,
        "red_px_frac": round(red_px / total, 6),
        "red_bbox": list(red_bbox) if red_bbox else None,
    }


# ── 덤프 지오메트리 검사 ──────────────────────────────────────────────────────

def _rect_intersection(a, b):
    """rect = [top, left, bottom, right] (InDesign geometricBounds 순서)."""
    t = max(a[0], b[0]); l = max(a[1], b[1])
    bt = min(a[2], b[2]); r = min(a[3], b[3])
    if bt <= t or r <= l:
        return 0.0
    return (bt - t) * (r - l)


def _rect_area(a):
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


# W49 (실서비스 0e3e6469 실증): 템플릿 furniture — 지문번호 라벨(본문2-1),
# STEP 섹션 탭(어휘 선택 1/본문 O/X/문장 배열…), 러닝 헤더/푸터(STEP BY STEP,
# STEP01, FRAME), 간지 목차(A1 어휘 선택 A2 본문 O/X…) — 은 디자인상 재단선
# 밖·여백에 고정되고 배경 밴드와 겹쳐 배치된다. 전부 '단일 프레임 + 짧은 라벨
# 텍스트' 스토리다. 본문 플로우(다중 프레임/장문)와 구조적으로 구별되므로
# GEOM_OOB(단일 프레임 review)·GEOM_OVERLAP(furniture끼리)에서 오탐 제외한다.
# 어휘 특례가 아니라 furniture의 구조 지문(단일 프레임·소형 라벨)으로 판정.
_FURNITURE_TEXT_MAX = 64        # 라벨/탭/목차 furniture 최대 텍스트 길이
_FURNITURE_OOB_BLEED = 0.12     # furniture OOB를 오탐으로 볼 최대 이탈(블리드 관행)


def _story_text_len(st):
    return sum(len((p.get("t") or "").strip())
               for p in st.get("paragraphs", []) or [])


def _is_label_furniture(st, n_placed):
    """단일 프레임 + 짧은 라벨 텍스트 = 템플릿 furniture (GEOM 오탐 제외 대상)."""
    return n_placed <= 1 and _story_text_len(st) <= _FURNITURE_TEXT_MAX


def geometry_checks(dump, th=None):
    """덤프의 프레임 지오메트리(fb, additive)로 경계 이탈/겹침 검출.

    fb = 스토리별 프레임 geometricBounds [t,l,b,r] (fp와 병렬), 페이지 인벤토리의
    b = 페이지 bounds. 구버전 덤프(필드 없음)면 빈 결과 — fail-open.
    반환: {page_name: [flag, ...]}
    """
    th = th or THRESHOLDS
    page_bounds = {}
    for pg in dump.get("pages", []):
        if pg.get("b"):
            page_bounds[pg["p"]] = pg["b"]
    # 페이지별 (story_idx, rect, 스토리 프레임 수) 수집
    frames_by_page = {}
    for st in dump.get("stories", []):
        fps = st.get("fp") or []
        fbs = st.get("fb") or []
        n_placed = sum(1 for fp, fb in zip(fps, fbs) if fp and fb)
        furniture = _is_label_furniture(st, n_placed)
        for fp, fb in zip(fps, fbs):
            if not fp or not fb:
                continue
            frames_by_page.setdefault(fp, []).append(
                (st.get("idx"), fb, n_placed, furniture))

    flags = {}

    def add(pg, code, level, detail):
        flags.setdefault(pg, []).append(
            {"code": code, "level": level, "detail": detail})

    def _oob_frac(fb, pb):
        ph = max(1.0, pb[2] - pb[0])
        pw = max(1.0, pb[3] - pb[1])
        return max(
            (pb[0] - fb[0]) / ph, (fb[2] - pb[2]) / ph,
            (pb[1] - fb[1]) / pw, (fb[3] - pb[3]) / pw)

    for pg, frames in frames_by_page.items():
        pb = page_bounds.get(pg)
        if pb:
            for idx, fb, n_placed, furniture in frames:
                # 페이지 밖으로 나간 깊이 (각 변, 페이지 크기 비율).
                # 좌표계 이중 해석 (W30 r13 실측): 덤프 fb는 룰러 원점에 따라
                # 페이지 상대일 수 있는데 페이지 b는 스프레드 좌표라, 오른쪽
                # 페이지가 전부 '89% 이탈' 오탐됐다. 스프레드 해석과 페이지
                # 상대 해석([0,0,h,w]) 중 위반이 작은 쪽을 채택 — 어느 좌표계
                # 덤프든 진짜 이탈만 남는다 (세로 축은 두 해석이 동일).
                over = min(_oob_frac(fb, pb),
                           _oob_frac(fb, [0, 0, pb[2] - pb[0], pb[3] - pb[1]]))
                # W49: 단일 프레임 짧은 라벨 furniture(지문번호 사이드 라벨·
                # STEP 섹션 탭·러닝 헤더/푸터)가 재단선 밖으로 나가는 건 의도적
                # 블리드 디자인(실서비스 0e3e6469: 7.2% 이탈 22건 전부 섹션 탭)
                # → 오탐 제외. 단, 블리드 관행 범위(_FURNITURE_OOB_BLEED)까지만
                # 봐준다 — 라벨이 통째로 엉뚱한 위치로 떨어진 대이탈은 그대로 검출.
                if furniture and over <= _FURNITURE_OOB_BLEED:
                    continue
                # 단일 프레임 장식 스토리(섹션 탭/라벨)는 의도적 재단선 밖
                # 배치가 관행(r13 실측: 상단 탭 -21.5mm) — review로 낮춘다.
                # 다중 프레임(본문 플로우) 이탈은 내용 잘림 위험 → critical.
                if over > th["oob_critical_frac"]:
                    level = "critical" if n_placed > 1 else "review"
                    add(pg, "GEOM_OOB", level,
                        f"스토리 {idx} 프레임 {fb} 페이지 이탈 {over:.1%}")
                elif over > th["oob_review_frac"]:
                    add(pg, "GEOM_OOB", "review",
                        f"스토리 {idx} 프레임 {fb} 페이지 이탈 {over:.1%}")
        # 서로 다른 스토리 프레임 겹침
        for i in range(len(frames)):
            for j in range(i + 1, len(frames)):
                si, ra = frames[i][0], frames[i][1]
                sj, rb = frames[j][0], frames[j][1]
                if si == sj:
                    continue
                # W49: furniture끼리(러닝 헤더/푸터·STEP 탭·FRAME·간지 목차 등
                # 라벨 장식)의 겹침은 레이어드 디자인 관행 → 오탐 제외. 실서비스
                # 0e3e6469 doc_flags 16건 전부가 이 furniture×furniture 부류였다.
                # '한쪽만 furniture'(라벨 프레임이 본문 플로우를 침범 — r13
                # 추가지문 라벨×본문 실결함)는 그대로 검출한다. 본문 이중 조판
                # (양쪽 실콘텐츠)도 마찬가지로 검출.
                if frames[i][3] and frames[j][3]:
                    continue
                inter = _rect_intersection(ra, rb)
                if not inter:
                    continue
                denom = min(_rect_area(ra), _rect_area(rb)) or 1.0
                frac = inter / denom
                if frac > th["overlap_review_frac"]:
                    add(pg, "GEOM_OVERLAP", "review",
                        f"스토리 {si}×{sj} 겹침 {frac:.0%}")
    return flags


def overset_pages(dump):
    """오버셋 스토리 → 마지막 프레임이 놓인 페이지 이름 매핑. 미상은 ''."""
    out = []
    for st in dump.get("stories", []):
        if not st.get("overflow"):
            continue
        pg = ""
        for cand in reversed(st.get("fp") or []):
            if cand:
                pg = cand
                break
        if not pg:
            pgs = st.get("pg") or []
            pg = pgs[-1] if pgs else ""
        out.append({"story": st.get("idx"), "page": pg})
    return out


# ── 종합 검사 ─────────────────────────────────────────────────────────────────

def inspect_pages(png_paths, dump=None, thresholds=None):
    """페이지 PNG 목록(+옵션 덤프) → 시각 검수 리포트 dict."""
    th = dict(THRESHOLDS)
    if thresholds:
        th.update(thresholds)

    dump_pages = (dump or {}).get("pages") or []
    use_dump_pages = len(dump_pages) == len(png_paths)

    pages = []
    for i, png in enumerate(png_paths):
        m = page_metrics(png, th)
        rec = {"page": i + 1, "png": png, "flags": []}
        rec.update(m)
        if use_dump_pages:
            rec["name"] = dump_pages[i].get("p")
            rec["master"] = dump_pages[i].get("m")
            rec["side"] = dump_pages[i].get("side")
        else:
            rec["name"] = str(i + 1)
            rec["side"] = "R" if i % 2 == 0 else "L"   # offset 0 = p1 = 오른쪽
        pages.append(rec)

    def add(rec, code, level, detail):
        rec["flags"].append({"code": code, "level": level, "detail": detail})

    doc_flags = []

    # V1 — 거의 빈 페이지. 양품 실측(2026-07-18): 배면 단면 인쇄 패턴(같은
    # 좌/우면만 연속 공백 — c14_wb3 44장, c20_mock 22장)이 정상 존재 →
    # 동일면 3장 이상 패턴은 페이지별 info + 문서 요약 review 1건으로 병합.
    nb = [rec for rec in pages if rec["ink_ratio"] < th["near_blank_ink"]]
    nb_sides = {rec["side"] for rec in nb}
    nb_pattern = len(nb) >= 3 and len(nb_sides) == 1
    for rec in nb:
        expected_empty = use_dump_pages and dump_pages[rec["page"] - 1].get("empty")
        if expected_empty or nb_pattern:
            add(rec, "NEAR_BLANK", "info",
                f"잉크 비율 {rec['ink_ratio']:.3%}"
                + (" (덤프상 빈 페이지 — 예상됨)" if expected_empty else " (단면 패턴)"))
        else:
            add(rec, "NEAR_BLANK", "review", f"잉크 비율 {rec['ink_ratio']:.3%}")
    if nb_pattern:
        doc_flags.append({
            "code": "NEAR_BLANK_PATTERN", "level": "review",
            "detail": (f"{nb_sides.pop()}면 {len(nb)}장 연속 공백 패턴 "
                       f"(p{nb[0]['page']}~{nb[-1]['page']}) — 단면 구성 의도인지 1회 확인")})

    # V2/V3 — 과밀/적색. 전면 간지(잉크>fullbleed)는 정상 디자인이라 제외.
    for rec in pages:
        if th["overdense_ink"] < rec["ink_ratio"] <= th["fullbleed_ink"]:
            add(rec, "OVERDENSE", "review", f"잉크 비율 {rec['ink_ratio']:.1%}")
        if rec["red_px_frac"] > th["red_px_frac"]:
            add(rec, "RED_MARK", "review",
                f"순적색 픽셀 {rec['red_px_frac']:.3%} @ {rec['red_bbox']}")

    # V7 — (마스터, 좌우) 그룹 내 콘텐츠 박스 outlier.
    # 마스터 정보(덤프 페이지 인벤토리)가 있을 때만 — 좌/우 단독 그룹핑은 다중
    # 섹션 문서에서 오탐 폭발(양품 실측 c05_mock 73건) → 비활성.
    if use_dump_pages:
        groups = {}
        for rec in pages:
            if not rec.get("margins"):
                continue
            if not (th["layout_min_ink"] <= rec["ink_ratio"] <= th["fullbleed_ink"]):
                continue
            key = (rec.get("master") or "", rec.get("side") or "")
            groups.setdefault(key, []).append(rec)
        tol = th["layout_margin_tol"]
        for key, members in groups.items():
            if len(members) < th["layout_min_group"]:
                continue
            for edge in ("left", "top", "right", "bottom"):
                vals = sorted(r["margins"][edge] for r in members)
                med = vals[len(vals) // 2]
                for r in members:
                    dev = abs(r["margins"][edge] - med)
                    if dev > tol and not any(
                            f["code"] == "LAYOUT_OUTLIER" for f in r["flags"]):
                        add(r, "LAYOUT_OUTLIER", "review",
                            f"{edge} 여백 {r['margins'][edge]:.3f} vs "
                            f"그룹중앙 {med:.3f} (마스터 {key[0] or '?'}/{key[1]})")
    by_name = {}
    for rec in pages:
        by_name.setdefault(rec["name"], rec)

    # V4 — 오버셋 (덤프)
    if dump:
        for ov in overset_pages(dump):
            rec = by_name.get(ov["page"])
            detail = f"오버셋 스토리 {ov['story']}"
            if rec is not None:
                add(rec, "OVERSET", "critical", detail)
            else:
                doc_flags.append({"code": "OVERSET", "level": "critical",
                                  "detail": detail + " (페이지 미상)"})
        # V5/V6 — 지오메트리
        for pg_name, fl in geometry_checks(dump, th).items():
            rec = by_name.get(pg_name)
            for f in fl:
                if rec is not None:
                    rec["flags"].append(f)
                else:
                    doc_flags.append(dict(f, detail=f"{f['detail']} (p{pg_name})"))
        # W30 (r13 라벨 겹침 미검출 실증): fb 없는 구버전 덤프는 지오메트리
        # 검사가 조용히 건너뛰어져 '무플래그=통과'로 오독됐다 — 침묵 금지,
        # 미수행을 명시 플래그로 남긴다 (fail-open 유지: review 수준).
        if dump.get("stories") and not any(
                st.get("fb") for st in dump["stories"]):
            doc_flags.append({
                "code": "GEOM_SKIPPED", "level": "review",
                "detail": "덤프에 프레임 지오메트리(fb) 없음(구버전) — "
                          "겹침/이탈 검사 미수행. 재덤프 권장."})

    all_flags = doc_flags + [f for r in pages for f in r["flags"]]
    n_crit = sum(1 for f in all_flags if f["level"] == "critical")
    n_review = sum(1 for f in all_flags if f["level"] == "review")
    flagged = [r["page"] for r in pages
               if any(f["level"] in ("critical", "review") for f in r["flags"])]
    return {
        "version": 1,
        "thresholds": th,
        "page_count": len(pages),
        "pages": pages,
        "doc_flags": doc_flags,
        "summary": {
            "critical": n_crit,
            "review": n_review,
            "flagged_pages": flagged,
            "dump_used": bool(dump),
        },
        "ok": n_crit == 0,
    }


# ── job 레벨 진입점 (verify 후처리 훅) ────────────────────────────────────────

def _find_output_files(obj, exts, out):
    if isinstance(obj, str):
        if obj.lower().endswith(exts) and os.path.isfile(obj):
            out.append(obj)
    elif isinstance(obj, list):
        for v in obj:
            _find_output_files(v, exts, out)
    elif isinstance(obj, dict):
        for v in obj.values():
            _find_output_files(v, exts, out)
    return out


def inspect_job_visual(job_dir, log, result=None, dpi=DEFAULT_DPI,
                       allow_indesign=False, timeout=900):
    """job 산출물을 자동 발견해 시각 검수 실행 → visual_report.json.

    발견 순서: verify result → .settings.json 에서 .pdf (없으면 .indd).
    PDF가 없고 allow_indesign=False 면 None (InDesign 재기동을 강제하지 않음).
    덤프는 job_dir/typeset_dump*.json 이 있으면 함께 사용.
    반환: report dict (report["report_path"] 포함) 또는 None(대상 없음).
    """
    job_dir = os.path.abspath(job_dir)
    sources = []
    if isinstance(result, dict):
        sources.append(result)
    settings_path = os.path.join(job_dir, ".settings.json")
    if os.path.isfile(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            sources.append(json.load(f))

    pdfs, indds = [], []
    for src in sources:
        _find_output_files(src, (".pdf",), pdfs)
        _find_output_files(src, (".indd",), indds)
    pdfs = list(dict.fromkeys(pdfs))
    indds = list(dict.fromkeys(indds))

    dump = None
    for name in sorted(os.listdir(job_dir)):
        if name.startswith("typeset_dump") and name.endswith(".json"):
            try:
                with open(os.path.join(job_dir, name), encoding="utf-8") as f:
                    dump = json.load(f)
                break
            except (OSError, ValueError):
                continue

    pages_dir = os.path.join(job_dir, "visual_pages")
    if pdfs:
        pngs, backend = render_pdf_pages(pdfs[0], pages_dir, dpi=dpi, log=log)
        source = pdfs[0]
    elif indds and allow_indesign:
        pngs, backend = render_indd_pages(indds[0], pages_dir, log,
                                          dpi=dpi, timeout=timeout)
        source = indds[0]
    else:
        return None

    report = inspect_pages(pngs, dump=dump)
    report["source"] = source
    report["render_backend"] = backend
    report["dpi"] = dpi
    report_path = os.path.join(job_dir, "visual_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    report["report_path"] = report_path
    if log:
        s = report["summary"]
        log(f"[시각검수] {report['page_count']}p — critical {s['critical']}, "
            f"review {s['review']} (페이지 {s['flagged_pages'][:10]}…)"
            if len(s["flagged_pages"]) > 10 else
            f"[시각검수] {report['page_count']}p — critical {s['critical']}, "
            f"review {s['review']} (페이지 {s['flagged_pages']})")
    return report
