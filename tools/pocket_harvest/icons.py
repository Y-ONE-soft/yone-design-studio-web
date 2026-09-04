# -*- coding: utf-8 -*-
"""완성본 IDML → 계열 아이콘 SVG.

포켓북의 딱지(FLOW NOTE·암기 TEST·동반의어)와 노란 형광펜의 '서술형★' 표식은
**글자가 아니라 벡터 그룹**이다. 이모지나 글리프로 대신하면 원본과 아예 다른
그림이 된다(실측 지적). 원본에서 패스를 그대로 떠 온다.

받는 것:
    Group  ├ Polygon    색면
           ├ EPSText    아웃라인 글자(동반의어의 A·B·C)
           └ TextFrame  틀 모양 자체가 그림인 경우(서술형의 ★)

색은 CMYK 라 **USWebCoatedSWOP** 로 옮긴다 — 그래야 완성본에서 잰 값과 맞는다
(`chip #869CD0`·`band #EAE6DC` 로 검증).

    python3 tools/pocket_harvest/icons.py [출력폴더]
"""
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

REF = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북/_idml/pocketbook/26-1-중간")
BOOK_MAIN = os.path.join(REF, "광문1", "광문1_포켓북_내지.idml")
BOOK_HL = os.path.join(REF, "광문2", "광문2_포켓북_내지.idml")
OUT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))),
    "core", "render_vivlio", "assets", "pocketbook")
PROFILE = ("/Library/Application Support/Adobe/Color/Profiles/Recommended/"
           "USWebCoatedSWOP.icc")
SHAPES = ("Polygon", "Rectangle", "Oval", "EPSText", "TextFrame", "GraphicLine")


def _swatches(z):
    out = {}
    for n in z.namelist():
        if n.startswith("Resources/Graphic"):
            for c in ET.fromstring(z.read(n)).iter("Color"):
                out[c.get("Self")] = c.get("ColorValue")
    return out


def _rgb(cv, fallback="#000000"):
    if not cv:
        return fallback
    from PIL import Image, ImageCms
    c, m, y, k = [float(v) for v in cv.split()]
    im = Image.new("CMYK", (1, 1), tuple(round(v * 255 / 100)
                                         for v in (c, m, y, k)))
    px = ImageCms.profileToProfile(
        im, PROFILE, ImageCms.createProfile("sRGB"),
        renderingIntent=0, outputMode="RGB").getpixel((0, 0))
    return "#%02X%02X%02X" % px


def _paths(el, dx, dy):
    """도형 → SVG path d. 앵커·핸들이 곧 3차 베지에다."""
    out = []
    for gp in el.iter("GeometryPathType"):
        pts = []
        for q in gp.findall("PathPointArray/PathPointType"):
            def pt(name):
                v = [float(x) for x in q.get(name).split()]
                return (v[0] + dx, v[1] + dy)
            pts.append((pt("Anchor"), pt("LeftDirection"), pt("RightDirection")))
        if len(pts) < 2:
            continue
        d = ["M%.2f %.2f" % pts[0][0]]
        for i in range(1, len(pts)):
            d.append("C%.2f %.2f %.2f %.2f %.2f %.2f"
                     % (pts[i - 1][2] + pts[i][1] + pts[i][0]))
        d.append("C%.2f %.2f %.2f %.2f %.2f %.2fZ"
                 % (pts[-1][2] + pts[0][1] + pts[0][0]))
        out.append(" ".join(d))
    return out


def group_svg(z, group, sw, base=(0.0, 0.0), fallback="#000000"):
    """앵커 그룹 → SVG 문자열. 자식의 ItemTransform 을 그대로 더한다."""
    parts = []

    def walk(el, dx, dy):
        for ch in el:
            if ch.tag not in SHAPES and ch.tag != "Group":
                continue
            tf = [float(v) for v in
                  (ch.get("ItemTransform") or "1 0 0 1 0 0").split()]
            x, y = dx + tf[4], dy + tf[5]
            if ch.tag == "Group":
                walk(ch, x, y)
                continue
            fill = _rgb(sw.get(ch.get("FillColor")), fallback)
            for d in _paths(ch, x, y):
                parts.append((fill, d))

    walk(group, base[0], base[1])
    xs, ys = [], []
    for _f, d in parts:
        for m in re.finditer(r"(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)", d):
            xs.append(float(m.group(1)))
            ys.append(float(m.group(2)))
    if not xs:
        return None
    vb = (min(xs) - .2, min(ys) - .2,
          max(xs) - min(xs) + .4, max(ys) - min(ys) + .4)
    body = "".join('<path fill="%s" fill-rule="evenodd" d="%s"/>' % (f, d)
                   for f, d in parts)
    return ('<svg xmlns="http://www.w3.org/2000/svg" '
            'viewBox="%.2f %.2f %.2f %.2f">%s</svg>' % (vb + (body,))), vb


