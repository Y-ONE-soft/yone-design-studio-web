# -*- coding: utf-8 -*-
"""중등 내신 정규 교재 — **자리를 옮기지 않고** 3계층에 잇는 다리.

## 왜 다리인가

이 교재만 조판 코드가 3계층 밖에 산다
(`조판/교재/중등부/내신 정규 교재/automation/`, 파이썬 4,600줄).
그래서 `bin/viv` 도 내지 작업대도 이 여덟 권을 못 봤다.

코드를 통째로 옮기는 것이 옳지만, 그건 렌더러 1,315줄을 계열 규격으로 다시
쓰는 일이고 **이미 납품한 여덟 권이 픽셀까지 같아야** 한다. 지금 필요한 것은
"작업대에서 이 책도 열린다" 이지 "코드가 예쁘다" 가 아니다. 그래서
**automation 을 그대로 부르는 얇은 다리**를 놓는다.

    config.json (책 폴더)  →  이 계열  →  automation/*.py (그대로)

옮기는 일은 나중에 해도 늦지 않고, 그때도 이 다리가 회귀 그물이 된다
(다리를 지난 결과와 automation 직접 실행 결과가 같아야 한다).

## ⚠ 한 권에 두 벌이 있다

중등부는 한 교재 폴더 안에 **1권(같이새김)·2권(홀로새김)** 이 같이 있다.
3계층은 폴더 하나 = 책 하나라, config 의 `middle.vol` 이 지금 보는 권을 정한다.
작업대에서 손잡이로 바꾼다.

## ⚠ 산출물 자리가 다르다

automation 은 `automation/work/<교재키>/build<권>/` 에 조판하고 PDF 는 교재
폴더에 낸다. 3계층은 `<책폴더>/build/` 를 본다. `render_only()` 는 automation 이
만든 `index.html` 경로를 **그대로** 돌려준다 — 복사하면 두 벌이 되어 어느 것이
참인지 모르게 된다.
"""
import json
import os
import subprocess
import sys

from core.render_vivlio import knobs
from core.render_vivlio.series.base import Series


def _auto_dir():
    from core.render_vivlio.config import _studio_root
    return os.path.join(_studio_root(), "조판", "교재", "중등부",
                        "내신 정규 교재", "automation")


def _repo():
    """이 리포의 뿌리 — automation 이 `core.render_vivlio` 를 찾을 수 있게."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(here))))


def _run(script, bookkey, vol, log, extra=()):
    a = _auto_dir()
    cmd = [sys.executable, "-u", os.path.join(a, script),
           "--book", bookkey, "--vol", str(vol)] + list(extra)
    # ⚠ automation 은 이 리포 밖에 있어서, 그냥 부르면 `core.render_vivlio` 를
    #   못 찾는다. 그 안의 자리표 심기는 import 실패를 **조용히 넘기도록**
    #   되어 있어(automation 단독 실행을 살리려고) 아무 티도 안 난다 —
    #   지면은 나오는데 클릭만 안 먹는다. 그래서 길을 넣어 준다.
    env = dict(os.environ)
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _repo() + (os.pathsep + pp if pp else "")
    p = subprocess.Popen(cmd, cwd=a, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, env=env)
    for line in p.stdout:
        log("  " + line.rstrip())
    if p.wait() != 0:
        raise RuntimeError(f"{script} 실패 (교재 {bookkey} {vol}권)")


class MiddleSeries(Series):

    name = "middle"
    display = "중등 내신 정규 교재"
    theme = ""                    # automation/theme.css 를 그대로 쓴다

    # ── 어느 교재·어느 권인가 ──
    @staticmethod
    def _pick(cfg):
        m = cfg.section("middle") or {}
        key = m.get("book")
        if not key:
            raise ValueError("config 에 `middle.book`(교재 키)이 없다")
        return key, int(m.get("vol") or 1)

    @staticmethod
    def _paths(bookkey, vol):
        a = _auto_dir()
        w = os.path.join(a, "work", bookkey)
        return {"data": os.path.join(w, f"data{vol}.json"),
                "raw": os.path.join(w, f"raw{vol}.json"),
                "build": os.path.join(w, f"build{vol}")}

    # 작업대에 나오는 사람 이름 — 무엇을 고르는지 알아야 손을 댄다.
    style_names = {
        "sechd": "구역 머리", "code": "구역 번호", "tail": "구역 꼬리",
        "ghd": "묶음 머리", "vlist": "낱말 목록", "vrow": "낱말 한 줄",
        "no": "번호", "bd": "낱말과 뜻", "w": "낱말", "k": "뜻",
        "nt": "덧말", "plist": "구 목록",
        "qs": "문항 묶음", "qi": "문항 한 개", "row": "문항 줄",
        "b": "문항 본문", "boxed": "상자 문항", "two": "2단 문항",
        "bank": "<보기> 상자", "instr": "안내문", "keep": "붙여 두는 덩어리",
        "qpass": "지문 묶음", "plate": "간지", "memo": "메모 면",
    }

    def build_dir(self, cfg):
        key, vol = self._pick(cfg)
        return self._paths(key, vol)["build"]

    # ── ① 원고 → data ──
    def gen_data(self, cfg, log):
        key, vol = self._pick(cfg)
        _run("extract.py", key, vol, log)
        _run("gen_data.py", key, vol, log)
        return self._paths(key, vol)["data"]

    # ── ③ 조판 ──
    def build(self, cfg, log, sample=False, **_):
        key, vol = self._pick(cfg)
        if sample:
            log("  [알림] 이 계열은 견본을 따로 만들지 않는다 — 전권을 조판한다")
        _run("build.py", key, vol, log)
        return {"pdf": None, "pages": None}

    # ── 미리보기: HTML 까지만 ──
    def render_only(self, cfg, log, **_):
        """automation 의 `render.py` 가 `build<권>/index.html` 을 쓴다.

        ⚠ `build()` 를 가로채는 공용 방식(`cli.skip_build`)을 못 쓴다 — 여기서는
          조판을 **다른 프로세스**가 부르기 때문이다. 그래서 렌더 단계만 직접
          부른다. 대신 서체·테마·자산 배치도 같이 해야 한다(build.py 의 stage()).
        """
        key, vol = self._pick(cfg)
        p = self._paths(key, vol)
        if not os.path.exists(p["data"]):
            raise FileNotFoundError(
                f"{p['data']} 가 없다 — 먼저 `gen_data` 를 돌릴 것")
        _run("build.py", key, vol, log, extra=["--htmlonly"])
        html = os.path.join(p["build"], "index.html")
        if not os.path.exists(html):
            raise RuntimeError(f"조판할 HTML 이 없다: {html}")
        return html

    # ── 손잡이 ──
    # 색은 `automation/palette.py` 가 **권(같이새김/홀로새김)** 을 따라 고른다
    # — 교재가 아니다. 그래서 색 손잡이는 열지 않는다(열면 교재별로 갈라져
    # 그 규칙이 깨진다). 여는 것은 "어느 권을 보는가" 하나다.
    def knobs(self, cfg):
        return [knobs.Knob("middle.vol", "enum", "보는 권",
                           values=(1, 2), default=1, group="섹션",
                           affects="1권 같이새김 · 2권 홀로새김",
                           resettable=True)]

    # ── ④ 검수 ──
    def verify(self, cfg, log, report):
        key, vol = self._pick(cfg)
        try:
            _run("verify.py", key, vol, log)
        except RuntimeError as e:
            report.fail("G-중등 " + str(e))
        return report
