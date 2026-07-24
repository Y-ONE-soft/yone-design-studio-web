"""해설지 IR -> HTML (문제지와 동일 판형·머리표·로고).

문제지와 달리 '한 문항 한 단' 제약이 없다 — 정답·해설은 연속 흐름이 정상이라
2단으로 자연스럽게 흘린다. 각 문항은 번호+정답 헤드 뒤에 라벨별 섹션을 붙인다.
"""
import html
import re

from render_exam import esc
from parse_solution import split_choices

# 문제지 상단 정답표(빠른 확인용) — 해설지 첫머리에 배치
SECTION_ORDER = ["출제의도", "해석", "어구", "어휘 및 어구", "해설", "선지 해석"]
LABEL_SHORT = {"어휘 및 어구": "어구"}


def _answer_grid(items):
    cells = "".join(
        f'<li><span class="mk">{it["n"]}</span>'
        f'<span class="av">{esc(it["answer"])}</span></li>' for it in items)
    return ('<section class="ans-quick"><h2>빠른 정답</h2>'
            f'<ol class="anslist">{cells}</ol></section>')


def _section_html(sec):
    label = LABEL_SHORT.get(sec["label"], sec["label"])
    if sec["label"] == "선지 해석":
        chs = split_choices(sec["text"])
        if chs:
            lis = "".join(
                f'<li><span class="mk">{esc(l)}</span>'
                f'<span class="ct">{esc(t)}</span></li>' for l, t in chs)
            return (f'<div class="sec"><p class="seclab">{esc(label)}</p>'
                    f'<ol class="sol-choices">{lis}</ol></div>')
    body = "<br>".join(esc(x) for x in sec["text"].split("\n"))
    return (f'<div class="sec"><span class="seclab">{esc(label)}</span>'
            f'<span class="sectext">{body}</span></div>')


def _item_html(it):
    secs = "".join(_section_html(s) for s in it["sections"])
    return (
        f'<section class="sol" id="s{it["n"]}">'
        f'<p class="solhead"><span class="snum">{it["n"]}</span>'
        f'<span class="sans">{esc(it["answer"])}</span></p>'
        f'{secs}'
        f'</section>'
    )


def build_html(doc, cfg, css="solution_theme.css"):
    items = doc["items"]
    logo = cfg.get("logo", "")
    head = ('<meta charset="utf-8">'
            f'<title>{esc(cfg["title"])} 해설</title>'
            f'<link rel="stylesheet" href="{css}">')
    info = f"선택형 {len(items)}문항 · {cfg.get('exam_date_short','')}"
    masthead = (
        '<header class="masthead">'
        + (f'<img class="logo" src="{esc(logo)}" alt="">' if logo else "")
        + f'<p class="line1">{esc(cfg["subtitle"])}</p>'
        + f'<h1><span class="period">정답 및 해설</span>'
        + f'<span class="maintitle">{esc(cfg["title"])}</span></h1>'
        + f'<p class="info">{esc(info)}</p>'
        + '</header>')
    running = (
        '<div class="runhead" role="presentation">'
        f'<span class="rh-title">{esc(cfg["title"])} 해설</span></div>'
        + (f'<div class="logohead" role="presentation">'
           f'<img src="{esc(logo)}" alt=""></div>' if logo else ""))
    body = "".join(_item_html(it) for it in items)
    return (
        f"<!doctype html><html lang=ko><head>{head}</head><body>"
        f"{running}{masthead}"
        f'{_answer_grid(items)}'
        f'<main class="flow">{body}</main>'
        "</body></html>")
