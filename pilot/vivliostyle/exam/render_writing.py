"""서답형 워크시트 IR -> HTML (문제지와 동일 판형/머리표/로고).

세트 = 지문 박스 + 하위문항(발문/보기/요약문/어법지문 + 답란).
하위문항은 단 경계에서 쪼개지지 않게(break-inside:avoid) 묶는다.
"""
import html
import re

from render_exam import esc
from parse_writing import blankify

RE_UND = re.compile(r"_{2,}")


def _runs_html(runs):
    out = []
    for r in runs:
        if r.get("blank"):
            n = r.get("blen", 12)
            cls = "wl" if n >= 20 else "wb"      # 긴 답란 vs 짧은 빈칸
            out.append(f'<span class="{cls}"></span>')
            continue
        t = esc(r.get("t", ""))
        if not t:
            continue
        if r.get("ul"):
            t = f"<u>{t}</u>"
        out.append(t)
    return "".join(out)


def _para_html(clean, cls=""):
    runs = blankify(clean)
    c = f' class="{cls}"' if cls else ""
    return f"<p{c}>{_runs_html(runs)}</p>"


def _answer_line_html(clean):
    """답란 — 언더스코어를 필기용 밑줄로. (A)/→/번호: 라벨은 살린다."""
    runs = blankify(clean)
    return f'<p class="ansline">{_runs_html(runs)}</p>'


def _sub_html(sub):
    parts = [f'<p class="qstem"><span class="qlabel">{esc(sub["label"])}</span>'
             f'{esc(sub["question"])}</p>']
    if sub.get("passage"):                       # 어법 밑줄 지문
        parts.append(f'<div class="passage sub-pass">'
                     f'{_para_html(sub["passage"])}</div>')
    if sub.get("summary"):                        # 요약문
        parts.append(f'<div class="summary">{_para_html(sub["summary"])}</div>')
    for b in sub.get("boxes", []):                # <보기>
        txt = re.sub(r"^\s*<\s*보기\s*>\s*", "", b["text"]).strip()
        parts.append(f'<div class="bogi"><span class="bogi-lab">보기</span>'
                     f'<span class="bogi-txt">{esc(txt)}</span></div>')
    for a in sub.get("answer_lines", []):
        parts.append(_answer_line_html(a))
    return f'<div class="subq">{"".join(parts)}</div>'


def _set_html(s):
    passage = (f'<div class="passage">{_para_html(s["passage"])}</div>'
               if s.get("passage") else "")
    subs = "".join(_sub_html(sub) for sub in s["subs"])
    return (
        f'<section class="wset" id="w{s["n"]}">'
        f'<p class="setnum"><span class="snum">{s["n"]}</span></p>'
        f'{passage}{subs}'
        f'</section>'
    )


def build_html(doc, cfg, css="writing_theme.css"):
    sets = doc["sets"]
    head = ('<meta charset="utf-8">'
            f'<title>{esc(cfg["title"])}</title>'
            f'<link rel="stylesheet" href="{css}">')
    logo = cfg.get("logo", "")
    info = cfg.get("exam_date_short", "")
    masthead = (
        '<header class="masthead">'
        + (f'<img class="logo" src="{esc(logo)}" alt="">' if logo else "")
        + f'<p class="line1">{esc(cfg["subtitle"])}</p>'
        + f'<h1><span class="period">서답형</span>'
        + f'<span class="maintitle">{esc(cfg["title"])}</span></h1>'
        + (f'<p class="info">{esc(info)}</p>' if info else "")
        + '</header>')
    running = (
        '<div class="runhead" role="presentation">'
        f'<span class="rh-title">{esc(cfg["title"])}</span></div>'
        + (f'<div class="logohead" role="presentation">'
           f'<img src="{esc(logo)}" alt=""></div>' if logo else ""))
    body = "".join(_set_html(s) for s in sets)
    return (
        f"<!doctype html><html lang=ko><head>{head}</head><body>"
        f"{running}{masthead}"
        f'<main class="flow">{body}</main>'
        "</body></html>")
