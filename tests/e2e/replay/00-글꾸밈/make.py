"""기능 확인 — 글자 골라 꾸미기(문자 스타일 · 윗주 · 옆 메모)를 사람처럼 한 번. 원본과 맞대는 단위가 아니다(끝의 js 가 결과를 본다).

브랜드에 문자 스타일 둘 → 글상자 그리기 → 윗주·옆 메모 기본값 → 글을 두 번 눌러 고치기 창에서 단어를 끌어 고르고 「아래 윗주」 ·
구절을 골라 문자 스타일 「형광 민트」 · 커서 자리에 「옆 메모」 → 칸 밖을 눌러 확정 → 저장된 조각 목록을 확인.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
WORK = os.environ.get("REPLAY_WORK") or HERE

CS = '#sbody [data-cs="{}:{}"]'
st = open_doc("글꾸밈 시험") + expect_pages(1)
st += [S("브랜드 — 문자 스타일 둘", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
       {"click": "#side #s-skin-edit", "wait": 1500},
       {"answer": "형광 민트"}, {"click": "#cs-new", "wait": 1200}, F(CS.format("형광 민트", "bg"), "#d7efe6", 900), F(CS.format("형광 민트", "bg_pad"), 0.4, 900),
       {"answer": "분석 표기"}, {"click": "#cs-new", "wait": 1200}, F(CS.format("분석 표기", "size"), 5.5, 900), F(CS.format("분석 표기", "color"), "#3b5998", 900),
       {"click": "#sheet-x", "wait": 1200}]
st += text(20, 40, 120, 30, "Cuju holds a significant place in sporting history.", 10.5, "#231f20", label="글상자", leading=26)
st += [S("윗주 · 옆 메모 기본값 — 글상자 패널", 1200),
       {"pick": {"at": '#side select[data-a="ruby.cs"]', "value": "분석 표기"}, "wait": 900}, F('#side input[data-a="ruby.off_below"]', 1.5, 800),
       F('#side input[data-a="side.x"]', 130, 800), F('#side input[data-a="side.w"]', 45, 800), F('#side input[data-a="side.off"]', -3, 800),
       {"pick": {"at": '#side select[data-a="side.cs"]', "value": "분석 표기"}, "wait": 900}]
st += [S("고치기 창 — 단어 골라 아래 윗주", 1300), {"dbl": {"mm": [40, 44]}, "wait": 1200},
       {"select": {"text": "Cuju"}, "wait": 600}, {"answer": "단 S"}, {"click": "#rt-rbb", "wait": 900},
       S("구절 골라 문자 스타일 「형광 민트」", 1200), {"select": {"text": "holds a significant place"}, "wait": 600},
       {"pick": {"at": "#rt-cs", "value": "형광 민트"}, "wait": 900},
       S("커서 자리에 옆 메모", 1200), {"select": {"text": "history"}, "wait": 600}, {"answer": "* 메모 — 옆 칸에 놓인다"}, {"click": "#rt-side", "wait": 900},
       {"click": {"mm": [205, 294]}, "wait": 1500},
       {"js": "(() => { const it = page.items.find(i => (i.atom||{}).t === 'text'); return JSON.stringify(it.atom.text); })()", "wait": 300},
       {"js": "(() => { const t = page.items.find(i => (i.atom||{}).t === 'text').atom.text; const ok = Array.isArray(t) && t.some(r => r.ruby && r.ruby.t === '단 S' && r.t === 'Cuju') "
              "&& t.some(r => r.cs === '형광 민트' && r.t === 'holds a significant place') && t.some(r => r.side); if (!ok) throw new Error('꾸밈 저장 안 됨'); return '꾸밈 저장 확인'; })()"},
       {"shot": "glkkumim.png", "wait": 1500}]
json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump({"1": []}, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"))
json.dump({"ref": "catalog/workbook/designs/d1/reference.pdf", "pages": [2]}, open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
