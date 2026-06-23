"""파이널 직전보충 — InDesign 조판 실행기.

모든 InDesign 작업을 JSX 파일로 실행한다.
인라인 _jsx()는 짧은 명령에만 사용하고,
데이터 삽입/스타일 적용 등 긴 작업은 JSX 파일로 생성 후 실행.
"""

import json
import os
import shutil
import subprocess
import time


def _find_app():
    for ver in ["2026", "2025", "2024"]:
        if os.path.isdir(f"/Applications/Adobe InDesign {ver}"):
            return f"Adobe InDesign {ver}"
    raise RuntimeError("InDesign을 찾을 수 없습니다.")


def _dismiss_indesign_dialogs(app_name):
    try:
        subprocess.run(
            ["osascript", "-e", f'''
                tell application "{app_name}" to activate
                delay 0.5
                try
                    tell application "System Events"
                        tell process "{app_name}"
                            set frontmost to true
                            delay 0.5
                            click button 1 of window 1
                        end tell
                    end tell
                on error
                    try
                        tell application "System Events" to key code 36
                    end try
                end try
            '''],
            capture_output=True, text=True, timeout=10
        )
    except Exception:
        pass


def _run_jsx_file(app_name, jsx_path, timeout=300):
    """JSX 파일을 InDesign에서 실행 (부트스트랩 방식)."""
    boot = (
        f'app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;'
        f'var _f = new File("{jsx_path}");'
        f'app.doScript(_f, ScriptLanguage.JAVASCRIPT);'
    )
    escaped = boot.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    script = f'tell application "{app_name}" to do script "{escaped}" language javascript'

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout
        )
        return True
    except subprocess.TimeoutExpired:
        return True  # InDesign이 백그라운드에서 처리 중일 수 있음
    except Exception:
        return False


def _wait_marker(marker_path, timeout=300):
    """마커 파일이 생성될 때까지 대기."""
    waited = 0
    while not os.path.exists(marker_path) and waited < timeout:
        time.sleep(3)
        waited += 3
    return os.path.exists(marker_path)


def _build_vocab_jsx(indd_path, left_json_path, right_json_path, marker, log_file, pid=0, grade=""):
    """중요어휘 전용 JSX — Vol1 문서를 열고 새 페이지에 왼/오 프레임 생성."""
    is_g3_js = "true" if grade == "\uace03" else "false"
    return f"""#target indesign
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
var L = [];
function log(m) {{ L.push(m); }}
var IS_G3 = {is_g3_js};
// 고3 전용: 섹션 라벨 "중요 어휘 / 요약문" → "중요 어휘", 오른쪽 프레임 top inset 10mm
var VOCAB_LABEL = IS_G3 ? "\\uC911\\uC694 \\uC5B4\\uD718" : "\\uC911\\uC694 \\uC5B4\\uD718 / \\uC694\\uC57D\\uBB38";

try {{
    var doc = app.open(File("{indd_path}"));
    log("opened=" + doc.pages.length + "p");

    // Ruler origin 강제 SPREAD_ORIGIN — 일부 템플릿이 PAGE_ORIGIN으로 저장되어 있으면
    // page.bounds[1]이 LEFT/RIGHT 모두 0이 되어 RIGHT 페이지에 추가한 프레임의
    // geometricBounds가 spread 좌표계상 LEFT 영역으로 잡혀 pasteboard orphan이 됨.
    // SPREAD_ORIGIN으로 고정하면 RIGHT 페이지의 bounds[1]=pageWidth가 되어 xOff 계산이 맞음.
    var _origRulerOrigin = null;
    try {{
        _origRulerOrigin = doc.viewPreferences.rulerOrigin;
        doc.viewPreferences.rulerOrigin = RulerOrigin.SPREAD_ORIGIN;
        log("rulerOrigin set to SPREAD_ORIGIN (was=" + _origRulerOrigin + ")");
    }} catch(eRO) {{}}

    // textDefaults 색상 강제 Black (Paper 상속 방지)
    try {{ doc.textDefaults.fillColor = doc.swatches.itemByName("Black"); }} catch(e) {{}}

    // 페이지 shuffle 허용 — pages.add()가 새 spread를 강제 생성하는 대신
    // 기존 spread의 빈 slot을 활용하게 해서 짝수 빈 페이지 방지
    try {{ doc.documentPreferences.allowPageShuffle = true; }} catch(eDPS) {{}}
    try {{
        for (var _spsI = 0; _spsI < doc.spreads.length; _spsI++) {{
            try {{ doc.spreads[_spsI].allowPageShuffle = true; }} catch(eSh) {{}}
        }}
    }} catch(eShAll) {{}}

    // JSON 로드
    var vfL = new File("{left_json_path}");
    vfL.encoding = "UTF-8"; vfL.open("r");
    var passL; try {{ passL = eval("(" + vfL.read() + ")"); }} catch(e) {{ passL = []; }} vfL.close();

    var vfR = new File("{right_json_path}");
    vfR.encoding = "UTF-8"; vfR.open("r");
    var passR; try {{ passR = eval("(" + vfR.read() + ")"); }} catch(e) {{ passR = []; }} vfR.close();

    log("passL=" + passL.length + " passR=" + passR.length);

    // 스타일
    var allPS = doc.allParagraphStyles;
    var psLeft = null, psRight = null;
    for (var i = 0; i < allPS.length; i++) {{
        if (allPS[i].name === "2. \\uC911\\uC694\\uC5B4\\uD718(\\uC67C)") psLeft = allPS[i];
        if (allPS[i].name === "2. \\uC911\\uC694\\uC5B4\\uD718_\\uC6D0\\uBB38(\\uC624)") psRight = allPS[i];
    }}

    var master = doc.pages[1].appliedMaster;
    var vocabCount = Math.max(passL.length, passR.length);

    // D-마스터: 중요어휘 섹션의 첫 페이지가 오른쪽이면 적용
    var dMasterVocab = null;
    try {{
        var dms = doc.masterSpreads.itemByName("D-\\uB9C8\\uC2A4\\uD130");
        if (dms.isValid) dMasterVocab = dms;
    }} catch(e) {{}}

    // 기존 중요어휘 샘플/빈 페이지를 모두 삭제 후 새로 생성
    // (슬롯 재사용은 원본 샘플 잔재/순서 엉킴 문제가 있어 모두 삭제하고 새로 생성)
    // 문장배열/문장삽입 콘텐츠 프레임 바운드가 있는 페이지만 보존.
    var vEvenB = [[27,18,153,101],[153,18,279,101],[27,105,153,188],[153,105,279,188]];
    var vOddB  = [[27,22,153,105],[153,22,279,105],[27,109,153,192],[153,109,279,192]];
    var removedOldVocab = 0;
    for (var vpi = doc.pages.length - 1; vpi >= 2; vpi--) {{
        var vpg = doc.pages[vpi];
        var vpItems = vpg.allPageItems;
        var hasContentFrame = false;
        var vRef = (vpg.documentOffset % 2 === 0) ? vOddB : vEvenB;
        var vPgXOff = 0;
        try {{ vPgXOff = vpg.bounds[1]; }} catch(e) {{}}
        for (var vii = 0; vii < vpItems.length; vii++) {{
            if (vpItems[vii].constructor.name !== "TextFrame") continue;
            var vcgb = vpItems[vii].geometricBounds;
            var vcLx1 = vcgb[1] - vPgXOff;
            var vcLx2 = vcgb[3] - vPgXOff;
            for (var vri = 0; vri < vRef.length; vri++) {{
                if (Math.abs(vcgb[0] - vRef[vri][0]) < 8 &&
                    Math.abs(vcLx1 - vRef[vri][1]) < 8 &&
                    Math.abs(vcgb[2] - vRef[vri][2]) < 8 &&
                    Math.abs(vcLx2 - vRef[vri][3]) < 8) {{
                    hasContentFrame = true; break;
                }}
            }}
            if (hasContentFrame) break;
        }}
        if (hasContentFrame) continue; // 문장배열/문장삽입 페이지는 보존
        try {{ vpg.remove(); removedOldVocab++; }} catch(e) {{}}
    }}
    log("removedOldVocabSlots=" + removedOldVocab);

    // pasteboard 잔재 정리 함수 — 페이지 삭제 시 spread로 이동된 orphan 프레임/화살표 제거.
    // 예외: 음수 y좌표 라벨 프레임("중요 어휘 / 요약문" 등)은 유지.
    function cleanPbOrphans(tag) {{
        var rm = 0;
        for (var oSi = doc.spreads.length - 1; oSi >= 0; oSi--) {{
            var oSp = doc.spreads[oSi];
            var items = oSp.textFrames;
            for (var oIi = items.length - 1; oIi >= 0; oIi--) {{
                var it = items[oIi];
                var pp = null;
                try {{ pp = it.parentPage; }} catch(ePp) {{}}
                if (pp !== null) continue;
                var gb;
                try {{ gb = it.geometricBounds; }} catch(eGb) {{ continue; }}
                if (gb[0] < 0) continue;
                // threaded 텍스트 프레임(스토리 체인)은 보존
                try {{
                    if (it.previousTextFrame || it.nextTextFrame) continue;
                }} catch(eChk) {{}}
                try {{ it.remove(); rm++; }} catch(eRm) {{}}
            }}
        }}
        log("pbOrphansRemoved(" + tag + ")=" + rm);
    }}
    cleanPbOrphans("afterVocabSlots");
    // 모든 vocab 페이지를 새로 생성 (슬롯 재사용 안 함)
    var vocabPages = [];
    log("vocabSlots=0 (cleared)");

    // 문자스타일 [없음]
    var csNone = doc.characterStyles[0]; // [없음] or [None]

    // 오른쪽 프레임 배경색 스워치
    var grayFill = null;
    try {{ grayFill = doc.swatches.itemByName("[\\uAC80\\uC815] 5%"); }} catch(e) {{}}
    if (!grayFill) try {{ grayFill = doc.swatches.itemByName("[Black] 5%"); }} catch(e) {{}}

    // 문서 텍스트 기본값 초기화 — 새 프레임에 엉뚱한 문자스타일 방지
    try {{ doc.textDefaults.appliedCharacterStyle = csNone; }} catch(e) {{}}

    // 기존 프레임에 데이터 채우기
    var filled = 0;
    var rightFilled = 0;
    var vocabStories = []; // 지문번호 charStyle 후처리용
    for (var vfi = 0; vfi < vocabCount; vfi++) {{
        var lFrame, rFrame;
        if (vfi < vocabPages.length) {{
            lFrame = vocabPages[vfi].left;
            rFrame = vocabPages[vfi].right;
        }} else {{
            // 기존 슬롯 부족 시 새 페이지 추가
            // spread 꽉 채우기: 마지막 spread가 1페이지면 같은 spread에 추가,
            // 2페이지면 새 spread 생성 → 짝수 빈 페이지 방지
            var newPg;
            var _lastPg = doc.pages[-1];
            var _lastSp = _lastPg.parent;
            try {{ _lastSp.allowPageShuffle = true; }} catch(eSh1) {{}}
            if (_lastSp.pages.length < 2) {{
                // 마지막 spread의 반대쪽에 페이지 추가 (pages.add + spread reference)
                newPg = doc.pages.add(LocationOptions.AT_END, _lastSp);
            }} else {{
                // 2페이지 spread 꽉 참 → 새 spread 생성 후 shuffle=true로 세팅
                newPg = doc.pages.add();
                try {{ newPg.parent.allowPageShuffle = true; }} catch(eSh2) {{}}
            }}
            if (vfi < 4) {{
                log("vfi=" + vfi + " newPg off=" + newPg.documentOffset + " side=" + (newPg.side == 1818653800 ? "L" : (newPg.side == 1919382632 ? "R" : "?")) + " sp.pages=" + newPg.parent.pages.length + " bounds=[" + newPg.bounds.join(",") + "]");
            }}
            if (master) newPg.appliedMaster = master;
            // 첫 번째 새 vocab 페이지: D-마스터 + 섹션 라벨 적용
            if (vfi === vocabPages.length) {{
                if (dMasterVocab) {{
                    var _isRight = (newPg.side == PageSideOptions.RIGHT_HAND) || (newPg.side == 1919382632);
                    if (_isRight) {{
                        newPg.appliedMaster = dMasterVocab;
                        log("D-master applied to new vocab page " + newPg.documentOffset);
                        // 섹션 마커 추가 (섹션 2 = 중요어휘)
                        try {{
                            var vocSec = doc.sections.add(newPg);
                            vocSec.marker = "2";
                            vocSec.continueNumbering = true;
                            log("section marker=2 added");
                        }} catch(e) {{ log("section err: " + e.message); }}
                    }}
                }}
                // 섹션 라벨 "중요 어휘 / 요약문" 추가
                // 원본 템플릿의 pasteboard에 있는 탭 스토리를 vocab 첫 페이지로 이동
                try {{
                    var _vocLblSrc = null;
                    for (var _sSi = 0; _sSi < doc.stories.length; _sSi++) {{
                        var _sSt = doc.stories[_sSi];
                        try {{
                            var _sCnt = (_sSt.contents || "").replace(/[\\r\\n]/g, "");
                            if (_sCnt === "\\uC911\\uC694 \\uC5B4\\uD718 / \\uC694\\uC57D\\uBB38") {{
                                var _sTc = _sSt.textContainers;
                                if (_sTc.length > 0) {{ _vocLblSrc = _sTc[0]; break; }}
                            }}
                        }} catch(eS2) {{}}
                    }}
                    if (_vocLblSrc) {{
                        // Pasteboard 프레임을 newPg가 속한 spread로 이동 후 위치 유지
                        try {{
                            var _dupFrame = _vocLblSrc.duplicate(newPg);
                            // 고3: 라벨 "중요 어휘 / 요약문" → "중요 어휘"
                            if (IS_G3) {{
                                try {{ _dupFrame.contents = VOCAB_LABEL; }} catch(eRn) {{}}
                            }}
                            log("vocab label tab duplicated to page " + newPg.documentOffset);
                        }} catch(eD) {{
                            try {{
                                _vocLblSrc.move(newPg);
                                if (IS_G3) {{ try {{ _vocLblSrc.contents = VOCAB_LABEL; }} catch(eRn2) {{}} }}
                                log("vocab label tab moved");
                            }} catch(eM) {{ log("vocab label err=" + eM.message); }}
                        }}
                    }} else {{
                        // 폴백: spread에 새 프레임 생성
                        try {{
                            var _lblSpread = newPg.parent;
                            var _lblXOff = newPg.bounds[1];
                            var labelFrame = _lblSpread.textFrames.add({{
                                geometricBounds: [-17, 30+_lblXOff, 0, 101+_lblXOff]
                            }});
                            labelFrame.contents = VOCAB_LABEL;
                            var csSec = null;
                            for (var csi = 0; csi < doc.allCharacterStyles.length; csi++) {{
                                if (doc.allCharacterStyles[csi].name === "\\uC139\\uC158") {{
                                    csSec = doc.allCharacterStyles[csi]; break;
                                }}
                            }}
                            if (csSec) labelFrame.parentStory.characters.everyItem().appliedCharacterStyle = csSec;
                            try {{ labelFrame.parentStory.characters.everyItem().appliedFont = app.fonts.itemByName("\\uC5D8\\uB9AC\\uC2A4 DX\\uB110\\uB9AC\\uCCB4 OTF\\tMedium"); }} catch(e) {{}}
                            log("vocab label tab created fallback");
                        }} catch(eLF) {{ log("vocab label fallback err=" + eLF.message); }}
                    }}
                }} catch(eVL) {{ log("vocab label err=" + eVL.message); }}
            }}
            var npEven = (newPg.documentOffset % 2 === 0);
            // geometricBounds는 spread 좌표계이므로 RIGHT 페이지(spread 내 x=pageWidth 시작)에는
            // page.bounds[1](=xOff)를 반드시 더해야 함. 미적용 시 RIGHT용 프레임이 같은 spread의
            // LEFT 페이지에 겹쳐 배치되어 중요어휘가 반대쪽 페이지에 쌓이는 버그 발생.
            var _npXOff = 0;
            try {{ _npXOff = newPg.bounds[1]; }} catch(eXo) {{}}
            var lB = npEven ? [27,22+_npXOff,279,105+_npXOff] : [27,18+_npXOff,279,101+_npXOff];
            lFrame = newPg.textFrames.add({{geometricBounds: lB}});
            lFrame.textFramePreferences.insetSpacing = [3,0,0,0];
            var rB = npEven ? [27,109+_npXOff,223,192+_npXOff] : [27,105+_npXOff,223,188+_npXOff];
            rFrame = newPg.textFrames.add({{geometricBounds: rB}});
            // 오른쪽 프레임 top 여백 (고3 포함 전 학년 동일 10pt)
            rFrame.textFramePreferences.insetSpacing = [10, 0, 6, 0];
            if (grayFill) try {{ rFrame.fillColor = grayFill; }} catch(e) {{}}
        }}

        if (vfi < passL.length && passL[vfi] && passL[vfi].length > 2) {{
            var leftText = passL[vfi].replace(/\\n/g, "\\r");
            lFrame.parentStory.contents = leftText;
            if (psLeft) try {{
                // 단락스타일 적용 + 문자 오버라이드만 클리어 → GREP 스타일(fillColor=None) 작동 보장
                // fillColor=Black을 문자 레벨로 강제하면 GREP 스타일이 적용 불가하므로 제거
                lFrame.parentStory.paragraphs.everyItem().appliedParagraphStyle = psLeft;
                lFrame.parentStory.paragraphs.everyItem().clearOverrides(OverrideType.CHARACTER_ONLY);
            }} catch(e) {{}}
            vocabStories.push(lFrame.parentStory);
            filled++;

            // >>내용요약 위치 동기화: 왼쪽에서 >>내용요약 단락의 baseline 위치를 기록
            var summaryY = -1;
            try {{
                var lParas = lFrame.parentStory.paragraphs.everyItem().getElements();
                for (var lpi = 0; lpi < lParas.length; lpi++) {{
                    var lpt = (lParas[lpi].contents || "");
                    if (lpt.indexOf(">>") === 0) {{
                        summaryY = lParas[lpi].baseline;
                        break;
                    }}
                }}
            }} catch(e) {{}}
        }}
        if (vfi < passR.length && passR[vfi] && passR[vfi].length > 2) {{
            // 텍스트 시작 \\r/\\n/공백 제거 (오른쪽 frame 맨위 빈 줄 방지)
            var rightText = passR[vfi].replace(/\\n/g, "\\r").replace(/^[\\r\\n\\s]+/, "");
            rFrame.parentStory.contents = rightText;
            if (psRight) try {{
                // 단락스타일 적용 + 문자 오버라이드만 클리어 → GREP 스타일(볼드) 작동 보장
                rFrame.parentStory.paragraphs.everyItem().appliedParagraphStyle = psRight;
                rFrame.parentStory.paragraphs.everyItem().clearOverrides(OverrideType.CHARACTER_ONLY);
            }} catch(e) {{}}
            // 오른쪽 첫 단락 앞 여백(spaceBefore) 제거 — paragraph style의 spaceBefore가
            // 첫 줄 위에 빈 줄처럼 보이는 현상 방지
            try {{ rFrame.parentStory.paragraphs[0].spaceBefore = 0; }} catch(e) {{}}
            if (grayFill) try {{ rFrame.fillColor = grayFill; }} catch(e) {{}}
            vocabStories.push(rFrame.parentStory);
            rightFilled++;
            // 오른쪽 프레임: 오버플로우 시 아래로만 확장 (top 고정, bottom만 왼쪽 프레임과 동일 수준까지)
            // autoSizingType은 locale/버전에 따라 CENTER_POINT로 동작하는 버그가 있어 직접 bounds 조정.
            try {{
                if (rFrame.parentStory.overflows) {{
                    // autoSizing off 확인
                    try {{ rFrame.textFramePreferences.autoSizingType = AutoSizingTypeEnum.OFF; }} catch(e) {{}}
                    var rgb = rFrame.geometricBounds;
                    // 왼쪽 프레임의 bottom과 동일 수준까지만 확장 (페이지 번호 영역 침범 방지)
                    var lgb = lFrame.geometricBounds;
                    var newBottom = lgb[2];
                    if (newBottom > rgb[2]) {{
                        rFrame.geometricBounds = [rgb[0], rgb[1], newBottom, rgb[3]];
                    }}
                }}
            }} catch(e) {{}}

            // >>내용요약 위치 동기화: 오른쪽에서 >>내용요약 단락 위에 spaceBefore 조정
            if (summaryY > 0) {{
                try {{
                    var rParas = rFrame.parentStory.paragraphs.everyItem().getElements();
                    for (var rpi = 0; rpi < rParas.length; rpi++) {{
                        var rpt = (rParas[rpi].contents || "");
                        if (rpt.indexOf(">>") === 0) {{
                            var rSumY = rParas[rpi].baseline;
                            var diff = summaryY - rSumY;
                            if (Math.abs(diff) > 1) {{
                                rParas[rpi].spaceBefore = Math.max(0, rParas[rpi].spaceBefore + diff);
                            }}
                            break;
                        }}
                    }}
                }} catch(e) {{}}
            }}
        }}
    }}

    // 남은 빈 중요어휘 슬롯 삭제 (데이터보다 슬롯이 많을 때)
    for (var rpi = vocabPages.length - 1; rpi >= vocabCount; rpi--) {{
        try {{ vocabPages[rpi].page.remove(); }} catch(e) {{}}
    }}

    // 올포 문자 헤더("올포 N강 분석/서술형/논술형")에 "지문번호" 캐릭터 스타일 적용
    // 원인: psLeft/psRight의 nestedGrepStyle이 숫자로 끝나는 단락(YYMMQQ)만 지문번호 스타일 적용.
    //       한글로 끝나는 "분석/서술형/논술형" 헤더는 기본 서식으로 남음.
    // 해결: 각 vocab 스토리의 단락을 순회해 JS 정규식으로 헤더 식별 후 문자스타일 적용.
    try {{
        var csPassNumV = null;
        var allCSv = doc.allCharacterStyles;
        for (var csvi = 0; csvi < allCSv.length; csvi++) {{
            if (allCSv[csvi].name === "\\uC9C0\\uBB38\\uBC88\\uD638") {{ csPassNumV = allCSv[csvi]; break; }}
        }}
        if (csPassNumV && vocabStories.length > 0) {{
            var vAppliedCount = 0;
            var vGwApplied = 0;
            var vPattern = /^\\uC62C\\uD3EC \\d+\\uAC15 (?:\\uBD84\\uC11D|\\uC11C\\uC220\\uD615|\\uB17C\\uC220\\uD615)$/;
            var vGwPattern = /^(?:\\d+\\uAC15|test\\d+)\\s+(Gateway)$/i;
            for (var vsi = 0; vsi < vocabStories.length; vsi++) {{
                try {{
                    var vParas = vocabStories[vsi].paragraphs.everyItem().getElements();
                    for (var vpi = 0; vpi < vParas.length; vpi++) {{
                        var vText = (vParas[vpi].contents || "").replace(/[\\r\\n]+$/, "");
                        if (vPattern.test(vText)) {{
                            try {{
                                vParas[vpi].characters.everyItem().appliedCharacterStyle = csPassNumV;
                                vAppliedCount++;
                            }} catch(eA) {{}}
                        }}
                        // "N강 Gateway" 헤더: 단락 전체에 지문번호 charStyle 적용 (GREP ^.+\\d 패턴 보완)
                        if (vGwPattern.test(vText)) {{
                            try {{
                                for (var vGci = 0; vGci < vText.length; vGci++) {{
                                    vParas[vpi].characters[vGci].appliedCharacterStyle = csPassNumV;
                                }}
                                vGwApplied++;
                            }} catch(eGw) {{}}
                        }}
                    }}
                }} catch(eS) {{}}
            }}
            log("vocab passageNum charStyle applied count=" + vAppliedCount);
            log("vocab Gateway charStyle applied=" + vGwApplied);
            // recompose로 텍스트 레이아웃 강제 재계산 (PDF export 전 반영 보장)
            try {{ doc.recompose(); }} catch(eRC) {{}}
        }}
    }} catch(eVCS) {{
        log("vocab csFix err=" + eVCS.message);
    }}

    // 빈 페이지 삭제 — 문장배열 영역과 중요어휘 영역을 분리하여 처리
    // 순서 보장: 중요어휘 페이지가 문장배열 사이에 끼지 않도록 방지
    {{
        // Step 1: 중요어휘 첫 페이지 offset 찾기 (스타일 기반)
        var vocabFirstOff = 999;
        for (var spi = 1; spi < doc.pages.length; spi++) {{
            var spg = doc.pages[spi];
            var spItems = spg.allPageItems;
            var isVP = false;
            for (var sii = 0; sii < spItems.length; sii++) {{
                if (spItems[sii].constructor.name !== "TextFrame") continue;
                try {{
                    var sps = spItems[sii].paragraphs[0].appliedParagraphStyle;
                    if (sps.name.indexOf("\\uC911\\uC694\\uC5B4\\uD718") >= 0) {{
                        isVP = true; break;
                    }}
                }} catch(e) {{}}
            }}
            if (isVP) {{ vocabFirstOff = spi; break; }}
        }}
        log("vocabFirstOff=" + vocabFirstOff);

        // Step 2: 문장배열 영역 (page 1 ~ vocabFirstOff-1) 빈 페이지만 삭제
        var removedArr = 0;
        var arrEnd = (vocabFirstOff < 999) ? vocabFirstOff - 1 : doc.pages.length - 2;
        for (var api = arrEnd; api >= 1; api--) {{
            var apg = doc.pages[api];
            var aHasText = false;
            var apItems = apg.allPageItems;
            for (var aii = 0; aii < apItems.length; aii++) {{
                if (apItems[aii].constructor.name !== "TextFrame") continue;
                // B-2 스레드 연속(continuation) 프레임이 있는 페이지는 보존 (빈 듯 보여도 본문 이어짐)
                try {{ if (apItems[aii].previousTextFrame !== null) {{ aHasText = true; break; }} }} catch(e) {{}}
                var aigb = apItems[aii].geometricBounds;
                if (aigb[0] < 0 || aigb[1] < 0 || (aigb[2] - aigb[0]) < 20) continue;
                try {{
                    var atxt = apItems[aii].contents.replace(/[\\r\\n\\s\\u2028\\u2029]/g, "");
                    if (atxt.length > 0) {{ aHasText = true; break; }}
                }} catch(e) {{}}
            }}
            if (!aHasText) {{
                try {{ apg.remove(); removedArr++; }} catch(e) {{}}
            }}
        }}
        if (removedArr > 0) log("removedArrBlankPages=" + removedArr);

        // Step 3: 중요어휘 첫 페이지 재탐색 (삭제 후 offset 변동)
        var vocabFirstOff2 = 999;
        for (var spi2 = 1; spi2 < doc.pages.length; spi2++) {{
            var spg2 = doc.pages[spi2];
            var spItems2 = spg2.allPageItems;
            var isVP2 = false;
            for (var sii2 = 0; sii2 < spItems2.length; sii2++) {{
                if (spItems2[sii2].constructor.name !== "TextFrame") continue;
                try {{
                    var sps2 = spItems2[sii2].paragraphs[0].appliedParagraphStyle;
                    if (sps2.name.indexOf("\\uC911\\uC694\\uC5B4\\uD718") >= 0) {{
                        isVP2 = true; break;
                    }}
                }} catch(e) {{}}
            }}
            if (isVP2) {{
                vocabFirstOff2 = spi2;
                // D-마스터 적용 (오른쪽 페이지인 경우)
                if (dMasterVocab) {{
                    var _isR = (spg2.side == PageSideOptions.RIGHT_HAND) || (spg2.side == 1919382632);
                    if (_isR) {{
                        spg2.appliedMaster = dMasterVocab;
                        log("D-master reapplied to vocab page " + spg2.documentOffset);
                    }}
                }}
                // 섹션 마커 "2" 적용
                try {{
                    var existingSec = false;
                    for (var esi = 0; esi < doc.sections.length; esi++) {{
                        if (doc.sections[esi].pageStart === spg2) {{ existingSec = true; break; }}
                    }}
                    if (!existingSec) {{
                        var vocSec = doc.sections.add(spg2);
                        vocSec.marker = "2";
                        vocSec.continueNumbering = true;
                        log("section marker=2 at page " + spg2.documentOffset);
                    }}
                }} catch(e) {{ log("section err: " + e.message); }}
                break;
            }}
        }}
    }}

    log("vocab=" + vocabCount + " leftFilled=" + filled + " rightFilled=" + rightFilled + " pages=" + doc.pages.length);

    // 마지막 페이지 (크레딧) 추가 — 마지막페이지.ai 배치
    // 크레딧 페이지는 반드시 왼쪽(짝수) 페이지에 위치해야 함
    try {{
        var lastAiPath = "/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/\\uB0B4 \\uB4DC\\uB77C\\uC774\\uBE0C/\\uCF58\\uD150\\uCE20 \\uAD00\\uB9AC/\\uB0B4\\uC2E0\\uB300\\uBE44/\\uC778\\uB514\\uC790\\uC778 \\uD30C\\uC77C/\\uD30C\\uC774\\uB110 \\uC9C1\\uC804\\uBCF4\\uCDA9/\\uB0B4\\uC9C0/\\uB9C8\\uC9C0\\uB9C9\\uD398\\uC774\\uC9C0.ai";
        var lastAiFile = new File(lastAiPath);
        if (lastAiFile.exists) {{
            // 현재 마지막 페이지가 왼쪽(LEFT)이면 빈 오른쪽 페이지 삽입
            var lastPg = doc.pages[-1];
            if (lastPg.side == PageSideOptions.LEFT_HAND || lastPg.side == 1818653800) {{
                var blankPg = doc.pages.add();
                try {{
                    blankPg.appliedMaster = doc.masterSpreads.itemByName("A-chapter1");
                }} catch(e) {{
                    try {{ blankPg.appliedMaster = master; }} catch(e2) {{}}
                }}
                log("blankRightPage=inserted offset=" + blankPg.documentOffset);
            }}
            var creditPage = doc.pages.add();
            creditPage.appliedMaster = NothingEnum.NOTHING;
            var rect = creditPage.rectangles.add({{
                geometricBounds: [-3, -3, 300, 213]
            }});
            rect.place(lastAiFile);
            try {{ rect.fit(FitOptions.FILL_PROPORTIONALLY); }} catch(e) {{}}
            log("creditPage=ok side=" + creditPage.side + " offset=" + creditPage.documentOffset);
        }} else {{
            log("creditPage=aiNotFound");
        }}
    }} catch(e) {{
        log("creditPageErr=" + e.message);
    }}

    // vocab 영역의 모든 LEFT 페이지에 "중요 어휘 / 요약문" 탭 추가
    // (원본 템플릿의 pasteboard 탭이 조판 과정에서 소실되므로 직접 생성)
    try {{
        // vocab 첫 페이지 offset 재탐색
        var _vStart = -1;
        for (var _spi = 1; _spi < doc.pages.length; _spi++) {{
            var _spg = doc.pages[_spi];
            var _spItems = _spg.allPageItems;
            for (var _sii = 0; _sii < _spItems.length; _sii++) {{
                if (_spItems[_sii].constructor.name !== "TextFrame") continue;
                try {{
                    var _sps = _spItems[_sii].paragraphs[0].appliedParagraphStyle.name;
                    if (_sps.indexOf("\\uC911\\uC694\\uC5B4\\uD718") >= 0) {{ _vStart = _spi; break; }}
                }} catch(eVS) {{}}
            }}
            if (_vStart >= 0) break;
        }}
        if (_vStart >= 0) {{
            var _csSecTab = null;
            for (var _csi = 0; _csi < doc.allCharacterStyles.length; _csi++) {{
                if (doc.allCharacterStyles[_csi].name === "\\uC139\\uC158") {{ _csSecTab = doc.allCharacterStyles[_csi]; break; }}
            }}
            var _tabCount = 0;
            for (var _vpi = _vStart; _vpi < doc.pages.length; _vpi++) {{
                var _vpg = doc.pages[_vpi];
                var _isLeft = (_vpg.side == PageSideOptions.LEFT_HAND || _vpg.side == 1818653800);
                if (!_isLeft) continue;
                // 이미 탭 있으면 스킵
                var _hasTab = false;
                var _vItems2 = _vpg.allPageItems;
                for (var _vii = 0; _vii < _vItems2.length; _vii++) {{
                    if (_vItems2[_vii].constructor.name !== "TextFrame") continue;
                    try {{
                        var _vgb = _vItems2[_vii].geometricBounds;
                        if (_vgb[0] < 5 && _vgb[1] > 25 && _vgb[1] < 35) {{ _hasTab = true; break; }}
                    }} catch(eVI) {{}}
                }}
                if (_hasTab) continue;
                // spread에 탭 프레임 추가
                try {{
                    var _tabSpread = _vpg.parent;
                    var _tabXOff = _vpg.bounds[1];
                    var _tabFrame = _tabSpread.textFrames.add({{
                        geometricBounds: [-16.6, 30.2 + _tabXOff, 0, 101.4 + _tabXOff]
                    }});
                    _tabFrame.contents = VOCAB_LABEL;
                    if (_csSecTab) {{
                        try {{ _tabFrame.parentStory.characters.everyItem().appliedCharacterStyle = _csSecTab; }} catch(eCS3) {{}}
                    }}
                    try {{ _tabFrame.parentStory.characters.everyItem().appliedFont = app.fonts.itemByName("\\uC5D8\\uB9AC\\uC2A4 DX\\uB110\\uB9AC\\uCCB4 OTF\\tMedium"); }} catch(eFT) {{}}
                    _tabCount++;
                }} catch(eTF) {{}}
            }}
            log("vocab label tabs added count=" + _tabCount + " vStart=" + _vStart);
        }} else {{
            log("vocab start not found for tab add");
        }}
    }} catch(eVT) {{ log("vocab tab add err=" + eVT.message); }}

    // 오버플로우 확인
    var ov = 0;
    for (var i = 0; i < doc.stories.length; i++) {{ if (doc.stories[i].overflows) ov++; }}
    log("overflow=" + ov);

    // 아래/위 첨자 유니코드 (U+2070~U+209F) 폰트 교체 — 한컴 함초롬돋움 우선, 미설치 시 Nanum Gothic / Apple SD Gothic Neo 폴백
    // (Vol1 JSX에서 적용된 후 vocab JSX가 페이지/스토리를 추가하며 새로 삽입된 텍스트도 같이 처리)
    try {{
        var _hcFontVB = null;
        var _fontCandVB = [
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0\\tRegular",
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0",
            "NanumGothic\\tRegular",
            "NanumGothic",
            "Nanum Gothic\\tRegular",
            "AppleSDGothicNeo\\tRegular",
            "AppleSDGothicNeo-Regular",
            "Apple SD Gothic Neo\\tRegular"
        ];
        for (var _fciVB = 0; _fciVB < _fontCandVB.length; _fciVB++) {{
            try {{
                var _fVB = app.fonts.itemByName(_fontCandVB[_fciVB]);
                if (_fVB && _fVB.isValid) {{ _hcFontVB = _fVB; break; }}
            }} catch(eFCVB) {{}}
        }}
        if (_hcFontVB) {{
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = "[\\u2070-\\u209F]";
            app.changeGrepPreferences.appliedFont = _hcFontVB;
            var _subChangedVB = doc.changeGrep();
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            log("subscript font applied vocab count=" + (_subChangedVB ? _subChangedVB.length : 0));
        }} else {{
            log("subscript font vocab: hamchorom not found");
        }}
    }} catch(eSubVB) {{
        log("subscript font err vocab: " + eSubVB.message);
        try {{ app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING; }} catch(e) {{}}
    }}

    // 직전보충: PDF 미내보내기 — 인디자인 파일(.indd)만 생성
    log("pdf=skip");

    // Ruler origin 원상 복구 (저장 전)
    try {{
        if (_origRulerOrigin !== null) doc.viewPreferences.rulerOrigin = _origRulerOrigin;
    }} catch(eRO2) {{}}

    doc.save();
    // 조판 결과는 닫지 않고 열어둠 (결과 즉시 확인용)

}} catch(ex) {{
    log("ERROR=" + ex.message);
    try {{ app.activeDocument.close(SaveOptions.NO); }} catch(e2) {{}}
}}

app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
var mf = new File("{marker}"); mf.open("w"); mf.write("done"); mf.close();
var lf = new File("{log_file}"); lf.open("w"); lf.encoding="UTF-8"; lf.write(L.join("\\n")); lf.close();
"""


