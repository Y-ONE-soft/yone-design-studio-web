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


def _build_vocab_jsx(indd_path, left_json_path, right_json_path, marker, log_file, pid=0):
    """중요어휘 전용 JSX — Vol1 문서를 열고 새 페이지에 왼/오 프레임 생성."""
    return f"""#target indesign
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
var L = [];
function log(m) {{ L.push(m); }}

try {{
    var doc = app.open(File("{indd_path}"));
    log("opened=" + doc.pages.length + "p");

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

    // 기존 중요어휘 빈 프레임 수집
    // 원본 구조: 각 페이지에 독립(non-threaded) 프레임 2~3개
    // 왼쪽(상단, y<110) + 오른쪽(하단, y>=105) + 라벨(음수 x좌표)
    // 콘텐츠 프레임(문장배열/문장삽입) 바운드 — 이 패턴에 맞는 프레임이 있으면 중요어휘 아님
    var vEvenB = [[27,18,153,101],[153,18,279,101],[27,105,153,188],[153,105,279,188]];
    var vOddB  = [[27,22,153,105],[153,22,279,105],[27,109,153,192],[153,109,279,192]];
    var vocabPages = [];
    for (var vpi = 2; vpi < doc.pages.length; vpi++) {{
        var vpg = doc.pages[vpi];
        var vpItems = vpg.allPageItems;
        var lFrame = null, rFrame = null;
        // 콘텐츠 프레임 바운드 매칭으로 문장배열/문장삽입 페이지 스킵
        var hasContentFrame = false;
        var vRef = (vpg.documentOffset % 2 === 0) ? vOddB : vEvenB;
        for (var vii = 0; vii < vpItems.length; vii++) {{
            if (vpItems[vii].constructor.name !== "TextFrame") continue;
            var vcgb = vpItems[vii].geometricBounds;
            for (var vri = 0; vri < vRef.length; vri++) {{
                if (Math.abs(vcgb[0] - vRef[vri][0]) < 8 &&
                    Math.abs(vcgb[1] - vRef[vri][1]) < 8 &&
                    Math.abs(vcgb[2] - vRef[vri][2]) < 8 &&
                    Math.abs(vcgb[3] - vRef[vri][3]) < 8) {{
                    hasContentFrame = true; break;
                }}
            }}
            if (hasContentFrame) break;
        }}
        if (hasContentFrame) continue; // 콘텐츠 페이지 스킵

        for (var vii2 = 0; vii2 < vpItems.length; vii2++) {{
            if (vpItems[vii2].constructor.name !== "TextFrame") continue;
            var vgb = vpItems[vii2].geometricBounds;
            // bounds = [top, left, bottom, right]
            var vTop = vgb[0];  // top 좌표
            var vLeft = vgb[1]; // left 좌표
            if (vLeft < 0 || vTop < 0) continue; // 라벨 프레임(음수 좌표) 스킵
            // 좌/우 칼럼 구분: left 좌표 기준 (왼쪽 x~18-22, 오른쪽 x~105-109)
            if (vLeft < 70) {{
                if (!lFrame) lFrame = vpItems[vii2];
            }} else {{
                if (!rFrame) rFrame = vpItems[vii2];
            }}
        }}
        if (lFrame && rFrame) {{
            vocabPages.push({{page: vpg, left: lFrame, right: rFrame}});
        }}
    }}
    log("vocabSlots=" + vocabPages.length);

    // 중요어휘 섹션 첫 페이지에 D-마스터 적용 (오른쪽 페이지인 경우)
    if (vocabPages.length > 0 && dMasterVocab) {{
        var vocFirstPg = vocabPages[0].page;
        try {{
            var isVocRight = (vocFirstPg.side == PageSideOptions.RIGHT_HAND) ||
                             (vocFirstPg.side == 1919382632);
            if (isVocRight) {{
                vocFirstPg.appliedMaster = dMasterVocab;
                log("D-master applied to vocab page " + vocFirstPg.documentOffset);
            }}
        }} catch(e) {{}}
    }}

    // 문자스타일 [없음]
    var csNone = doc.characterStyles[0]; // [없음] or [None]

    // 기존 슬롯을 페이지 순서로 정렬
    vocabPages.sort(function(a, b) {{
        return a.page.documentOffset - b.page.documentOffset;
    }});

    // 오른쪽 프레임 배경색 스워치
    var grayFill = null;
    try {{ grayFill = doc.swatches.itemByName("[\\uAC80\\uC815] 5%"); }} catch(e) {{}}
    if (!grayFill) try {{ grayFill = doc.swatches.itemByName("[Black] 5%"); }} catch(e) {{}}

    // 문서 텍스트 기본값 초기화 — 새 프레임에 엉뚱한 문자스타일 방지
    try {{ doc.textDefaults.appliedCharacterStyle = csNone; }} catch(e) {{}}

    // 기존 프레임에 데이터 채우기
    var filled = 0;
    for (var vfi = 0; vfi < vocabCount; vfi++) {{
        var lFrame, rFrame;
        if (vfi < vocabPages.length) {{
            lFrame = vocabPages[vfi].left;
            rFrame = vocabPages[vfi].right;
        }} else {{
            // 기존 슬롯 부족 시 새 페이지 추가
            var newPg = doc.pages.add();
            if (master) newPg.appliedMaster = master;
            var npEven = (newPg.documentOffset % 2 === 0);
            var lB = npEven ? [27,22,279,105] : [27,18,279,101];
            lFrame = newPg.textFrames.add({{geometricBounds: lB}});
            lFrame.textFramePreferences.insetSpacing = [3,0,0,0];
            var rB = npEven ? [27,109,223,192] : [27,105,223,188];
            rFrame = newPg.textFrames.add({{geometricBounds: rB}});
            rFrame.textFramePreferences.insetSpacing = [3,0,6,0];
            if (grayFill) try {{ rFrame.fillColor = grayFill; }} catch(e) {{}}
        }}

        if (vfi < passL.length && passL[vfi] && passL[vfi].length > 2) {{
            var leftText = passL[vfi].replace(/\\n/g, "\\r");
            lFrame.parentStory.contents = leftText;
            if (psLeft) try {{
                lFrame.parentStory.paragraphs.everyItem().appliedParagraphStyle = psLeft;
            }} catch(e) {{}}
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
            var rightText = passR[vfi].replace(/\\n/g, "\\r");
            rFrame.parentStory.contents = rightText;
            if (psRight) try {{
                rFrame.parentStory.paragraphs.everyItem().appliedParagraphStyle = psRight;
            }} catch(e) {{}}
            if (grayFill) try {{ rFrame.fillColor = grayFill; }} catch(e) {{}}
            // 오른쪽 프레임: 오버플로우 시 아래로만 확장
            try {{
                if (rFrame.parentStory.overflows) {{
                    rFrame.textFramePreferences.autoSizingType = AutoSizingTypeEnum.HEIGHT_ONLY;
                    rFrame.textFramePreferences.autoSizingReferencePoint = AutoSizingReferenceEnum.TOP_LEFT_POINT;
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

    // 남은 빈 중요어휘 페이지 삭제
    for (var rpi = vocabPages.length - 1; rpi >= vocabCount; rpi--) {{
        try {{ vocabPages[rpi].page.remove(); }} catch(e) {{}}
    }}

    log("vocab=" + vocabCount + " filled=" + filled + " pages=" + doc.pages.length);

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

    // 오버플로우 확인
    var ov = 0;
    for (var i = 0; i < doc.stories.length; i++) {{ if (doc.stories[i].overflows) ov++; }}
    log("overflow=" + ov);

    // PDF 재내보내기 (한글 경로 문제 방지를 위해 /tmp/ 경로 사용)
    var pdfPath = "{indd_path}".replace(".indd", ".pdf");
    doc.exportFile(ExportFormat.PDF_TYPE, new File(pdfPath));
    log("pdf=ok");

    doc.save();
    doc.close(SaveOptions.NO);

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
    # 기존 문서 닫기
    try:
        boot = 'while(app.documents.length>0)app.documents[0].close(SaveOptions.NO);'
        escaped = boot.replace('"', '\\"')
        subprocess.run(
            ["osascript", "-e",
             f'tell application "{app}" to do script "{escaped}" language javascript'],
            capture_output=True, text=True, timeout=15
        )
    except Exception:
        pass

    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)

    job_dir = os.path.dirname(settings_path)
    log_lines = []
    jobs = settings.get("jobs", [])

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
            jsx_code = _build_vol1_jsx(indd_path, data_path, pdf_path, marker, log_file, pid)
        else:
            jsx_code = _build_vol2_jsx(indd_path, data_path, pdf_path, marker, log_file, pid)

        jsx_path = f"/tmp/_final_{vol}_{pid}.jsx"
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(jsx_code)

        log("  JSX 실행 중...")
        _run_jsx_file(app, jsx_path, timeout=300)

        # 마커 대기
        if _wait_marker(marker, timeout=300):
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

            # /tmp/ 경로의 PDF를 실제 경로 + job_dir에 복사
            if os.path.exists(pdf_path):
                job_pdf = os.path.join(job_dir, os.path.basename(pdf_path))
                shutil.copy2(pdf_path, job_pdf)
                log(f"  PDF: {os.path.basename(pdf_path)}")
                log_lines.append(f"PDF: 성공 ({os.path.basename(pdf_path)})")
            else:
                log(f"  PDF 미생성")
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
                    vocab_marker, vocab_log_f, pid=pid
                )
                vocab_jsx_path = f"/tmp/_final_vocab_{pid}.jsx"
                with open(vocab_jsx_path, "w", encoding="utf-8") as f:
                    f.write(vocab_jsx)
                _run_jsx_file(app, vocab_jsx_path, timeout=300)
                if _wait_marker(vocab_marker, timeout=300):
                    if os.path.exists(vocab_log_f):
                        with open(vocab_log_f, encoding="utf-8") as lf:
                            for line in lf.read().strip().split("\n"):
                                log(f"  {line}")
                        os.remove(vocab_log_f)
                    os.remove(vocab_marker)
                    # vocab JSX가 /tmp/ 에 내보낸 PDF를 실제 경로 + job_dir에 복사
                    # 중요어휘 추가 후 PDF를 job_dir에 다시 복사
                    if os.path.exists(pdf_path):
                        job_pdf = os.path.join(job_dir, os.path.basename(pdf_path))
                        shutil.copy2(pdf_path, job_pdf)
                        log(f"  중요어휘 PDF 재복사: {os.path.basename(pdf_path)}")
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


def _build_vol1_jsx(indd_path, data_path, pdf_path, marker, log_file, pid):
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
            passages = []
            parts = _re.split(r"(?=^\d{6}(?:~\d{2})?$)", raw_text, flags=_re.MULTILINE)
            for part in parts:
                part = part.strip()
                if part:
                    passages.append(part)
            return passages

        def _vocab_sort_key(p):
            m = _re.match(r'^(\d{6})', p)
            return int(m.group(1)) if m else 999999

        left_passages = _split_vocab(data.get("중요어휘_왼", "") or "")
        right_passages = _split_vocab(data.get("중요어휘_오", "") or "")

        # 지문번호 기준으로 좌/우 동기화 정렬
        left_by_num = {}
        for p in left_passages:
            m = _re.match(r'^(\d{6}(?:~\d{2})?)', p)
            if m:
                left_by_num[m.group(1)] = p
        right_by_num = {}
        for p in right_passages:
            m = _re.match(r'^(\d{6}(?:~\d{2})?)', p)
            if m:
                right_by_num[m.group(1)] = p

        all_nums = sorted(set(list(left_by_num.keys()) + list(right_by_num.keys())),
                          key=lambda x: int(_re.match(r'\d{6}', x).group()) if _re.match(r'\d{6}', x) else 999999)

        sorted_left = [left_by_num.get(n, "") for n in all_nums]
        sorted_right = [right_by_num.get(n, "") for n in all_nums]

        for passages, path in [(sorted_left, vocab_left_path), (sorted_right, vocab_right_path)]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(passages, f, ensure_ascii=False)
    except Exception as e:
        import traceback
        traceback.print_exc()
        for p in [vocab_left_path, vocab_right_path]:
            with open(p, "w") as f:
                json.dump([], f)


    return f"""#target indesign
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
var L = [];
function log(m) {{ L.push(m); }}

