"""파이널 직전보충 — 워크북 .indd에서 텍스트 추출.

워크북 파일을 InDesign으로 열고, 단락 스타일 기반으로
문장배열/어법수정/영작배열 텍스트를 JSON으로 추출한다.
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


def _jsx(app_name, code, timeout=30, retries=3):
    """작은 JSX 코드를 InDesign에서 실행."""
    escaped = code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    script = f'tell application "{app_name}" to do script "{escaped}" language javascript'

    for attempt in range(retries):
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            time.sleep(3)
            continue

        if result.returncode == 0:
            return result.stdout.strip()

        stderr = result.stderr.strip()
        if "30486" in stderr:
            _dismiss_indesign_dialogs(app_name)
            time.sleep(3)
            continue
        if "-609" in stderr:
            time.sleep(5)
            continue

        raise RuntimeError(f"JSX 에러: {stderr[:200]}")

    raise RuntimeError("JSX 재시도 횟수 초과")


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


def _run_jsx_file(app_name, jsx_path, timeout=120):
    """JSX 파일을 InDesign에서 실행."""
    # 한글 경로 회피: /tmp에 복사 (이미 /tmp이면 스킵)
    if jsx_path.startswith("/tmp/"):
        tmp_jsx = jsx_path
    else:
        tmp_jsx = f"/tmp/final_extract_{os.getpid()}.jsx"
        shutil.copy2(jsx_path, tmp_jsx)

    boot = (
        f'app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;'
        f'var _f = new File("{tmp_jsx}");'
        f'app.doScript(_f, ScriptLanguage.JAVASCRIPT);'
    )
    escaped = boot.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    script = f'tell application "{app_name}" to do script "{escaped}" language javascript'

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return True
        stderr = result.stderr.strip()
        # -609는 InDesign이 백그라운드에서 처리 중일 수 있음
        if "-609" in stderr:
            time.sleep(5)
            return True
        if "30486" in stderr:
            _dismiss_indesign_dialogs(app_name)
            time.sleep(3)
            return True
    except subprocess.TimeoutExpired:
        # 타임아웃이어도 InDesign이 처리 중일 수 있음
        time.sleep(5)
        return True

    return False


def _build_extract_jsx(indd_path, output_json_path, style_filters):
    """워크북에서 스타일 기반 텍스트 추출 JSX를 생성."""
    styles_js = json.dumps(style_filters, ensure_ascii=False)

    jsx = f"""#target indesign
app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;

var targetStyles = {styles_js};
var inddPath = "{indd_path.replace(chr(92), '/')}";
var outputPath = "{output_json_path.replace(chr(92), '/')}";

var doc;
try {{
    doc = app.open(File(inddPath), false);
}} catch(e) {{
    var ef = new File(outputPath);
    ef.open("w"); ef.encoding = "UTF-8";
    ef.write('{{"error":"' + e.message + '","stories":[]}}');
    ef.close();
    // exit
}}

