"""스튜디오 루트 — 잡 폴더(_jobs) · 디자인 기준 PDF 의 ${STUDIO} 를 푸는 곳.

YONE_STUDIO_ROOT(배포서버는 /data)가 있으면 그것, 없으면 표식(조판/교재 · 디자인 · 검수 …)을 가장 많이 갖춘 후보.
(2026-10-19 예전 조판 엔진 core/render_vivlio/config.py 에서 그대로 옮김)
"""
import os

# 스튜디오 루트에 있어야 하는 것들. **몇 개나 맞는지로 고른다.**
_MARKS = ("조판/교재", "디자인", "검수", "자료", "원고 합치기", "통합웹사이트")


def _score(root):
    return sum(os.path.isdir(os.path.join(root, *m.split("/"))) for m in _MARKS)


def _is_studio(root):
    """표식을 몇 개나 갖췄는지로 본다 — 둘만 보면 부분 사본(~/dev/조판 + 후처리가 떨군 ~/dev/디자인)이 진짜를 가렸다"""
    return os.path.isdir(os.path.join(root, "조판", "교재")) and _score(root) >= 3


def studio_root():
    env = os.environ.get("YONE_STUDIO_ROOT")
    if env:
        return env
    cands = [os.path.expanduser("~/Documents/작업/Y.ONE STUDIO"), os.path.expanduser("~/dev")]
    best, best_score = None, 0
    for c in cands:
        if _is_studio(c) and _score(c) > best_score:
            best, best_score = c, _score(c)
    if best:
        return best
    for c in cands:                     # 완전 일치가 없으면 조판/교재 라도
        if os.path.isdir(os.path.join(c, "조판", "교재")):
            return c
    return os.path.expanduser("~")
