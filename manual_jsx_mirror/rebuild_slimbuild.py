#!/usr/bin/env python3
"""통합웹 엔진 JSX -> 수동 실행판 SlimBuild.jsx 생성.

로직은 engines/slim_merge/jsx/run.jsx 한 곳에만 둔다. 이 스크립트는
settings 로드부만 '수동 모드(열린 문서를 골라 진행)'로 바꿔 끼운다.

주의: 여기서 만드는 JS 코드에는 개행 이스케이프를 쓰지 않는다.
이 파일이 한 번 더 패치되면 백슬래시가 한 겹 벗겨져 JS 문자열 안에
진짜 줄바꿈이 들어가고, InDesign이 Unterminated string constant 로
죽는다 (2026-08-25 실사고). 개행은 NL 변수(String.fromCharCode)로 만든다.
"""
import os
import re
import sys

SRC = "/Users/nhj/dev/yone-design-web/engines/slim_merge/jsx/run.jsx"
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SlimBuild.jsx")

NEW_HEAD = '''// SlimBuild.jsx — 워크북 슬림버전 원샷 변환 (수동 실행판)
//
// ★ 이 파일은 통합웹 엔진 JSX(engines/slim_merge/jsx/run.jsx)에서 생성된다.
//   로직을 고칠 때는 엔진 쪽을 고치고 이 파일을 다시 생성할 것 —
//   따로 손대면 두 벌이 갈라져 한쪽만 고쳐지는 사고가 난다.
//   재생성: 조판/인디자인 스크립트/rebuild_slimbuild.sh
//
// 실행 방식
//   (A) 수동: InDesign에서 대상 문서를 열고 Scripts 패널에서 더블클릭
//             → 문서를 고르고 확인 → 진행
//   (B) 자동: __SETTINGS_PATH__ 를 JSON 경로로 치환한 사본을 실행
//
// 하는 일: 섹션 삭제/반쪽 병합/적층 병합 → 간지 스프레드 정렬(메모 삽입)
//          → 마스터 좌우 보정(A↔B, C↔D) → 단원 마커 교체 → 검증
'''

# JS 안에서 개행은 NL 변수로만 만든다 (백슬래시 이스케이프 금지)
NEW_LOAD = '''    var NL = String.fromCharCode(10);

    // settings 파일이 없으면 수동 모드 — 열려 있는 문서를 골라 진행한다.
    // (자동화 모드는 settings 로드 실패 시 job 로그에 흔적을 남긴다 —
    //  무로그 침묵 실패 방지, 2026-07-17 merge 계열 감사 패턴)
    var settings = null;
    var MANUAL = (SETTINGS_PATH.indexOf("__SETTINGS") === 0);
    if (!MANUAL) {
        try {
            settings = readJSON(SETTINGS_PATH);
        } catch (eBoot) {
            try {
                var _ef = new File(new File(SETTINGS_PATH).parent.fsName + "/slim_log.txt");
                _ef.encoding = "UTF-8";
                if (_ef.open("a")) {
                    _ef.write(ts() + "[치명적 오류] settings 로드 실패: " +
                              (eBoot.message || eBoot) + NL);
                    _ef.close();
                }
            } catch (eEf) {}
            throw eBoot;
        }
    } else {
        if (app.documents.length === 0) {
            alert("변환할 워크북 문서를 먼저 열어주세요.");
            return;
        }
        // 문서가 여러 개면 반드시 고르게 한다 — documents[0]/activeDocument 를
        // 그냥 쓰면 사용자가 참고로 열어둔 남의 파일이 변환된다.
        var target = null;
        if (app.documents.length === 1) {
            target = app.documents[0];
        } else {
            var dnames = [];
            for (var di = 0; di < app.documents.length; di++) {
                dnames.push(app.documents[di].name);
            }
            var dlg = app.dialogs.add({ name: "슬림 변환할 문서 선택" });
            var ddCol = dlg.dialogColumns.add();
            ddCol.staticTexts.add({
                staticLabel: "열린 문서 " + app.documents.length +
                             "개 — 변환할 문서를 고르세요" });
            var ddList = ddCol.dropdowns.add({ stringList: dnames,
                                               selectedIndex: 0 });
            var picked = dlg.show();
            var pickIdx = ddList.selectedIndex;
            dlg.destroy();
            if (!picked) { return; }
            target = app.documents[pickIdx];
        }
        var msg = "아래 문서를 슬림버전으로 변환합니다." + NL + NL +
                  target.fullName.fsName + NL + NL +
                  "· 어휘 선택 2 / 본문 정리 / 내용 종합 / 어법 O/X / 빈칸 어법 삭제" + NL +
                  "· 본문 O/X 반쪽 병합, 문장 배열 적층 병합" + NL +
                  "· 간지 정렬 + 마스터 좌우 보정" + NL + NL +
                  "되돌릴 수 없습니다. 사본으로 작업하세요. 계속할까요?";
        if (!confirm(msg)) { return; }
        settings = {
            output_indd: target.fullName.fsName,
            delete_sections: ["어휘 선택 2", "본문 정리", "내용 종합",
                              "어법 O/X", "빈칸 어법"],
            merge_half_sections: ["본문 O/X"],
            merge_stack_sections: ["문장 배열"],
            fix_divider_spreads: true,
            rename_markers: null,
            log_path: Folder.desktop.fsName + "/SlimBuild_로그.txt",
            log_paths: []
        };
        try { (new File(settings.log_path)).remove(); } catch (eRm) {}
    }

'''

