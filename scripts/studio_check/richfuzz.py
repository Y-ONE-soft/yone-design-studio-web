"""작업대가 **고를 수 있는 자리**에 글자 서식을 걸어도 조판이 죽지 않는가.

## 왜 있는가

작업대에서 글자에 서식을 걸면 그 값이 **서식 조각 목록**이 된다. 계열 렌더러가
그 자리에서 `html.escape()` 만 쓰고 있으면 **조판이 통째로 죽는다** —
겉으로는 "저장했는데 갑자기 책이 안 나온다" 로 보인다(실제로 겪었다).

그래서 `build/refs.json` 에 적힌 **고를 수 있는 자리 전부**를 서식 조각으로
바꿔 놓고 한 번 조판해 본다. 사람이 할 수 있는 최악을 미리 해 보는 것이다.

    python3 scripts/studio_check/richfuzz.py            # 전 계열
    python3 scripts/studio_check/richfuzz.py blackbook  # 한 계열

⚠ 원고 파일을 잠깐 바꿔치기한다. 끝나면 **반드시 되돌린다**(finally).
"""
import copy
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import routes.book_studio as BS                     # noqa: E402
from core.render_vivlio import book as B            # noqa: E402
from core.render_vivlio import edits as ed          # noqa: E402


def _rich(s):
    return [{"t": s, "st": {"letter-spacing": "-0.01em"}}]


def _put(data, ref):
    """그 자리 값이 **글**이면 서식 조각으로 바꾼다. 바꿨으면 True."""
    holder, key = ed._walk(data, ref)
    if holder is None:
        return False
    try:
        cur = holder[key]
    except (KeyError, IndexError, TypeError):
        return False
    if isinstance(cur, str) and cur.strip():
        holder[key] = _rich(cur)
        return True
    if isinstance(cur, list) and cur and all(isinstance(x, str) for x in cur):
        holder[key] = [_rich(x) if x.strip() else x for x in cur]
        return True
    # ⚠ **덩어리(dict)는 건드리지 않는다.** 작업대도 못 고친다(409). 예전에
    #   그 안의 글자를 다 바꿨더니 `kind` 같은 **구조 열쇠**까지 서식 조각이
    #   되어, 없는 결함이 있는 것처럼 나왔다.
    return False


def main(only=None):
    bad = 0
    seen = set()
    for b in BS._books():
        s = b["series"]
        if s in seen or (only and s != only):
            continue
        seen.add(s)
        d = BS._book_dir(b["bid"])[0]
        cfg = B.load(d)
        dp = ed.data_path(cfg)
        rp = os.path.join(B.build_dir(cfg), "refs.json")
        if not os.path.exists(dp):
            print("%-11s 원고 자료가 없는 계열 — 건너뜀" % s)
            continue
        if not os.path.exists(rp):
            print("%-11s 자리표가 없는 계열 — 건너뜀" % s)
            continue
        refs = json.load(open(rp, encoding="utf-8"))
        raw = json.load(open(dp, encoding="utf-8"))
        data = copy.deepcopy(raw)
        n = 0
        for ref in refs.values():
            if ref.startswith("#") or ref.startswith("book."):
                continue                       # 원고가 아닌 자리
            n += _put(data, ref)
        if not n:
            print("%-11s 바꿀 글 자리가 없다 — 건너뜀" % s)
            continue
        bak = dp + ".fuzzbak"
        os.replace(dp, bak)
        try:
            with open(dp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            B.render(cfg, log=lambda *a: None)
            print("%-11s ✓ %d자리에 서식을 걸어도 조판된다" % (s, n))
        except Exception as e:
            bad += 1
            print("%-11s ✗ %s: %s" % (s, type(e).__name__, str(e)[:80]))
            for line in traceback.format_exc().strip().splitlines()[-12:]:
                print("            " + line.strip())
        finally:
            os.replace(bak, dp)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
