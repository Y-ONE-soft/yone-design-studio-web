#!/usr/bin/env python3
"""W22 파트 경계 채움(alignPartFillers) 실기 프로브 — 실제 InDesign 실측.

r12 코퍼스(성덕 외부지문)는 모든 섹션이 짝수 페이지라 정상 재조판에서
채움 분기가 발동하지 않는다 (파트가 항상 오른쪽 페이지로 끝남). 이 프로브는
round12 출력 .indd의 스크래치 사본에서 간지 앞 페이지 1장을 지워 홀수
정렬을 인위로 만든 뒤, workbook_flow.body.jsx의 [W22 파트경계 유틸] 구간을
'소스 그대로 추출'해 실행한다 — 복사본 코드가 아니라 실코드의 실측.

검증: ① 사전(정렬 정상) 실행 = 삽입 0 ② 페이지 삭제로 간지 라벨이
왼쪽으로 밀린 상태에서 실행 = 밀린 간지마다 M 마스터 페이지 1장 삽입 +
라벨 전부 오른쪽 복귀.

사용: python3 scripts/e2e_round12_filler_probe.py [round12_out_indd]
  기본 대상: data_corpus/round12/out/워크북1_내지_v2_2.indd
출력: data_corpus/round12/probe/ (스크래치 사본 — 사용자 문서/원본 무접촉,
  문서는 저장하지 않고 측정만 한다)
"""
import json
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

BODY = os.path.join(REPO, "core", "jsx", "workbook_flow.body.jsx")
MARK_A = "// [W22 파트경계 유틸 시작]"
MARK_B = "// [W22 파트경계 유틸 끝]"

DRIVER = """
var INDD = "__INDD__";
var OUT = "__OUT__";
var LOG = "__LOG__";
var DELETE_PAGE_OFFSET = __DELETE_OFFSET__;   // -1 = 삭제 없음 (사전 검증)
var settingsPath = "__LOG__";  // runner 호환 (리터럴 문자열 필수 — 러너가 정규식으로 추출)

function wlog(msg) {
    var f = new File(LOG);
    f.encoding = "UTF-8";
    f.open("a");
    f.writeln(msg);
    f.close();
}

__EXTRACTED__

function pagesSnapshot(doc) {
    var rows = [];
    for (var i = 0; i < doc.pages.length; i++) {
        var pg = doc.pages[i];
        var m = "";
        try { m = pg.appliedMaster ? String(pg.appliedMaster.name) : ""; } catch (e) {}
        rows.push('{"p":"' + String(pg.name) + '","m":"' + m +
                  '","side":"' + pageSideOf(doc, pg) +
                  '","frames":' + pg.textFrames.length +
                  ',"label":' + (isDividerLabelPage(pg) ? "true" : "false") + "}");
    }
    return "[" + rows.join(",") + "]";
}

var doc = null;
try {
    wlog("프로브 시작: " + INDD);
    doc = app.open(File(INDD), false);
    if (DELETE_PAGE_OFFSET >= 0) {
        wlog("페이지 삭제(정렬 교란): offset " + DELETE_PAGE_OFFSET);
        doc.pages[DELETE_PAGE_OFFSET].remove();
    }
    var before = pagesSnapshot(doc);
    alignPartFillers(doc);
    var after = pagesSnapshot(doc);
    var out = new File(OUT);
    out.encoding = "UTF-8";
    out.open("w");
    out.write('{"before":' + before + ',"after":' + after + "}");
    out.close();
    doc.close(SaveOptions.NO);   // 측정만 — 저장하지 않음
    doc = null;
    wlog("프로브 완료");
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
}
"""


def extract_span():
    src = open(BODY, encoding="utf-8").read()
    assert MARK_A in src and MARK_B in src, "W22 마커 없음 — 프로브 불가"
    span = src.split(MARK_A)[1].split(MARK_B)[0]
    # 시작 마커 라인의 잔여 주석 텍스트(// 가 split에 소비됨)를 버린다 —
    # 남기면 주석 아닌 한글 라인이 되어 SyntaxError.
    span = span.split("\n", 1)[1] if "\n" in span else span
    # 끝 마커 직전의 미완 라인("// " 잔여)도 마지막 개행까지로 절단
    return span.rsplit("\n", 1)[0]


