# -*- coding: utf-8 -*-
"""포켓북 **어휘 파트** — 단어장 원고(xlsx) → 지면 항목.

학교에 따라 포켓북 뒤에 어휘(또는 듣기)가 붙는다. 광문1 은 `어휘끝 고교기본`
Unit 15~23 이 들어간다(26-1-기말 완성본에도 같은 자리에 있었다).

## 원고 모양 (광문보카 xlsx 실측)

시트 하나가 Unit 하나이고, 낱말 하나가 **빈 줄로 끊긴 덩이**다:

    B        C                          D
    DAY15    회독
    1        sensible                   [형] 분별력 있는, 현명한 (↔ senseless …)
             [ˈsɛnsəbəl]
             sensitivity [명] 민감함 …   It wasn’t [sensible] to go out alone …   ← 파생어는 C, 예문은 D
                                        너무 늦은 저녁에 혼자 밖에 나간 것은 …
    (빈 줄)

  · C 칸은 자리에 따라 **표제어 → 발음기호 → 파생어** 로 뜻이 바뀐다.
  · D 칸의 예문은 **영어·한글이 번갈아** 온다. 한 낱말에 예문이 둘일 수 있다.
  · `[…]` 는 그 낱말이 쓰인 자리다 — 지면에서 색이 붙는다.

## 지면 규격 (26-1-기말 광문1 완성본 실측)

    한 면 15낱말 · 한 DAY(30낱말) = 펼침면 하나
    상자 115×177mm · 표제어 10pt / 뜻 7pt(행간 12) / 예문·예문뜻 6pt(행간 7)
    강조색 CMYK 10/85/57/0 = #DB4D5D
"""
import os
import re

_HAN = re.compile(r"[가-힣]")
_IPA = re.compile(r"^\[[^]]*\]$")
_DAY = re.compile(r"^(DAY|Day|Unit)\s*(\d+)", re.I)


def read(path, log=lambda m: None):
    """단어장 xlsx → [{day, no, word, ipa, mean, derived, ex:[(en,ko)…]}].

    시트 차례가 곧 책 차례다(Unit 15 → 16 → …). 시트 이름이 아니라 **B 칸의
    `DAY15`** 를 머리말로 쓴다 — 완성본 꼬리말이 그 말을 쓴다.
    """
    try:
        import openpyxl
    except ImportError:
        log("[어휘] openpyxl 이 없어 어휘 파트를 건너뛴다")
        return []
    if not path or not os.path.exists(path):
        log("[어휘] 원고를 못 찾았다: %s" % path)
        return []
    wb = openpyxl.load_workbook(path, data_only=True)
    out = []
    for name in wb.sheetnames:
        rows = list(wb[name].iter_rows(values_only=True))
        out += _sheet(rows, name)
    log("■ 어휘 %d낱말 (%d일치)" % (out and len(out) or 0,
                                len({e["day"] for e in out})))
    return out


def _cell(r, i):
    v = r[i] if r and len(r) > i else None
    return "" if v is None else str(v).strip()


def _sheet(rows, sheet):
    out, cur, day = [], None, sheet
    for r in rows:
        b, c, d = _cell(r, 1), _cell(r, 2), _cell(r, 3)
        if _DAY.match(b):                      # `DAY15 / 회독` — 덩이 머리
            day = b
            continue
        if not (b or c or d):                  # 빈 줄 — 덩이 끝
            if cur:
                out.append(cur)
                cur = None
            continue
        if b.isdigit():                        # 번호 줄 = 표제어와 뜻
            if cur:
                out.append(cur)
            cur = {"day": day, "no": int(b), "word": c, "ipa": "",
                   "mean": d, "derived": "", "ex": []}
            continue
        if cur is None:
            continue
        if c and not cur["ipa"] and _IPA.match(c):
            cur["ipa"] = c
        elif c:
            cur["derived"] = (cur["derived"] + " " + c).strip()
        if d:
            # 예문은 영어 → 한글 차례로 온다. 한글이면 앞 예문의 짝이다.
            if cur["ex"] and cur["ex"][-1][1] == "" and _HAN.search(d):
                cur["ex"][-1] = (cur["ex"][-1][0], d)
            else:
                cur["ex"].append((d, ""))
    if cur:
        out.append(cur)
    return out


def pages(entries, per=15):
    """낱말 목록 → 면 목록. **DAY 가 바뀌면 면을 새로 연다.**

    완성본은 한 DAY(30낱말)가 펼침면 하나다. 이어 붙이면 DAY 가 면 가운데서
    갈려 학생이 어디까지가 오늘 몫인지 알 수 없다.
    """
    out, cur, day = [], [], None
    for e in entries:
        if day is not None and (e["day"] != day or len(cur) >= per):
            out.append({"day": day, "items": cur})
            cur = []
        day = e["day"]
        cur.append(e)
    if cur:
        out.append({"day": day, "items": cur})
    return out