def run_typeset(settings_path, log):
    """settings.json을 읽고 Vol1/Vol2 순차 조판."""
    app = _find_app()
    log(f"[조판] InDesign: {app}")

    _dismiss_indesign_dialogs(app)
    # 작업 중인 다른 문서 보호: 전체 문서 닫기(close-all) 제거.
    # 조판 대상은 매 실행 safe_copy_indd가 새 경로(_2, _3…)로 생성하므로 충돌 없음.

    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)

    job_dir = os.path.dirname(settings_path)
    log_lines = []
    jobs = settings.get("jobs", [])
    grade = settings.get("grade", "")  # 고3 전용 분기 용도

    for job in jobs:
        vol = job["vol"]
        indd_path = job["indd_path"]  # 구글드라이브 최종 경로
        data = job["data"]
        vol_label = "Vol.1" if vol == "vol1" else "Vol.2"

        log(f"[조판] {vol_label} 시작: {os.path.basename(indd_path)}")

        pid = os.getpid()
        marker = f"/tmp/_final_{vol}_done_{pid}.txt"
        log_file = f"/tmp/_final_{vol}_log_{pid}.txt"
        for p in [marker, log_file]:
            if os.path.exists(p):
                os.remove(p)

        # 데이터를 /tmp에 JSON으로 저장
        data_path = f"/tmp/_final_{vol}_data_{pid}.json"
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        # PDF 경로 (InDesign에서 접근 가능한 경로 — indd와 같은 위치)
        pdf_path = indd_path.replace(".indd", ".pdf")

        # JSX 생성
        if vol == "vol1":
            jsx_code = _build_vol1_jsx(indd_path, data_path, pdf_path, marker, log_file, pid, grade=grade)
        else:
            jsx_code = _build_vol2_jsx(indd_path, data_path, pdf_path, marker, log_file, pid)

        jsx_path = f"/tmp/_final_{vol}_{pid}.jsx"
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(jsx_code)

        log("  JSX 실행 중...")
        _run_jsx_file(app, jsx_path, timeout=600)

        # 마커 대기
        if _wait_marker(marker, timeout=600):
            if os.path.exists(log_file):
                with open(log_file, encoding="utf-8") as lf:
                    for line in lf.read().strip().split("\n"):
                        log(f"  {line}")
                        if "overflow=" in line:
                            try:
                                ov = int(line.split("overflow=")[1].split()[0])
                                log_lines.append(f"오버플로우: {ov}개")
                            except Exception:
                                pass
                os.remove(log_file)
            os.remove(marker)

            # 직전보충: PDF 미생성 — 인디자인 파일만 저장 (indd_path에 doc.save() 완료)
            if os.path.exists(indd_path):
                log(f"  내지(.indd): {os.path.basename(indd_path)}")
                log_lines.append(f"내지: 성공 ({os.path.basename(indd_path)})")
            else:
                log(f"  내지 미생성")
        else:
            log(f"  {vol_label} 타임아웃")
            log_lines.append(f"{vol_label} 타임아웃")

        # Vol1 중요어휘 — 별도 JSX로 실행
        if vol == "vol1" and os.path.exists(indd_path):
            vocab_left_json = f"/tmp/_final_vocab_left_{pid}.json"
            vocab_right_json = f"/tmp/_final_vocab_right_{pid}.json"
            vl_size = os.path.getsize(vocab_left_json) if os.path.exists(vocab_left_json) else 0
            vr_size = os.path.getsize(vocab_right_json) if os.path.exists(vocab_right_json) else 0
            log(f"  중요어휘 JSON: left={vl_size}B right={vr_size}B")
            has_vocab = vl_size > 5 or vr_size > 5
            if has_vocab:
                log("  중요어휘 배치 중...")
                vocab_marker = f"/tmp/_final_vocab_done_{pid}.txt"
                vocab_log_f = f"/tmp/_final_vocab_log_{pid}.txt"
                for p in [vocab_marker, vocab_log_f]:
                    if os.path.exists(p):
                        os.remove(p)
                vocab_jsx = _build_vocab_jsx(
                    indd_path, vocab_left_json, vocab_right_json,
                    vocab_marker, vocab_log_f, pid=pid, grade=grade
                )
                vocab_jsx_path = f"/tmp/_final_vocab_{pid}.jsx"
                with open(vocab_jsx_path, "w", encoding="utf-8") as f:
                    f.write(vocab_jsx)
                _run_jsx_file(app, vocab_jsx_path, timeout=600)
                if _wait_marker(vocab_marker, timeout=900):
                    if os.path.exists(vocab_log_f):
                        with open(vocab_log_f, encoding="utf-8") as lf:
                            for line in lf.read().strip().split("\n"):
                                log(f"  {line}")
                        os.remove(vocab_log_f)
                    os.remove(vocab_marker)
                    # 직전보충: 중요어휘 추가 후 .indd 저장 완료 (PDF 미생성)
                    log("  중요어휘 완료")
                else:
                    log("  중요어휘 타임아웃")
                for tmp in [vocab_jsx_path]:
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass

        # 임시 파일 정리
        for tmp in [data_path, jsx_path]:
            try:
                os.remove(tmp)
            except Exception:
                pass

    # 로그 저장
    log_path = os.path.join(job_dir, "typeset_log.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    log("[조판] 완료")


def _build_vol1_jsx(indd_path, data_path, pdf_path, marker, log_file, pid, grade=""):
    """Vol1 전체 처리 JSX 생성.

    완성본 분석 기반 구조:
    - Story[3] (가장 큰 스토리): 문장배열 메인
      패턴: [1. 문장 배열 번호] 헤더 → [문장 배열 그랩] (A)~(J) → [1. 문장 배열 그랩] 빈줄 → [[기본 단락]] ＞ + 앵커 → FB
    - Story[32] (page 11~ 시작): 문장삽입/순서배열
      패턴: [[기본 단락]] {헤더} → [C1_문장 배열/문장 배열 하단 문제] 지문 → [문장 배열 하단 ] 박스
    - 중요어휘: 개별 스토리들 (2. 중요어휘(왼) / 2. 중요어휘_원문(오))
    """
    # 중요어휘 데이터를 지문별 JSON 배열로 저장
    vocab_left_path = f"/tmp/_final_vocab_left_{pid}.json"
    vocab_right_path = f"/tmp/_final_vocab_right_{pid}.json"

    try:
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
        import re as _re

        def _split_vocab(raw_text):
            raw_text = _re.sub(r'^(\d{4})(41|42)$', r'\g<1>41~42', raw_text, flags=_re.MULTILINE)
            # 고3 강+지문번호 헤더("3강 01", "3강 Gateway", "test1 01", "test1 24~25") 또는 기존 YYMMQQ 헤더로 분할
            has_lecture = bool(_re.search(r'^\d+강\s+(?:\d{2}(?:[~\-]\d{2})?|Gateway)$', raw_text, _re.MULTILINE | _re.IGNORECASE))
            has_test = bool(_re.search(r'^test\d+\s+(?:\d{2}(?:[~\-]\d{2})?|Gateway)$', raw_text, _re.MULTILINE | _re.IGNORECASE))
            has_olpo = bool(_re.search(r'^\uc62c\ud3ec\s+\d+\uac15\s+\S+', raw_text, _re.MULTILINE))
            has_rp = bool(_re.search(r'^\ub9ac\ub529\ud30c\uc6cc\s+\d+\uac15\s+\S+', raw_text, _re.MULTILINE))
            has_tb = bool(_re.search(r'^\uad50\uacfc\uc11c\S+?\s+\ubcf8\ubb38\d+$', raw_text, _re.MULTILINE))
            if has_lecture or has_test or has_tb:
                # 고3: "N강 MM" / "N강 Gateway" / "test1 24~25" / "교과서N과 본문M" 헤더 기준 분할
                parts = _re.split(r"(?=^(?:\d+강|test\d+)\s+(?:\d{2}(?:[~\-]\d{2})?|Gateway)$|^\uad50\uacfc\uc11c\S+?\s+\ubcf8\ubb38\d+$)", raw_text, flags=_re.MULTILINE | _re.IGNORECASE)
            elif has_olpo or has_rp:
                # 파이널 고1/고2: YYMMQQ / "올포 N강 {섹션}" / "리딩파워 N강 {ExMM|MM}" 헤더 기준 분할
                parts = _re.split(r"(?=^(?:\d{6}(?:~\d{2})?|\uc62c\ud3ec\s+\d+\uac15\s+\S+|\ub9ac\ub529\ud30c\uc6cc\s+\d+\uac15\s+\S+)$)", raw_text, flags=_re.MULTILINE)
            else:
                # 기존: YYMMQQ 기준 분할
                parts = _re.split(r"(?=^\d{6}(?:~\d{2})?$)", raw_text, flags=_re.MULTILINE)
            passages = []
            for part in parts:
                part = part.strip()
                if part:
                    passages.append(part)
            return passages

        def _extract_vocab_key(p):
            """중요어휘 패시지에서 정렬/동기화 키 추출."""
            # 파이널 리딩파워: "리딩파워 N강 ExMM" / "리딩파워 N강 MM"
            m = _re.match(r'^(\ub9ac\ub529\ud30c\uc6cc\s+\d+\uac15\s+\S+)', p)
            if m:
                return m.group(1)
            # 파이널 올포: "올포 N강 {섹션}" (섹션: 분석/본문1/본문2/본문3/서술형/논술형)
            m = _re.match(r'^(\uc62c\ud3ec\s+\d+\uac15\s+\S+)', p)
            if m:
                return m.group(1)
            # 고3 강+지문번호 헤더 ("3강 01", "3강 Gateway", "test1 24~25")
            m = _re.match(r'^((?:\d+강|test\d+)\s+(?:\d{2}(?:[~\-]\d{2})?|Gateway))', p, _re.IGNORECASE)
            if m:
                return m.group(1)
            # 고3 교과서 헤더 ("교과서2과 본문1")
            m = _re.match(r'^(\uad50\uacfc\uc11c\S+?\s+\ubcf8\ubb38\d+)', p)
            if m:
                return m.group(1)
            # 기존 YYMMQQ
            m = _re.match(r'^(\d{6}(?:~\d{2})?)', p)
            if m:
                return m.group(1)
            return ""

        def _vocab_sort_key(key):
            # 파이널 통합 순서: 교과서(0) → 리딩파워(1, 강별 Ex 먼저) → 올포(1.2) → YYMMQQ(2)
            # 파이널 리딩파워: "리딩파워 N강 ExMM" / "리딩파워 N강 MM"
            m = _re.match(r'^\ub9ac\ub529\ud30c\uc6cc\s+(\d+)\uac15\s+(?:Ex)?(\d+)', key)
            if m:
                lec_n = int(m.group(1))
                is_ex = 0 if "Ex" in key else 1  # Ex(0) → 문제(1) 순
                num = int(m.group(2))
                return (1, lec_n, is_ex, num)
            # 파이널 올포: "올포 N강 섹션"
            m = _re.match(r'^\uc62c\ud3ec\s+(\d+)\uac15\s+(\S+)', key)
            if m:
                lec_n = int(m.group(1))
                sec = m.group(2)
                sec_ord_map = {
                    "\ubd84\uc11d": 0,
                    "\ubcf8\ubb381": 1,
                    "\ubcf8\ubb382": 2,
                    "\ubcf8\ubb383": 3,
                    "\uc11c\uc220\ud615": 4,
                    "\ub17c\uc220\ud615": 5,
                }
                return (1.2, lec_n, sec_ord_map.get(sec, 99))
            # "3강 Gateway" → (0, 3, 0) — 동일 강의 숫자 지문보다 먼저
            m = _re.match(r'^(\d+)강\s+Gateway', key, _re.IGNORECASE)
            if m:
                return (0, int(m.group(1)), 0)
            # "3강 01" → (0, 3, 1), "test1 24~25" → (1, 1, 24)
            m = _re.match(r'^(\d+)강\s+(\d+)', key)
            if m:
                return (0, int(m.group(1)), int(m.group(2)))
            m = _re.match(r'^(\d+)강$', key)
            if m:
                return (0, int(m.group(1)), 0)
            # "test1 Gateway" → (1, 1, 0) — 숫자보다 먼저
            m = _re.match(r'^test(\d+)\s+Gateway', key, _re.IGNORECASE)
            if m:
                return (1, int(m.group(1)), 0)
            m = _re.match(r'^test(\d+)\s+(\d+)', key)
            if m:
                return (1, int(m.group(1)), int(m.group(2)))
            m = _re.match(r'^(\d{6})', key)
            if m:
                return (2, int(m.group(1)), 0)
            # 교과서N과 본문M → (1.5, N, M): 강(0,1) 뒤 & YYMMQQ(2) 앞
            m = _re.match(r'^\uad50\uacfc\uc11c(\d+)\uacfc\s+\ubcf8\ubb38(\d+)', key)
            if m:
                return (0, int(m.group(1)), int(m.group(2)))
            return (4, 0, 0)

        left_passages = _split_vocab(data.get("중요어휘_왼", "") or "")
        right_passages = _split_vocab(data.get("중요어휘_오", "") or "")

        # 오른쪽에 헤더가 없는 경우 (고3): 빈줄로 분할 후 왼쪽과 1:1 매칭
        right_has_keys = any(_extract_vocab_key(p) for p in right_passages)
        if right_has_keys:
            # 키 기준 좌/우 동기화. 순서는 content.json의 등장 순서를 그대로 유지
            # (워크북 파일 순서대로 이미 정렬돼 있음 — 다시 YYMMQQ 숫자 정렬로 뒤집지 않는다)
            left_by_num = {}
            left_keys_ordered = []
            for p in left_passages:
                k = _extract_vocab_key(p)
                if k and k not in left_by_num:
                    left_by_num[k] = p
                    left_keys_ordered.append(k)
            right_by_num = {}
            for p in right_passages:
                k = _extract_vocab_key(p)
                if k and k not in right_by_num:
                    right_by_num[k] = p
            # right에만 있는 키를 등장 순서로 뒤에 추가
            for p in right_passages:
                k = _extract_vocab_key(p)
                if k and k not in left_by_num and k not in left_keys_ordered:
                    left_keys_ordered.append(k)
            all_nums = left_keys_ordered
            sorted_left = [left_by_num.get(n, "") for n in all_nums]
            sorted_right = [right_by_num.get(n, "") for n in all_nums]
        else:
            # 고3: 오른쪽에 헤더 없음 → 빈줄(\n\n)로 분할하여 순서 매칭.
            # 좌(중요어휘_왼)와 우(중요어휘_오)는 파서가 같은 순서로 emit하므로
            # 인덱스로 1:1 대응한다. 정렬이 필요하면 반드시 좌/우를 '쌍으로 묶어'
            # 같은 키로 정렬해야 한다. (과거엔 왼쪽만 따로 정렬해서, content.json의
            # 패시지 순서가 정렬 순서와 다르거나(test2가 test1보다 먼저 등) 유령/
            # 중복 블록이 끼면 test1 04부터 좌우가 한 칸씩 어긋났다.)
            right_raw = data.get("중요어휘_오", "") or ""
            right_by_blank = [p.strip() for p in right_raw.split("\n\n") if p.strip()]
            _n = min(len(left_passages), len(right_by_blank))
            _pairs = [[left_passages[i], right_by_blank[i]] for i in range(_n)]
            # 좌가 더 많으면(우 분할 누락 등) 남는 좌는 빈 우와 매칭
            for _lp in left_passages[_n:]:
                _pairs.append([_lp, ""])
            _pairs.sort(key=lambda pr: _vocab_sort_key(_extract_vocab_key(pr[0]) or ""))
            sorted_left = [pr[0] for pr in _pairs]
            sorted_right = [pr[1] for pr in _pairs]

        # 오른쪽(원문)에서 지문번호 헤더 라인을 완전히 제거한다.
        # 왼쪽은 단락 스타일에서 헤더 처리하지만, 오른쪽은 헤더 텍스트가 남으면
        # 공백 줄이 되어 왼쪽/오른쪽 첫 문장 시작 높이가 어긋난다.
        _vocab_header_re = _re.compile(
            r'^(?:\d{6}(?:~\d{2})?|'
            r'\uc62c\ud3ec\s+\d+\uac15\s+\S+|'
            r'(?:\ub9ac\ub529\ud30c\uc6cc\s+)?(?:\d+\uac15|test\d+)\s+(?:Ex\d+|\d{2}(?:[~\-]\d{2})?|Gateway)|'
            r'\uad50\uacfc\uc11c\S+?\s+\ubcf8\ubb38\d+)\s*\n',
            _re.IGNORECASE,
        )
        # 오른쪽 프레임 본문은 왼쪽 프레임과 동일 높이에서 시작해야 함.
        # 헤더 제거 후 맨 앞에 남은 빈 줄(\n 또는 공백)을 제거하여 시작 위치를 맞춘다.
        stripped_right = []
        for p in sorted_right:
            _p_cleaned = _vocab_header_re.sub('', p, count=1)
            # 맨 앞 연속 빈 줄/공백 제거
            _p_cleaned = _re.sub(r'^[\s\r\n]+', '', _p_cleaned)
            stripped_right.append(_p_cleaned)

        for passages, path in [(sorted_left, vocab_left_path), (stripped_right, vocab_right_path)]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(passages, f, ensure_ascii=False)
    except Exception as e:
        import traceback
        traceback.print_exc()
        for p in [vocab_left_path, vocab_right_path]:
            with open(p, "w") as f:
                json.dump([], f)


    is_g3_js = "true" if grade == "\uace03" else "false"
    return f"""#target indesign
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
var L = [];
function log(m) {{ L.push(m); }}
var IS_G3 = {is_g3_js};

try {{
    var doc = app.open(File("{indd_path}"));
    log("opened=" + doc.pages.length + "p");

    // Ruler origin 강제 SPREAD_ORIGIN — PAGE_ORIGIN 템플릿에서 addFramePage 시
    // 새 페이지의 bounds[1]=0 반환으로 RIGHT 페이지 프레임이 spread pasteboard로
    // 떨어지는 버그 방지. PDF export 후 저장 전 원본 값으로 복원.
    var _origRulerOrigin = null;
    try {{
        _origRulerOrigin = doc.viewPreferences.rulerOrigin;
        doc.viewPreferences.rulerOrigin = RulerOrigin.SPREAD_ORIGIN;
        log("rulerOrigin set to SPREAD_ORIGIN (was=" + _origRulerOrigin + ")");
    }} catch(eRO) {{}}

    // pasteboard 잔재 정리 함수 — 페이지 삭제 시 spread로 이동된 orphan 프레임/화살표 제거.
    // 예외: 음수 y좌표 라벨 프레임은 유지.
    function cleanPbOrphans(tag) {{
        var rm = 0;
        for (var oSi = doc.spreads.length - 1; oSi >= 0; oSi--) {{
            var oSp = doc.spreads[oSi];
            var items = oSp.textFrames;
            for (var oIi = items.length - 1; oIi >= 0; oIi--) {{
                var it = items[oIi];
                var pp = null;
                try {{ pp = it.parentPage; }} catch(ePp) {{}}
                if (pp !== null) continue;
                var gb;
                try {{ gb = it.geometricBounds; }} catch(eGb) {{ continue; }}
                if (gb[0] < 0) continue;
                // threaded 텍스트 프레임(스토리 체인)은 보존
                try {{
                    if (it.previousTextFrame || it.nextTextFrame) continue;
                }} catch(eChk) {{}}
                try {{ it.remove(); rm++; }} catch(eRm) {{}}
            }}
        }}
        log("pbOrphansRemoved(" + tag + ")=" + rm);
    }}

    // textDefaults 색상 강제 Black (Paper 상속 방지)
    try {{ doc.textDefaults.fillColor = doc.swatches.itemByName("Black"); }} catch(e) {{}}

    // 기존 크레딧 페이지 삭제 (이전 실행에서 템플릿에 저장된 잔재 제거)
    // 마지막 페이지만 확인 (master=null 인 경우). page 0(표지)은 절대 건드리지 않음.
    // 두 번째 실행부터 표지 페이지가 master=null로 남아 있어서 역방향 탐색 시
    // 크레딧이 이미 삭제된 상태에서 표지까지 제거되는 회귀를 방지.
    try {{
        var _lastIdx = doc.pages.length - 1;
        if (_lastIdx > 0) {{
            var _lastPg = doc.pages[_lastIdx];
            if (_lastPg.appliedMaster == NothingEnum.NOTHING || !_lastPg.appliedMaster) {{
                _lastPg.remove();
                log("removed old creditPage at offset=" + _lastIdx);
            }}
        }}
    }} catch(e) {{}}

    // ========================================
    // 1. 데이터 로드
    // ========================================
    var cf = new File("{data_path}");
    cf.encoding = "UTF-8"; cf.open("r");
    var data = eval("(" + cf.read() + ")");
    cf.close();
    var blocks = data["\\uBB38\\uC7A5\\uBC30\\uC5F4"] || [];
    var insertBlocks = data["\\uBB38\\uC7A5\\uC0BD\\uC785"] || [];
    log("blocks=" + blocks.length + " insertBlocks=" + insertBlocks.length);

    // ========================================
    // 2. 스타일 수집
    // ========================================
    var allPS = doc.allParagraphStyles;
    var psHeader = null;
    var psGrab = null;
    var psGrabEnd = null;
    var psBasic = null;
    var psInsertQ = null;
    var psInsertBox = null;
    var psInsertC1 = null;
    var psInsertPassage = null;  // 문장 배열 하단 지문 (박스 다음 지문 단락)
    var psPassage = null;  // 고3 분석편 원문 (C1_문장 배열 하단)

    for (var i = 0; i < allPS.length; i++) {{
        var n = allPS[i].name;
        if (n === "1. \\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uBC88\\uD638") psHeader = allPS[i];
        if (n === "\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uADF8\\uB7A9") psGrab = allPS[i];
        if (n === "1. \\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uADF8\\uB7A9") psGrabEnd = allPS[i];
        if (n === "[\\uAE30\\uBCF8 \\uB2E8\\uB77D]" || n === "[Basic Paragraph]") psBasic = allPS[i];
        if (n === "\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8 \\uBB38\\uC81C") psInsertQ = allPS[i];
        if (n === "\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8 " || n === "\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8") {{
            if (!psInsertBox) psInsertBox = allPS[i];
        }}
        if (n === "\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8 \\uC9C0\\uBB38") psInsertPassage = allPS[i];
        if (n === "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4") psInsertC1 = allPS[i];
        if (n === "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8") psPassage = allPS[i];
    }}

    var csArrow = null;
    var allCS = doc.allCharacterStyles;
    for (var ci = 0; ci < allCS.length; ci++) {{
        if (allCS[ci].name === "1. \\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD654\\uC0B4\\uD45C") {{
            csArrow = allCS[ci];
            break;
        }}
    }}
    if (csArrow) log("csArrow=" + csArrow.name);

    // ========================================
    // 3. 화살표 앵커 소스 찾기 (마스터 페이지)
    // ========================================
    var arrowSrc = null;
    for (var si = 0; si < doc.stories.length; si++) {{
        var st = doc.stories[si];
        try {{
            if (st.paragraphs.length >= 1 && st.paragraphs.length <= 3) {{
                var tc = st.textContainers;
                if (tc.length > 0 && !tc[0].parentPage) {{
                    if (st.allPageItems && st.allPageItems.length > 0) {{
                        for (var ai = 0; ai < st.allPageItems.length; ai++) {{
                            if (st.allPageItems[ai].constructor.name === "GraphicLine") {{
                                arrowSrc = st;
                                log("arrowSrc=Story[" + si + "]");
                                break;
                            }}
                        }}
                        if (arrowSrc) break;
                    }}
                }}
            }}
        }} catch(e) {{}}
    }}
    if (!arrowSrc) log("arrowSrc=NOT_FOUND");

    // ========================================
    // 4. 섹션 경계 탐지
    // ========================================
    var insertStartPageRef = null;
    var insertStartPageOff = -1;

    // 4a. D-마스터 탐지
    for (var pi = 2; pi < doc.pages.length; pi++) {{
        try {{
            var m = doc.pages[pi].appliedMaster;
            if (m && m.name.indexOf("D-") === 0) {{
                insertStartPageOff = pi;
                insertStartPageRef = doc.pages[pi];
                break;
            }}
        }} catch(e) {{}}
    }}

    // 4b. 섹션 제목 프레임 탐지 ("삽입" 또는 "순서" 포함)
    if (insertStartPageOff < 0) {{
        for (var pi = 2; pi < doc.pages.length; pi++) {{
            var tfs = doc.pages[pi].textFrames;
            for (var ti = 0; ti < tfs.length; ti++) {{
                try {{
                    var c = (tfs[ti].contents || "");
                    if (c.indexOf("\\uC0BD\\uC785") >= 0 || c.indexOf("\\uC21C\\uC11C") >= 0) {{
                        insertStartPageOff = pi;
                        insertStartPageRef = doc.pages[pi];
                        break;
                    }}
                }} catch(e) {{}}
            }}
            if (insertStartPageOff >= 0) break;
        }}
    }}

    // 4c. 폴백: 블록 수 기반 추정
    if (insertStartPageOff < 0) {{
        var estPages = Math.ceil(blocks.length / 4) + 1;
        insertStartPageOff = 1 + estPages;
        if (insertStartPageOff < doc.pages.length) {{
            insertStartPageRef = doc.pages[insertStartPageOff];
        }}
    }}
    log("insertStartPageOff=" + insertStartPageOff);

    // 4d. 내용요약 시작 페이지 탐지
    var summaryStartPageRef = null;
    var summaryStartPageOff = 999;

    // 섹션 제목 "내용요약" 또는 "내용" 포함 프레임 탐지
    for (var spi2 = (insertStartPageOff > 0 ? insertStartPageOff + 1 : 2); spi2 < doc.pages.length; spi2++) {{
        var stfs = doc.pages[spi2].textFrames;
        for (var sti = 0; sti < stfs.length; sti++) {{
            try {{
                var sc = (stfs[sti].contents || "");
                if (sc.indexOf("\\uB0B4\\uC6A9\\uC694\\uC57D") >= 0 || sc.indexOf("\\uB0B4\\uC6A9 \\uC694\\uC57D") >= 0) {{
                    summaryStartPageOff = spi2;
                    summaryStartPageRef = doc.pages[spi2];
                    break;
                }}
            }} catch(e) {{}}
        }}
        if (summaryStartPageOff < 999) break;
    }}
    log("summaryStartPageOff=" + summaryStartPageOff);

    // 4e. 중요어휘 시작 페이지 탐지
    var vocabStartPageRef = null;
    var vocabStartPageOff = 999;

    // 섹션 제목 "어휘" 또는 "중요" 포함 프레임 탐지
    for (var vpi = (insertStartPageOff > 0 ? insertStartPageOff + 1 : 2); vpi < doc.pages.length; vpi++) {{
        var vtfs = doc.pages[vpi].textFrames;
        for (var vti = 0; vti < vtfs.length; vti++) {{
            try {{
                var vc = (vtfs[vti].contents || "");
                if (vc.indexOf("\\uC5B4\\uD718") >= 0 || vc.indexOf("\\uC911\\uC694") >= 0) {{
                    vocabStartPageOff = vpi;
                    vocabStartPageRef = doc.pages[vpi];
                    break;
                }}
            }} catch(e) {{}}
        }}
        if (vocabStartPageOff < 999) break;
    }}

    // 폴백: 전폭 프레임 (width > 180) 탐지
    if (vocabStartPageOff >= 999) {{
        for (var vpi2 = (insertStartPageOff > 0 ? insertStartPageOff + 1 : 2); vpi2 < doc.pages.length; vpi2++) {{
            var vtfs2 = doc.pages[vpi2].textFrames;
            for (var vti2 = 0; vti2 < vtfs2.length; vti2++) {{
                try {{
                    var vgb = vtfs2[vti2].geometricBounds;
                    if ((vgb[3] - vgb[1]) > 180) {{
                        vocabStartPageOff = vpi2;
                        vocabStartPageRef = doc.pages[vpi2];
                        break;
                    }}
                }} catch(e) {{}}
            }}
            if (vocabStartPageOff < 999) break;
        }}
    }}
    log("vocabStartPageOff=" + vocabStartPageOff);

    // ========================================
    // 5. 프레임 바운드 상수
    // ========================================
    var evenBounds = [[27,18,153,101],[153,18,279,101],[27,105,153,188],[153,105,279,188]];
    var oddBounds  = [[27,22,153,105],[153,22,279,105],[27,109,153,192],[153,109,279,192]];

    // ========================================
    // 5a. 페이지 순서 보정 — 프레임 바운드 기반 even/odd 불일치 감지
    // 템플릿에서 페이지 순서가 뒤바뀐 경우 (예: page 10↔11) 자동 교정
    // ========================================
    var swapped = 0;
    for (var spi = 1; spi < doc.pages.length - 1; spi++) {{
        var curPg = doc.pages[spi];
        var nxtPg = doc.pages[spi + 1];
        // 현재 페이지의 프레임 바운드 top 값 확인
        var curTop = -1, nxtTop = -1;
        for (var sf = 0; sf < curPg.textFrames.length; sf++) {{
            var sgb = curPg.textFrames[sf].geometricBounds;
            if ((sgb[2] - sgb[0]) > 50 && (sgb[3] - sgb[1]) > 50) {{
                curTop = sgb[0]; break;
            }}
        }}
        for (var sf2 = 0; sf2 < nxtPg.textFrames.length; sf2++) {{
            var sgb2 = nxtPg.textFrames[sf2].geometricBounds;
            if ((sgb2[2] - sgb2[0]) > 50 && (sgb2[3] - sgb2[1]) > 50) {{
                nxtTop = sgb2[0]; break;
            }}
        }}
        if (curTop < 0 || nxtTop < 0) continue;
        // even 페이지(짝수 offset)는 top~27, odd 페이지(홀수 offset)는 top~22
        // 현재 페이지가 even인데 top이 odd 패턴(~22)이면 뒤바뀜
        var curIsEvenOff = (curPg.documentOffset % 2 === 0);
        var curMatchesEven = (Math.abs(curTop - 27) < 3);
        var curMatchesOdd = (Math.abs(curTop - 22) < 3);
        var nxtIsEvenOff = (nxtPg.documentOffset % 2 === 0);
        var nxtMatchesEven = (Math.abs(nxtTop - 27) < 3);
        var nxtMatchesOdd = (Math.abs(nxtTop - 22) < 3);

        if (curIsEvenOff && curMatchesOdd && !curMatchesEven &&
            nxtIsEvenOff === false && nxtMatchesEven && !nxtMatchesOdd) {{
            // even offset에 odd 바운드, odd offset에 even 바운드 → 교환 필요
            nxtPg.move(LocationOptions.BEFORE, curPg);
            log("swapPages " + (spi) + "<->" + (spi+1));
            swapped++;
            break;
        }}
    }}
    if (swapped > 0) log("pageSwaps=" + swapped);

    // ========================================
    // 6. 프레임 수집 함수 — 4프레임 레이아웃 바운드 매칭
    // ========================================
    // 허용 바운드: even/odd 페이지 4프레임 패턴에 맞는 프레임만 수집
    // 주의: evenBounds/oddBounds는 page-local 좌표. RIGHT 페이지의 geometricBounds는
    //       spread 좌표이므로 비교 전에 page.bounds[1] (xOff)를 빼서 local로 정규화해야 함.
    function matchesBounds(gb, pg) {{
        var tol = 8;
        var xOff = 0;
        try {{ xOff = pg.bounds[1]; }} catch(e) {{}}
        var lx1 = gb[1] - xOff;
        var lx2 = gb[3] - xOff;
        var ly1 = gb[0];
        var ly2 = gb[2];
        var ref = (pg.documentOffset % 2 === 0) ? oddBounds : evenBounds;
        for (var ri = 0; ri < ref.length; ri++) {{
            if (Math.abs(ly1 - ref[ri][0]) < tol &&
                Math.abs(lx1 - ref[ri][1]) < tol &&
                Math.abs(ly2 - ref[ri][2]) < tol &&
                Math.abs(lx2 - ref[ri][3]) < tol) {{
                return true;
            }}
        }}
        return false;
    }}

    function collectFrames(startOff, endOff) {{
        var result = [];
        for (var pi = startOff; pi <= endOff && pi < doc.pages.length; pi++) {{
            var pg = doc.pages[pi];
            var pgOff = pg.documentOffset;
            var pgXOff = 0;
            try {{ pgXOff = pg.bounds[1]; }} catch(e) {{}}
            var pgFrames = [];
            for (var fi = pg.textFrames.length - 1; fi >= 0; fi--) {{
                var tf = pg.textFrames[fi];
                var gb = tf.geometricBounds;
                if (gb[0] < 0) continue;
                // 4프레임 레이아웃 바운드 매칭 (page-local 좌표 비교)
                if (!matchesBounds(gb, pg)) continue;
                // col 판별은 page-local X로. RIGHT 페이지의 spread X=232+를
                // local X=22+로 변환해야 col 0/1 구분이 정상 작동.
                var localX1 = gb[1] - pgXOff;
                pgFrames.push({{
                    frame: tf,
                    pageOff: pi,
                    isTop: gb[0] < 100,
                    bounds: [gb[0], gb[1], gb[2], gb[3]],
                    col: (localX1 < 100) ? 0 : 1
                }});
            }}
            pgFrames.sort(function(a, b) {{
                if (a.col !== b.col) return a.col - b.col;
                if (a.isTop !== b.isTop) return a.isTop ? -1 : 1;
                return 0;
            }});
            for (var j = 0; j < pgFrames.length; j++) {{
                result.push(pgFrames[j]);
            }}
        }}
        return result;
    }}

    // ========================================
    // 7. 새 페이지 추가 함수
    // ========================================
    // 새 페이지 추가 — pages.add(AFTER, lastSectionPage)로 페이지 생성 + 4개 본문 프레임 직접 추가
    // AFTER 방식을 사용해야 offset이 연속적으로 증가하며 spread 경계 문제 회피
    // beforePageRef는 레거시 호환용 — 이 함수는 frames 배열의 마지막 페이지를 기준으로 AFTER 삽입
    // 마지막으로 추가한 overflow 페이지 캐시 (섹션별)
    var _lastAddedPage = null;

    function addFramePage(beforePageRef, frames) {{
        var prevCount = doc.pages.length;
        var newPage = null;

        // anchor 우선순위:
        // 1) 이전 호출에서 추가한 페이지 (연속 순차 추가 보장)
        // 2) beforePageRef 직전 페이지 (첫 호출 시)
        // 3) frames 마지막 프레임의 페이지 (폴백)
        var anchorPage = null;
        if (_lastAddedPage && _lastAddedPage.isValid) {{
            anchorPage = _lastAddedPage;
        }}
        if (!anchorPage && beforePageRef && beforePageRef.isValid) {{
            var refOff2 = beforePageRef.documentOffset;
            if (refOff2 > 0) {{
                try {{ anchorPage = doc.pages[refOff2 - 1]; }} catch(e) {{}}
            }}
        }}
        if ((!anchorPage || !anchorPage.isValid) && frames && frames.length > 0) {{
            try {{ anchorPage = frames[frames.length - 1].frame.parentPage; }} catch(e) {{}}
        }}

        try {{
            if (anchorPage && anchorPage.isValid) {{
                newPage = doc.pages.add(LocationOptions.AFTER, anchorPage);
            }} else {{
                newPage = doc.pages.add();
            }}
        }} catch(e) {{
            log("addFramePage pages.add err: " + e.message);
        }}
        if (!newPage || doc.pages.length === prevCount) {{
            log("addFramePage FAILED prevCount=" + prevCount);
            return null;
        }}

        // 마스터 페이지는 anchorPage와 동일하게 적용 (같은 섹션에 속하므로)
        try {{
            if (anchorPage && anchorPage.isValid) {{
                var srcM = anchorPage.appliedMaster;
                if (srcM && srcM.isValid) {{
                    newPage.appliedMaster = srcM;
                }}
            }}
        }} catch(e) {{}}

        // 새 페이지 offset 기준으로 4개 본문 프레임 직접 생성
        // pgOff가 even(짝수)이면 oddBounds, odd(홀수)이면 evenBounds
        var pgOff = newPage.documentOffset;
        var useBounds = (pgOff % 2 === 0) ? oddBounds : evenBounds;
        // textFrames.add는 spread 좌표계를 사용 → 페이지가 spread의 오른쪽에 있으면
        // xOff를 더해야 프레임이 해당 페이지 위에 정확히 배치된다.
        var xOff = newPage.bounds[1];

        var newFrames = [];
        for (var bi = 0; bi < useBounds.length; bi++) {{
            try {{
                var nb = [useBounds[bi][0], useBounds[bi][1] + xOff, useBounds[bi][2], useBounds[bi][3] + xOff];
                var newTF = newPage.textFrames.add({{geometricBounds: nb}});
                // col 판별은 page-local 좌표(useBounds[bi][1])로 해야 한다. xOff 포함된 nb[1]을 쓰면
                // 오른쪽 페이지에서 모든 프레임이 col=1이 되어 정렬이 망가진다.
                newFrames.push({{
                    frame: newTF,
                    pageOff: pgOff,
                    isTop: nb[0] < 100,
                    bounds: [nb[0], nb[1], nb[2], nb[3]],
                    col: (useBounds[bi][1] < 100) ? 0 : 1
                }});
            }} catch(e) {{
                log("addFrame err: " + e.message);
            }}
        }}
        newFrames.sort(function(a, b) {{
            if (a.col !== b.col) return a.col - b.col;
            if (a.isTop !== b.isTop) return a.isTop ? -1 : 1;
            return 0;
        }});
        for (var ni = 0; ni < newFrames.length; ni++) {{
            frames.push(newFrames[ni]);
        }}
        var prevMaster = "";
        try {{ prevMaster = newPage.appliedMaster ? newPage.appliedMaster.name : "null"; }} catch(e) {{}}
        log("addedPage off=" + pgOff + " docPages=" + doc.pages.length + " master=" + prevMaster + " frames=" + newFrames.length);
        _lastAddedPage = newPage;
        return newPage;
    }}

    // ----------------------------------------
    // 8-pre. 경미 오버플로우 in-place 해소 (A단계 — 프레임 이동/흡수/페이지추가 없음)
    //   지문 문단 자간(tracking) 미세 축소 → 그래도 넘치면 행간(leading) 약간 축소.
    //   가독성 보호: tracking 최저 -25, leading -0.5pt까지만. 헤더 문단([기본 단락])은 보존.
    //   해소되면 true. (3~4줄+ 초과 = 흡수/이동/페이지추가는 B단계에서 별도 처리)
    // ----------------------------------------
    function isHeaderPara(p) {{
        try {{
            var sn = p.appliedParagraphStyle.name;
            return (sn === "[기본 단락]" || sn === "[Basic Paragraph]");
        }} catch(e) {{ return false; }}
    }}
    function tryShrinkFit(story) {{
        try {{ story.recompose(); }} catch(e) {{}}
        if (!story.overflows) return true;
        var steps = [-10, -15, -20, -25];
        for (var t = 0; t < steps.length; t++) {{
            var paras = story.paragraphs;
            for (var p = 0; p < paras.length; p++) {{
                if (isHeaderPara(paras[p])) continue;
                try {{ paras[p].tracking = steps[t]; }} catch(e) {{}}
            }}
            try {{ story.recompose(); }} catch(e) {{}}
            if (!story.overflows) return true;
        }}
        // 자간만으로 부족 → 지문 문단 행간 -0.5pt (숫자 leading만, autoleading 보존)
        var paras2 = story.paragraphs;
        for (var p2 = 0; p2 < paras2.length; p2++) {{
            if (isHeaderPara(paras2[p2])) continue;
            try {{
                var cl = paras2[p2].leading;
                if (typeof cl === "number" && cl > 5) paras2[p2].leading = cl - 0.5;
            }} catch(e) {{}}
        }}
        try {{ story.recompose(); }} catch(e) {{}}
        return !story.overflows;
    }}

    // ========================================
    // 8. 오버플로우 처리 함수
    // returns: true if block was placed, false if needs retry
    // side effect: may modify frames array (splice)
    // ========================================
    function handleOverflow(frames, frameIdx, section, blockIdx) {{
        var fi = frames[frameIdx];
        var frame = fi.frame;
        var story = frame.parentStory;

        // 내용 삽입·스타일 변경 직후 레이아웃 재계산 강제
        // (recompose 안 하면 실제론 fit되는데 overflow=true로 false-positive 판정됨)
        try {{ story.recompose(); }} catch(e) {{}}

        if (!story.overflows) return true;

        if (fi.isTop) {{
            // 상단 프레임 overflow: 배치 중엔 내용 유지. (흡수/이동은 후속 배치와 충돌 → 금지)
            // 자간/행간 shrink-fit은 배치·스타일·clearOverrides가 다 끝난 뒤 마지막 post-pass에서 적용한다
            // (clearOverrides(CHARACTER_ONLY)가 배치 중 적용한 tracking/leading override를 지우기 때문).
            log(section + " topOv_keepContent block=" + blockIdx);
            return true;
        }} else {{
            // 하단 프레임 -> 확장 시도 -> 실패시 다음 상단으로 이동
            var pg = frame.parentPage;
            var pageBottom = 279;
            try {{ pageBottom = pg.bounds[2]; }} catch(e) {{}}
            var origBounds = [fi.bounds[0], fi.bounds[1], fi.bounds[2], fi.bounds[3]];
            var expandedBottom = pageBottom - 3;

            if (expandedBottom > fi.bounds[2]) {{
                frame.geometricBounds = [fi.bounds[0], fi.bounds[1], expandedBottom, fi.bounds[3]];
                if (!story.overflows) {{
                    log(section + " expandBottom block=" + blockIdx);
                    return true;
                }}
            }}

            // 확장해도 넘침 -> 내용 유지 (자간/행간 shrink-fit은 마지막 post-pass에서 적용)
            log(section + " bottomOv_keepContent block=" + blockIdx);
            return true;
        }}
    }}

    // ========================================
    // 9. 문장배열 배치
    // ========================================
    app.doScript(function() {{
        // 문장삽입 블록이 있으면 그 시작 페이지 직전까지만 문장배열로 사용.
        // 없으면(고3 등) 중요어휘 시작 페이지 직전까지 확장하여 insertStartPageOff 잘못 감지로
        // 문장배열 영역이 축소되는 문제 방지.
        var arrEndOff;
        if (insertBlocks.length > 0 && insertStartPageOff > 0) {{
            arrEndOff = insertStartPageOff - 1;
        }} else if (vocabStartPageOff > 0 && vocabStartPageOff < 999) {{
            arrEndOff = vocabStartPageOff - 1;
        }} else {{
            arrEndOff = doc.pages.length - 1;
        }}
        var arrFrames = collectFrames(1, arrEndOff);
        log("arrFrames=" + arrFrames.length + " for pages 1~" + arrEndOff);

        // 배치 전 모든 arrFrames의 문자 스타일을 [없음]으로 초기화
        // (템플릿 후반 프레임에 남아있던 "4. 영작 보기 메뉴" 등의 큰 폰트 스타일이
        //  짧은 지문도 overflow로 판정시켜 expandTop/expandBottom을 유발하던 문제 방지)
        var noneCSInit = doc.characterStyles[0];
        for (var riInit = 0; riInit < arrFrames.length; riInit++) {{
            try {{
                var rstoInit = arrFrames[riInit].frame.parentStory;
                if (rstoInit.characters.length > 0) {{
                    rstoInit.characters.everyItem().appliedCharacterStyle = noneCSInit;
                }}
            }} catch(e) {{}}
        }}

        // 새 페이지 삽입 기준: 문장삽입 있으면 그 앞, 없으면 vocab 앞
        // (insertStartPageRef만 쓰면 D-마스터 잘못 감지 시 중간에 페이지가 끼어들어 순서 엉킴)
        var arrInsertRef = (insertBlocks.length > 0 && insertStartPageRef)
            ? insertStartPageRef
            : (vocabStartPageRef || insertStartPageRef);

        _lastAddedPage = null; // 섹션 시작 시 캐시 리셋
        var arrIdx = 0;
        for (var b = 0; b < blocks.length; b++) {{
            // 프레임 부족시 새 페이지 추가
            if (arrIdx >= arrFrames.length) {{
                addFramePage(arrInsertRef, arrFrames);
            }}
            if (arrIdx >= arrFrames.length) {{
                log("arr NO_FRAME block=" + b);
                break;
            }}

            var fi = arrFrames[arrIdx];
            var frame = fi.frame;
            var story = frame.parentStory;
            var block = blocks[b];
            var items = block.items || [];
            var hdr = block.header || ("\\uC9C0\\uBB38 " + (b+1));

            // 내용 삽입
            story.contents = "";
            story.insertionPoints[-1].contents = hdr + "\\r";
            // 고3 분석편: 헤더 다음에 원문(passage) 삽입
            var passageText = block.passage || "";
            if (passageText) {{
                story.insertionPoints[-1].contents = passageText + "\\r";
            }}
            for (var c = 0; c < items.length; c++) {{
                story.insertionPoints[-1].contents = items[c] + "\\r";
            }}
            story.insertionPoints[-1].contents = "\\r";
            story.insertionPoints[-1].contents = "\\uFF1E \\r";

            // 문자 스타일 [없음] 초기화 — addFramePage로 추가된 새 프레임도 포함
            // (이전 프레임 또는 기본값의 큰 폰트 character style이 overflow 오판정 유발 방지)
            try {{ story.characters.everyItem().appliedCharacterStyle = doc.characterStyles[0]; }} catch(e) {{}}

            // 스타일 적용
            var p = story.paragraphs.everyItem().getElements();
            for (var pi = 0; pi < p.length; pi++) {{
                var t = (p[pi].contents || "").replace(/\\r$/, "");
                if (t === "") {{
                    if (psGrabEnd) p[pi].appliedParagraphStyle = psGrabEnd;
                }} else if (t.indexOf("\\uFF1E") === 0) {{
                    if (psBasic) p[pi].appliedParagraphStyle = psBasic;
                    if (csArrow) {{
                        try {{ p[pi].characters.everyItem().appliedCharacterStyle = csArrow; }} catch(e) {{}}
                        try {{ p[pi].characters[1].underline = false; }} catch(e) {{}}
                    }}
                }} else if (/^\\s*\\([A-Z]\\)/.test(t)) {{
                    if (psGrab) p[pi].appliedParagraphStyle = psGrab;
                }} else if (pi === 0) {{
                    // 첫 단락 = 헤더
                    if (psHeader) p[pi].appliedParagraphStyle = psHeader;
                }} else {{
                    // 헤더 이후 "(A)" 패턴 아닌 텍스트 = 지문/passage → C1_문장 배열 하단
                    // (리딩파워 non-Example 워크북의 '문장 배열 그랩' 스타일 첫 지문 문장 대응)
                    if (psPassage) p[pi].appliedParagraphStyle = psPassage;
                    else if (psHeader) p[pi].appliedParagraphStyle = psHeader;
                }}
            }}

            // 화살표 앵커 삽입
            if (arrowSrc) {{
                p = story.paragraphs.everyItem().getElements();
                for (var api = p.length - 1; api >= 0; api--) {{
                    var at = (p[api].contents || "").replace(/\\r$/, "");
                    if (at.indexOf("\\uFF1E") === 0) {{
                        try {{
                            var srcItems = arrowSrc.allPageItems;
                            for (var ai2 = 0; ai2 < srcItems.length; ai2++) {{
                                if (srcItems[ai2].constructor.name !== "GraphicLine") continue;
                                try {{ srcItems[ai2].locked = false; }} catch(e) {{}}
                                var clone = srcItems[ai2].duplicate();
                                var ip = p[api].insertionPoints[-2];
                                clone.anchoredObjectSettings.insertAnchoredObject(
                                    ip, AnchorPosition.INLINE_POSITION
                                );
                            }}
                        }} catch(e) {{
                            log("arrowErr block=" + b + " " + e.message);
                        }}
                    }}
                }}
            }}

            // 오버플로우 처리
            var placed = handleOverflow(arrFrames, arrIdx, "arr", b);
            if (!placed) {{
                // 하단 프레임 넘침 -> 다음 상단 프레임으로 이동
                var nextTop = -1;
                for (var ni = arrIdx + 1; ni < arrFrames.length; ni++) {{
                    if (arrFrames[ni].isTop) {{ nextTop = ni; break; }}
                }}
                if (nextTop < 0) {{
                    addFramePage(arrInsertRef, arrFrames);
                    for (var ni2 = arrIdx + 1; ni2 < arrFrames.length; ni2++) {{
                        if (arrFrames[ni2].isTop) {{ nextTop = ni2; break; }}
                    }}
                }}
                if (nextTop >= 0) {{
                    arrIdx = nextTop;
                    b--;
                    continue;
                }} else {{
                    log("arr CANNOT_PLACE block=" + b);
                }}
            }}
            arrIdx++;
        }}

        // 문자 오버라이드 제거 (GREP 스타일 작동 보장) + 화살표 ＞ Paper 처리
        // 순서: clearOverrides 먼저 → 화살표 Paper 나중 (clearOverrides가 Paper 덮어쓰는 것 방지)
        var paperSw = doc.swatches.itemByName("Paper");
        if (!paperSw || !paperSw.isValid) {{
            // 한국어 InDesign fallback
            try {{ paperSw = doc.swatches.itemByName("[\\uC6A9\\uC9C0]"); }} catch(e) {{}}
        }}
        log("paperSw valid=" + (paperSw && paperSw.isValid));
        // 지문번호 charStyle 찾기 (Gateway 헤더 수동 적용용 — GREP 패턴이 숫자만 처리하므로)
        var csArrPassNum = null;
        var allCSarr = doc.allCharacterStyles;
        for (var csai = 0; csai < allCSarr.length; csai++) {{
            if (allCSarr[csai].name === "\\uC9C0\\uBB38\\uBC88\\uD638") {{ csArrPassNum = allCSarr[csai]; break; }}
        }}
        var arrPaperApplied = 0;
        var arrGwApplied = 0;
        var noneCS = doc.characterStyles[0];  // [없음] 문자 스타일
        for (var bci = 0; bci < arrIdx && bci < arrFrames.length; bci++) {{
            try {{
                var bcSt = arrFrames[bci].frame.parentStory;
                // STEP 1: 모든 문자의 character style을 [없음]으로 초기화
                // (기존 템플릿 프레임에서 상속된 "4. 영작 보기 메뉴" 같은 문자 스타일이 Paper 색을 가져와 헤더 흰색으로 만드는 문제 방지)
                try {{ bcSt.characters.everyItem().appliedCharacterStyle = noneCS; }} catch(e) {{}}
                // STEP 2: 문자 오버라이드 제거 → 단락스타일의 fillColor(Black) + GREP 스타일 정상 작동
                bcSt.paragraphs.everyItem().clearOverrides(OverrideType.CHARACTER_ONLY);
                // STEP 3: 화살표 ＞ 줄은 csArrow + Paper(흰색)로 덮어쓰기 (clearOverrides 이후에 적용)
                var bcP = bcSt.paragraphs.everyItem().getElements();
                for (var rpi = 0; rpi < bcP.length; rpi++) {{
                    var rpt = (bcP[rpi].contents || "");
                    if (rpt.indexOf("\\uFF1E") === 0) {{
                        try {{
                            if (csArrow) {{
                                bcP[rpi].characters.everyItem().appliedCharacterStyle = csArrow;
                            }}
                            if (paperSw && paperSw.isValid) {{
                                bcP[rpi].characters.everyItem().fillColor = paperSw;
                                arrPaperApplied++;
                            }}
                            // 화살표 뒤 공백의 밑줄 해제 (csArrow의 underline=true가 상속되는 문제 방지)
                            try {{ bcP[rpi].characters[1].underline = false; }} catch(e) {{}}
                        }} catch(e) {{}}
                    }}
                    // "N강 Gateway" 헤더 — GREP ^.+\\d(?=\\r) 패턴이 Gateway(비숫자)를 못 잡음.
                    // "3강 01"과 동일한 외양을 위해 단락 전체에 "지문번호" charStyle 적용.
                    // 추가: "교과서N과 딥러닝" 헤더(딥러닝 워크북) — 동일 처리.
                    if (csArrPassNum) {{
                        var rptClean = rpt.replace(/[\\r\\n]+$/, "");
                        if (/^(?:\\d+\\uAC15|test\\d+)\\s+Gateway$/i.test(rptClean)
                            || /^\\uAD50\\uACFC\\uC11C\\S+?\\s+\\uB525\\uB7EC\\uB2DD$/.test(rptClean)) {{
                            try {{
                                for (var gci = 0; gci < rptClean.length; gci++) {{
                                    bcP[rpi].characters[gci].appliedCharacterStyle = csArrPassNum;
                                }}
                                arrGwApplied++;
                            }} catch(egw) {{}}
                        }}
                    }}
                }}
            }} catch(e) {{}}
        }}
        log("arr Gateway charStyle applied=" + arrGwApplied);
        // 문장배열 페이지에 잘못된 D-마스터가 적용된 경우 A-chapter1으로 교정
        // (템플릿에 D-마스터 페이지가 섞여 있어 content는 맞지만 상단 섹션 라벨이
        //  "중요 어휘 / 요약문"으로 잘못 표시되는 문제 방지)
        try {{
            var aChap = doc.masterSpreads.itemByName("A-chapter1");
            if (aChap && aChap.isValid) {{
                var arrPagesSeen = {{}};
                var arrMasterFixed = 0;
                for (var mbi = 0; mbi < arrIdx && mbi < arrFrames.length; mbi++) {{
                    try {{
                        var mbPg = arrFrames[mbi].frame.parentPage;
                        if (!mbPg) continue;
                        var pof = mbPg.documentOffset;
                        if (arrPagesSeen[pof]) continue;
                        arrPagesSeen[pof] = true;
                        var curM = mbPg.appliedMaster;
                        if (curM && curM.name.indexOf("D-") === 0) {{
                            mbPg.appliedMaster = aChap;
                            arrMasterFixed++;
                        }}
                    }} catch(e) {{}}
                }}
                if (arrMasterFixed > 0) log("arr masterFix D→A count=" + arrMasterFixed);
            }}
        }} catch(e) {{}}

        log("arr placed=" + blocks.length + " usedFrames=" + arrIdx + " arrPaperApplied=" + arrPaperApplied);
    }}, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "Vol1_arr");

    // ========================================
    // 10. 문장삽입 배치
    // ========================================
    if (insertBlocks.length > 0 && insertStartPageOff > 0) {{

        app.doScript(function() {{
            // Arr 섹션에서 새 페이지가 추가되었을 수 있음 — 섹션 재탐지
            // D-마스터 또는 "문장 삽입/순서" 라벨이 있는 페이지가 ins 시작
            var newInsOff = -1;
            var newInsRef = null;
            for (var rpi = 2; rpi < doc.pages.length; rpi++) {{
                try {{
                    var rpg = doc.pages[rpi];
                    var rm = rpg.appliedMaster;
                    if (rm && rm.name.indexOf("D-") === 0) {{
                        newInsOff = rpi;
                        newInsRef = rpg;
                        break;
                    }}
                }} catch(e) {{}}
            }}
            if (newInsOff < 0) {{
                // 폴백: "문장 삽입" 라벨 찾기
                for (var rpi2 = 2; rpi2 < doc.pages.length; rpi2++) {{
                    var rtfs = doc.pages[rpi2].textFrames;
                    for (var rti = 0; rti < rtfs.length; rti++) {{
                        try {{
                            var rc = (rtfs[rti].contents || "");
                            if (rc.indexOf("\\uC0BD\\uC785") >= 0 || rc.indexOf("\\uC21C\\uC11C") >= 0) {{
                                newInsOff = rpi2;
                                newInsRef = doc.pages[rpi2];
                                break;
                            }}
                        }} catch(e) {{}}
                    }}
                    if (newInsOff >= 0) break;
                }}
            }}
            if (newInsOff >= 0 && newInsOff !== insertStartPageOff) {{
                log("insertStartPageOff re-detected: " + insertStartPageOff + " -> " + newInsOff);
                insertStartPageOff = newInsOff;
                insertStartPageRef = newInsRef;
            }}

            // summaryStartPageRef, vocabStartPageRef도 재탐지 (섹션 라벨 기반)
            var newVocabOff = 999;
            var newVocabRef = null;
            for (var vrpi = insertStartPageOff + 1; vrpi < doc.pages.length; vrpi++) {{
                var vrtfs = doc.pages[vrpi].textFrames;
                for (var vrti = 0; vrti < vrtfs.length; vrti++) {{
                    try {{
                        var vrc = (vrtfs[vrti].contents || "");
                        if (vrc.indexOf("\\uC5B4\\uD718") >= 0 || vrc.indexOf("\\uC911\\uC694") >= 0) {{
                            newVocabOff = vrpi;
                            newVocabRef = doc.pages[vrpi];
                            break;
                        }}
                    }} catch(e) {{}}
                }}
                if (newVocabOff < 999) break;
            }}
            if (newVocabOff < 999) {{
                if (newVocabOff !== vocabStartPageOff) {{
                    log("vocabStartPageOff re-detected: " + vocabStartPageOff + " -> " + newVocabOff);
                }}
                vocabStartPageOff = newVocabOff;
                vocabStartPageRef = newVocabRef;
            }}

            // 내용요약 시작 전까지, 없으면 중요어휘 시작 전까지
            // 주의: arr 섹션이 새 페이지를 추가하면 stale integer offset(summaryStartPageOff 등)은
            // 더 이상 실제 페이지 위치를 가리키지 않는다. page ref는 자동으로 shift되므로
            // ref.documentOffset로 재계산해야 inverted range(예: 19~18)로 collectFrames가 0이 되는
            // 회귀를 막는다. ref가 insertStartPageOff 이하면 무시(stale 판정 방지).
            var insEndOff = doc.pages.length - 1;
            var _sumOffCur = -1;
            if (summaryStartPageRef && summaryStartPageRef.isValid) {{
                try {{ _sumOffCur = summaryStartPageRef.documentOffset; }} catch(eSm) {{}}
            }}
            var _vocOffCur = -1;
            if (vocabStartPageRef && vocabStartPageRef.isValid) {{
                try {{ _vocOffCur = vocabStartPageRef.documentOffset; }} catch(eVm) {{}}
            }}
            if (_sumOffCur > insertStartPageOff) {{
                insEndOff = _sumOffCur - 1;
            }} else if (_vocOffCur > insertStartPageOff) {{
                insEndOff = _vocOffCur - 1;
            }} else if (summaryStartPageOff < 999 && summaryStartPageOff > insertStartPageOff) {{
                insEndOff = summaryStartPageOff - 1;
            }} else if (vocabStartPageOff < 999 && vocabStartPageOff > insertStartPageOff) {{
                insEndOff = vocabStartPageOff - 1;
            }}
            var insFrames = collectFrames(insertStartPageOff, insEndOff);
            log("insFrames=" + insFrames.length + " for pages " + insertStartPageOff + "~" + insEndOff);

            // 모든 insFrames의 텍스트 색상을 Black으로 초기화 (Paper 상속 방지)
            // Vol1_arr에서 화살표 ＞에 Paper 색을 적용했는데, 그 색상이 ins 프레임에도 상속되는 문제 방지
            var blackSw = null;
            try {{ blackSw = doc.swatches.itemByName("Black"); }} catch(e) {{}}
            if (!blackSw || !blackSw.isValid) {{
                try {{ blackSw = doc.swatches.itemByName("[\\uAC80\\uC815]"); }} catch(e) {{}}
            }}
            var noneCSIns = doc.characterStyles[0];
            for (var riIns = 0; riIns < insFrames.length; riIns++) {{
                try {{
                    var rstoIns = insFrames[riIns].frame.parentStory;
                    if (rstoIns.characters.length > 0) {{
                        rstoIns.characters.everyItem().appliedCharacterStyle = noneCSIns;
                    }}
                    // 문자 레벨 fillColor override를 지워 단락 스타일 기본값 복원
                    try {{ rstoIns.paragraphs.everyItem().clearOverrides(OverrideType.CHARACTER_ONLY); }} catch(e) {{}}
                    // textFrame 기본 fillColor를 Black으로 (상속된 Paper 방지)
                    if (blackSw && blackSw.isValid) {{
                        try {{
                            var tfIns = insFrames[riIns].frame;
                            if (tfIns.characters.length > 0) {{
                                tfIns.characters.everyItem().fillColor = blackSw;
                            }}
                        }} catch(e) {{}}
                    }}
                }} catch(e) {{}}
            }}

            _lastAddedPage = null; // 섹션 시작 시 캐시 리셋
            var insIdx = 0;
            for (var b = 0; b < insertBlocks.length; b++) {{
                if (insIdx >= insFrames.length) {{
                    addFramePage(summaryStartPageRef || vocabStartPageRef, insFrames);
                }}
                if (insIdx >= insFrames.length) {{
                    log("ins NO_FRAME block=" + b);
                    break;
                }}

                var fi = insFrames[insIdx];
                var frame = fi.frame;
                var story = frame.parentStory;
                var block = insertBlocks[b];
                var hdr = block.header || ("\\uC9C0\\uBB38 " + (b+1));
                var paras = block.paras || [];

                // 헤더 마커 단락 제거: {{본문N}}, {{N}}, {{N~M}}, {{~N}}, {{Read More}}, {{Further Reading}}, {{FR}}
                // 여러 마커가 한 단락에 연쇄된 경우도 처리 (예: "{{41}}{{~42}}", "{{20}}{{21}}")
                var _filteredParas = [];
                var _markerChain = /^(?:[\{{\[](?:\d+(?:[~\-]\d+)?|~\d+|\uBCF8\uBB38\d+|Read\s*More|Further\s*Reading|FR)[\}}\]])+$/i;
                for (var _fi = 0; _fi < paras.length; _fi++) {{
                    var _fp = paras[_fi];
                    var _ft = "";
                    if (typeof _fp === "string") _ft = _fp;
                    else if (_fp && _fp.text) _ft = _fp.text;
                    // 공백/탭/U+FFFC 등 불가시 문자 제거 후 비교
                    var _fnsp = _ft.replace(/[\s\uFFFC]/g, "");
                    if (!_fnsp) continue;
                    if (_markerChain.test(_fnsp)) continue;
                    _filteredParas.push(_fp);
                }}
                paras = _filteredParas;

                // 새 프레임의 색상을 Black으로 초기화 (addFramePage로 추가된 프레임도 포함)
                if (blackSw && blackSw.isValid && story.characters.length > 0) {{
                    try {{ story.characters.everyItem().fillColor = blackSw; }} catch(e) {{}}
                }}

                // 내용 삽입 — paras는 dict {{text, style}} 또는 문자열(모의고사 동기화용)
                story.contents = "";
                story.insertionPoints[-1].contents = hdr + "\\r";
                for (var pi2 = 0; pi2 < paras.length; pi2++) {{
                    var _pItem = paras[pi2];
                    var txt = "";
                    if (typeof _pItem === "string") {{
                        txt = _pItem;
                    }} else if (_pItem && _pItem.text) {{
                        txt = _pItem.text;
                    }}
                    story.insertionPoints[-1].contents = txt + "\\r";
                }}

                // 스타일 적용
                var ip = story.paragraphs.everyItem().getElements();
                var paraIdx = 0;

                // 헤더 단락 — 지문번호 스타일(psHeader) 적용 (psBasic보다 우선)
                if (paraIdx < ip.length) {{
                    if (psHeader) ip[paraIdx].appliedParagraphStyle = psHeader;
                    else if (psBasic) ip[paraIdx].appliedParagraphStyle = psBasic;
                    paraIdx++;
                }}

                // 블록 내 역할 판정 — 발문/첫 내용(박스)/나머지(지문) 구분
                // 사용자 규칙: 첫 비-발문 단락 = psInsertBox(문장 배열 하단, 음영),
                //              나머지 = psInsertPassage(문장 배열 하단 지문),
                //              발문("주어진 문장", "이어질 문장", "적절한 순서") = psInsertQ(문장 배열 하단 문제)
                var _promptRE = /\\uC8FC\\uC5B4\\uC9C4\\s*\\uBB38\\uC7A5|\\uC774\\uC5B4\\uC9C8\\s*\\uBB38\\uC7A5|\\uC801\\uC808\\uD55C\\s*\\uC21C\\uC11C/;
                var _firstContentIdx = -1;
                for (var _bi = 0; _bi < paras.length; _bi++) {{
                    var _pbp = paras[_bi];
                    var _pbt = "";
                    if (typeof _pbp === "string") _pbt = _pbp;
                    else if (_pbp && _pbp.text) _pbt = _pbp.text;
                    _pbt = _pbt.replace(/^[\\s\\uFFFC]+|[\\s\\uFFFC]+$/g, "");
                    if (!_pbt) continue;
                    if (_promptRE.test(_pbt)) continue;
                    _firstContentIdx = _bi;
                    break;
                }}

                // 내용 단락 스타일 적용
                for (var pi3 = 0; pi3 < paras.length; pi3++) {{
                    if (paraIdx >= ip.length) break;
                    var _pItem3 = paras[pi3];
                    var srcStyle = "";
                    if (typeof _pItem3 !== "string" && _pItem3 && _pItem3.style) {{
                        srcStyle = _pItem3.style;
                    }}
                    var _txt3 = (ip[paraIdx].contents || "").replace(/\\r$/, "").replace(/^[\\s\\uFFFC]+|[\\s\\uFFFC]+$/g, "");

                    // 고3 C1_ 스타일 원본 (분석편): 기존 매핑 유지
                    if (srcStyle === "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8") {{
                        if (psInsertBox) ip[paraIdx].appliedParagraphStyle = psInsertBox;
                    }} else if (srcStyle === "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8 \\uC9C0\\uBB38") {{
                        if (psInsertPassage) ip[paraIdx].appliedParagraphStyle = psInsertPassage;
                        else if (psInsertQ) ip[paraIdx].appliedParagraphStyle = psInsertQ;
                    }} else if (srcStyle === "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4" || (srcStyle.indexOf("C1_") === 0 && srcStyle !== "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8")) {{
                        if (psInsertC1) ip[paraIdx].appliedParagraphStyle = psInsertC1;
                    }}
                    // 발문 — psInsertQ (문장 배열 하단 문제)
                    else if (_promptRE.test(_txt3)) {{
                        if (psInsertQ) ip[paraIdx].appliedParagraphStyle = psInsertQ;
                    }}
                    // 첫 내용 단락 — psInsertBox (문장 배열 하단, 음영)
                    else if (pi3 === _firstContentIdx) {{
                        if (psInsertBox) ip[paraIdx].appliedParagraphStyle = psInsertBox;
                    }}
                    // 나머지 — psInsertPassage (문장 배열 하단 지문)
                    else {{
                        if (psInsertPassage) ip[paraIdx].appliedParagraphStyle = psInsertPassage;
                        else if (psInsertQ) ip[paraIdx].appliedParagraphStyle = psInsertQ;
                    }}
                    paraIdx++;
                }}

                // 오버플로우 처리
                var placed = handleOverflow(insFrames, insIdx, "ins", b);
                if (!placed) {{
                    // 현재 Bottom frame이 부적합 → 비우고 삭제하고 다음 frame으로 순차 진행
                    // (건너뛴 frame에 나중 블록이 거꾸로 들어가 순서 꼬이는 문제 방지)
                    try {{ insFrames[insIdx].frame.parentStory.contents = ""; }} catch(eC) {{}}
                    try {{ insFrames[insIdx].frame.remove(); }} catch(eR) {{}}
                    insFrames.splice(insIdx, 1);
                    if (insIdx >= insFrames.length) {{
                        addFramePage(summaryStartPageRef || vocabStartPageRef, insFrames);
                    }}
                    if (insIdx < insFrames.length) {{
                        b--;
                        continue;
                    }} else {{
                        log("ins CANNOT_PLACE block=" + b);
                    }}
                }}
                insIdx++;
            }}

            // 배치 완료 후: 모든 사용된 ins 프레임에 Black 색상 재적용 (Paper 잔재 제거)
            var insBlackFixed = 0;
            // 지문번호 charStyle (문장삽입 헤더 비숫자 끝 보강용)
            var csInsPassNum = null;
            try {{
                var allCSins = doc.allCharacterStyles;
                for (var csii2 = 0; csii2 < allCSins.length; csii2++) {{
                    if (allCSins[csii2].name === "\\uC9C0\\uBB38\\uBC88\\uD638") {{ csInsPassNum = allCSins[csii2]; break; }}
                }}
            }} catch(eCsLk) {{}}
            var insGwApplied = 0;
            for (var bIns = 0; bIns < insIdx && bIns < insFrames.length; bIns++) {{
                try {{
                    var bStIns = insFrames[bIns].frame.parentStory;
                    // STEP 1: 문자 스타일 [없음]으로 초기화
                    try {{ bStIns.characters.everyItem().appliedCharacterStyle = noneCSIns; }} catch(e) {{}}
                    // STEP 2: 문자 레벨 fillColor override 제거 → 단락 스타일 기본값(Black)으로 복원
                    try {{ bStIns.paragraphs.everyItem().clearOverrides(OverrideType.CHARACTER_ONLY); }} catch(e) {{}}
                    // STEP 3: Black으로 강제 (단락 스타일이 Paper여도 덮어씀)
                    if (blackSw && blackSw.isValid && bStIns.characters.length > 0) {{
                        bStIns.characters.everyItem().fillColor = blackSw;
                        insBlackFixed++;
                    }}
                    // STEP 4: "교과서N과 딥러닝" 헤더에 지문번호 charStyle 적용 (GREP ^.+\\d 패턴이 비숫자 끝 미적용)
                    if (csInsPassNum) {{
                        try {{
                            var insP = bStIns.paragraphs.everyItem().getElements();
                            for (var ipi3 = 0; ipi3 < insP.length; ipi3++) {{
                                var insPt = (insP[ipi3].contents || "").replace(/[\\r\\n]+$/, "");
                                if (/^\\uAD50\\uACFC\\uC11C\\S+?\\s+\\uB525\\uB7EC\\uB2DD$/.test(insPt)) {{
                                    try {{
                                        for (var iGci = 0; iGci < insPt.length; iGci++) {{
                                            insP[ipi3].characters[iGci].appliedCharacterStyle = csInsPassNum;
                                        }}
                                        insGwApplied++;
                                    }} catch(eIg) {{}}
                                }}
                            }}
                        }} catch(eIp) {{}}
                    }}
                }} catch(e) {{}}
            }}
            log("ins placed=" + insertBlocks.length + " usedFrames=" + insIdx + " insBlackFixed=" + insBlackFixed + " insDeepApplied=" + insGwApplied);
        }}, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "Vol1_ins");
    }} else {{
        log("insert=skip (no blocks or no section)");
        // 고3: 문장삽입/순서배열 섹션 잔재 제거
        if (IS_G3) {{
            // (a) 스프레드/페이스트보드에 "문장 삽입 / 순서 배열" 탭 프레임 삭제
            //     이 탭이 남아있으면 이후 페이지 마스터의 Running Header 변수가
            //     "문장 삽입 / 순서 배열"을 상속해서 p11~p15 상단에 노출됨
            var _delTabs = 0;
            for (var _tsi = doc.stories.length - 1; _tsi >= 0; _tsi--) {{
                try {{
                    var _tst = doc.stories[_tsi];
                    var _tcn = (_tst.contents || "").replace(/[\\r\\n]/g, " ");
                    if (_tcn.indexOf("\\uBB38\\uC7A5 \\uC0BD\\uC785") >= 0 &&
                        _tcn.indexOf("\\uC21C\\uC11C \\uBC30\\uC5F4") >= 0) {{
                        // 탭 프레임이 긴 TOC/인덱스 텍스트가 아닌 경우만 삭제 (길이 30자 이내)
                        if (_tcn.length <= 40) {{
                            var _tcs = _tst.textContainers;
                            for (var _tci = _tcs.length - 1; _tci >= 0; _tci--) {{
                                try {{ _tcs[_tci].remove(); _delTabs++; }} catch(eT) {{}}
                            }}
                        }}
                    }}
                }} catch(eS) {{}}
            }}
            if (_delTabs > 0) log("g3: deleted insert section tabs=" + _delTabs);

            // (b) 템플릿에 남은 D-마스터 헤더 페이지 삭제 (arr/vocab 컨텐츠 없는 것만)
            var _delIns = 0;
            for (var _dpi = doc.pages.length - 1; _dpi >= 1; _dpi--) {{
                try {{
                    var _dpg = doc.pages[_dpi];
                    var _dm = _dpg.appliedMaster;
                    if (!_dm) continue;
                    if (String(_dm.name).indexOf("D-") !== 0) continue;
                    // 이 페이지에 arr/vocab 컨텐츠(문장배열/중요어휘 단락 스타일)가 있으면 보존
                    var _dHasContent = false;
                    var _dItems = _dpg.allPageItems;
                    for (var _dii = 0; _dii < _dItems.length; _dii++) {{
                        if (_dItems[_dii].constructor.name !== "TextFrame") continue;
                        try {{
                            var _dps = _dItems[_dii].paragraphs[0].appliedParagraphStyle.name;
                            if (_dps.indexOf("\\uBB38\\uC7A5 \\uBC30\\uC5F4") >= 0 ||
                                _dps.indexOf("\\uC911\\uC694\\uC5B4\\uD718") >= 0 ||
                                _dps.indexOf("1. \\uBB38\\uC7A5") >= 0) {{
                                _dHasContent = true; break;
                            }}
                        }} catch(eDP) {{}}
                    }}
                    if (!_dHasContent) {{
                        try {{ _dpg.remove(); _delIns++; }} catch(eRm) {{}}
                    }}
                }} catch(eD) {{}}
            }}
            if (_delIns > 0) log("g3: deleted insert section pages=" + _delIns);
        }}
    }}

    // ========================================
    // 11. 중요어휘 오버플로우 처리
    // ========================================
    for (var vsi = 0; vsi < doc.stories.length; vsi++) {{
        var vst = doc.stories[vsi];
        if (!vst.overflows) continue;
        var vps = "";
        try {{ vps = vst.paragraphs[0].appliedParagraphStyle.name; }} catch(e) {{}}
        if (vps.indexOf("\\uC911\\uC694") === -1) continue;

        var vAdded = 0;
        while (vst.overflows && vAdded < 20) {{
            var vLastF = vst.textContainers[vst.textContainers.length - 1];
            var vNewPage = doc.pages.add();
            try {{
                var vMaster = vLastF.parentPage.appliedMaster;
                if (vMaster) vNewPage.appliedMaster = vMaster;
            }} catch(e) {{}}
            var vxOff = vNewPage.bounds[1];
            var vBounds = (vNewPage.documentOffset % 2 === 0) ?
                [27,22+vxOff,279,105+vxOff] : [27,18+vxOff,279,101+vxOff];
            var vNewTF = vNewPage.textFrames.add({{geometricBounds: vBounds}});
            vLastF.nextTextFrame = vNewTF;
            vAdded++;
        }}
        if (vAdded > 0) log("vocab_overflow_" + vsi + " addedPages=" + vAdded);
    }}

    // ========================================
    // 12. 빈 프레임/페이지 정리
    // ========================================
    // 중요어휘 시작 offset 재확인
    var vocabCurOff = 999;
    if (vocabStartPageRef) {{
        try {{ vocabCurOff = vocabStartPageRef.documentOffset; }} catch(e) {{}}
    }}

    var removedPages = 0;
    for (var rpi = doc.pages.length - 1; rpi >= 1; rpi--) {{
        var rpg = doc.pages[rpi];
        // 중요어휘/내용요약 영역 보호 — 콘텐츠 프레임이 아닌 페이지는 스킵
        var hasContentBounds = false;
        var rpItems2 = rpg.allPageItems;
        for (var ri2 = 0; ri2 < rpItems2.length; ri2++) {{
            if (rpItems2[ri2].constructor.name !== "TextFrame") continue;
            var rgb = rpItems2[ri2].geometricBounds;
            if (rgb[0] < 0 || rgb[1] < 0) continue;
            if (matchesBounds(rgb, rpg)) {{ hasContentBounds = true; break; }}
        }}
        if (!hasContentBounds) {{
            var isVocabFrame = false;
            for (var vci = 0; vci < rpItems2.length; vci++) {{
                if (rpItems2[vci].constructor.name !== "TextFrame") continue;
                try {{
                    var vcps = rpItems2[vci].paragraphs[0].appliedParagraphStyle;
                    if (vcps.name.indexOf("\\uC911\\uC694\\uC5B4\\uD718") >= 0) {{
                        isVocabFrame = true; break;
                    }}
                }} catch(e) {{}}
            }}
            if (isVocabFrame) continue;
        }}

        var hasContent = false;
        var rpgItems = rpg.allPageItems;
        for (var rii = 0; rii < rpgItems.length; rii++) {{
            if (rpgItems[rii].constructor.name === "TextFrame") {{
                var rgbb = rpgItems[rii].geometricBounds;
                if (rgbb[0] < 0 || rgbb[1] < 0 || (rgbb[2] - rgbb[0]) < 20) continue;
                try {{
                    var rtxt = rpgItems[rii].contents.replace(/[\\r\\n\\s\\u2028\\u2029]/g, "");
                    if (rtxt.length > 0) {{ hasContent = true; break; }}
                }} catch(e) {{}}
            }}
        }}
        if (!hasContent) {{
            try {{ rpg.remove(); removedPages++; }} catch(e) {{}}
        }}
    }}
    if (removedPages > 0) log("removedPages=" + removedPages);

    // 12-pre. \u017D/\u017E (Ž/ž) 특수문자 폰트 깨짐 수정 — 함초롬돋움 폰트 적용 (글자 유지)
    try {{
        var _fontCandsZ = [
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0\\tRegular",
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0",
            "\\uD568\\uCD08\\uB86C \\uB3CB\\uC6C0",
            "HCR Dotum\\tRegular",
            "HCR Dotum"
        ];
        var _fntZ = null;
        var _fntZName = null;
        for (var _fi = 0; _fi < _fontCandsZ.length; _fi++) {{
            try {{
                var _f = app.fonts.itemByName(_fontCandsZ[_fi]);
                if (_f && _f.isValid) {{ _fntZ = _f; _fntZName = _fontCandsZ[_fi]; break; }}
            }} catch(eFC) {{}}
        }}
        if (_fntZ) {{
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = "[\\u017D\\u017E]";
            app.changeGrepPreferences.appliedFont = _fntZ;
            var _zChanged = doc.changeGrep();
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            log("Zz font applied: " + _fntZName + " count=" + (_zChanged ? _zChanged.length : 0));
        }} else {{
            log("Zz font missing: \\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0 \\uBBF8\\uC124\\uCE58");
        }}
    }} catch(eZf) {{ log("Zz font err: " + eZf.message); }}

    // 12-pre2. 아래/위 첨자 유니코드 (U+2070~U+209F) — 현재 본문 폰트에 글리프 없음
    // 화학식(CO₂ 등)의 ₂가 누락 사각형(notdef)으로 표시되는 문제 해결.
    // 한컴 폰트 우선, 미설치 시 NanumGothic / Apple SD Gothic Neo 폴백.
    try {{
        var _hcFont = null;
        var _fontCand = [
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0\\tRegular",
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0",
            "NanumGothic\\tRegular",
            "NanumGothic",
            "Nanum Gothic\\tRegular",
            "AppleSDGothicNeo\\tRegular",
            "AppleSDGothicNeo-Regular",
            "Apple SD Gothic Neo\\tRegular"
        ];
        for (var _fci = 0; _fci < _fontCand.length; _fci++) {{
            try {{
                var _ft = app.fonts.itemByName(_fontCand[_fci]);
                if (_ft && _ft.isValid) {{ _hcFont = _ft; break; }}
            }} catch(eFC) {{}}
        }}
        if (_hcFont) {{
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            // U+2070~U+209F: 위/아래 첨자 + 아래첨자 라틴 소문자 일부
            app.findGrepPreferences.findWhat = "[\\u2070-\\u209F]";
            app.changeGrepPreferences.appliedFont = _hcFont;
            var _subChanged = doc.changeGrep();
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            log("subscript font applied count=" + (_subChanged ? _subChanged.length : 0));
        }} else {{
            log("subscript font: hamchorom not found");
        }}
    }} catch(eSub) {{
        log("subscript font err: " + eSub.message);
        try {{ app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING; }} catch(e) {{}}
    }}

    // 12a. D-마스터 정리
    // 1) 모든 기존 D-마스터를 A-chapter1로 복원
    try {{
        var mA = doc.masterSpreads.itemByName("A-chapter1");
        var mD = doc.masterSpreads.itemByName("D-\\uB9C8\\uC2A4\\uD130");
        if (mA.isValid && mD.isValid) {{
            for (var dpi = 0; dpi < doc.pages.length; dpi++) {{
                try {{
                    if (doc.pages[dpi].appliedMaster === mD) {{
                        doc.pages[dpi].appliedMaster = mA;
                    }}
                }} catch(e) {{}}
            }}
            // 2) 고3은 문장삽입 섹션이 없으므로 insert firstPage 탐색/D-마스터 재적용 스킵
            if (!IS_G3 && insertBlocks.length > 0) {{
                var insFirstPage = null;
                for (var ifp = 1; ifp < doc.pages.length; ifp++) {{
                    var ifpg = doc.pages[ifp];
                    var iftfs = ifpg.textFrames;
                    for (var ift = 0; ift < iftfs.length; ift++) {{
                        var ifc = (iftfs[ift].contents || "");
                        if (ifc.indexOf("\\uC0BD\\uC785") >= 0 || ifc.indexOf("\\uC21C\\uC11C") >= 0 ||
                            ifc.substring(0,3).indexOf("\\uC544\\uB798") === 0 || ifc.substring(0,1) === "{{") {{
                            insFirstPage = ifpg;
                            break;
                        }}
                    }}
                    if (insFirstPage) break;
                }}
                // 3) RIGHT이면 D-마스터 적용. LEFT이면 아무것도 안 함 (D-마스터/빈페이지 X)
                if (insFirstPage && insFirstPage.side == 1919382632) {{
                    insFirstPage.appliedMaster = mD;
                    log("D-master applied to ins firstPage off=" + insFirstPage.documentOffset);
                }} else if (insFirstPage) {{
                    log("ins firstPage is LEFT — skip D-master (off=" + insFirstPage.documentOffset + ")");
                }}
            }}
        }}
    }} catch(e) {{
        log("D-master err=" + e.message);
    }}

    // 크레딧 페이지는 Vocab JSX에서 마지막에 추가 (Vol1 JSX에서는 추가하지 않음)

    // ========================================
    // 12-post. 경미 오버플로우 최종 해소 (자간/행간 shrink-fit) — A단계
    //   모든 배치·스타일·clearOverrides가 끝난 뒤 마지막에 적용해야 tracking/leading override가
    //   clearOverrides(CHARACTER_ONLY)에 지워지지 않는다. 여전히 넘치는 지문 스토리만 대상.
    //   3~4줄+ 과다초과는 tryShrinkFit이 false 반환(B단계). 헤더 문단 보존, tracking>=-25/leading-0.5pt.
    // ========================================
    var postShrinkOk = 0, postShrinkFail = 0;
    for (var psi = 0; psi < doc.stories.length; psi++) {{
        try {{
            var pst = doc.stories[psi];
            if (!pst.overflows) continue;
            if (tryShrinkFit(pst)) postShrinkOk++; else postShrinkFail++;
        }} catch(e) {{}}
    }}
    log("postShrink ok=" + postShrinkOk + " fail=" + postShrinkFail);

    // ========================================
    // 12-reb. 칼럼 리밸런싱 (B-1) — 같은 칼럼 경계선 이동으로 3~4줄+ 과다초과 해소
    //   상단/하단 중 한쪽만 넘치고 짝꿍에 여백이 있으면, 둘 사이 경계선을 이동해 넘치는
    //   프레임을 키우고 짝꿍 프레임을 줄인다. 내용 이동/페이지추가 없음(짝꿍 지문은 제자리,
    //   프레임만 축소). 둘 다 넘치면 스킵(B-2 페이지추가 대상). 이 시점 doc=배열+삽입만.
    // ========================================
    function _isContentFrame(f) {{
        try {{
            var st = f.parentStory; if (!st) return false;
            var ps = st.paragraphs;
            for (var ci=0; ci<ps.length; ci++) {{
                if (ps[ci].appliedParagraphStyle.name.indexOf("문장 배열") >= 0) return true;
            }}
        }} catch(e){{}}
        return false;
    }}
    function _setBoundary(topF, botF, tb, bb, y) {{
        topF.geometricBounds = [tb[0], tb[1], y, tb[3]];
        botF.geometricBounds = [y, bb[1], bb[2], bb[3]];
        try {{ topF.parentStory.recompose(); botF.parentStory.recompose(); }} catch(e){{}}
    }}
    function _rebalanceCol(topF, botF) {{
        var ts = topF.parentStory, bs = botF.parentStory;
        try {{ ts.recompose(); bs.recompose(); }} catch(e){{}}
        if (ts.overflows == bs.overflows) return ts.overflows ? "both" : "none";
        var tb = topF.geometricBounds, bb = botF.geometricBounds;
        var y = tb[2], step = 4;
        var lo = tb[0] + 12, hi = bb[2] - 12;
        if (ts.overflows) {{
            while (ts.overflows && y + step <= hi) {{
                y += step; _setBoundary(topF, botF, tb, bb, y);
                if (bs.overflows) {{ y -= step; _setBoundary(topF, botF, tb, bb, y); break; }}
            }}
        }} else {{
            while (bs.overflows && y - step >= lo) {{
                y -= step; _setBoundary(topF, botF, tb, bb, y);
                if (ts.overflows) {{ y += step; _setBoundary(topF, botF, tb, bb, y); break; }}
            }}
        }}
        return (!ts.overflows && !bs.overflows) ? "ok" : "partial";
    }}
    var rebOk=0, rebBoth=0, rebPartial=0;
    for (var rpg=0; rpg<doc.pages.length; rpg++) {{
        var _cf = [];
        var _tfs = doc.pages[rpg].textFrames;
        for (var _ti=0; _ti<_tfs.length; _ti++) {{ if (_isContentFrame(_tfs[_ti])) _cf.push(_tfs[_ti]); }}
        for (var _a=0; _a<_cf.length; _a++) {{
            for (var _b=_a+1; _b<_cf.length; _b++) {{
                var _ba = _cf[_a].geometricBounds, _bb2 = _cf[_b].geometricBounds;
                if (Math.abs(_ba[1]-_bb2[1]) > 6) continue;      // 다른 칼럼
                if (Math.abs(_ba[0]-_bb2[0]) < 30) continue;     // 같은 행(이상 케이스)
                var _top = _ba[0] < _bb2[0] ? _cf[_a] : _cf[_b];
                var _bot = _ba[0] < _bb2[0] ? _cf[_b] : _cf[_a];
                var _r = _rebalanceCol(_top, _bot);
                if (_r=="ok") rebOk++; else if (_r=="both") rebBoth++; else if (_r=="partial") rebPartial++;
            }}
        }}
    }}
    log("columnRebalance ok=" + rebOk + " both=" + rebBoth + " partial=" + rebPartial);

    // ========================================
    // 12-hard. 강한 shrink (B-2c) — 리밸런싱 후에도 풀높이 프레임에서 1~2줄 근접초과인 장문.
    //   자간 -40까지 + 행간 추가 -0.7pt. 그래도 넘치면(진짜 3~4줄+ 장문) B-2 페이지추가 대상.
    // ========================================
    var hardOk=0, hardFail=0;
    for (var hsi=0; hsi<doc.stories.length; hsi++) {{
        try {{
            var hst = doc.stories[hsi];
            if (!hst.overflows) continue;
            var hp = hst.paragraphs;
            for (var htv=-30; htv>=-40; htv-=5) {{
                for (var hi=0; hi<hp.length; hi++) {{ if (!isHeaderPara(hp[hi])) {{ try {{ hp[hi].tracking = htv; }} catch(e){{}} }} }}
                try {{ hst.recompose(); }} catch(e){{}}
                if (!hst.overflows) break;
            }}
            if (hst.overflows) {{
                for (var hj=0; hj<hp.length; hj++) {{
                    if (isHeaderPara(hp[hj])) continue;
                    try {{ var hcl=hp[hj].leading; if (typeof hcl==="number" && hcl>5) hp[hj].leading = hcl - 0.7; }} catch(e){{}}
                }}
                try {{ hst.recompose(); }} catch(e){{}}
            }}
            if (hst.overflows) hardFail++; else hardOk++;
        }} catch(e){{}}
    }}
    log("hardShrink ok=" + hardOk + " fail=" + hardFail);

    // ========================================
    // 12-cascade. B-2 (배치-후 post-pass): 넘치는 지문마다 연속 슬롯을 끼워넣고 뒤 지문을 앞으로 민다.
    //   배치가 끝나 프레임 고정 상태에서 frame.move로 이동(복제X → 헤더·박스·화살표 보존).
    //   "진행 중 배치와 충돌"이라는 과거 근본원인이 구조적으로 없음. 이 시점 doc=배열/삽입만.
    //   그리드 슬롯: 페이지당 4(LU,LL,RU,RL 읽기순). 새 페이지/프레임은 그리드 바운드(중요어휘 JSX 보존).
    // ========================================
    var GEB = [[27,18,153,101],[153,18,279,101],[27,105,153,188],[153,105,279,188]];   // even page
    var GOB = [[27,22,153,105],[153,22,279,105],[27,109,153,192],[153,109,279,192]];   // odd page
    function _gb(pg, slot) {{
        var ref = (pg.documentOffset % 2 === 0) ? GOB : GEB;   // addFramePage와 동일 규칙
        var x = 0; try {{ x = pg.bounds[1]; }} catch(e){{}}
        var b = ref[slot];
        return [b[0], b[1]+x, b[2], b[3]+x];
    }}
    // 1) 콘텐츠 프레임 읽기순 수집
    var cf = [];
    for (var pgx=0; pgx<doc.pages.length; pgx++) {{
        var tfx = doc.pages[pgx].textFrames;
        for (var tx=0; tx<tfx.length; tx++) {{
            if (_isContentFrame(tfx[tx])) {{ var gbx=tfx[tx].geometricBounds; cf.push({{f:tfx[tx], pg:pgx, y:gbx[0], x:gbx[1]}}); }}
        }}
    }}
    cf.sort(function(a,b){{ if(a.pg!=b.pg) return a.pg-b.pg; if(Math.abs(a.x-b.x)>6) return a.x-b.x; return a.y-b.y; }});
    var ncf = cf.length, overCnt = 0;
    for (var i=0;i<ncf;i++){{ cf[i].ov=false; try{{cf[i].ov=cf[i].f.parentStory.overflows;}}catch(e){{}} if(cf[i].ov) overCnt++; }}
    var pageAddOk=0, pageAddSkip=0;
    if (overCnt === 0) {{ log("cascade: overflow 없음 — 스킵"); }}
    else {{
        // 빈 그리드 프레임 제거 (이동 시 위치충돌 방지). 콘텐츠 프레임/비그리드 프레임은 보존.
        for (var pz=0; pz<doc.pages.length; pz++) {{
            var tz=doc.pages[pz].textFrames; var px2=0; try{{px2=doc.pages[pz].bounds[1];}}catch(e){{}}
            for (var kz=tz.length-1; kz>=0; kz--) {{
                var fz=tz[kz]; if (_isContentFrame(fz)) continue;
                var gz=fz.geometricBounds; var isGrid=(Math.abs(gz[0]-27)<8||Math.abs(gz[0]-153)<8)&&(gz[2]-gz[0])>40;
                var c2=""; try{{c2=(fz.contents||"").replace(/\s/g,"");}}catch(e){{}}
                var thr=false; try{{thr=(fz.previousTextFrame!=null);}}catch(e){{}}
                if (isGrid && c2.length===0 && !thr) {{ try{{fz.remove();}}catch(e){{}} }}
            }}
        }}
        // 목표 슬롯 = ncf + overCnt. 부족하면 끝에 그리드 페이지 추가.
        var totalSlots = ncf + overCnt;
        while (doc.pages.length*4 < totalSlots) {{
            var lastP = doc.pages[doc.pages.length-1];
            var np = doc.pages.add(LocationOptions.AFTER, lastP);
            try {{ if(lastP.appliedMaster && lastP.appliedMaster.isValid) np.appliedMaster=lastP.appliedMaster; }} catch(e){{}}
            for (var sj=0;sj<4;sj++) {{ try{{ np.textFrames.add({{geometricBounds:_gb(np,sj)}}); }}catch(e){{}} }}
        }}
        function _slot(idx) {{ var p=doc.pages[Math.floor(idx/4)]; return {{page:p, bounds:_gb(p, idx%4)}}; }}
        // 목표 인덱스: i + (앞의 overflow 누계)
        var sh=0, tIdx=[];
        for (var i2=0;i2<ncf;i2++){{ tIdx[i2]=i2+sh; if(cf[i2].ov) sh++; }}
        // 백워드 이동 + continuation 스레드
        for (var i3=ncf-1;i3>=0;i3--) {{
            var t=tIdx[i3], sl=_slot(t);
            try {{ cf[i3].f.move(sl.page); cf[i3].f.geometricBounds=sl.bounds; }} catch(e){{ log("cascade move ERR i="+i3+" "+e.message); }}
            if (cf[i3].ov) {{
                var slc=_slot(t+1);
                try {{ var Gc=slc.page.textFrames.add({{geometricBounds:slc.bounds}}); cf[i3].f.nextTextFrame=Gc; cf[i3].f.parentStory.recompose(); pageAddOk++; }}
                catch(e){{ log("cascade cont ERR i="+i3+" "+e.message); }}
            }}
        }}
        // 빈 꼬리 페이지 제거
        for (var pe=doc.pages.length-1; pe>=1; pe--) {{
            var pg2=doc.pages[pe], has=false, it2=pg2.textFrames;
            for (var k2=0;k2<it2.length;k2++){{ var cc=""; try{{cc=(it2[k2].contents||"").replace(/\s/g,"");}}catch(e){{}} var tt=false; try{{tt=(it2[k2].previousTextFrame!=null);}}catch(e){{}} if(cc.length>0||tt){{has=true;break;}} }}
            if (!has) {{ try{{pg2.remove();}}catch(e){{}} }}
        }}
        log("cascade: passages="+ncf+" overflow="+overCnt+" addedSlots="+overCnt);
    }}
    log("pageAdd ok=" + pageAddOk + " skip=" + pageAddSkip);

    // ========================================
    // 13. 최종 로그 + PDF + 저장
    // ========================================
    var finalOv = 0;
    for (var fsi = 0; fsi < doc.stories.length; fsi++) {{
        if (doc.stories[fsi].overflows) finalOv++;
    }}
    log("finalPages=" + doc.pages.length + " overflow=" + finalOv);

    // 직전보충: PDF 미내보내기 — 인디자인 파일(.indd)만 생성
    log("pdf=skip");

    // Ruler origin 원상 복구 (저장 전)
    try {{
        if (_origRulerOrigin !== null) doc.viewPreferences.rulerOrigin = _origRulerOrigin;
    }} catch(eRO2) {{}}

    doc.save();
    // 조판 결과는 닫지 않고 열어둠 (결과 즉시 확인용)

}} catch(ex) {{
    log("ERROR=" + ex.message);
    try {{ app.activeDocument.close(SaveOptions.NO); }} catch(e2) {{}}
}}

app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
var mf = new File("{marker}"); mf.open("w"); mf.write("done"); mf.close();
var lf = new File("{log_file}"); lf.open("w"); lf.encoding="UTF-8"; lf.write(L.join("\\n")); lf.close();
"""

def _build_vol2_jsx(indd_path, data_path, pdf_path, marker, log_file, pid):
    """Vol2 전체 처리 JSX 생성.

    완성본 분석 기반 구조:
    - 어법수정 스토리 (pages 2~13): 3. 어법수정 번호 스타일
      패턴: 헤더(1과 본문1 / 221129) + 지문 → 프레임브레이크 → 다음 헤더
    - 서술형영작 스토리 (pages 14~25):
      패턴: [[기본 단락]] [헤더] → [C_영작 배열 번호] 한글 → [영작 배열 보기] 보기 → [밑줄] → FB
    """
    return f"""#target indesign
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
var L = [];
function log(m) {{ L.push(m); }}

try {{
    var doc = app.open(File("{indd_path}"));
    log("opened=" + doc.pages.length + "p");

    // Ruler origin 강제 SPREAD_ORIGIN — PAGE_ORIGIN 템플릿에서 addFramePage 시
    // 새 페이지의 bounds[1]=0 반환으로 RIGHT 페이지 프레임이 spread pasteboard로
    // 떨어지는 버그 방지. PDF export 후 저장 전 원본 값으로 복원.
    var _origRulerOrigin = null;
    try {{
        _origRulerOrigin = doc.viewPreferences.rulerOrigin;
        doc.viewPreferences.rulerOrigin = RulerOrigin.SPREAD_ORIGIN;
        log("rulerOrigin set to SPREAD_ORIGIN (was=" + _origRulerOrigin + ")");
    }} catch(eRO) {{}}

    // pasteboard 잔재 정리 함수 — 페이지 삭제 시 spread로 이동된 orphan 프레임/화살표 제거.
    // 예외: 음수 y좌표 라벨 프레임은 유지.
    function cleanPbOrphans(tag) {{
        var rm = 0;
        for (var oSi = doc.spreads.length - 1; oSi >= 0; oSi--) {{
            var oSp = doc.spreads[oSi];
            var items = oSp.textFrames;
            for (var oIi = items.length - 1; oIi >= 0; oIi--) {{
                var it = items[oIi];
                var pp = null;
                try {{ pp = it.parentPage; }} catch(ePp) {{}}
                if (pp !== null) continue;
                var gb;
                try {{ gb = it.geometricBounds; }} catch(eGb) {{ continue; }}
                if (gb[0] < 0) continue;
                // threaded 텍스트 프레임(스토리 체인)은 보존
                try {{
                    if (it.previousTextFrame || it.nextTextFrame) continue;
                }} catch(eChk) {{}}
                try {{ it.remove(); rm++; }} catch(eRm) {{}}
            }}
        }}
        log("pbOrphansRemoved(" + tag + ")=" + rm);
    }}

    // Vol2 textDefaults.fillColor가 Paper(흰색)인 경우 Black으로 강제 설정
    try {{
        var blackSwatch = doc.swatches.itemByName("Black");
        if (blackSwatch.isValid) {{
            doc.textDefaults.fillColor = blackSwatch;
            log("textDefaults.fillColor=Black (forced)");
        }}
    }} catch(e) {{ log("fillColor override err=" + e.message); }}

    var cf = new File("{data_path}");
    cf.encoding = "UTF-8"; cf.open("r");
    var data = eval("(" + cf.read() + ")");
    cf.close();

    // ========================================
    // 스타일 수집
    // ========================================
    var allPS = doc.allParagraphStyles;
    var psGrammar = null;  // 3. 어법수정 번호
    var psKorean = null;   // C_영작 배열 번호
    var psChoices = null;  // 영작 배열 보기
    var psUnder = null;    // 밑줄
    var psBasic = null;    // [기본 단락]

    for (var i = 0; i < allPS.length; i++) {{
        var n = allPS[i].name;
        if (n === "3. \\uC5B4\\uBC95\\uC218\\uC815 \\uBC88\\uD638") psGrammar = allPS[i];
        if (n === "C_\\uC601\\uC791 \\uBC30\\uC5F4 \\uBC88\\uD638") psKorean = allPS[i];
        if (n === "\\uC601\\uC791 \\uBC30\\uC5F4 \\uBCF4\\uAE30") psChoices = allPS[i];
        if (n === "\\uBC11\\uC904") psUnder = allPS[i];
        if (n === "[\\uAE30\\uBCF8 \\uB2E8\\uB77D]" || n === "[Basic Paragraph]") psBasic = allPS[i];
    }}

    // ========================================
    // 1. 어법수정 스토리 찾기
    // ========================================
    // 방법: page 2에서 시작하는 가장 많은 프레임을 가진 스토리
    var gLines = data["\\uC5B4\\uBC95\\uC218\\uC815"] || [];
    var gStoryIdx = -1;
    var wStoryIdx2 = -1;  // 서술형 영작 스토리 인덱스 (D-마스터용)

    if (gLines.length > 0) {{
        var gStory = null;
        gStoryIdx = -1;

        // page 2 (documentOffset 1)의 텍스트프레임에서 가장 많은 프레임을 가진 스토리 찾기
        for (var si = 0; si < doc.stories.length; si++) {{
            try {{
                var st = doc.stories[si];
                var tc = st.textContainers;
                if (tc.length >= 12) {{
                    var pg = tc[0].parentPage;
                    if (pg && pg.documentOffset <= 2) {{
                        gStory = st;
                        gStoryIdx = si;
                        break;
                    }}
                }}
            }} catch(e) {{}}
        }}

        // 대체: 가장 큰 빈 스토리
        if (!gStory) {{
            var sizes = [];
            for (var si = 0; si < doc.stories.length; si++) {{
                try {{
                    var tc = doc.stories[si].textContainers;
                    if (tc.length >= 4) {{
                        var gb = tc[0].geometricBounds;
                        sizes.push({{i: si, frames: tc.length, p: doc.stories[si].paragraphs.length}});
                    }}
                }} catch(e) {{}}
            }}
            sizes.sort(function(a,b) {{ return b.frames - a.frames; }});
            if (sizes.length > 0) {{
                gStory = doc.stories[sizes[0].i];
                gStoryIdx = sizes[0].i;
            }}
        }}

        if (gStory) {{
            // 어법수정 스토리 프레임 중 페이지 갭 > 2인 지점 이후 프레임 분리
            // 템플릿 설계상 어법수정 overflow용 프레임이 영작 섹션 뒤 페이지에 배치되어 있어,
            // 어법수정 분량이 많으면 영작 마스터 페이지에 어법수정 내용이 흘러들어가는 문제 해결.
            // 분리 후 overflow는 별도 처리 루프가 어법수정 마스터로 새 페이지 추가
            try {{
                var _gTC = gStory.textContainers;
                var _unthreadFrom = -1;
                for (var _gfi = 1; _gfi < _gTC.length; _gfi++) {{
                    try {{
                        var _prevPg = _gTC[_gfi - 1].parentPage.documentOffset;
                        var _curPg = _gTC[_gfi].parentPage.documentOffset;
                        if (_curPg - _prevPg > 2) {{
                            _unthreadFrom = _gfi;
                            break;
                        }}
                    }} catch(eG) {{}}
                }}
                if (_unthreadFrom > 0) {{
                    var _cutFrame = _gTC[_unthreadFrom - 1];
                    var _laterFrames = [];
                    for (var _lfi = _unthreadFrom; _lfi < _gTC.length; _lfi++) _laterFrames.push(_gTC[_lfi]);
                    try {{ _cutFrame.nextTextFrame = null; }} catch(eCT) {{}}
                    for (var _lri = 0; _lri < _laterFrames.length; _lri++) {{
                        try {{ _laterFrames[_lri].remove(); }} catch(eRM) {{}}
                    }}
                    log("grammar unthreaded " + _laterFrames.length + " frames after page gap");
                }}
            }} catch(eGG) {{ log("grammar unthread err=" + eGG.message); }}

            app.doScript(function() {{
                gStory.contents = "";

                // 어법수정 헤더 목록 (어법_헤더 배열)
                var gHeaders = data["\\uC5B4\\uBC95_\\uD5E4\\uB354"] || [];
                // 헤더 Set 구축
                var gHeaderSet = {{}};
                for (var hi = 0; hi < gHeaders.length; hi++) {{
                    gHeaderSet[gHeaders[hi]] = true;
                }}

                // 어법수정 데이터 삽입 — 헤더 줄 앞에 프레임 브레이크
                var gBlockCount = 0;
                for (var li = 0; li < gLines.length; li++) {{
                    var lineText = gLines[li];
                    var isHeader = gHeaderSet[lineText] ||
                        /^\\uAD50\\uACFC\\uC11C/.test(lineText) ||
                        /^\\d{{1,2}}\\uACFC\\s/.test(lineText) ||
                        /^S\\d+\\uACFC\\s/.test(lineText) ||
                        /^SL\\s/.test(lineText) ||
                        /^\\d{{6}}/.test(lineText) ||
                        /^\\d+\\uAC15(\\s|$)/.test(lineText) ||
                        /^test\\d+(\\s|$)/i.test(lineText) ||
                        /^\\uC62C\\uD3EC\\s+\\d+\\uAC15\\s+(\\uBCF8\\uBB38\\d+|\\uBD84\\uC11D|\\uC11C\\uC220\\uD615|\\uB17C\\uC220\\uD615)/.test(lineText) ||
                        /^\\uB9AC\\uB529\\uD30C\\uC6CC\\s+\\d+\\uAC15\\s+\\uBCF8\\uBB38\\d+/.test(lineText) ||
                        /^\\uB9C8\\uB354\\uD145\\d*\\s+\\uBCF8\\uBB38\\d+/.test(lineText);

                    if (isHeader && gBlockCount > 0) {{
                        // 프레임 브레이크 삽입
                        gStory.insertionPoints[-1].contents = SpecialCharacters.FRAME_BREAK;
                    }}
                    if (isHeader) gBlockCount++;

                    gStory.insertionPoints[-1].contents = lineText + "\\r";
                }}

                // 전체 스타일 적용
                if (psGrammar) {{
                    try {{ gStory.paragraphs.everyItem().appliedParagraphStyle = psGrammar; }} catch(e) {{}}
                }}

                // "올포 N강 분석/서술형/논술형" 헤더에 "지문번호" 캐릭터 스타일 적용
                // 원인: psGrammar의 nestedGrepStyle이 숫자로 끝나는 단락에만 "지문번호"를 적용하므로,
                //       한글로 끝나는 "분석/서술형/논술형" 헤더는 기본 스타일(8.5pt Noto Sans Regular)로 남음.
                // 해결: findText로 정확히 일치하는 헤더 문자열만 찾아 "지문번호" 캐릭터 스타일 적용.
                try {{
                    var csPassageNum = null;
                    var allCSg2 = doc.allCharacterStyles;
                    for (var csgi2 = 0; csgi2 < allCSg2.length; csgi2++) {{
                        if (allCSg2[csgi2].name === "\\uC9C0\\uBB38\\uBC88\\uD638") {{ csPassageNum = allCSg2[csgi2]; break; }}
                    }}
                    if (csPassageNum) {{
                        // 각 헤더 문자열을 한 번씩 찾아 charStyle 적용 (gHeaders 배열 이용 — 이미 알려진 헤더만)
                        var appliedCount = 0;
                        for (var ghi = 0; ghi < gHeaders.length; ghi++) {{
                            var ghTxt = gHeaders[ghi];
                            // 한글/영문으로 끝나는 헤더: "올포 N강 분석/서술형/논술형" + "교과서N과 FR" + "교과서SL FR" + "교과서N과 딥러닝"
                            var _isNonDigitEnd = /^\\uC62C\\uD3EC\\s+\\d+\\uAC15\\s+(\\uBD84\\uC11D|\\uC11C\\uC220\\uD615|\\uB17C\\uC220\\uD615)$/.test(ghTxt)
                                || /^\\uAD50\\uACFC\\uC11C\\S+?\\s+FR$/.test(ghTxt)
                                || /^\\uAD50\\uACFC\\uC11C\\S+?\\s+\\uB525\\uB7EC\\uB2DD$/.test(ghTxt);
                            if (!_isNonDigitEnd) continue;
                            app.findTextPreferences = NothingEnum.NOTHING;
                            app.changeTextPreferences = NothingEnum.NOTHING;
                            app.findTextPreferences.findWhat = ghTxt;
                            app.changeTextPreferences.appliedCharacterStyle = csPassageNum;
                            var tc = gStory.changeText();
                            appliedCount += (tc ? tc.length : 0);
                            app.findTextPreferences = NothingEnum.NOTHING;
                            app.changeTextPreferences = NothingEnum.NOTHING;
                        }}
                        log("grammar passageNum charStyle applied count=" + appliedCount);

                        // "N강 Gateway" 헤더 + "교과서N과 FR" 헤더: 단락 전체에 지문번호 charStyle 직접 적용
                        // (nestedGrepStyle은 숫자로 끝나는 단락만 대상이므로 FR/Gateway 같은 한글/영문 끝 헤더는 직접 char 스타일 할당 필요)
                        var gGwApplied = 0;
                        var gFRApplied = 0;
                        try {{
                            var gPs = gStory.paragraphs.everyItem().getElements();
                            for (var gpi = 0; gpi < gPs.length; gpi++) {{
                                var gPt = (gPs[gpi].contents || "").replace(/[\\r\\n]+$/, "");
                                if (/^(?:\\d+\\uAC15|test\\d+)\\s+Gateway$/i.test(gPt)) {{
                                    try {{
                                        for (var gGci = 0; gGci < gPt.length; gGci++) {{
                                            gPs[gpi].characters[gGci].appliedCharacterStyle = csPassageNum;
                                        }}
                                        gGwApplied++;
                                    }} catch(eGwG) {{}}
                                }}
                                // "교과서N과 FR", "교과서SL FR", "올포 N강 분석/서술형/논술형", "교과서N과 딥러닝"
                                else if (/^\\uAD50\\uACFC\\uC11C\\S+?\\s+FR$/.test(gPt)
                                    || /^\\uAD50\\uACFC\\uC11C\\S+?\\s+\\uB525\\uB7EC\\uB2DD$/.test(gPt)
                                    || /^\\uC62C\\uD3EC\\s+\\d+\\uAC15\\s+(\\uBD84\\uC11D|\\uC11C\\uC220\\uD615|\\uB17C\\uC220\\uD615)$/.test(gPt)) {{
                                    try {{
                                        // paragraph 단위로 적용 (nestedGrepStyle은 "^.+\\d" 패턴으로 숫자 끝만 대상)
                                        gPs[gpi].appliedCharacterStyle = csPassageNum;
                                        gFRApplied++;
                                    }} catch(eGwF) {{
                                        try {{
                                            for (var gFci = 0; gFci < gPt.length; gFci++) {{
                                                gPs[gpi].characters[gFci].appliedCharacterStyle = csPassageNum;
                                            }}
                                            gFRApplied++;
                                        }} catch(e2) {{}}
                                    }}
                                }}
                            }}
                        }} catch(eGwGs) {{}}
                        log("grammar Gateway charStyle applied=" + gGwApplied + " FR=" + gFRApplied);
                    }}
                }} catch(eCS2) {{
                    log("grammar csFix err=" + eCS2.message);
                    try {{ app.findTextPreferences = NothingEnum.NOTHING; app.changeTextPreferences = NothingEnum.NOTHING; }} catch(e) {{}}
                }}

                // fillColor를 Black으로 강제 적용 (Paper 상속 방지)
                try {{
                    gStory.texts.everyItem().fillColor = doc.swatches.itemByName("Black");
                    log("grammar fillColor=Black forced");
                }} catch(e) {{ log("grammar fillColor err=" + e.message); }}

                // 어법수정 스토리 첫 페이지에 섹션 마커 "3" 설정
                try {{
                    var gFirstPg = gStory.textContainers[0].parentPage;
                    if (gFirstPg) {{
                        var gSecExists = false;
                        for (var gsi = 0; gsi < doc.sections.length; gsi++) {{
                            if (doc.sections[gsi].pageStart === gFirstPg) {{ gSecExists = true; break; }}
                        }}
                        if (!gSecExists) {{
                            var gSec = doc.sections.add(gFirstPg);
                            gSec.marker = "3";
                            gSec.continueNumbering = true;
                            log("grammar section marker=3 at page " + gFirstPg.documentOffset);
                        }}
                    }}
                }} catch(e) {{ log("grammar section err=" + e.message); }}

                log("grammar=ok lines=" + gLines.length + " blocks=" + gBlockCount);
            }}, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "Vol2_grammar");
        }} else {{
            log("grammar=noStory");
        }}
    }}

    // ========================================
    // 2. 서술형 영작
    // ========================================
    var wPairs = data["\\uC11C\\uC220\\uD615\\uC601\\uC791"] || [];
    if (wPairs.length > 0) {{
        // 서술형영작 스토리 찾기: 어법수정 다음으로 많은 프레임을 가진 스토리
        var wStory = null;
        var wStoryIdx = -1;

        var storySizes = [];
        for (var si = 0; si < doc.stories.length; si++) {{
            if (si === gStoryIdx) continue;
            try {{
                var st = doc.stories[si];
                var tc = st.textContainers;
                if (tc.length >= 4) {{
                    var pg = tc[0].parentPage;
                    if (pg && pg.documentOffset >= 10) {{
                        storySizes.push({{i: si, frames: tc.length}});
                    }}
                }}
            }} catch(e) {{}}
        }}
        storySizes.sort(function(a,b) {{ return b.frames - a.frames; }});
        if (storySizes.length > 0) {{
            wStory = doc.stories[storySizes[0].i];
            wStoryIdx = storySizes[0].i;
            wStoryIdx2 = storySizes[0].i;
        }}

        if (wStory) {{
            app.doScript(function() {{
                wStory.contents = "";

                // 영작_헤더_상세: [{{"header":"1과 본문1","start_idx":0}}, ...]
                var wHeadersDetailed = data["\\uC601\\uC791_\\uD5E4\\uB354_\\uC0C1\\uC138"] || [];
                var wHeaders = data["\\uC601\\uC791_\\uD5E4\\uB354"] || [];

                // 헤더 삽입 위치 맵 구축
                var headerMap = {{}};
                if (wHeadersDetailed.length > 0) {{
                    for (var hi = 0; hi < wHeadersDetailed.length; hi++) {{
                        var hd = wHeadersDetailed[hi];
                        headerMap[hd.start_idx] = hd.header;
                    }}
                }} else if (wHeaders.length > 0) {{
                    var pairsPerHeader = Math.ceil(wPairs.length / wHeaders.length);
                    for (var hi = 0; hi < wHeaders.length; hi++) {{
                        headerMap[hi * pairsPerHeader] = wHeaders[hi];
                    }}
                }}

                // 삽입된 단락의 유형을 추적 (스타일 적용용)
                // 유형: "header", "korean", "choices", "underline", "fb_empty"
                var paraTypes = [];
                var wBlockCount = 0;

                for (var pi = 0; pi < wPairs.length; pi++) {{
                    // 헤더 삽입 + 프레임 브레이크
                    if (headerMap[pi] !== undefined) {{
                        var hdrText = headerMap[pi];
                        var hdrFormatted;
                        if (/^\\d{{6}}/.test(hdrText)) {{
                            hdrFormatted = "{{" + hdrText + "}}";
                        }} else if (/^\\d+\\uAC15/.test(hdrText) || /^test\\d+/i.test(hdrText)) {{
                            hdrFormatted = "[" + hdrText + "]";
                        }} else {{
                            hdrFormatted = "[" + hdrText + "]";
                        }}

                        // 첫 번째 블록 제외 프레임 브레이크
                        if (wBlockCount > 0) {{
                            wStory.insertionPoints[-1].contents = SpecialCharacters.FRAME_BREAK;
                            paraTypes.push("fb_empty");
                        }}
                        wBlockCount++;

                        wStory.insertionPoints[-1].contents = hdrFormatted + "\\r";
                        paraTypes.push("header");
                    }}

                    var pr = wPairs[pi];
                    // 한글
                    if (pr.korean) {{
                        wStory.insertionPoints[-1].contents = pr.korean + "\\r";
                        paraTypes.push("korean");
                    }}
                    // 영어 보기
                    if (pr.choices) {{
                        wStory.insertionPoints[-1].contents = pr.choices + "\\r";
                        paraTypes.push("choices");
                    }}
                    // 밑줄 (공백 50자)
                    var ul = "";
                    for (var u = 0; u < 50; u++) ul += " ";
                    wStory.insertionPoints[-1].contents = ul + "\\r";
                    paraTypes.push("underline");
                }}

                // 스타일 적용 — paraTypes 배열 기반으로 정확하게 적용
                var wP = wStory.paragraphs.everyItem().getElements();
                for (var i = 0; i < wP.length; i++) {{
                    if (i >= paraTypes.length) break;
                    var pType = paraTypes[i];

                    if (pType === "header") {{
                        if (psBasic) wP[i].appliedParagraphStyle = psBasic;
                    }} else if (pType === "korean") {{
                        if (psKorean) wP[i].appliedParagraphStyle = psKorean;
                    }} else if (pType === "choices") {{
                        if (psChoices) wP[i].appliedParagraphStyle = psChoices;
                    }} else if (pType === "underline") {{
                        if (psUnder) wP[i].appliedParagraphStyle = psUnder;
                    }} else if (pType === "fb_empty") {{
                        if (psBasic) wP[i].appliedParagraphStyle = psBasic;
                    }}
                }}

                // fillColor를 Black으로 강제 적용 (Paper 상속 방지)
                try {{
                    wStory.texts.everyItem().fillColor = doc.swatches.itemByName("Black");
                    log("writing fillColor=Black forced");
                }} catch(e) {{ log("writing fillColor err=" + e.message); }}

                // "N강 Gateway" 헤더: Gateway 문자에만 지문번호 charStyle 적용
                try {{
                    var csWPassNum = null;
                    var allCSw = doc.allCharacterStyles;
                    for (var cswi = 0; cswi < allCSw.length; cswi++) {{
                        if (allCSw[cswi].name === "\\uC9C0\\uBB38\\uBC88\\uD638") {{ csWPassNum = allCSw[cswi]; break; }}
                    }}
                    if (csWPassNum) {{
                        var wGwApplied = 0;
                        var wFRApplied = 0;
                        var wPs2 = wStory.paragraphs.everyItem().getElements();
                        for (var wpi = 0; wpi < wPs2.length; wpi++) {{
                            var wPt = (wPs2[wpi].contents || "").replace(/[\\r\\n]+$/, "");
                            // "[3강 Gateway]", "[test1 Gateway]"
                            if (/^\\[(?:\\d+\\uAC15|test\\d+)\\s+Gateway\\]$/i.test(wPt)) {{
                                try {{
                                    for (var wGci = 1; wGci < wPt.length - 1; wGci++) {{
                                        wPs2[wpi].characters[wGci].appliedCharacterStyle = csWPassNum;
                                    }}
                                    wGwApplied++;
                                }} catch(eGwW) {{}}
                            }}
                            // "[교과서N과 FR]", "[교과서SL FR]", "[올포 N강 분석/서술형/논술형]", "[교과서N과 딥러닝]"
                            else if (/^\\[\\uAD50\\uACFC\\uC11C\\S+?\\s+FR\\]$/.test(wPt)
                                || /^\\[\\uAD50\\uACFC\\uC11C\\S+?\\s+\\uB525\\uB7EC\\uB2DD\\]$/.test(wPt)
                                || /^\\[\\uC62C\\uD3EC\\s+\\d+\\uAC15\\s+(\\uBD84\\uC11D|\\uC11C\\uC220\\uD615|\\uB17C\\uC220\\uD615)\\]$/.test(wPt)) {{
                                try {{
                                    for (var wFci = 1; wFci < wPt.length - 1; wFci++) {{
                                        wPs2[wpi].characters[wFci].appliedCharacterStyle = csWPassNum;
                                    }}
                                    wFRApplied++;
                                }} catch(eFRW) {{}}
                            }}
                        }}
                        log("writing Gateway charStyle applied=" + wGwApplied + " FR=" + wFRApplied);
                    }}
                }} catch(eWGw) {{}}

                log("writing=ok pairs=" + wPairs.length + " headers=" + wHeaders.length);
            }}, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "Vol2_writing");
        }} else {{
            log("writing=noStory");
        }}
    }}

    // ========================================
    // 3. 오버플로우 처리
    // ========================================
    // Vol2: 상/하 2개 프레임 (전체 폭)
    var v2EvenBounds = [[27,18,279,101],[27,105,279,188]];
    var v2OddBounds  = [[27,22,279,105],[27,109,279,192]];

    var overflowStories = [];
    for (var si = 0; si < doc.stories.length; si++) {{
        if (doc.stories[si].overflows) overflowStories.push(si);
    }}
    log("overflow_before=" + overflowStories.length);
    // 어법수정 스토리는 맨 나중에 처리 (그 시점 doc.pages.length 최대값 = Vol2 맨 뒤)
    overflowStories.sort(function(a, b) {{
        if (a === gStoryIdx) return 1;
        if (b === gStoryIdx) return -1;
        return 0;
    }});

    for (var oi = 0; oi < overflowStories.length; oi++) {{
        var ovStory = doc.stories[overflowStories[oi]];
        var added = 0;
        // 한도 500: 어법수정 768줄(상일2)에서 100 페이지(232 frames)로도 부족.
        // 약 84 페이지 더 필요한 케이스 확인됨. 500은 모든 학교 범위 + 마진 포함.
        // 무한루프 방지(프레임 추가 후에도 frame count가 늘지 않으면 break)와
        // 과도한 추가 방지(동일 프레임에 텍스트가 안 흘러도 그 다음 페이지 추가는 무의미)
        // 둘 다 적용.
        var prevFrameCount = ovStory.textContainers.length;
        var prevLastChars = -1;
        var noProgressStreak = 0;
        while (ovStory.overflows && added < 500) {{
            var lastF = ovStory.textContainers[ovStory.textContainers.length - 1];

            // 마스터 페이지 결정
            var storyMaster = null;
            try {{ storyMaster = ovStory.textContainers[0].parentPage.appliedMaster; }} catch(e) {{}}

            // 마지막 프레임의 페이지 바로 뒤에 삽입 (순서 유지).
            // 어법수정 overflow는 첫 iteration에서 반드시 영작 첫 페이지 앞에 삽입하여
            // 어법수정이 문서 맨 뒤(서술형 영작 뒤)로 튀는 문제 방지.
            var lastPgOfStory = lastF.parentPage;
            var np = null;
            var isGrammarOverflow = (overflowStories[oi] === gStoryIdx);
            if (isGrammarOverflow && added === 0 && wStoryIdx2 >= 0) {{
                var wFirstPg_ov = null;
                try {{ wFirstPg_ov = doc.stories[wStoryIdx2].textContainers[0].parentPage; }} catch(eWF) {{}}
                if (wFirstPg_ov) {{
                    np = doc.pages.add(LocationOptions.BEFORE, wFirstPg_ov);
                    log("grammar overflow inserted BEFORE writing p=" + wFirstPg_ov.documentOffset);
                }}
            }}
            if (!np) {{
                if (lastPgOfStory && lastPgOfStory.documentOffset < doc.pages.length - 1) {{
                    np = doc.pages.add(LocationOptions.AFTER, lastPgOfStory);
                }} else {{
                    np = doc.pages.add();
                }}
            }}
            if (storyMaster) np.appliedMaster = storyMaster;

            // 어법수정 첫 overflow 새 페이지에 섹션 마커 "3" 부여 → 라벨이 영작으로 상속되지 않도록
            if (overflowStories[oi] === gStoryIdx && added === 0) {{
                try {{
                    var secExists = false;
                    for (var sj = 0; sj < doc.sections.length; sj++) {{
                        if (doc.sections[sj].pageStart === np) {{ secExists = true; break; }}
                    }}
                    if (!secExists) {{
                        var newGSec = doc.sections.add(np);
                        newGSec.marker = "3";
                        newGSec.continueNumbering = true;
                        log("grammar overflow section marker=3 at page " + np.documentOffset);
                    }}
                }} catch(eSec) {{}}
            }}

            var pgIdx = np.documentOffset;
            var bnds = (pgIdx % 2 === 0) ? v2OddBounds : v2EvenBounds;
            var npxOff = np.bounds[1];
            var prev = lastF;
            for (var fi = 0; fi < bnds.length; fi++) {{
                var _b = bnds[fi];
                var ntf = np.textFrames.add({{geometricBounds: [_b[0], _b[1]+npxOff, _b[2], _b[3]+npxOff]}});
                prev.nextTextFrame = ntf;
                prev = ntf;
            }}
            added++;
            // 1) 프레임이 늘지 않으면 더 진행해도 의미 없음 → break
            var curFrameCount = ovStory.textContainers.length;
            if (curFrameCount <= prevFrameCount) {{
                log("story" + overflowStories[oi] + " no frame progress at added=" + added + " — break");
                break;
            }}
            prevFrameCount = curFrameCount;
            // 2) 마지막 프레임에 텍스트가 흘러 들어가지 않는 상태가 5회 연속이면 break
            //    (단일 거대 단락이 어떤 프레임에도 못 들어가는 병리적 케이스 방지)
            try {{
                var _newLast = ovStory.textContainers[ovStory.textContainers.length - 1];
                var _lastChars = (_newLast.contents || "").length;
                if (_lastChars === 0 && prevLastChars === 0) {{
                    noProgressStreak++;
                    if (noProgressStreak >= 5) {{
                        log("story" + overflowStories[oi] + " text not flowing into new frames at added=" + added + " — break");
                        break;
                    }}
                }} else {{
                    noProgressStreak = 0;
                }}
                prevLastChars = _lastChars;
            }} catch(eLC) {{}}
        }}
        if (added > 0) log("story" + overflowStories[oi] + " addedPages=" + added + " stillOverflows=" + ovStory.overflows);
    }}

    // ========================================
    // 4. 빈 페이지 삭제 (콘텐츠 영역 프레임이 모두 비어 있으면 삭제)
    // threaded 프레임이라도 이어지는 내용이 없으면(예: 오버플로우가 필요 없어진 뒤의
    //  남은 꼬리 프레임) 삭제 대상. 콘텐츠 영역 밖의 외곽 탭/마스터 프레임은 무시.
    // ========================================
    for (var pi = doc.pages.length - 1; pi >= 2; pi--) {{
        var pg = doc.pages[pi];
        var pItems = pg.allPageItems;
        var hasContent = false;
        var hasAnyTF = false;
        for (var ii = 0; ii < pItems.length; ii++) {{
            if (pItems[ii].constructor.name !== "TextFrame") continue;
            hasAnyTF = true;
            try {{
                var _gb = pItems[ii].geometricBounds;
                // 콘텐츠 영역 바깥(페이지 외곽 탭 등)은 제외
                if (_gb[0] < 0 || _gb[1] < 0) continue;
                var _fh = _gb[2] - _gb[0];
                var _fw = _gb[3] - _gb[1];
                // 페이지 번호(높이 작음), 세로 사이드 탭(폭 좁음) 제외
                if (_fh < 20) continue;
                if (_fw < 25) continue;
                var _ct = (pItems[ii].contents || "").replace(/[\\r\\n\\s\\u2028\\u2029]/g, "");
                if (_ct.length > 0) {{ hasContent = true; break; }}
            }} catch(e) {{}}
        }}
        // 텍스트프레임이 아예 없는 페이지도 삭제 대상 (기존 동작 유지)
        if (!hasContent) {{
            try {{ pg.remove(); }} catch(e) {{}}
        }}
    }}
    cleanPbOrphans("vol2_afterBlankPages");

    // ========================================
    // 4b. 어법수정 overflow 페이지가 영작 섹션 뒤로 밀린 경우 영작 앞으로 이동
    // (pages.add(BEFORE, writingFirstPage) 삽입이 spread 경계 및 빈 페이지 삭제를 거치며
    //  overflow 페이지가 문서 맨 뒤로 이동되는 회귀 방지)
    // ========================================
    if (gStoryIdx >= 0 && wStoryIdx2 >= 0) {{
        try {{
            var _wFirst = null;
            try {{ _wFirst = doc.stories[wStoryIdx2].textContainers[0].parentPage; }} catch(eWFM) {{}}
            if (_wFirst) {{
                var _wFirstOff = _wFirst.documentOffset;
                var _gSt = doc.stories[gStoryIdx];
                var _gTc = _gSt.textContainers;
                var _movePages = [];
                var _seenIds = {{}};
                for (var _tci = 0; _tci < _gTc.length; _tci++) {{
                    try {{
                        var _tcPg = _gTc[_tci].parentPage;
                        if (!_tcPg) continue;
                        if (_tcPg.documentOffset > _wFirstOff) {{
                            var _pid = _tcPg.id;
                            if (!_seenIds[_pid]) {{
                                _seenIds[_pid] = 1;
                                _movePages.push(_tcPg);
                            }}
                        }}
                    }} catch(eMP) {{}}
                }}
                var _movedCnt = 0;
                for (var _mi = _movePages.length - 1; _mi >= 0; _mi--) {{
                    try {{
                        _movePages[_mi].move(LocationOptions.BEFORE, _wFirst);
                        _movedCnt++;
                    }} catch(eMV) {{}}
                }}
                if (_movedCnt > 0) {{
                    log("grammar overflow pages moved BEFORE writing count=" + _movedCnt);
                    cleanPbOrphans("vol2_afterGrammarMove");
                }}
            }}
        }} catch(e) {{}}
    }}

    // ========================================
    // 4c. 어법수정 overflow 페이지(LEFT)에 "어법 수정" 탭 프레임 복제
    // (원본 어법수정 페이지에만 있는 왼쪽 외곽 탭이 overflow 페이지엔 없어 "서술형 영작"으로 잘못 표시)
    // ========================================
    if (gStoryIdx >= 0) {{
        try {{
            // 원본 어법수정 페이지에서 "어법 수정" 탭 소스 찾기
            var _labelSrc = null;
            for (var _spi = 0; _spi < doc.pages.length; _spi++) {{
                var _spg = doc.pages[_spi];
                var _sItems = _spg.allPageItems;
                for (var _sii = 0; _sii < _sItems.length; _sii++) {{
                    var _sIt = _sItems[_sii];
                    if (_sIt.constructor.name !== "TextFrame") continue;
                    try {{
                        var _sgb = _sIt.geometricBounds;
                        if (_sgb[0] < -10 && _sgb[1] > 25 && _sgb[1] < 35 && _sgb[3] > 95 && _sgb[3] < 110) {{
                            var _cnt = (_sIt.contents || "").replace(/[\\r\\n]/g, "");
                            if (_cnt === "\\uC5B4\\uBC95 \\uC218\\uC815") {{
                                _labelSrc = _sIt;
                                break;
                            }}
                        }}
                    }} catch(eS1) {{}}
                }}
                if (_labelSrc) break;
            }}

            if (_labelSrc) {{
                var _gsF = doc.stories[gStoryIdx];
                var _gtcF = _gsF.textContainers;
                var _firstOff = -1;
                try {{ _firstOff = _gtcF[0].parentPage.documentOffset; }} catch(eFO) {{}}
                // 갭 > 1 이후 모든 프레임의 페이지 = overflow 페이지
                var _ovPageSet = {{}};
                var _ovReached = false;
                var _prevOff2 = _firstOff;
                for (var _fi = 1; _fi < _gtcF.length; _fi++) {{
                    try {{
                        var _fpg = _gtcF[_fi].parentPage;
                        if (!_fpg) continue;
                        var _curOff = _fpg.documentOffset;
                        if (_curOff - _prevOff2 > 1) _ovReached = true;
                        if (_ovReached) _ovPageSet[_curOff] = _fpg;
                        _prevOff2 = _curOff;
                    }} catch(eF3) {{}}
                }}
                var _dupCount = 0;
                for (var _ok in _ovPageSet) {{
                    var _opg = _ovPageSet[_ok];
                    var _isLeft = (_opg.side === PageSideOptions.LEFT_HAND || _opg.side === 1818653800);
                    if (!_isLeft) continue;
                    var _has = false;
                    var _pgIt = _opg.allPageItems;
                    for (var _pii = 0; _pii < _pgIt.length; _pii++) {{
                        try {{
                            if (_pgIt[_pii].constructor.name === "TextFrame") {{
                                var _pgb = _pgIt[_pii].geometricBounds;
                                if (_pgb[0] < -10 && _pgb[1] > 25 && _pgb[1] < 35) {{ _has = true; break; }}
                            }}
                        }} catch(eP) {{}}
                    }}
                    if (_has) continue;
                    try {{ _labelSrc.duplicate(_opg); _dupCount++; }} catch(eD) {{}}
                }}
                log("grammar label tab duplicated count=" + _dupCount);
            }} else {{
                log("grammar label tab source not found");
            }}
        }} catch(eTab) {{ log("grammar label tab err=" + eTab.message); }}
    }}

    // ========================================
    // 4b. 어법수정 overflow 페이지에 섹션 마커 "3" 재설정
    // (빈 페이지 삭제 + 페이지 재배치 후, 어법수정 스토리 프레임의 실제 위치 기준)
    // ========================================
    if (gStoryIdx >= 0) {{
        try {{
            var _gStoryFinal = doc.stories[gStoryIdx];
            var _gtcFinal = _gStoryFinal.textContainers;
            var _grammarOverflowStart = -1;
            var _firstPgOff = -1;
            // 어법수정 스토리의 첫 프레임 페이지 찾기
            for (var _fi0 = 0; _fi0 < _gtcFinal.length; _fi0++) {{
                try {{
                    var _fpg0 = _gtcFinal[_fi0].parentPage;
                    if (_fpg0) {{ _firstPgOff = _fpg0.documentOffset; break; }}
                }} catch(eF0) {{}}
            }}
            // 페이지 갭 발생 지점이 overflow 시작 (첫 지점부터 연속이지 않으면 거기)
            if (_firstPgOff >= 0) {{
                var _prevOff = _firstPgOff;
                for (var _fi1 = 1; _fi1 < _gtcFinal.length; _fi1++) {{
                    try {{
                        var _fpg1 = _gtcFinal[_fi1].parentPage;
                        if (!_fpg1) continue;
                        var _curOff = _fpg1.documentOffset;
                        if (_curOff - _prevOff > 1) {{
                            _grammarOverflowStart = _curOff;
                            break;
                        }}
                        _prevOff = _curOff;
                    }} catch(eF1) {{}}
                }}
            }}
            if (_grammarOverflowStart > 0) {{
                try {{
                    var _overflowPg = doc.pages[_grammarOverflowStart];
                    var _secExistsF = false;
                    for (var _fsj = 0; _fsj < doc.sections.length; _fsj++) {{
                        if (doc.sections[_fsj].pageStart === _overflowPg) {{ _secExistsF = true; break; }}
                    }}
                    if (!_secExistsF) {{
                        var _finSec = doc.sections.add(_overflowPg);
                        _finSec.marker = "3";
                        _finSec.continueNumbering = true;
                        log("grammar overflow final section marker=3 at page " + _grammarOverflowStart);
                    }}
                }} catch(eFS) {{}}
            }}
        }} catch(eGF) {{ log("grammar overflow section err=" + eGF.message); }}
    }}

    // ========================================
    // 4a. D-마스터: 서술형 영작 섹션 첫 페이지가 RIGHT이면 적용
    // ========================================
    try {{
        var mA2 = doc.masterSpreads.itemByName("A-chapter1");
        var mD2 = doc.masterSpreads.itemByName("D-\\uB9C8\\uC2A4\\uD130");
        if (mA2.isValid && mD2.isValid) {{
            // 기존 D-마스터를 모두 A-chapter1로 복원
            for (var dpi2 = 0; dpi2 < doc.pages.length; dpi2++) {{
                try {{
                    if (doc.pages[dpi2].appliedMaster === mD2) {{
                        doc.pages[dpi2].appliedMaster = mA2;
                    }}
                }} catch(e) {{}}
            }}
            // 서술형 영작 스토리의 첫 페이지 찾기
            if (wStoryIdx2 >= 0) {{
                try {{
                    var wFirstPg = doc.stories[wStoryIdx2].textContainers[0].parentPage;
                    if (wFirstPg && (wFirstPg.side == 1919382632 || wFirstPg.side == PageSideOptions.RIGHT_HAND)) {{
                        wFirstPg.appliedMaster = mD2;
                        log("D-master applied to writing firstPage off=" + wFirstPg.documentOffset);
                    }} else if (wFirstPg) {{
                        log("writing firstPage is LEFT off=" + wFirstPg.documentOffset + " -> no D-master");
                    }}
                    // 서술형 영작 첫 페이지에 섹션 마커 "4" 설정
                    if (wFirstPg) {{
                        var wSecExists = false;
                        for (var wsi = 0; wsi < doc.sections.length; wsi++) {{
                            if (doc.sections[wsi].pageStart === wFirstPg) {{ wSecExists = true; break; }}
                        }}
                        if (!wSecExists) {{
                            var wSec = doc.sections.add(wFirstPg);
                            wSec.marker = "4";
                            wSec.continueNumbering = true;
                            log("writing section marker=4 at page " + wFirstPg.documentOffset);
                        }}
                    }}
                }} catch(e) {{
                    log("D-master writing err=" + e.message);
                }}
            }}
        }}
    }} catch(e) {{
        log("D-master err=" + e.message);
    }}

    // Vol2 \u017D/\u017E (Ž/ž) 특수문자 폰트 깨짐 수정 — 함초롬돋움 폰트 적용 (글자 유지)
    try {{
        var _fontCandsZV2 = [
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0\\tRegular",
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0",
            "\\uD568\\uCD08\\uB86C \\uB3CB\\uC6C0",
            "HCR Dotum\\tRegular",
            "HCR Dotum"
        ];
        var _fntZV2 = null;
        var _fntZV2Name = null;
        for (var _fiV2 = 0; _fiV2 < _fontCandsZV2.length; _fiV2++) {{
            try {{
                var _fV2 = app.fonts.itemByName(_fontCandsZV2[_fiV2]);
                if (_fV2 && _fV2.isValid) {{ _fntZV2 = _fV2; _fntZV2Name = _fontCandsZV2[_fiV2]; break; }}
            }} catch(eFCV) {{}}
        }}
        if (_fntZV2) {{
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = "[\\u017D\\u017E]";
            app.changeGrepPreferences.appliedFont = _fntZV2;
            var _zChangedV2 = doc.changeGrep();
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            log("Zz font applied V2: " + _fntZV2Name + " count=" + (_zChangedV2 ? _zChangedV2.length : 0));
        }} else {{
            log("Zz font missing V2: \\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0");
        }}
    }} catch(eZfV2) {{ log("Zz char err V2: " + eZfV2.message); }}

    // Vol2 아래/위 첨자 유니코드 (U+2070~U+209F) 폰트 교체 — 한컴 함초롬돋움 우선, 미설치 시 NanumGothic/Apple SD 폴백
    // 본문 폰트(Noto 계열 등)에 글리프가 없어 화학식의 ₂가 누락 사각형으로 출력되는 문제 해결.
    try {{
        var _hcFontV2 = null;
        var _fontCandV2 = [
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0\\tRegular",
            "\\uD568\\uCD08\\uB86C\\uB3CB\\uC6C0",
            "NanumGothic\\tRegular",
            "NanumGothic",
            "Nanum Gothic\\tRegular",
            "AppleSDGothicNeo\\tRegular",
            "AppleSDGothicNeo-Regular",
            "Apple SD Gothic Neo\\tRegular"
        ];
        for (var _fciV2 = 0; _fciV2 < _fontCandV2.length; _fciV2++) {{
            try {{
                var _fV2 = app.fonts.itemByName(_fontCandV2[_fciV2]);
                if (_fV2 && _fV2.isValid) {{ _hcFontV2 = _fV2; break; }}
            }} catch(eFCV2) {{}}
        }}
        if (_hcFontV2) {{
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            app.findGrepPreferences.findWhat = "[\\u2070-\\u209F]";
            app.changeGrepPreferences.appliedFont = _hcFontV2;
            var _subChangedV2 = doc.changeGrep();
            app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING;
            log("subscript font applied V2 count=" + (_subChangedV2 ? _subChangedV2.length : 0));
        }} else {{
            log("subscript font V2: hamchorom not found");
        }}
    }} catch(eSubV2) {{
        log("subscript font err V2: " + eSubV2.message);
        try {{ app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING; }} catch(e) {{}}
    }}

    var finalOv = 0;
    for (var i = 0; i < doc.stories.length; i++) {{ if (doc.stories[i].overflows) finalOv++; }}
    log("finalPages=" + doc.pages.length + " overflow=" + finalOv);

    // 마지막 페이지 (크레딧) 추가 — 마지막페이지.ai 배치
    // 크레딧 페이지는 반드시 왼쪽(짝수) 페이지에 위치해야 함
    try {{
        var lastAiPath = "/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/\\uB0B4 \\uB4DC\\uB77C\\uC774\\uBE0C/\\uCF58\\uD150\\uCE20 \\uAD00\\uB9AC/\\uB0B4\\uC2E0\\uB300\\uBE44/\\uC778\\uB514\\uC790\\uC778 \\uD30C\\uC77C/\\uD30C\\uC774\\uB110 \\uC9C1\\uC804\\uBCF4\\uCDA9/\\uB0B4\\uC9C0/\\uB9C8\\uC9C0\\uB9C9\\uD398\\uC774\\uC9C0.ai";
        var lastAiFile = new File(lastAiPath);
        if (lastAiFile.exists) {{
            var lastPg = doc.pages[-1];
            if (lastPg.side == PageSideOptions.LEFT_HAND || lastPg.side == 1818653800) {{
                var blankPg = doc.pages.add();
                try {{
                    blankPg.appliedMaster = doc.masterSpreads.itemByName("A-chapter1");
                }} catch(e) {{
                    try {{ blankPg.appliedMaster = doc.pages[1].appliedMaster; }} catch(e2) {{}}
                }}
                log("blankRightPage=inserted offset=" + blankPg.documentOffset);
            }}
            var creditPage = doc.pages.add();
            creditPage.appliedMaster = NothingEnum.NOTHING;
            var rect = creditPage.rectangles.add({{
                geometricBounds: [-3, -3, 300, 213]
            }});
            rect.place(lastAiFile);
            try {{ rect.fit(FitOptions.FILL_PROPORTIONALLY); }} catch(e) {{}}
            log("creditPage=ok side=" + creditPage.side + " offset=" + creditPage.documentOffset);
        }} else {{
            log("creditPage=aiNotFound");
        }}
    }} catch(e) {{
        log("creditPageErr=" + e.message);
    }}

    // 직전보충: PDF 미내보내기 — 인디자인 파일(.indd)만 생성
    log("pdf=skip");

    // Ruler origin 원상 복구 (저장 전)
    try {{
        if (_origRulerOrigin !== null) doc.viewPreferences.rulerOrigin = _origRulerOrigin;
    }} catch(eRO2) {{}}

    doc.save();
    // 조판 결과는 닫지 않고 열어둠 (결과 즉시 확인용)

}} catch(ex) {{
    log("ERROR=" + ex.message);
    try {{ app.activeDocument.close(SaveOptions.NO); }} catch(e2) {{}}
}}

app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
var mf = new File("{marker}"); mf.open("w"); mf.write("done"); mf.close();
var lf = new File("{log_file}"); lf.open("w"); lf.encoding="UTF-8"; lf.write(L.join("\\n")); lf.close();
"""
