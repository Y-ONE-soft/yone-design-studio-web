"""분석본 .indd에서 지문 데이터 추출 — InDesign stepper 방식.

분석본 InDesign 파일을 열고 각 스토리에서 영어 본문과 한글 해석을
분리 추출하여 JSON으로 저장한다.

분석본 유형별 처리:
- 올림포스/모의고사: 영어·한글이 별도 프레임 → top 위치로 구분
- 교과서: 영어·한글이 한 프레임에 교차 → 줄 단위 분리
"""

import json
import os
import re
import subprocess
import time


def find_indesign_app():
    """실행 가능한 InDesign 앱 이름 반환."""
    for ver in ["2026", "2025", "2024", "2023"]:
        app = f"Adobe InDesign {ver}"
        if os.path.isdir(f"/Applications/{app}"):
            try:
                result = subprocess.run(
                    ["osascript", "-e",
                     f'tell application "{app}" to return running'],
                    capture_output=True, text=True, timeout=3)
                if "true" in result.stdout:
                    return app
            except subprocess.TimeoutExpired:
                pass
    for ver in ["2026", "2025", "2024", "2023"]:
        if os.path.isdir(f"/Applications/Adobe InDesign {ver}"):
            return f"Adobe InDesign {ver}"
    raise RuntimeError("Adobe InDesign을 찾을 수 없습니다.")


