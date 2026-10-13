"""편집기 템플릿에 원본 PDF 붙이기 + 템플릿 보기 확인 — 절차 8단계(템플릿 등록) 뒤, 10단계(반영)에서 배포서버에도.

    python3 tests/e2e/attach_origin.py <틀>/<템플릿> <원본.pdf | 같은 틀의 PDF 등록 카드 id> [--base URL]
    python3 tests/e2e/attach_origin.py --check [--base URL]

붙이면 템플릿 폴더 참고/원본.pdf 가 생기고, 관리 템플릿 보기(/design/<틀>/<템플릿>)에
「상위 페이지」(편집기 문서) · 「원본 페이지 차례」(원본 PDF 판정 — PDF 등록 카드와 같은 판정) 두 칸이 나온다.
--check = 그 서버의 편집기 템플릿 전부를 실제 화면 글로 본다 — 두 칸 제목 · 원본 쪽 그림이 없으면 실패(종료 코드 1).
기본 base = http://127.0.0.1:5099. 배포서버는 --base https://yos-studio.fly.dev (배포는 기존 템플릿에 새 파일을 안 옮긴다 — 이 도구로 올린다).
"""
import json, os, re, subprocess, sys

args = sys.argv[1:]
base = "http://127.0.0.1:5099"
if "--base" in args:
    k = args.index("--base")
    base = args[k + 1].rstrip("/")
    del args[k:k + 2]


def curl(*a):
    r = subprocess.run(["curl", "-s", "--max-time", "600", *a], capture_output=True, text=True)
    return r.stdout


def check_one(series, did):
    """템플릿 보기 화면 → (통과, 설명)"""
    html = curl(f"{base}/design/{series}/{did}")
    top = re.search(r"<h2>상위 페이지 <span class=\"n\">(\d+)개", html)
    org = re.search(r"<h2>원본 페이지 차례 <span class=\"n\">(\d+)개[^<]*\(원본 (\d+)페이지\)", html)
    imgs = len(re.findall(r"\.png\?dpi=30&(?:amp;)?src=origin", html))
    if not top:
        return False, "「상위 페이지」 칸 없음"
    if not org or not imgs:
        return False, f"상위 페이지 {top.group(1)}개 · 「원본 페이지 차례」 없음"
    return True, f"상위 페이지 {top.group(1)}개 · 원본 페이지 차례 {org.group(1)}개 (원본 {org.group(2)}페이지)"


def check_all():
    cat = json.loads(curl(f"{base}/api/v1/catalog"))
    bad = 0
    for dr in cat["dirs"]:
        for t in dr["templates"]:
            for d in t.get("designs") or []:
                if not (d.get("source") or "").startswith("편집기:"):
                    continue
                ok, why = check_one(t["series"], d["id"])
                bad += not ok
                print(f"{'○' if ok else '✗'} {t['series']}/{d['id']} 「{d['name']}」 — {why}")
    print(f"{base} — 편집기 템플릿 확인" + (f" 실패 {bad}" if bad else " 모두 통과"))
    return 1 if bad else 0


def attach(key, src):
    series, _, did = key.partition("/")
    if os.path.isfile(src):
        out = curl("-F", f"file=@{src};type=application/pdf", f"{base}/api/catalog/design/{series}/{did}/origin")
    else:
        out = curl("-F", f"from={src}", f"{base}/api/catalog/design/{series}/{did}/origin")
    try:
        j = json.loads(out)
    except ValueError:
        sys.exit(f"붙이기 실패 — {out[:300]}")
    if j.get("error"):
        sys.exit(f"붙이기 실패 — {j['error']}")
    print(f"붙임 {key} ← {src} · 원본 {j['pages']}페이지 · 원본 페이지 차례 {j['layouts']}개")
    ok, why = check_one(series, did)
    print(f"{'○' if ok else '✗'} 템플릿 보기 — {why}")
    return 0 if ok else 1


if __name__ == "__main__":
    if args[:1] == ["--check"]:
        sys.exit(check_all())
    if len(args) != 2 or "/" not in args[0]:
        sys.exit(__doc__)
    sys.exit(attach(args[0], args[1]))