def _story_groups(z, story_id):
    n = "Stories/Story_%s.xml" % story_id
    if n not in z.namelist():
        return []
    st = ET.fromstring(z.read(n))
    return [g for csr in st.iter("CharacterStyleRange")
            for g in csr if g.tag == "Group"]


def from_master_chips(path, wanted):
    """마스터의 딱지 프레임 안에 앵커된 그룹을 이름별로 뽑는다."""
    z = zipfile.ZipFile(path)
    sw = _swatches(z)
    found = {}
    for n in sorted(x for x in z.namelist() if x.startswith("MasterSpreads/")):
        for tf in ET.fromstring(z.read(n)).iter("TextFrame"):
            sid = tf.get("ParentStory")
            fn = "Stories/Story_%s.xml" % sid
            if fn not in z.namelist():
                continue
            txt = "".join(t.text or ""
                          for t in ET.fromstring(z.read(fn)).iter("Content"))
            for key, needle in wanted.items():
                if key in found or needle not in txt:
                    continue
                for g in _story_groups(z, sid):
                    got = group_svg(z, g, sw)
                    if got:
                        found[key] = got
                        break
    return found


def from_highlight(path):
    """노란 형광펜에 앵커된 '서술형★'."""
    z = zipfile.ZipFile(path)
    sw = _swatches(z)
    for n in z.namelist():
        if not n.startswith("Stories/"):
            continue
        raw = z.read(n).decode("utf-8", "ignore")
        if "노랑" not in raw:
            continue
        for csr in ET.fromstring(raw).iter("CharacterStyleRange"):
            if "노랑" not in (csr.get("AppliedCharacterStyle") or ""):
                continue
            g = csr.find("Group")
            if g is None:
                continue
            got = group_svg(z, g, sw, fallback="#D2232A")
            if got:
                return got
    return None


def _with_abc(svg, vb):
    """동반의어 표식의 **A·B·C**.

    `EPSText` 는 아웃라인이 아니라 **글자를 품고 있다** — 데이터를 풀어 보면
    `JalnanOTF`(여기어때 잘난체)와 남색(c66m52y0k19)이 나온다. 우리도 그 서체를
    쓰므로 **같은 글자를 같은 서체로** 얹으면 원본 그대로가 된다. 기울기까지
    맞춘다(원본 ItemTransform: 10.9°·-13.3°·0°) — 색면이 기울어 있으니 글자도
    같이 기울어야 한다.
    ⚠ 그래서 이 표식은 `<img>` 가 아니라 **HTML 안에 그대로 심어야** 한다
      (외부 SVG 는 지면 서체를 못 쓴다).
    """
    import math
    boxes = []
    for m in re.finditer(r'd="([^"]+)"', svg):
        pts = [(float(q.group(1)), float(q.group(2)))
               for q in re.finditer(r"(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)",
                                    m.group(1))]
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        # 첫 변의 기울기 = 그 색면의 기울기
        ang = math.degrees(math.atan2(pts[3][1] - pts[0][1],
                                      pts[3][0] - pts[0][0])) if len(pts) > 3 else 0.0
        while ang > 45:
            ang -= 90
        while ang < -45:
            ang += 90
        boxes.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                      max(xs) - min(xs), ang))
    boxes.sort(key=lambda b: b[0])
    size = (sum(b[2] for b in boxes) / max(len(boxes), 1)) * 0.62
    txt = "".join(
        '<text x="%.2f" y="%.2f" font-size="%.2f" fill="#54669F" '
        'font-family="PBJalnan,sans-serif" text-anchor="middle" '
        'dominant-baseline="central" transform="rotate(%.1f %.2f %.2f)">%s</text>'
        % (b[0], b[1], size, b[3], b[0], b[1], ch)
        for b, ch in zip(boxes, "ABC"))
    return svg.replace("</svg>", txt + "</svg>"), vb


def main(out=None):
    out = out or OUT
    os.makedirs(out, exist_ok=True)
    got = from_master_chips(BOOK_MAIN, {
        "chip_flow": "FLOW NOTE",
        "chip_memtest": "암기 TEST",
        "synmark": "동반의어",
    })
    seosul = from_highlight(BOOK_HL)
    if seosul:
        got["seosul"] = seosul
    if "synmark" in got:
        got["synmark"] = _with_abc(*got["synmark"])
    for name, (svg, vb) in sorted(got.items()):
        p = os.path.join(out, name + ".svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write(svg)
        print("  %-14s %6.2f×%-6.2fpt  %6d bytes  → %s"
              % (name, vb[2], vb[3], len(svg), os.path.basename(p)))
    missing = {"chip_flow", "chip_memtest", "synmark", "seosul"} - set(got)
    if missing:
        print("  ⚠ 못 찾음: %s" % ", ".join(sorted(missing)))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
