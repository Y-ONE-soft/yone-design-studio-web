"""기능 확인 — 다른 개체(반투명 도형) 위 새 글상자 고치기 · 여러 줄 글(Enter) · 작은 글(7.6pt)에서 낱말 끌어 고르기 → 문자 스타일.
(2026-10-11 광문 분석본에서 찾은 편집기 문제 셋 — 도형 위에서 확정 안 됨 · 줄바꿈이 끝으로 감 · 골라진 글 위에서 끌면 「글 옮기기」)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
WORK = os.environ.get("REPLAY_WORK") or HERE
st = open_doc("겹친 글상자 시험") + expect_pages(1)
st += [{"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-skin-edit", "wait": 1500},
       {"answer": "연한"}, {"click": "#cs-new", "wait": 1200}, F('#sbody [data-cs="연한:color"]', "#a7bcbc", 900), {"click": "#sheet-x", "wait": 1200}]
st += shape(118.2, 233.5, 94.8, 66.5, "#dfe1e3", d="M0 1 L1 1 L1 0 Z", label="아래 도형") + opacity(60)
st += text(30, 30, 60, 10, "첫 글상자", 12, "#231f20", label="도형 위 글상자")
st += text(30, 60, 60, 20, "교재 이름\n00강 강 제목", 12, "#231f20", label="두 줄 글")
st += text(147.0, 23.0, 34.4, 3.4, "GRAMMAR POINT", 7.58, "#759b9b", label="작은 글", font="Gmarket Sans", weight=700)
st += [{"dbl": {"mm": [160.0, 24.7]}, "wait": 1200}, {"select": {"text": "POINT"}, "wait": 600}, {"pick": {"at": "#rt-cs", "value": "연한"}, "wait": 900},
       {"click": AWAY, "wait": 1200}]
st += [{"js": "(() => { const t = page.items.filter(i => (i.atom||{}).t === 'text').map(i => i.atom.text); "
              "if (t[1] !== '교재 이름\\n00강 강 제목') throw new Error('두 줄 글 ' + JSON.stringify(t[1])); "
              "if (!Array.isArray(t[2]) || !t[2].some(r => r.cs === '연한' && r.t === 'POINT')) throw new Error('작은 글 고르기 ' + JSON.stringify(t[2])); "
              "return '확인 — ' + JSON.stringify(t); })()"}]
json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump({"1": []}, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"))
json.dump({"ref": "catalog/workbook/designs/d1/reference.pdf", "pages": [2]}, open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"))