if (doc) {{
    var results = [];

    for (var si = 0; si < doc.stories.length; si++) {{
        var st = doc.stories[si];
        if (st.paragraphs.length < 2) continue;

        var storyParas = [];
        var hasTarget = false;

        for (var pi = 0; pi < st.paragraphs.length; pi++) {{
            var para = st.paragraphs[pi];
            var styleName = "";
            try {{ styleName = para.appliedParagraphStyle.name; }} catch(e) {{}}

            var txt = para.contents;
            if (txt) txt = txt.replace(/\\r$/, "");

            // 대상 스타일 포함 여부
            for (var ti = 0; ti < targetStyles.length; ti++) {{
                if (styleName === targetStyles[ti]) {{ hasTarget = true; break; }}
            }}

            storyParas.push({{
                s: styleName,
                t: txt
            }});
        }}

        if (hasTarget && storyParas.length > 0) {{
            // 프레임 페이지 오프셋 수집
            var tc = st.textContainers;
            var framePages = [];
            for (var fpi = 0; fpi < tc.length; fpi++) {{
                try {{
                    if (tc[fpi].parentPage) framePages.push(tc[fpi].parentPage.documentOffset);
                    else framePages.push(-1);
                }} catch(e) {{ framePages.push(-1); }}
            }}

            // 페이지 갭 감지: 프레임 간 페이지 차이 > 2면 분할 지점
            var splitPoints = [0]; // 단락 인덱스 기준 분할 지점
            if (tc.length > 2) {{
                var prevPage = framePages[0];
                var paraAccum = 0;
                for (var fpi2 = 0; fpi2 < tc.length; fpi2++) {{
                    if (fpi2 > 0 && framePages[fpi2] >= 0 && prevPage >= 0) {{
                        if (framePages[fpi2] - prevPage > 2) {{
                            // 갭 발견 — 이 프레임부터 새 블록
                            // 현재 프레임의 첫 단락 인덱스 계산
                            var paraSoFar = 0;
                            for (var cfp = 0; cfp < fpi2; cfp++) {{
                                try {{ paraSoFar += tc[cfp].parentStory.textContainers[cfp].texts[0].paragraphs.length; }} catch(e) {{
                                    // 폴백: 프레임 텍스트 길이 기반 추정
                                    try {{ paraSoFar += tc[cfp].paragraphs.length; }} catch(e2) {{}}
                                }}
                            }}
                            if (paraSoFar > 0 && paraSoFar < storyParas.length) {{
                                splitPoints.push(paraSoFar);
                            }}
                        }}
                    }}
                    if (framePages[fpi2] >= 0) prevPage = framePages[fpi2];
                }}
            }}

            // 지문번호 읽기 함수
            function _readPageQNum(thePage) {{
                var pqn = "";
                if (!thePage) return pqn;
                try {{
                    var pgItems = thePage.textFrames;
                    for (var pfi = 0; pfi < pgItems.length; pfi++) {{
                        var firstLine = "";
                        try {{ firstLine = pgItems[pfi].paragraphs[0].contents.replace(/\\r$/, "").replace(/\\s/g, ""); }} catch(e3) {{ continue; }}
                        if (/^\\d{{6}}$/.test(firstLine)) {{ pqn = firstLine; break; }}
                        var numOnly = firstLine.replace(/[\\{{\\}}\\[\\]]/g, "");
                        if (/^\\d{{2}}$/.test(numOnly)) {{
                            var n = parseInt(numOnly, 10);
                            if (n >= 18 && n <= 45) {{ pqn = numOnly; break; }}
                        }}
                        var rangeClean = firstLine.replace(/[\\{{\\}}\\[\\]]/g, "").replace("-", "~");
                        if (/^\\d{{2}}~\\d{{2}}$/.test(rangeClean)) {{ pqn = rangeClean; break; }}
                    }}
                }} catch(e2) {{}}
                return pqn;
            }}

            // 분할 지점이 1개(=분할 없음)면 기존 방식
            if (splitPoints.length <= 1) {{
                var pageOff = framePages.length > 0 ? framePages[0] : -1;
                var thePage = null;
                try {{ thePage = tc[0].parentPage; }} catch(e) {{}}
                results.push({{
                    idx: si,
                    pageOff: pageOff,
                    pageQNum: _readPageQNum(thePage),
                    paras: storyParas
                }});
            }} else {{
                // 분할 지점으로 블록 나누기
                splitPoints.push(storyParas.length);
                var splitFrameIdx = 0;
                for (var spi = 0; spi < splitPoints.length - 1; spi++) {{
                    var from = splitPoints[spi];
                    var to = splitPoints[spi + 1];
                    var subParas = storyParas.slice(from, to);
                    // 해당 분할의 첫 프레임 페이지
                    var spPage = null;
                    var spOff = -1;
                    // splitFrameIdx 추적: from 이상의 단락을 포함하는 프레임
                    while (splitFrameIdx < tc.length) {{
                        try {{ spPage = tc[splitFrameIdx].parentPage; spOff = spPage.documentOffset; }} catch(e) {{}}
                        break;
                    }}
                    results.push({{
                        idx: si,
                        pageOff: spOff,
                        pageQNum: _readPageQNum(spPage),
                        paras: subParas
                    }});
                    // 다음 분할의 프레임 시작점 이동
                    for (var nfp = splitFrameIdx; nfp < tc.length; nfp++) {{
                        if (framePages[nfp] >= 0 && framePages[nfp] > framePages[splitFrameIdx] + 1) {{
                            splitFrameIdx = nfp;
                            break;
                        }}
                    }}
                }}
            }}
        }}
    }}

    // JSON 저장
    var outFile = new File(outputPath);
    outFile.open("w");
    outFile.encoding = "UTF-8";

    // ES3 JSON 직렬화
    var jsonStr = '[';
    for (var ri = 0; ri < results.length; ri++) {{
        if (ri > 0) jsonStr += ',';
        var pqn = results[ri].pageQNum || "";
        var pqnEsc = pqn.replace(/"/g, '\\\\"');
        jsonStr += '{{"idx":' + results[ri].idx + ',"pageOff":' + results[ri].pageOff + ',"pageQNum":"' + pqnEsc + '","paras":[';
        var pp = results[ri].paras;
        for (var ppi = 0; ppi < pp.length; ppi++) {{
            if (ppi > 0) jsonStr += ',';
            // 텍스트 이스케이프
            var escaped = pp[ppi].t || "";
            escaped = escaped.replace(/\\\\/g, "\\\\\\\\");
            escaped = escaped.replace(/"/g, '\\\\"');
            escaped = escaped.replace(/\\n/g, "\\\\n");
            escaped = escaped.replace(/\\t/g, "\\\\t");
            var sEsc = pp[ppi].s || "";
            sEsc = sEsc.replace(/"/g, '\\\\"');
            jsonStr += '{{"s":"' + sEsc + '","t":"' + escaped + '"}}';
        }}
        jsonStr += ']}}';
    }}
    jsonStr += ']';

    outFile.write(jsonStr);
    outFile.close();

    doc.close(SaveOptions.NO);
}}
"""
    return jsx


def extract_from_workbooks(indd_paths, style_filters, output_path, log):
    """여러 워크북 .indd에서 텍스트를 추출하여 통합 JSON 생성.

    Args:
        indd_paths: 워크북 .indd 파일 경로 리스트
        style_filters: 추출할 단락 스타일명 리스트
        output_path: 결과 JSON 저장 경로
        log: 로그 콜백 함수
    """
    app_name = _find_app()
    log(f"[추출] InDesign: {app_name}")

    # InDesign 초기화
    _dismiss_indesign_dialogs(app_name)
    try:
        _jsx(app_name,
             'while(app.documents.length>0)app.documents[0].close(SaveOptions.NO);',
             timeout=15)
    except Exception:
        pass

    all_stories = []

    for i, indd_path in enumerate(indd_paths):
        basename = os.path.basename(indd_path)
        log(f"[추출] ({i+1}/{len(indd_paths)}) {basename}")

        # 한글 경로 회피: /tmp에 복사
        tmp_indd = f"/tmp/final_wb_{os.getpid()}.indd"
        try:
            shutil.copy2(indd_path, tmp_indd)
        except Exception as e:
            log(f"  파일 복사 실패: {e}")
            continue

        # 추출 결과 경로
        tmp_result = f"/tmp/final_extract_result_{os.getpid()}.json"
        if os.path.exists(tmp_result):
            os.remove(tmp_result)

        # JSX 생성 및 실행
        jsx_code = _build_extract_jsx(tmp_indd, tmp_result, style_filters)
        jsx_path = f"/tmp/final_extract_{os.getpid()}.jsx"
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(jsx_code)

        success = _run_jsx_file(app_name, jsx_path, timeout=120)

        # 결과 대기 (로그 파일 폴링 방식)
        waited = 0
        while not os.path.exists(tmp_result) and waited < 60:
            time.sleep(2)
            waited += 2

        if os.path.exists(tmp_result):
            try:
                with open(tmp_result, encoding="utf-8") as f:
                    stories = json.load(f)
                if isinstance(stories, dict) and stories.get("error"):
                    log(f"  추출 에러: {stories['error']}")
                elif isinstance(stories, list):
                    log(f"  {len(stories)}개 스토리 추출")
                    for st in stories:
                        st["source_file"] = basename
                    all_stories.extend(stories)
            except Exception as e:
                log(f"  JSON 파싱 실패: {e}")
        else:
            log(f"  추출 결과 없음 (타임아웃)")

        # 임시 파일 정리
        for tmp in [tmp_indd, tmp_result, jsx_path]:
            try:
                os.remove(tmp)
            except Exception:
                pass

    # 통합 JSON 저장
    result = {
        "workbook_count": len(indd_paths),
        "story_count": len(all_stories),
        "stories": all_stories
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log(f"[추출] 완료: {len(all_stories)}개 스토리 → {os.path.basename(output_path)}")
    return output_path