def _run_jsx_file(app_name, jsx_path, timeout=120):
    """InDesign에서 JSX 파일 실행."""
    bootstrap = (
        'app.scriptPreferences.userInteractionLevel = '
        'UserInteractionLevels.NEVER_INTERACT;'
        f'var _f = new File("{jsx_path}");'
        'app.doScript(_f, ScriptLanguage.JAVASCRIPT);'
        'app.scriptPreferences.userInteractionLevel = '
        'UserInteractionLevels.INTERACT_WITH_ALL;'
    )
    escaped = bootstrap.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "{app_name}" to do script "{escaped}" language javascript'
    proc = subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def extract_from_analysis(indd_paths, output_path, log=None):
    """분석본 .indd 파일들에서 지문 텍스트 추출 → JSON.

    Args:
        indd_paths: 분석본 .indd 파일 경로 리스트
        output_path: 결과 JSON 저장 경로
        log: 로그 콜백

    Returns:
        추출된 지문 데이터 dict
    """
    if log is None:
        log = lambda m: None

    app_name = find_indesign_app()
    log(f"[추출] InDesign: {app_name}")

    all_passages = []

    for indd_path in indd_paths:
        if not os.path.exists(indd_path):
            log(f"[경고] 파일 없음: {indd_path}")
            continue

        filename = os.path.basename(indd_path)
        log(f"[추출] {filename} 처리 중...")

        cat_match = re.search(r"\(([^)]+)\)", filename)
        category = cat_match.group(1) if cat_match else filename

        # JSX: 분석본 열기 → 스토리 추출 → JSON 저장
        tmp_result = output_path + ".tmp"
        extract_jsx = _build_extract_jsx(indd_path, tmp_result)

        # /tmp에 JSX 파일 저장 (한글 경로 회피)
        tmp_jsx = f"/tmp/pocketbook_extract_{os.getpid()}.jsx"
        with open(tmp_jsx, "w", encoding="utf-8") as f:
            f.write(extract_jsx)

        _run_jsx_file(app_name, tmp_jsx, timeout=120)

        if os.path.exists(tmp_result):
            with open(tmp_result, encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    passages = data.get("passages", [])
                    for p in passages:
                        p["source_file"] = filename
                        p["category"] = category
                    all_passages.extend(passages)
                    log(f"[추출] {filename}: {len(passages)}개 지문")
                except json.JSONDecodeError:
                    log(f"[경고] {filename} JSON 파싱 실패")
            os.remove(tmp_result)
        else:
            log(f"[경고] {filename} 추출 결과 없음")

        if os.path.exists(tmp_jsx):
            os.remove(tmp_jsx)

    result = {
        "type": "analysis_extract",
        "passages": all_passages,
        "total_passages": len(all_passages),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log(f"[추출] 총 {len(all_passages)}개 지문 추출 완료")
    return result


def _build_extract_jsx(indd_path, output_path):
    """분석본에서 지문을 추출하는 JSX 코드 생성.

    분석본 구조 (실측):
    왼쪽 페이지(side=1818653800):
      교과서: 영어+한글 혼합 프레임 [30,20,~217,139] 1개
      올림포스/모의: 영어 [29,20,~201,139] + 한글 [211,20,~382,139] 별도
      어법주석: [~30,145,...] (left>100 → 제외)
    오른쪽 페이지(side=1919382632):
      주제/요약문: [20,22,39,190]
    """
    indd_escaped = indd_path.replace("\\", "/")
    out_escaped = output_path.replace("\\", "/")

    return f'''// PocketbookExtract.jsx — 분석본에서 지문 추출 (교과서 혼합 프레임 대응)
(function() {{
    var inddPath = "{indd_escaped}";
    var outputPath = "{out_escaped}";

    var theDoc = null;
    var targetName = File(inddPath).name;
    for (var d = 0; d < app.documents.length; d++) {{
        if (app.documents[d].name === targetName) {{
            theDoc = app.documents[d];
            break;
        }}
    }}
    if (!theDoc) {{
        try {{ theDoc = app.open(File(inddPath)); }}
        catch(e) {{ return; }}
    }}

    function countKorean(text) {{
        var cnt = 0;
        for (var i = 0; i < text.length; i++) {{
            var c = text.charCodeAt(i);
            if ((c >= 0xAC00 && c <= 0xD7AF) || (c >= 0x1100 && c <= 0x11FF)) cnt++;
        }}
        return cnt;
    }}

    function isKoreanLine(line) {{
        if (line.length === 0) return false;
        var kr = countKorean(line);
        return kr > line.length * 0.3;
    }}

    function isMaster(pg) {{
        try {{ return pg.parent.constructor.name === "MasterSpread"; }}
        catch(e) {{ return false; }}
    }}

    // 1) 페이지별 스토리 수집
    var pageMap = {{}};
    var stories = theDoc.stories.everyItem().getElements();
    for (var s = 0; s < stories.length; s++) {{
        try {{
            var st = stories[s];
            var tc = st.textContainers[0];
            if (!tc || !tc.parentPage || isMaster(tc.parentPage)) continue;
            if (st.characters.length < 20) continue;

            var pg = tc.parentPage;
            var pgName = pg.name;
            var gb = tc.geometricBounds;

            if (!pageMap[pgName]) pageMap[pgName] = [];
            pageMap[pgName].push({{
                side: pg.side,
                top: gb[0], left: gb[1], bottom: gb[2], right: gb[3],
                chars: st.characters.length,
                content: st.contents
            }});
        }} catch(e) {{ continue; }}
    }}

    // 2) 왼쪽 페이지에서 영어+한글 추출
    var passages = [];
    for (var pgName in pageMap) {{
        var items = pageMap[pgName];

        // 왼쪽 페이지 본문 프레임만 (left < 100, 어법해설 제외)
        var bodyItems = [];
        for (var i = 0; i < items.length; i++) {{
            if (items[i].side != 1818653800) continue;
            if (items[i].left > 100) continue;
            if (items[i].chars < 50) continue;
            bodyItems.push(items[i]);
        }}

        if (bodyItems.length === 0) continue;

        var finalEng = "";
        var finalKor = "";
        var title = "";

        if (bodyItems.length >= 2) {{
            // ── 올림포스/모의고사: 영어·한글 별도 프레임 ──
            bodyItems.sort(function(a, b) {{ return a.top - b.top; }});
            var engItem = bodyItems[0];
            var korItem = bodyItems[1];
            if (countKorean(engItem.content.substring(0, 300)) >
                countKorean(korItem.content.substring(0, 300))) {{
                var tmp = engItem; engItem = korItem; korItem = tmp;
            }}

            // 영어: 한글 라인 제거, 연속 텍스트화
            var engLines = engItem.content.split("\\r");
            var pureEng = [];
            for (var e = 0; e < engLines.length; e++) {{
                var ln = engLines[e].replace(/^\\s+|\\s+$/g, "");
                if (ln.length > 0 && !isKoreanLine(ln)) {{
                    // 문장번호 제거: "1 Our environment..." → "Our environment..."
                    ln = ln.replace(/^\\d+\\s+/, "");
                    pureEng.push(ln);
                }}
            }}
            finalEng = pureEng.join(" ");

            // 한글: 제목(첫 줄 영어) 분리
            var korLines = korItem.content.split("\\r");
            var pureKor = [];
            for (var k = 0; k < korLines.length; k++) {{
                var kl = korLines[k].replace(/^\\s+|\\s+$/g, "");
                if (kl.length === 0) continue;
                if (pureKor.length === 0 && !isKoreanLine(kl)) {{
                    title = kl;
                }} else {{
                    pureKor.push(kl);
                }}
            }}
            finalKor = pureKor.join(" ");

        }} else {{
            // ── 교과서: 영어+한글 혼합 프레임 ──
            var mixed = bodyItems[0].content;
            var lines = mixed.split("\\r");
            var engParts = [];
            var korParts = [];

            for (var m = 0; m < lines.length; m++) {{
                var ml = lines[m].replace(/^\\s+|\\s+$/g, "");
                if (ml.length === 0) continue;

                if (isKoreanLine(ml)) {{
                    korParts.push(ml);
                }} else {{
                    // 제목 감지 (첫 영어 줄이 짧고 문장번호 없음)
                    if (engParts.length === 0 && !(/^\\d+\\s/).test(ml) && ml.length < 60) {{
                        title = ml;
                    }} else {{
                        // 문장번호 제거
                        ml = ml.replace(/^\\d+\\s+/, "");
                        engParts.push(ml);
                    }}
                }}
            }}
            finalEng = engParts.join(" ");
            finalKor = korParts.join(" ");
        }}

        // 연속 공백 정리
        finalEng = finalEng.replace(/\\s{{2,}}/g, " ").replace(/^\\s+|\\s+$/g, "");
        finalKor = finalKor.replace(/\\s{{2,}}/g, " ").replace(/^\\s+|\\s+$/g, "");

        if (finalEng.length > 20 || finalKor.length > 20) {{
            // 지문번호 추출 (카테고리 프레임: top<5, left<50)
            var passageNo = "";
            for (var ni = 0; ni < items.length; ni++) {{
                if (items[ni].side == 1818653800 && items[ni].top < 5 && items[ni].left < 50) {{
                    passageNo = items[ni].content.replace(/^\\s+|\\s+$/g, "");
                    break;
                }}
            }}

            passages.push({{
                page: pgName,
                title: title,
                english: finalEng,
                korean: finalKor,
                passage_no: passageNo,
                engChars: finalEng.length,
                korChars: finalKor.length
            }});
        }}
    }}

    // 페이지 번호순 정렬
    passages.sort(function(a, b) {{ return parseInt(a.page) - parseInt(b.page); }});

    // 3) 오른쪽 페이지에서 주제/요약문 추출
    for (var p = 0; p < passages.length; p++) {{
        var nextPg = String(parseInt(passages[p].page) + 1);
        if (!pageMap[nextPg]) continue;
        var rightItems = pageMap[nextPg];
        for (var r = 0; r < rightItems.length; r++) {{
            if (rightItems[r].side == 1919382632 && rightItems[r].top < 45 && rightItems[r].chars > 30) {{
                passages[p].topic = rightItems[r].content.substring(0, 500);
                break;
            }}
        }}
    }}

    // 4) JSON 저장
    function escJ(s) {{
        if (!s) return "";
        var r = "";
        for (var ci = 0; ci < s.length; ci++) {{
            var ch = s.charCodeAt(ci);
            if (ch === 0x5C) r += "\\\\\\\\";      // backslash
            else if (ch === 0x22) r += '\\\\"';  // double quote
            else if (ch === 0x0D) r += "\\\\r";  // CR
            else if (ch === 0x0A) r += "\\\\n";  // LF
            else if (ch === 0x09) r += "\\\\t";  // tab
            else if (ch < 0x20) r += "";         // 기타 제어문자 제거
            else r += s.charAt(ci);
        }}
        return r;
    }}
    var json = '{{"passages":[';
    for (var j = 0; j < passages.length; j++) {{
        if (j > 0) json += ",";
        var pp = passages[j];
        json += '{{';
        json += '"page":"' + escJ(pp.page) + '",';
        json += '"title":"' + escJ(pp.title || "") + '",';
        json += '"english":"' + escJ(pp.english) + '",';
        json += '"korean":"' + escJ(pp.korean) + '",';
        json += '"passage_no":"' + escJ(pp.passage_no || "") + '",';
        json += '"engChars":' + pp.engChars + ',';
        json += '"korChars":' + pp.korChars;
        if (pp.topic) json += ',"topic":"' + escJ(pp.topic) + '"';
        json += '}}';
    }}
    json += ']}}';

    var outFile = new File(outputPath);
    outFile.open("w");
    outFile.encoding = "UTF-8";
    outFile.write(json);
    outFile.close();
}})();
'''
