"""폰트 cmap 커버리지 판독 (W23 r13 — 게이트 G29 [글리프커버리지]).

의존성 없는 최소 sfnt cmap 파서: 덤프가 기록한 폰트 파일(location)의
cmap 테이블에서 '이 폰트가 이 문자의 글리프를 갖는가'를 실측한다 —
InDesign은 글리프 없는 문자를 tofu/공백으로 인쇄하는데 스크립팅 DOM에
글리프 조회 API가 없어, 폰트 파일 자체가 유일한 진실이다 (r13 피드백 F3:
CO₂의 U+2082가 본문 폰트 미지원으로 미표시).

지원 포맷: TrueType/OpenType sfnt(ttf/otf) + TrueType Collection(ttc).
cmap 서브테이블은 format 12(UCS-4) 우선, format 4(BMP) 폴백. 판독 불가
(포맷 미지원/파일 없음/손상)는 None — 게이트는 fail-open(검사 생략)한다.

커버리지는 '세그먼트 포함' 근사: format 4의 idRangeOffset 경유 glyphId 0
매핑(드묾)은 커버로 간주될 수 있다 — 과소 검출 방향의 근사라 게이트
warning의 오탐을 만들지 않는다. ttc는 전 폰트 얼굴의 합집합(마찬가지로
과소 검출 방향 — 얼굴별 차이는 드물고, 합집합이 '지원'이라 하면 실제로
형제 얼굴 중 하나는 지원한다).
"""
import os
import struct
from bisect import bisect_right

_COV_CACHE = {}   # path -> sorted [(start, end)] 리스트 또는 None(판독 불가)


def _read_at(f, off, n):
    f.seek(off)
    data = f.read(n)
    if len(data) != n:
        raise ValueError("truncated")
    return data


def _parse_cmap_subtable(f, off):
    """cmap 서브테이블 → [(start, end)] (미지원 포맷은 None)."""
    fmt = struct.unpack(">H", _read_at(f, off, 2))[0]
    ranges = []
    if fmt == 4:
        seg_x2 = struct.unpack(">H", _read_at(f, off + 6, 2))[0]
        seg = seg_x2 // 2
        ends = struct.unpack(">%dH" % seg, _read_at(f, off + 14, seg_x2))
        starts = struct.unpack(">%dH" % seg,
                               _read_at(f, off + 16 + seg_x2, seg_x2))
        for s, e in zip(starts, ends):
            if s == 0xFFFF and e == 0xFFFF:
                continue          # 종료 센티널 세그먼트
            ranges.append((s, e))
        return ranges
    if fmt == 12:
        n_groups = struct.unpack(">I", _read_at(f, off + 12, 4))[0]
        if n_groups > 200000:
            return None
        data = _read_at(f, off + 16, 12 * n_groups)
        for g in range(n_groups):
            s, e, _gid = struct.unpack_from(">III", data, 12 * g)
            ranges.append((s, e))
        return ranges
    return None


def _parse_face(f, face_off):
    """sfnt 얼굴 1개 → cmap 커버 [(start, end)] 또는 None."""
    hdr = _read_at(f, face_off, 12)
    num_tables = struct.unpack(">H", hdr[4:6])[0]
    if num_tables > 512:
        return None
    recs = _read_at(f, face_off + 12, 16 * num_tables)
    cmap_off = None
    for i in range(num_tables):
        tag, _cs, toff, _tlen = struct.unpack_from(">4sIII", recs, 16 * i)
        if tag == b"cmap":
            cmap_off = toff
            break
    if cmap_off is None:
        return None
    n_sub = struct.unpack(">H", _read_at(f, cmap_off + 2, 2))[0]
    if n_sub > 64:
        return None
    subs = []
    data = _read_at(f, cmap_off + 4, 8 * n_sub)
    for i in range(n_sub):
        pid, eid, soff = struct.unpack_from(">HHI", data, 8 * i)
        subs.append((pid, eid, cmap_off + soff))
    # 유니코드 서브테이블 우선순위: (3,10)/(0,4·6) fmt12 > (3,1)/(0,3) fmt4
    def _prio(rec):
        pid, eid, _ = rec
        if (pid, eid) in ((3, 10), (0, 4), (0, 6)):
            return 0
        if (pid, eid) in ((3, 1), (0, 3), (0, 2), (0, 1), (0, 0)):
            return 1
        return 9
    best = None
    for rec in sorted(subs, key=_prio):
        if _prio(rec) >= 9:
            continue
        try:
            best = _parse_cmap_subtable(f, rec[2])
        except (ValueError, struct.error):
            best = None
        if best is not None:
            return best
    return None


def _load_coverage(path):
    """폰트 파일 → 병합·정렬된 [(start, end)] 또는 None (판독 불가)."""
    try:
        with open(path, "rb") as f:
            head = _read_at(f, 0, 4)
            faces = [0]
            if head == b"ttcf":
                n = struct.unpack(">I", _read_at(f, 8, 4))[0]
                if n > 64:
                    return None
                faces = list(struct.unpack(">%dI" % n, _read_at(f, 12, 4 * n)))
            elif head not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
                return None
            ranges = []
            got = False
            for face_off in faces:
                cov = _parse_face(f, face_off)
                if cov is not None:
                    got = True
                    ranges.extend(cov)
            if not got:
                return None
    except (OSError, ValueError, struct.error):
        return None
    ranges.sort()
    merged = []
    for s, e in ranges:
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def font_covers(path, ch):
    """폰트 파일이 문자 ch의 글리프를 갖는가 — True/False/None(판독 불가)."""
    if not path or not os.path.isfile(path):
        return None
    cov = _COV_CACHE.get(path)
    if path not in _COV_CACHE:
        cov = _load_coverage(path)
        _COV_CACHE[path] = cov
    if cov is None:
        return None
    cp = ord(ch)
    i = bisect_right(cov, (cp, 0x10FFFF))
    if i > 0 and cov[i - 1][0] <= cp <= cov[i - 1][1]:
        return True
    if i < len(cov) and cov[i][0] <= cp <= cov[i][1]:
        return True
    return False
