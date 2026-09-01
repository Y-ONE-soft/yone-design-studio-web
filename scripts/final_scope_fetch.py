#!/usr/bin/env python3
"""Y.OS 시험범위 → `scope.json` (사람 손 없이).

Y.OS `/work/exam` 은 아직 읽기 API 가 없다. 그래서 **화면에서 그대로 떠 온다**.
브라우저에 로그인된 상태에서 아래 한 줄을 콘솔에 넣으면 표가 통째로 나온다:

    [...document.querySelectorAll("tbody tr")].flatMap(tr => {
      const who = tr.children[0].innerText.replace(/\\n+/g, "·").trim();
      return [...tr.children[2].querySelectorAll(":scope > div > div")]
        .map(d => [who, ...[...d.children].map(x => x.innerText.trim())]);
    })

그 결과를 파일로 주면 여기서 **지문수 대조**까지 하고 `scope.json` 을 쓴다.

    python3 scripts/final_scope_fetch.py rows.json --school 명일여고 --grade 고1

⚠ 이건 임시 길이다. Y.OS 화면 모양이 바뀌면 떠 오는 게 달라진다 —
  그래서 **지문수 대조를 통과하지 못하면 파일을 쓰지 않는다.** 조용히 틀린
  범위로 조판하는 것보다 멈추는 편이 낫다.
  정식 길은 `docs/yos_시험범위_읽기API_요청서.md`.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.final import scope_source as S     # noqa: E402


def pick(rows, school, grade):
    """`[[누구, 구분, 교재, 범위, 지문수], …]` 에서 그 반의 줄만."""
    out = []
    for r in rows or []:
        who = (r[0] or "")
        if school and school not in who:
            continue
        if grade and grade not in who:
            continue
        out.append(tuple(r[1:]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows", help="브라우저에서 떠 온 JSON")
    ap.add_argument("--school", required=True)
    ap.add_argument("--grade", required=True, help="고1 · 고2 · 고3")
    ap.add_argument("-o", "--out", default="scope.json")
    ap.add_argument("--check", action="store_true",
                    help="원고 폴더까지 열어 범위 안 지문이 실제로 몇 개인지 센다")
    a = ap.parse_args()

    rows = json.load(open(a.rows, encoding="utf-8"))
    entries = pick(rows, a.school, a.grade)
    if not entries:
        sys.exit("[범위] %s %s 줄을 찾지 못했습니다." % (a.school, a.grade))

    g = int("".join(c for c in a.grade if c.isdigit()) or 0)
    scope = S.from_yos_entries(entries, grade=g)
    scope["school"], scope["grade_text"] = a.school, a.grade

    bad = S.count_gate(entries, scope)
    for e in entries:
        print("  · %-8s %-34s %s" % (e[0], (e[1] or "")[:32],
                                     (e[2] or "")[:44]))
    print("■ 범위: " + ", ".join(S.token_text(t) for t in scope["tokens"]))
    free = sum(1 for e in entries if (e[0] or "").strip() == "직접 입력")
    if free:
        print("  ⚠ 직접 입력 %d줄 — 지문수가 없어 대조할 수 없습니다." % free)
    if bad:
        for b in bad:
            print("  ★ 지문수 어긋남: %s — Y.OS %d, 읽어 낸 것 %d"
                  % (b["book"], b["want"], b["got"]))
        sys.exit("[범위] 대조를 통과하지 못해 쓰지 않았습니다.")

    json.dump(S.to_json(scope), open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("■ 지문수 대조 통과 · %s" % a.out)

    if a.check:
        check(scope, g)


def check(scope, grade):
    """범위와 원고를 맞대 본다 — **어느 번호가 없는지**까지 짚는다.

    숫자만 세면 "13 vs 30" 이라 뭘 해야 할지 알 수 없다. 범위가 짚었는데
    원고에 없는 번호를 그대로 늘어놓으면 그게 곧 할 일 목록이 된다.

    다른 게 곧 결함은 아니다 — 모의고사 15~18 은 듣기라 지문 원고가 없다.
    """
    from engines.final import manuscript as M, manuscript_locate as L
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engines", "final", "config.json"),
        encoding="utf-8"))
    base = os.path.expanduser(cfg["gdrive_content_base"])
    total = want_all = 0
    for d, spec in S.folders(scope, base, grade=grade, log=print):
        blocks, _ = M.read(d, "arrange")
        labs = [x for x in (L.to_final_label(spec, b["raw"]) for b in blocks)
                if x]
        keep = [x for x in labs if S.in_scope(x, scope)]
        total += len(keep)
        # 이 폴더가 맡은 토큰이 짚은 번호 중, 원고 라벨로 안 나타난 것
        missing = []
        for t in scope["tokens"]:
            only = (scope.get("detail", {}).get(t) or {}).get("only") or []
            if not only:
                continue
            got = set()
            for lab in labs:
                tok, _tail = S.label_token(lab)
                if tok is None or S._key(tok) != S._key(t):
                    continue
                m = S.RE_LAB_NO.search(
                    lab[4:] if t[0] == "mock" else S.label_token(lab)[1])
                if m:
                    got.add(int(m.group(1)))
            if got or any(S._key(S.label_token(x)[0] or ("?",)) == S._key(t)
                          for x in labs):
                want_all += len(only)
                missing += [(t, n) for n in only if n not in got]
        print("  · %-28s 원고 %2d → 범위 안 %2d%s"
              % (os.path.basename(d)[:28], len(labs), len(keep),
                 ("   원고에 없음: " + ", ".join(str(n) for _t, n in missing))
                 if missing else ""))
    print("■ 범위 안 %d지문 (범위가 짚은 번호 %d개)%s"
          % (total, want_all,
             "" if total == want_all else "  ← 위의 '원고에 없음' 확인"))


if __name__ == "__main__":
    main()