def run_case(indd_src, probe_dir, name, delete_offset):
    from core.indesign.runner import run_jsx
    work = os.path.join(probe_dir, name)
    os.makedirs(work, exist_ok=True)
    indd = os.path.join(work, "probe.indd")
    shutil.copy2(indd_src, indd)
    out_json = os.path.join(work, "result.json")
    log_path = os.path.join(work, "probe.log")
    for p in (out_json, log_path):
        try:
            os.remove(p)
        except OSError:
            pass
    jsx = (DRIVER
           .replace("__EXTRACTED__", extract_span())
           .replace("__INDD__", indd.replace("\\", "\\\\").replace('"', '\\"'))
           .replace("__OUT__", out_json)
           .replace("__LOG__", log_path)
           .replace("__DELETE_OFFSET__", str(delete_offset)))
    jsx_path = os.path.join(work, "probe.jsx")
    open(jsx_path, "w", encoding="utf-8").write(jsx)
    run_jsx(jsx_path, lambda m: print(f"  {m}", flush=True),
            poll_log_path=log_path, timeout=600,
            completion_marker="프로브 완료")
    return json.load(open(out_json, encoding="utf-8"))


def label_sides(rows):
    return [(r["p"], r["side"], r["m"]) for r in rows if r["label"]]


def main():
    indd_src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        REPO, "data_corpus", "round12", "out", "워크북1_내지_v2_2.indd")
    assert os.path.exists(indd_src), f"대상 indd 없음: {indd_src}"
    probe_dir = os.path.join(REPO, "data_corpus", "round12", "probe")

    print("== 케이스 1: 정렬 정상 문서 — 삽입 0 기대")
    r1 = run_case(indd_src, probe_dir, "aligned", -1)
    assert len(r1["after"]) == len(r1["before"]), "정렬 정상인데 페이지 수 변화"
    for p, side, _m in label_sides(r1["after"]):
        assert side == "R", f"간지 p{p}가 왼쪽"
    print(f"   페이지 {len(r1['before'])} → {len(r1['after'])} (삽입 0), "
          f"간지 { [p for p, _s, _m in label_sides(r1['after'])] } 전부 R ✓")

    # 케이스 2: 마지막 간지 '앞' 콘텐츠 페이지 1장을 지워 홀수 정렬 유발.
    # 삭제 지점 = 첫 라벨 페이지 이후 & 마지막 라벨 이전의 콘텐츠 페이지
    labels_b = [i for i, r in enumerate(r1["before"]) if r["label"]]
    assert labels_b, "간지 라벨 페이지 없음"
    del_off = labels_b[-1] - 3   # 간지 스프레드(동반+라벨) 앞 콘텐츠 페이지
    assert not r1["before"][del_off]["label"]
    print(f"== 케이스 2: offset {del_off} 페이지 삭제 → 간지 좌측 밀림 → M 채움 기대")
    r2 = run_case(indd_src, probe_dir, "shifted", del_off)
    before_labels = label_sides(r2["before"])
    after_labels = label_sides(r2["after"])
    shifted = [p for p, side, _m in before_labels if side == "L"]
    assert shifted, f"교란 후에도 좌측 간지 없음: {before_labels}"
    for p, side, _m in after_labels:
        assert side == "R", f"실행 후에도 간지 p{p}가 왼쪽: {after_labels}"
    inserted = len(r2["after"]) - len(r2["before"])
    assert inserted == len(shifted), (inserted, shifted)
    m_pages = [(r["p"], r["side"]) for r in r2["after"]
               if r["m"].startswith("M")]
    assert m_pages and all(s == "R" for _p, s in m_pages), m_pages
    # M 페이지 다음은 간지 스프레드(마스터 없음)
    idx = {r["p"]: i for i, r in enumerate(r2["after"])}
    for p, _s in m_pages:
        nxt = r2["after"][idx[p] + 1]
        assert nxt["m"] == "", (p, nxt)
    print(f"   교란 간지 {shifted} (L) → 삽입 {inserted}개 M(R, 간지 직전) "
          f"→ 간지 전부 R 복귀 ✓ M 페이지: {m_pages}")
    print("\n결과: ✅ alignPartFillers 실기 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