TAIL_OLD = '''    try { doc.close(SaveOptions.NO); } catch (eCl) {}

    writeLog("===== 완료 =====");
})();'''

TAIL_NEW = '''    if (!MANUAL) {
        try { doc.close(SaveOptions.NO); } catch (eCl) {}
    }

    writeLog("===== 완료 =====");

    if (MANUAL) {
        alert("슬림 변환 완료" + NL + NL +
              "페이지: " + pagesBefore + "p → " + doc.pages.length + "p" + NL +
              "처리 섹션: " + actionCount + "개" + NL +
              "오버셋: " + overset + "건 / 누락 링크: " + missLink + "건" + NL + NL +
              "로그: " + settings.log_path);
    }
})();'''


def build():
    s = open(SRC, encoding="utf-8").read()
    s = NEW_HEAD + s[s.index("#target indesign"):]
    old_load = s[s.index("    // settings 로드 실패 시에도"):
                 s.index("    var LOG_PATH  = settings.log_path;")]
    s = s.replace(old_load, NEW_LOAD, 1)
    s = s.replace('    writeLog("변환 전 페이지: " + doc.pages.length);',
                  '    var pagesBefore = doc.pages.length;\n'
                  '    writeLog("변환 전 페이지: " + pagesBefore);')
    if TAIL_OLD not in s:
        raise SystemExit("[실패] 엔진 JSX 꼬리 패턴을 찾지 못했습니다")
    s = s.replace(TAIL_OLD, TAIL_NEW, 1)
    open(DST, "w", encoding="utf-8").write(s)
    return s


def check(s):
    problems = []
    depth, defs = 0, {}
    for n, line in enumerate(s.split("\n"), 1):
        code = line.split("//")[0]
        # 문자열이 줄을 넘지 않는지 — 이스케이프 사고(2026-08-25) 재발 방지
        probe = code.replace('\\"', "").replace("\\'", "")
        if probe.count('"') % 2:
            problems.append(f"{n}: 따옴표 홀수 — 문자열이 줄을 넘습니다")
        stripped = re.sub(r'"[^"]*"', "", code)
        stripped = re.sub(r"'[^']*'", "", stripped)
        m = re.match(r"\s*function (\w+)", line)
        if m:
            defs[m.group(1)] = depth
        depth += stripped.count("{") - stripped.count("}")
        for bad in (" let ", " const ", "=>", "`"):
            if bad in stripped:
                problems.append(f"{n}: ES3 위반 {bad!r}")
    if depth != 0:
        problems.append(f"중괄호 불균형: {depth}")
    for fn in ("isRight", "noMasterRuns", "isDividerRun", "fixDividerSpreads",
               "masterByPrefix", "fitHalfSplit", "mergeHalf", "mergeStack",
               "deleteSection", "renameMarkers"):
        if fn not in defs:
            problems.append(f"함수 없음: {fn}")
        elif defs[fn] != 1:
            problems.append(f"{fn} 스코프 깊이 {defs[fn]} (1이어야 함)")
    return problems


if __name__ == "__main__":
    src = build()
    probs = check(src)
    print(f"[재생성] {DST} ({len(src)} bytes)")
    if probs:
        print("[검증 실패]")
        for p in probs:
            print("  -", p)
        sys.exit(1)
    print("[검증] 문자열·스코프·ES3·필수 함수 이상 없음")
