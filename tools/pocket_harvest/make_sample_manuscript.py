# -*- coding: utf-8 -*-
"""교재팀에게 줄 **포켓북 원고 양식 샘플**(.hwpx)을 만든다.

새 서식을 발명하지 않는다. 지금 쓰는 플로우노트 원고가 이미
**지문 1개 = 표 1개 / 3행**(제목·흐름·주제요약) 구조이므로, 거기에
**`동반의어` 행 하나만 더** 붙인 모습을 실물로 보여 준다.

한글이 확실히 열도록 **실제 원고 파일을 뼈대로 삼아** 표 두 개만 남기고
내용을 바꾼다(스타일 ID·표 속성을 그대로 물려받는다). 빈 문서에서 hwpx 를
조립하면 한글이 거부할 위험이 있다.

⚠ GDrive 원본은 열지 않는다 — 로컬로 복사한 사본에서만 읽는다.
"""
import os
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
P = "{%s}" % NS

SRC = ("~/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/"
       "콘텐츠 관리/내신대비/플로우노트DB/고2/2409.hwpx")

# 샘플 두 벌 — ① 회차 지문(키가 이미 있는 것) ② 학교 지문(키를 새로 적는 것)
SAMPLES = [
    {
        "title": "24-9 21번 Flow",
        "flow": [
            "정보화시대 – 목표 = 오류 방지, 반복 가능성 X",
            "[반대로] 목표 = 창의성, 속도, 그리고 명민함",
            "산업화 시대 – 목표 = 변화를 최소화 시키는 것",
            "[그러나] 오늘날 – 변화를 극대화",
        ],
        "blank": [
            "정보화시대 – 목표 = 오류 방지, _____________ X",
            "[반대로] 목표 = __________, _____, 그리고 _______",
            "산업화 시대 – 목표 = 변화를 ________ 시키는 것",
            "[그러나] 오늘날 – 변화를 __________",
        ],
        "topic": [
            "주제: 현대 기업에서의 혁신과 창의성의 중요성",
            "요약문: 정보화 시대의 기업들은 과거 산업시대의 일관성과 오류 예방 "
            "중심에서 벗어나, 창의성과 변화를 수용하는 유연한 조직으로 변화해야 한다.",
        ],
        "syn": [
            "동반의어",
            "consistency 일관성 = uniformity, steadiness ↔ variability, change",
            "agility 민첩함 = nimbleness, quickness ↔ sluggishness, delay",
            "minimize 최소화하다 = reduce, lessen ↔ maximize, expand",
            "pursue 추구하다 = seek, chase ↔ abandon, give up",
            "organization 조직 = institution, body ↔ individual",
            "adapt 적응하다 = adjust, accommodate ↔ resist, refuse",
        ],
    },
    {
        "title": "명일2 4과 본문2",
        "flow": [
            "① 도입 — 커피 소비가 만드는 폐기물",
            "→ 전 세계가 하루 20억 잔을 마시고 그만큼의 커피박이 남는다.",
            "② 문제 — 매립되면 메탄이 나온다",
            "→ 유기물이라 그냥 묻으면 온실가스가 된다.",
        ],
        "blank": [
            "① 도입 — 커피 소비가 만드는 _______",
            "→ 전 세계가 하루 20억 잔을 마시고 그만큼의 _______이 남는다.",
            "② 문제 — 매립되면 _____이 나온다",
            "→ 유기물이라 그냥 묻으면 _______가 된다.",
        ],
        "topic": [
            "주제: 커피 폐기물의 환경적 영향과 순환 경제",
            "요약문: 커피박은 매립 시 온실가스를 배출하지만 자원으로 되돌리면 "
            "순환 경제의 좋은 사례가 된다.",
        ],
        "syn": [
            "동반의어",
            "waste 폐기물 = refuse, byproduct ↔ resource, asset",
            "landfill 매립지 = dump, tip",
            "emit 배출하다 = release, give off ↔ absorb, retain",
            "circular 순환의 = cyclical, recurring ↔ linear",
            "depend on ~ ~에 달려 있다 = rely on, hinge on",
        ],
    },
]

HEAD = ("[포켓북 원고 양식]  표 하나 = 지문 하나 (4행: 키 / 흐름 / 주제·요약문 / 동반의어).  "
        "흐름은 쓰시던 그대로.  주제·요약문은 **한글**로 반드시 채워 주세요"
        "(분석본의 영어 주제는 포켓북에 못 씁니다).  동반의어 행은 새로 씁니다.  "
        "색·굵게(**별표**)는 쓰지 마세요 — 별표가 그대로 인쇄됩니다. "
        "화살표(→)만 주황으로 나갑니다 — 나머지는 검정입니다.")


def _para_text(p):
    return "".join(t.text or "" for t in p.iter(P + "t"))