try {{
    var doc = app.open(File("{indd_path}"));
    log("opened=" + doc.pages.length + "p");

    // 기존 크레딧 페이지 삭제 (이전 실행에서 템플릿에 저장된 잔재 제거)
    for (var _cp = doc.pages.length - 1; _cp >= 0; _cp--) {{
        try {{
            var _cpg = doc.pages[_cp];
            if (_cpg.appliedMaster == NothingEnum.NOTHING || !_cpg.appliedMaster) {{
                _cpg.remove();
                log("removed old creditPage at offset=" + _cp);
                break;
            }}
        }} catch(e) {{}}
    }}

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
        if (n === "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4") psInsertC1 = allPS[i];
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
    function matchesBounds(gb, pgOff) {{
        var tol = 8;
        var ref = (pgOff % 2 === 0) ? oddBounds : evenBounds;
        for (var ri = 0; ri < ref.length; ri++) {{
            if (Math.abs(gb[0] - ref[ri][0]) < tol &&
                Math.abs(gb[1] - ref[ri][1]) < tol &&
                Math.abs(gb[2] - ref[ri][2]) < tol &&
                Math.abs(gb[3] - ref[ri][3]) < tol) {{
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
            var pgFrames = [];
            for (var fi = pg.textFrames.length - 1; fi >= 0; fi--) {{
                var tf = pg.textFrames[fi];
                var gb = tf.geometricBounds;
                if (gb[0] < 0 || gb[1] < 0) continue;
                // 4프레임 레이아웃 바운드 매칭
                if (!matchesBounds(gb, pgOff)) continue;
                pgFrames.push({{
                    frame: tf,
                    pageOff: pi,
                    isTop: gb[0] < 100,
                    bounds: [gb[0], gb[1], gb[2], gb[3]],
                    col: (gb[1] < 100) ? 0 : 1
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
    function addFramePage(beforePageRef, frames) {{
        var newPage;
        if (beforePageRef) {{
            newPage = doc.pages.add(LocationOptions.BEFORE, beforePageRef);
        }} else {{
            newPage = doc.pages.add();
        }}
        try {{
            var prevPg = doc.pages[newPage.documentOffset > 0 ? newPage.documentOffset - 1 : 0];
            if (prevPg && prevPg.appliedMaster) newPage.appliedMaster = prevPg.appliedMaster;
        }} catch(e) {{}}

        var pgOff = newPage.documentOffset;
        var bds = (pgOff % 2 === 0) ? oddBounds : evenBounds;
        var newFrames = [];
        for (var fi = 0; fi < 4; fi++) {{
            var tf = newPage.textFrames.add({{geometricBounds: bds[fi]}});
            var gb = tf.geometricBounds;
            newFrames.push({{
                frame: tf,
                pageOff: pgOff,
                isTop: gb[0] < 100,
                bounds: [gb[0], gb[1], gb[2], gb[3]],
                col: (gb[1] < 100) ? 0 : 1
            }});
        }}
        newFrames.sort(function(a, b) {{
            if (a.col !== b.col) return a.col - b.col;
            if (a.isTop !== b.isTop) return a.isTop ? -1 : 1;
            return 0;
        }});
        for (var ni = 0; ni < newFrames.length; ni++) {{
            frames.push(newFrames[ni]);
        }}
        log("addedPage off=" + pgOff);
        return newPage;
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

        if (!story.overflows) return true;

        if (fi.isTop) {{
            // 상단 프레임 -> 하단 프레임 흡수
            var belowIdx = -1;
            for (var bi = frameIdx + 1; bi < frames.length; bi++) {{
                if (frames[bi].pageOff === fi.pageOff &&
                    !frames[bi].isTop &&
                    frames[bi].col === fi.col) {{
                    belowIdx = bi;
                    break;
                }}
            }}
            if (belowIdx >= 0) {{
                var below = frames[belowIdx];
                frame.geometricBounds = [fi.bounds[0], fi.bounds[1], below.bounds[2], fi.bounds[3]];
                try {{ below.frame.remove(); }} catch(e) {{}}
                frames.splice(belowIdx, 1);
                log(section + " expandTop block=" + blockIdx);
                if (story.overflows) {{
                    log(section + " STILL_OVERFLOW block=" + blockIdx);
                }}
            }}
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

            // 확장해도 넘침 -> 내용 비우고 다음 상단으로 이동
            story.contents = "";
            frame.geometricBounds = origBounds;
            return false;
        }}
    }}

    // ========================================
    // 9. 문장배열 배치
    // ========================================
    app.doScript(function() {{
        var arrEndOff = (insertStartPageOff > 0) ? insertStartPageOff - 1 : doc.pages.length - 1;
        var arrFrames = collectFrames(1, arrEndOff);
        log("arrFrames=" + arrFrames.length + " for pages 1~" + arrEndOff);

        var arrIdx = 0;
        for (var b = 0; b < blocks.length; b++) {{
            // 프레임 부족시 새 페이지 추가
            if (arrIdx >= arrFrames.length) {{
                addFramePage(insertStartPageRef, arrFrames);
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
            for (var c = 0; c < items.length; c++) {{
                story.insertionPoints[-1].contents = items[c] + "\\r";
            }}
            story.insertionPoints[-1].contents = "\\r";
            story.insertionPoints[-1].contents = "\\uFF1E \\r";

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
                }} else {{
                    if (psHeader) p[pi].appliedParagraphStyle = psHeader;
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
                    addFramePage(insertStartPageRef, arrFrames);
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

        log("arr placed=" + blocks.length + " usedFrames=" + arrIdx);
    }}, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "Vol1_arr");

    // ========================================
    // 10. 문장삽입 배치
    // ========================================
    if (insertBlocks.length > 0 && insertStartPageOff > 0) {{

        app.doScript(function() {{
            // 내용요약 시작 전까지, 없으면 중요어휘 시작 전까지
            var insEndOff = doc.pages.length - 1;
            if (summaryStartPageOff < 999) {{
                insEndOff = summaryStartPageOff - 1;
            }} else if (vocabStartPageOff < 999) {{
                insEndOff = vocabStartPageOff - 1;
            }}
            var insFrames = collectFrames(insertStartPageOff, insEndOff);
            log("insFrames=" + insFrames.length + " for pages " + insertStartPageOff + "~" + insEndOff);

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

                // 내용 삽입
                story.contents = "";
                story.insertionPoints[-1].contents = hdr + "\\r";
                for (var pi2 = 0; pi2 < paras.length; pi2++) {{
                    var txt = paras[pi2].text || "";
                    story.insertionPoints[-1].contents = txt + "\\r";
                }}

                // 스타일 적용
                var ip = story.paragraphs.everyItem().getElements();
                var paraIdx = 0;

                // 헤더 단락
                if (paraIdx < ip.length) {{
                    if (psBasic) ip[paraIdx].appliedParagraphStyle = psBasic;
                    paraIdx++;
                }}

                // 내용 단락
                for (var pi3 = 0; pi3 < paras.length; pi3++) {{
                    if (paraIdx >= ip.length) break;
                    var srcStyle = paras[pi3].style || "";

                    if (srcStyle === "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8") {{
                        if (psInsertBox) ip[paraIdx].appliedParagraphStyle = psInsertBox;
                    }} else if (srcStyle === "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8 \\uC9C0\\uBB38") {{
                        if (psInsertQ) ip[paraIdx].appliedParagraphStyle = psInsertQ;
                    }} else if (srcStyle === "\\uD558\\uB2E8 \\uBB38\\uC81C") {{
                        if (psInsertQ) ip[paraIdx].appliedParagraphStyle = psInsertQ;
                    }} else if (srcStyle === "\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8 \\uBB38\\uC81C") {{
                        if (psInsertQ) ip[paraIdx].appliedParagraphStyle = psInsertQ;
                    }} else if (srcStyle === "\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8 " || srcStyle === "\\uBB38\\uC7A5 \\uBC30\\uC5F4 \\uD558\\uB2E8") {{
                        if (psInsertBox) ip[paraIdx].appliedParagraphStyle = psInsertBox;
                    }} else if (srcStyle === "C1_\\uBB38\\uC7A5 \\uBC30\\uC5F4" || srcStyle.indexOf("C1_") === 0) {{
                        if (psInsertC1) ip[paraIdx].appliedParagraphStyle = psInsertC1;
                    }} else {{
                        var t = (ip[paraIdx].contents || "").replace(/\\r$/, "");
                        if (/^\\uC544\\uB798/.test(t)) {{
                            if (psInsertC1) ip[paraIdx].appliedParagraphStyle = psInsertC1;
                        }} else if (/^\\s{{4,}}/.test(t) && !/^\\s*\\(/.test(t)) {{
                            if (psInsertBox) ip[paraIdx].appliedParagraphStyle = psInsertBox;
                        }} else {{
                            if (psInsertQ) ip[paraIdx].appliedParagraphStyle = psInsertQ;
                        }}
                    }}
                    paraIdx++;
                }}

                // 오버플로우 처리
                var placed = handleOverflow(insFrames, insIdx, "ins", b);
                if (!placed) {{
                    var nextTop = -1;
                    for (var ni = insIdx + 1; ni < insFrames.length; ni++) {{
                        if (insFrames[ni].isTop) {{ nextTop = ni; break; }}
                    }}
                    if (nextTop < 0) {{
                        addFramePage(summaryStartPageRef || vocabStartPageRef, insFrames);
                        for (var ni2 = insIdx + 1; ni2 < insFrames.length; ni2++) {{
                            if (insFrames[ni2].isTop) {{ nextTop = ni2; break; }}
                        }}
                    }}
                    if (nextTop >= 0) {{
                        insIdx = nextTop;
                        b--;
                        continue;
                    }} else {{
                        log("ins CANNOT_PLACE block=" + b);
                    }}
                }}
                insIdx++;
            }}

            log("ins placed=" + insertBlocks.length + " usedFrames=" + insIdx);
        }}, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "Vol1_ins");
    }} else {{
        log("insert=skip (no blocks or no section)");
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
            var vBounds = (vNewPage.documentOffset % 2 === 0) ?
                [27,22,279,105] : [27,18,279,101];
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
            if (matchesBounds(rgb, rpg.documentOffset)) {{ hasContentBounds = true; break; }}
        }}
        if (!hasContentBounds && rpItems2.length > 0) continue; // 콘텐츠 아닌 프레임이 있는 페이지(중요어휘/내용요약) 보호

        var hasContent = false;
        var rpgItems = rpg.allPageItems;
        for (var rii = 0; rii < rpgItems.length; rii++) {{
            if (rpgItems[rii].constructor.name === "TextFrame") {{
                try {{
                    var rtxt = rpgItems[rii].contents.replace(/[\\r\\s]/g, "");
                    if (rtxt.length > 0) {{ hasContent = true; break; }}
                }} catch(e) {{}}
            }}
        }}
        if (!hasContent && rpgItems.length > 0) {{
            try {{ rpg.remove(); removedPages++; }} catch(e) {{}}
        }}
    }}
    if (removedPages > 0) log("removedPages=" + removedPages);

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
            // 2) find first page with insert content
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
            // 3) RIGHT이면 D-마스터 적용
            if (insFirstPage && insFirstPage.side == 1919382632) {{
                insFirstPage.appliedMaster = mD;
                log("D-master applied to ins firstPage off=" + insFirstPage.documentOffset);
            }} else if (insFirstPage) {{
                log("ins firstPage is LEFT off=" + insFirstPage.documentOffset + " -> no D-master");
            }}
        }}
    }} catch(e) {{
        log("D-master err=" + e.message);
    }}

    // 크레딧 페이지는 Vocab JSX에서 마지막에 추가 (Vol1 JSX에서는 추가하지 않음)

    // ========================================
    // 13. 최종 로그 + PDF + 저장
    // ========================================
    var finalOv = 0;
    for (var fsi = 0; fsi < doc.stories.length; fsi++) {{
        if (doc.stories[fsi].overflows) finalOv++;
    }}
    log("finalPages=" + doc.pages.length + " overflow=" + finalOv);

    doc.exportFile(ExportFormat.PDF_TYPE, new File("{pdf_path}"));
    log("pdf=ok");

    doc.save();
    doc.close(SaveOptions.NO);

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
                        /^\\d{{6}}/.test(lineText);

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

    for (var oi = 0; oi < overflowStories.length; oi++) {{
        var ovStory = doc.stories[overflowStories[oi]];
        var added = 0;
        while (ovStory.overflows && added < 30) {{
            var lastF = ovStory.textContainers[ovStory.textContainers.length - 1];

            // 마스터 페이지 결정
            var storyMaster = null;
            try {{ storyMaster = ovStory.textContainers[0].parentPage.appliedMaster; }} catch(e) {{}}

            var np = doc.pages.add();
            if (storyMaster) np.appliedMaster = storyMaster;

            var pgIdx = np.documentOffset;
            var bnds = (pgIdx % 2 === 0) ? v2OddBounds : v2EvenBounds;
            var prev = lastF;
            for (var fi = 0; fi < bnds.length; fi++) {{
                var ntf = np.textFrames.add({{geometricBounds: bnds[fi]}});
                prev.nextTextFrame = ntf;
                prev = ntf;
            }}
            added++;
        }}
        if (added > 0) log("story" + overflowStories[oi] + " addedPages=" + added);
    }}

    // ========================================
    // 4. 빈 페이지 삭제 (threaded 텍스트프레임만 체크)
    // ========================================
    for (var pi = doc.pages.length - 1; pi >= 2; pi--) {{
        var pg = doc.pages[pi];
        var hasC = false;
        var pItems = pg.allPageItems;
        for (var ii = 0; ii < pItems.length; ii++) {{
            if (pItems[ii].constructor.name === "TextFrame") {{
                try {{
                    // threaded 프레임만 체크 (previousTextFrame 또는 nextTextFrame이 있는 것)
                    var isThreaded = false;
                    try {{ isThreaded = (pItems[ii].previousTextFrame != null || pItems[ii].nextTextFrame != null); }} catch(e2) {{}}
                    if (!isThreaded) continue;  // 마스터 페이지 아이템은 threaded 아님

                    var ft = pItems[ii].contents.replace(/[\\r\\s]/g, "");
                    if (ft.length > 0) {{ hasC = true; break; }}
                }} catch(e) {{}}
            }}
        }}
        if (!hasC) {{ try {{ pg.remove(); }} catch(e) {{}} }}
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
                }} catch(e) {{
                    log("D-master writing err=" + e.message);
                }}
            }}
        }}
    }} catch(e) {{
        log("D-master err=" + e.message);
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

    doc.exportFile(ExportFormat.PDF_TYPE, new File("{pdf_path}"));
    log("pdf=ok");
    doc.save();
    doc.close(SaveOptions.NO);

}} catch(ex) {{
    log("ERROR=" + ex.message);
    try {{ app.activeDocument.close(SaveOptions.NO); }} catch(e2) {{}}
}}

app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
var mf = new File("{marker}"); mf.open("w"); mf.write("done"); mf.close();
var lf = new File("{log_file}"); lf.open("w"); lf.encoding="UTF-8"; lf.write(L.join("\\n")); lf.close();
"""