def _set_lines(cell, lines):
    """셀의 문단을 lines 로 갈아 끼운다. 첫 문단을 틀로 복제한다."""
    sub = cell.find(P + "subList")
    paras = sub.findall(P + "p")
    tmpl = paras[0]
    for p in paras[1:]:
        sub.remove(p)
    # 줄 배치 캐시는 지운다 — 한글이 열 때 다시 계산한다
    for lsa in tmpl.findall(P + "linesegarray"):
        tmpl.remove(lsa)
    made = []
    for i, line in enumerate(lines):
        p = tmpl if i == 0 else _clone(tmpl)
        t = p.find(".//" + P + "t")
        if t is None:                       # 빈 셀은 run 만 있고 t 가 없다
            run = p.find(P + "run")
            if run is None:
                run = ET.SubElement(p, P + "run")
                run.set("charPrIDRef", "3")
            t = ET.SubElement(run, P + "t")
        t.text = line
        if i:
            sub.append(p)
        made.append(p)
    return made


def _clone(el):
    import copy
    return copy.deepcopy(el)


def build(out_path):
    src = os.path.expanduser(SRC)
    if not os.path.exists(src):
        raise SystemExit("원본 없음: %s" % src)
    tmp = tempfile.mkdtemp(prefix="pbsample_")
    local = os.path.join(tmp, "src.hwpx")
    shutil.copy2(src, local)                     # GDrive 는 읽기만, 사본에서 작업

    zin = zipfile.ZipFile(local)
    sec = zin.read("Contents/section0.xml").decode("utf-8")
    ET.register_namespace("hp", NS)
    for pfx, uri in _prefixes(sec).items():
        ET.register_namespace(pfx, uri)
    root = ET.fromstring(sec)

    # ⚠ 표는 **한 run 안에 형제로 여러 개** 들어 있다(원본은 문단 2개에 표 19개).
    #   문단이나 run 을 통째로 지우면 표가 딸려 오거나 남는다 → tbl 을 하나씩 뗀다.
    body = root
    parent = {}
    for anc in body.iter():
        for ch in list(anc):
            parent[id(ch)] = anc
    kept_tbls = []
    for t in list(body.iter(P + "tbl")):
        if len(kept_tbls) < len(SAMPLES):
            kept_tbls.append(t)
        else:
            parent[id(t)].remove(t)
    # 표가 빠져 알맹이가 없어진 문단은 지운다
    for para in list(body.findall(P + "p")):
        if not list(para.iter(P + "tbl")) and not _para_text(para).strip():
            body.remove(para)

    for tbl, spec in zip(kept_tbls, SAMPLES):
        rows = tbl.findall(P + "tr")
        title_cells = rows[0].findall(P + "tc")
        _set_lines(title_cells[0], [spec["title"]])
        if len(title_cells) > 1:
            _set_lines(title_cells[1], [""])
        body_cells = rows[1].findall(P + "tc")
        _set_lines(body_cells[0], spec["flow"])
        if len(body_cells) > 1:
            _set_lines(body_cells[1], spec["blank"])
        topic_cells = rows[2].findall(P + "tc")
        _set_lines(topic_cells[0], spec["topic"])

        # ── 동반의어 행 추가 ──
        new_tr = _clone(rows[2])
        tc = new_tr.find(P + "tc")
        addr = tc.find(P + "cellAddr")
        if addr is not None:
            addr.set("rowAddr", "3")
        _set_lines(tc, spec["syn"])
        tbl.append(new_tr)
        tbl.set("rowCnt", "4")
        # 표 높이는 한글이 다시 잡는다 — 지정값이 남으면 잘려 보인다
        sz = tbl.find(P + "sz")
        if sz is not None:
            sz.set("height", str(int(sz.get("height", "28929")) * 4 // 3))

    out_sec = ET.tostring(root, encoding="unicode")
    if not out_sec.startswith("<?xml"):
        out_sec = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + out_sec

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zo:
        # mimetype 은 압축하지 않고 맨 앞에 둔다(OPC 규약)
        zo.writestr(zipfile.ZipInfo("mimetype"),
                    zin.read("mimetype"), zipfile.ZIP_STORED)
        for n in zin.namelist():
            if n == "mimetype":
                continue
            if n == "Contents/section0.xml":
                zo.writestr(n, out_sec.encode("utf-8"))
            elif n == "Preview/PrvText.txt":
                zo.writestr(n, HEAD.encode("utf-8"))
            else:
                zo.writestr(n, zin.read(n))
    zin.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return out_path


def _prefixes(xml_text):
    import re
    return dict(re.findall(r'xmlns:([A-Za-z0-9_]+)="([^"]+)"', xml_text[:4000]))


if __name__ == "__main__":
    p = build(os.path.expanduser(sys.argv[1]))
    print("→", p, os.path.getsize(p), "bytes")
