// [ENGINE TEMPLATE] 동형모의고사 조판 JSX
// /var/folders/lm/y0vv243n1nq4zvkjjplcj9tc0000gn/T/mockexam_test_gqcgyl0o/.settings.json 는 engine.py에서 실제 경로로 치환됨
#target indesign

(function() {
    var settingsPath = "/var/folders/lm/y0vv243n1nq4zvkjjplcj9tc0000gn/T/mockexam_test_gqcgyl0o/.settings.json";

    // ── 유틸 ─────────────────────────────────────────────────────────────────

    function readJSON(path) {
        var f = new File(path);
        f.encoding = "UTF-8";
        if (!f.open("r")) throw new Error("파일 열기 실패: " + path);
        var raw = f.read();
        f.close();
        return eval("(" + raw + ")");
    }

    function writeLog(logPath, msg) {
        var f = new File(logPath);
        f.encoding = "UTF-8";
        f.open("a");
        var now = new Date();
        var ts = "[" + ("0" + now.getHours()).slice(-2) + ":" +
                 ("0" + now.getMinutes()).slice(-2) + ":" +
                 ("0" + now.getSeconds()).slice(-2) + "] ";
        f.writeln(ts + msg);
        f.close();
    }

    function resetGrep() {
        app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.nothing;
        app.findTextPreferences = app.changeTextPreferences = NothingEnum.nothing;
    }

    // Dingbat 원문자(U+2780~U+2784) → 표준 원문자(U+2460~U+2464) 치환
    // 두 글리프 모두 BMP 1글자이므로 길이/인덱스 보존됨 → runs 오프셋 안전
    var DINGBAT_CIRCLED = {
        "\u2780": "\u2460", // ➀ → ①
        "\u2781": "\u2461", // ➁ → ②
        "\u2782": "\u2462", // ➂ → ③
        "\u2783": "\u2463", // ➃ → ④
        "\u2784": "\u2464"  // ➄ → ⑤
    };

    function normalizeCircledDigits(text) {
        if (!text) return text;
        var out = "";
        for (var i = 0; i < text.length; i++) {
            var ch = text.charAt(i);
            out += DINGBAT_CIRCLED[ch] || ch;
        }
        // InDesign 메타문자 리터럴 '^8' → '• ' (불릿 + 공백). 2글자 → 2글자.
        out = out.replace(/\^8/g, "\u2022 ");
        return out;
    }

    // 학교별 단락 스타일 alias 매핑
    // 표준 pstyle → 해당 학교에서 실제 사용하는 스타일 이름
    var STYLE_ALIAS = {
        "명일여고": {
            // 명일 final indd: 박스 = '테두리_순서삽입' / '테두리_조건' / '테두리_보기'
            // 요약·순서 박스는 모두 '테두리_순서삽입'으로 통일
            "테두리_요약": "테두리_순서삽입",
            "테두리_순서": "테두리_순서삽입"
        },
        "배재고": {
            // 배재 final indd: 박스 = '보기 테두리', 순서지문 = '영어지문-순서'
            "테두리_조건": "보기 테두리",
            "테두리_보기": "보기 테두리",
            "테두리_요약": "보기 테두리",
            "테두리_순서": "보기 테두리",
            "테두리_순서삽입": "보기 테두리",
            "지문_순서": "영어지문-순서"
        },
        "상일여고": {
            // 상일 final indd: 모든 박스류 = '테두리'
            "테두리_조건": "테두리",
            "테두리_보기": "테두리",
            "테두리_요약": "테두리",
            "테두리_순서": "테두리",
            "테두리_순서삽입": "테두리"
        },
        "성덕고": {
            // 성덕 final indd: 모든 박스류 = '테두리'
            "테두리_조건": "테두리",
            "테두리_보기": "테두리",
            "테두리_요약": "테두리",
            "테두리_순서": "테두리",
            "테두리_순서삽입": "테두리"
        },
        "한영고": {
            // 한영 final indd: 학년/회차별 다양 — 미정의 박스만 '테두리' fallback
            // (테두리_조건/테두리_보기/테두리_순서는 indd에 존재하므로 그대로)
            "테두리_요약": "테두리",
            "테두리_순서삽입": "테두리"
        },
        "강동고": {
            // 강동 final indd: 박스 = '테두리'/'테두리_보기'/'테두리_조건'/'테두리_대화'
            // 학년2의 번호_영어/테두리_대화는 parser에서 직접 출력 시 활용
            "테두리_요약": "테두리",
            "테두리_순서": "테두리",
            "테두리_순서삽입": "테두리"
        }
    };

    function resolveStyleName(school, name) {
        var aliasMap = STYLE_ALIAS[school];
        if (aliasMap && aliasMap[name]) return aliasMap[name];
        return name;
    }

    // 단락 스타일 가져오기 (없으면 생성, 그룹 안도 검색)
    function getPStyle(doc, name) {
        var ps = doc.paragraphStyles.itemByName(name);
        if (ps.isValid) return ps;
        // 그룹 안 검색 (한영2/3 같은 케이스)
        for (var i = 0; i < doc.paragraphStyleGroups.length; i++) {
            var ps2 = doc.paragraphStyleGroups[i].paragraphStyles.itemByName(name);
            if (ps2.isValid) return ps2;
        }
        // 없으면 기본 단락 기반으로 생성
        return doc.paragraphStyles.add({name: name});
    }

    // 문자 스타일 가져오기 (밑줄)
    function getUnderlineCStyle(doc) {
        var cs = doc.characterStyles.itemByName("밑줄");
        if (cs.isValid) return cs;
        return doc.characterStyles.add({name: "밑줄", underline: true});
    }

    // ── 마스터 페이지 시험 정보 교체 ──────────────────────────────────────────

    // examDate "2026.4.23(수)" -> {year, month, day, weekday}
    function parseExamDate(s) {
        if (!s) return null;
        var m = s.match(/(\d{4})\.(\d{1,2})\.(\d{1,2})\.?\s*(?:\(([^)]*)\))?/);
        if (!m) return null;
        return {year: m[1], month: m[2], day: m[3], weekday: m[4] || ""};
    }

    // examType "1학기 중간고사" -> {semester, name}
    function parseExamType(s) {
        if (!s) return null;
        var m = s.match(/(\d)\s*학기\s*(.+?)\s*고사/);
        if (!m) return null;
        return {semester: m[1], name: m[2]};
    }

    function pad2(s) { s = String(s); return s.length < 2 ? "0" + s : s; }

    // 학교별 정규식 치환 패턴 목록 생성
    function getMasterPatterns(school, data) {
        var d = parseExamDate(data.exam_date);
        var t = parseExamType(data.exam_type);
        if (!d || !t) return [];

        var YEAR = d.year;
        var MM = pad2(d.month);
        var DD = pad2(d.day);
        var W = d.weekday;
        var SEM = t.semester;
        var NAME = t.name;
        var EXAM_TYPE_FULL = SEM + "학기 " + NAME + "고사";

        // 시험명 치환 (학년도+학기+고사 한 덩어리)
        var P_FULL_NAME = {
            re: /\d{4}학년도(\s*\([^)]*\))?\s*\d학기\s*[가-힣]+고사/g,
            rep: function(match, paren) {
                return YEAR + "학년도" + (paren || "") + " " + EXAM_TYPE_FULL;
            }
        };
        // 학년도만 단독 치환 (위가 안 잡힌 경우용 — but 사용 안 함)
        // 명일/광문 형태 [ N ]학기 [ XX ]고사
        var P_BRACKET_EXAM = {
            re: /\[\s*\d\s*\]\s*학기\s*\[\s*[가-힣]+\s*\]\s*고사/g,
            rep: "[ " + SEM + " ]학기   [ " + NAME + " ]고사"
        };
        // 명일 형태 [ M ]월 [ D ]일
        var P_BRACKET_DATE = {
            re: /\[\s*\d{1,2}\s*\]\s*월\s*\[\s*\d{1,2}\s*\]\s*일/g,
            rep: "[ " + d.month + " ]월  [ " + d.day + " ]일"
        };
        // 한영 형태 (M)월 (D)일 (공백 허용)
        var P_PAREN_DATE = {
            re: /\(\s*\d{1,2}\s*\)\s*월\s*\(\s*\d{1,2}\s*\)\s*일/g,
            rep: "( " + d.month + " )월 ( " + d.day + " )일"
        };
        // 강동/배재 형태 YYYY.MM.DD.(W) 또는 YYYY.MM.DD.
        // 원본에 요일 자리가 있으면 새 요일로 갱신, 없으면 추가하지 않음
        var P_DOT_DATE = {
            re: /\d{4}\.\d{1,2}\.\d{1,2}\.?(\([^)]*\))?/g,
            rep: function(match, paren) {
                var base = YEAR + "." + MM + "." + DD + ".";
                if (paren) return base + (W ? "(" + W + ")" : paren);
                return base;
            }
        };
        // 성덕/광문 형태 YYYY년 M월 D일
        var P_KO_DATE = {
            re: /\d{4}년\s*\d{1,2}월\s*\d{1,2}일/g,
            rep: YEAR + "년 " + d.month + "월 " + d.day + "일"
        };
        // 상일 형태 M월 D일 (학년도/학기 없이 단독)
        var P_KO_MD = {
            re: /(?:^|[^\d년])(\d{1,2})월\s+(\d{1,2})일/g,
            rep: function(match, m, dy) {
                // 앞 글자 보존
                var lead = match.charAt(0).match(/\d|년/) ? "" : match.charAt(0);
                return lead + d.month + "월 " + d.day + "일";
            }
        };

        // 학교별 패턴 조합
        if (school.indexOf("강동") >= 0 || school.indexOf("배재") >= 0) {
            return [P_FULL_NAME, P_DOT_DATE];
        }
        if (school.indexOf("명일") >= 0) {
            // 학년도 부분과 [학기][고사] 분리되어 있음
            return [
                {re: /\d{4}학년도/g, rep: YEAR + "학년도"},
                P_BRACKET_EXAM,
                P_BRACKET_DATE
            ];
        }
        if (school.indexOf("상일") >= 0) {
            // "2025학년도 1학기 중간고사   5월 2일" 형태 (학년도+공백+학기+공백+시험명)
            return [
                {re: /\d{4}학년도\s+\d학기\s+[가-힣]+고사/g,
                 rep: YEAR + "학년도 " + EXAM_TYPE_FULL},
                P_KO_MD
            ];
        }
        if (school.indexOf("성덕") >= 0) {
            return [
                {re: /\d{4}학년도\s+\d학기\s+[가-힣]+고사/g,
                 rep: YEAR + "학년도 " + EXAM_TYPE_FULL},
                P_KO_DATE
            ];
        }
        if (school.indexOf("한영") >= 0) {
            return [
                {re: /\d{4}학년도\s+\d학기\s+[가-힣]+고사/g,
                 rep: YEAR + "학년도 " + EXAM_TYPE_FULL},
                P_PAREN_DATE
            ];
        }
        if (school.indexOf("광문") >= 0) {
            return [
                P_BRACKET_EXAM,
                {re: /\d학기\s+[가-힣]+고사/g, rep: SEM + "학기 " + NAME + "고사"},
                P_KO_DATE
            ];
        }
        return [];
    }

    function applyPatterns(text, patterns) {
        if (!text || patterns.length === 0) return text;
        for (var i = 0; i < patterns.length; i++) {
            var p = patterns[i];
            text = text.replace(p.re, p.rep);
        }
        return text;
    }

    // 텍스트프레임/표 셀 모두 순회하며 패턴 적용
    function updateText(items, patterns, logFn) {
        var changed = 0;
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            if (it.constructor.name !== "TextFrame") continue;
            var tCount = 0;
            try { tCount = it.tables.length; } catch(e) {}

            if (tCount > 0) {
                // 표 셀 contents 치환
                for (var ti = 0; ti < tCount; ti++) {
                    var tab;
                    try { tab = it.tables[ti]; } catch(e) { continue; }
                    var rows = 0, cols = 0;
                    try { rows = tab.rows.length; cols = tab.columns.length; } catch(e) {}
                    for (var r = 0; r < rows; r++) {
                        for (var c = 0; c < cols; c++) {
                            var cell;
                            try { cell = tab.rows[r].cells[c]; } catch(e) { continue; }
                            var oldText = "";
                            try { oldText = String(cell.contents || ""); } catch(e) { continue; }
                            if (!oldText.length) continue;
                            var newText = applyPatterns(oldText, patterns);
                            if (newText !== oldText) {
                                try { cell.contents = newText; changed++; } catch(e) {}
                            }
                        }
                    }
                }
            } else {
                // 일반 텍스트프레임 contents 치환
                var oldT = "";
                try { oldT = it.contents || ""; } catch(e) { continue; }
                if (!oldT.length) continue;
                var newT = applyPatterns(oldT, patterns);
                if (newT !== oldT) {
                    try { it.contents = newT; changed++; } catch(e) {}
                }
            }
        }
        return changed;
    }

    function updateMasterInfo(doc, school, data) {
        if (!data.exam_date && !data.exam_type) return;
        var patterns = getMasterPatterns(school || "", data);
        if (patterns.length === 0) return;

        // 모든 마스터 스프레드 → allPageItems (그룹 내부 포함) 순회
        for (var ms = 0; ms < doc.masterSpreads.length; ms++) {
            var spread = doc.masterSpreads[ms];
            try {
                var items = spread.allPageItems;
                updateText(items, patterns);
            } catch(e) {}
        }
    }

    // ── 본문 스토리 찾기 ─────────────────────────────────────────────────────

    function findMainStory(doc, logPath) {
        // 방법1 (우선): 페이지 textframes의 parentStory 집계 → 가장 많이 등장하는 스토리
        // 명일은 story.textFrames=3이지만 실제 페이지 frame은 14 (모두 같은 story).
        // 상일/배재는 story.textFrames=0으로 나옴(버그성) — 페이지 집계로 우회.
        var storyVotes = {};
        var storyById = {};
        for (var p = 0; p < doc.pages.length; p++) {
            var page = doc.pages[p];
            for (var t = 0; t < page.textFrames.length; t++) {
                var tf = page.textFrames[t];
                try {
                    if (tf.parentPage && tf.parentPage.parent &&
                        tf.parentPage.parent.constructor.name === "MasterSpread") continue;
                } catch(e) {}
                try {
                    var st = tf.parentStory;
                    if (!st) continue;
                    var sid = String(st.id);
                    storyVotes[sid] = (storyVotes[sid] || 0) + 1;
                    storyById[sid] = st;
                } catch(e) {}
            }
        }

        var bestStory = null;
        var bestVotes = 0;
        for (var sid2 in storyVotes) {
            if (storyVotes[sid2] > bestVotes) {
                bestVotes = storyVotes[sid2];
                bestStory = storyById[sid2];
            }
        }

        if (bestStory && bestVotes >= 2) {
            writeLog(logPath, "스토리 탐색: 페이지 frame 집계 (" + bestVotes + "개 frame)");
            return bestStory;
        }

        // 방법2 (fallback): 가장 긴 contents를 가진 스토리
        var bestContent = null;
        var bestCLen = 0;
        for (var j = 0; j < doc.stories.length; j++) {
            var st3 = doc.stories[j];
            var cLen = 0;
            try { cLen = st3.contents.length; } catch(e) {}
            if (cLen > bestCLen) {
                bestCLen = cLen;
                bestContent = st3;
            }
        }
        if (bestContent) {
            writeLog(logPath, "스토리 탐색: 내용 길이 방식 (" + bestCLen + "자)");
            return bestContent;
        }

        return bestStory;
    }

    // ── 텍스트 배치 + 스타일 적용 ────────────────────────────────────────────

    function placeContent(doc, story, questions, logPath, school) {
        // 1) 전체 텍스트 빌드
        var allText = "";
        var paraStyles = [];  // [{ pstyle, runs }]
        var paraCount = 0;

        for (var qi = 0; qi < questions.length; qi++) {
            var q = questions[qi];
            var paras = q.paragraphs;
            for (var pi = 0; pi < paras.length; pi++) {
                var p = paras[pi];
                if (paraCount > 0) allText += "\r";
                allText += p.text;
                paraStyles.push({
                    pstyle: p.pstyle,
                    runs: p.runs || []
                });
                paraCount++;
            }
        }

        writeLog(logPath, "텍스트 배치: " + paraCount + "개 단락");

        // 2) 스토리에 텍스트 할당 (Dingbat 원문자 ➀~➄ → 표준 원문자 ①~⑤)
        story.contents = normalizeCircledDigits(allText);

        // 2-1) 문자 스타일 초기화 ([없음])
        story.characters.everyItem().appliedCharacterStyle = doc.characterStyles[0];

        // 3) 단락 스타일 적용
        var csUnderline = getUnderlineCStyle(doc);
        var styleCache = {};
        // runner의 stall 감지(5분)에 걸리지 않도록 50단락마다 진행 로그 기록
        var PROGRESS_INTERVAL = 50;

        for (var si = 0; si < paraStyles.length && si < story.paragraphs.length; si++) {
            var info = paraStyles[si];
            var styleName = resolveStyleName(school, info.pstyle);

            // 스타일 캐시
            if (!styleCache[styleName]) {
                styleCache[styleName] = getPStyle(doc, styleName);
            }
            story.paragraphs[si].appliedParagraphStyle = styleCache[styleName];

            // 4) 밑줄 적용 (runs 기반)
            var runs = info.runs;
            if (runs && runs.length > 0) {
                var hasUL = false;
                for (var ri = 0; ri < runs.length; ri++) {
                    if (runs[ri].ul) { hasUL = true; break; }
                }
                if (hasUL) {
                    var para = story.paragraphs[si];
                    var charOffset = 0;
                    for (var ri2 = 0; ri2 < runs.length; ri2++) {
                        var run = runs[ri2];
                        var runLen = run.t.length;
                        if (runLen <= 0) continue;
                        if (run.ul) {
                            var startIdx = charOffset;
                            var endIdx = charOffset + runLen - 1;
                            if (startIdx < para.characters.length && endIdx < para.characters.length) {
                                para.characters.itemByRange(startIdx, endIdx).appliedCharacterStyle = csUnderline;
                            }
                        }
                        charOffset += runLen;
                    }
                }
            }

            if ((si + 1) % PROGRESS_INTERVAL === 0) {
                writeLog(logPath, "스타일 적용 진행: " + (si + 1) + "/" + paraStyles.length);
            }
        }

        writeLog(logPath, "스타일 적용 완료: " + paraCount + "개 단락");

        // 5) 한글/원문자 폰트 강제 적용 (Times 글리프 누락으로 한글이 박스로 표시되는 현상 방지)
        applyKoreanFonts(doc, story, logPath);

        // 6) 페이스트보드 박스 헤더 자동 배치 (학교가 페이지 옆에 미리 둔 <보기>/<조건> 라벨)
        try {
            autoPlacePasteboardHeaders(doc, story, logPath);
        } catch(e) {
            writeLog(logPath, "[경고] 페이스트보드 헤더 배치 실패: " + (e.message || e));
        }
    }

    // ── 페이스트보드 박스 헤더 자동 배치 ──────────────────────────────────────
    //
    // 학교들은 페이지 외부(페이스트보드)에 <보기>, <조건>, <요약문>, ↓ 같은
    // 박스 헤더 라벨 텍스트프레임을 미리 배치해 둠. 사용자가 박스 단락 옆으로
    // 끌어들여 사용. 이를 자동으로 박스 단락 옆에 복제 배치한다.

    function _isInPage(spread, bnds) {
        // bnds: [y1, x1, y2, x2]
        var cy = (bnds[0] + bnds[2]) / 2;
        var cx = (bnds[1] + bnds[3]) / 2;
        for (var i = 0; i < spread.pages.length; i++) {
            var pb;
            try { pb = spread.pages[i].bounds; } catch(e) { continue; }
            if (cy >= pb[0] && cy <= pb[2] && cx >= pb[1] && cx <= pb[3]) {
                return spread.pages[i];
            }
        }
        return null;
    }

    // 텍스트프레임 contents를 매칭하여 박스 카테고리 결정
    function _matchHeaderCategory(contents) {
        if (!contents) return null;
        // 유니코드 정규화 (NFD 한글 대응): InDesign에서 charCodeAt 기반 매칭은 ES3 안전
        var s = "";
        for (var i = 0; i < contents.length; i++) {
            var c = contents.charAt(i);
            // 보기 / 조건 / 요약문 / 화살표 매칭 — 공백/구두점 없이 한글 글자만 추출
            if (c >= "가" && c <= "힣") s += c;
        }
        // 화살표 / 특수문자 별도 매칭
        var hasArrow = (contents.indexOf("⇓") >= 0 ||
                        contents.indexOf("↓") >= 0 ||
                        contents.indexOf("⬇") >= 0 ||
                        contents.indexOf("") >= 0);

        if (s.indexOf("요약문") >= 0 || s.indexOf("요약") >= 0) return "요약";
        if (s.indexOf("보기") >= 0) return "보기";
        if (s.indexOf("조건") >= 0) return "조건";
        if (hasArrow) return "화살표";
        return null;
    }

    // 페이스트보드의 헤더 텍스트프레임 수집 (각 카테고리별 첫 번째 발견)
    function collectPasteboardHeaders(doc) {
        var headers = {};  // {보기: tf, 조건: tf, 요약: tf, 화살표: tf}
        for (var s = 0; s < doc.spreads.length; s++) {
            var spread = doc.spreads[s];
            var items;
            try { items = spread.allPageItems; } catch(e) { continue; }
            for (var k = 0; k < items.length; k++) {
                var it = items[k];
                var ctor = "";
                try { ctor = it.constructor.name; } catch(e) {}
                if (ctor !== "TextFrame") continue;
                var bnds;
                try { bnds = it.geometricBounds; } catch(e) { continue; }
                if (!bnds || bnds.length < 4) continue;
                // 페이지 안이면 skip (본문)
                if (_isInPage(spread, bnds)) continue;

                var contents = "";
                try { contents = it.contents; } catch(e) { continue; }
                if (!contents) continue;

                var cat = _matchHeaderCategory(contents);
                if (!cat) continue;
                if (!headers[cat]) {
                    headers[cat] = it;
                }
            }
        }
        return headers;
    }

    // parser pstyle → 박스 카테고리
    var _PSTYLE_TO_CATEGORY = {
        "테두리_보기": "보기",
        "테두리_조건": "조건",
        "테두리_요약": "요약",
        "테두리_순서삽입": "보기"  // 순서삽입은 헤더 없을 수도 있고, 보기 헤더 재사용
    };

    // 박스 단락의 첫 줄 위치 옆에 헤더 복제 배치
    // (textframe 옆이 아닌 박스 단락 실제 위치)
    function _placeHeaderNextTo(headerTF, paragraph, page) {
        var hb = headerTF.geometricBounds;  // [y1, x1, y2, x2]
        var hh = hb[2] - hb[0];
        var hw = hb[3] - hb[1];

        // 박스 단락의 첫 줄 위치
        var lineY = null, lineX = null;
        try {
            var firstLine = paragraph.lines[0];
            // baseline은 첫 줄 기준선 y. lineHeight는 그 위치.
            var lastLine = paragraph.lines[-1];
            lineY = firstLine.baseline;  // 박스 첫 줄 베이스라인 (y)
            // textframe의 시작 x (박스 단락이 시작하는 x)
            var ptfs = paragraph.parentTextFrames;
            if (ptfs && ptfs.length > 0) {
                lineX = ptfs[0].geometricBounds[1];  // textframe x1
            }
        } catch(e) {}

        if (lineY === null || lineX === null) return null;

        // 헤더 위치: 박스 첫 줄의 좌측 외부, 헤더 가운데 ≈ 박스 첫 줄 베이스라인
        // 한글 세로 라벨 기준: 박스 첫 줄 base에서 약간 위로 시작
        var newY1 = lineY - hh + 2;  // 베이스라인 위에 헤더 끝점
        var newX1 = lineX - hw - 3;  // 박스 textframe 좌측에서 3pt 외부
        var newY2 = newY1 + hh;
        var newX2 = newX1 + hw;

        var clone;
        try {
            clone = headerTF.duplicate();
        } catch(e) { return null; }
        try { clone.geometricBounds = [newY1, newX1, newY2, newX2]; } catch(e) {}
        // 페이지로 이동 (페이스트보드 → 페이지)
        try {
            if (page && clone.parentPage !== page) {
                clone.move(page);
            }
        } catch(e) {}
        return clone;
    }

    function autoPlacePasteboardHeaders(doc, story, logPath) {
        var headers = collectPasteboardHeaders(doc);
        var hk = [];
        for (var k in headers) if (headers.hasOwnProperty(k)) hk.push(k);
        if (hk.length === 0) {
            writeLog(logPath, "페이스트보드 헤더 없음 - 자동 배치 스킵");
            return;
        }
        writeLog(logPath, "페이스트보드 헤더 발견: " + hk.join(","));

        var paragraphs = story.paragraphs;
        var prevCat = "";
        var placedCount = 0;

        for (var i = 0; i < paragraphs.length; i++) {
            var para = paragraphs[i];
            var psName = "";
            try { psName = para.appliedParagraphStyle.name; } catch(e) {}

            var cat = _PSTYLE_TO_CATEGORY[psName];
            if (!cat) {
                prevCat = "";
                continue;
            }

            // 같은 박스 카테고리 연속 단락이면 첫 단락에만 헤더 배치
            if (cat === prevCat) continue;
            prevCat = cat;

            var hdr = headers[cat];
            if (!hdr) continue;

            // 박스 단락의 textframe + 페이지
            var boxPage = null;
            try {
                var ptfs = para.parentTextFrames;
                if (ptfs && ptfs.length > 0) boxPage = ptfs[0].parentPage;
            } catch(e) {}
            if (!boxPage) continue;

            var clone = _placeHeaderNextTo(hdr, para, boxPage);
            if (clone) placedCount++;
        }

        writeLog(logPath, "페이스트보드 헤더 배치: " + placedCount + "개");
    }

    // ── 한글 폰트 강제 적용 ──────────────────────────────────────────────────
    // 원본 단락 스타일들("지문", "영단어", "테두리" 등)이 Times로 설정되어 있어
    // 한국어 헤더 텍스트(예: "선택형 38문항")가 해당 스타일에 들어가면 한글에
    // Times가 적용되어 글리프 박스(.notdef)로 표시됨.
    //
    // 학교마다 한글 폰트가 다름(강동/광문=함초롬바탕, 명일=바탕체, 배재/성덕=나눔명조,
    // 상일=Pretendard, 한영1/3=함초롬돋움). 따라서 학교마다 한글 단락 스타일에서
    // 폰트를 동적으로 감지하고, 영문 단락 스타일(Times 등)에만 한글 GREP을 적용한다.

    function isLatinFontName(fn) {
        if (!fn) return false;
        return fn.indexOf("Times") >= 0 ||
               fn.indexOf("Arial") >= 0 ||
               fn.indexOf("Helvetica") >= 0 ||
               fn.indexOf("Garamond") >= 0;
    }

    function getStyleFontInfo(ps) {
        try {
            var af = ps.appliedFont;
            var fn = (typeof af === "string") ? af : af.name;
            var fs;
            try { fs = ps.fontStyle; } catch(e) { fs = "Regular"; }
            return {name: fn, style: fs};
        } catch(e) { return null; }
    }

    function detectHangulFont(doc) {
        // 학교의 한글 단락 스타일 후보 (이 중 하나는 한글 폰트로 설정되어 있음)
        var candidates = ["문제 번호", "기본", "해석", "다음 글을 읽고", "서술형 번호"];
        for (var i = 0; i < candidates.length; i++) {
            var ps = doc.paragraphStyles.itemByName(candidates[i]);
            if (!ps.isValid) {
                for (var g = 0; g < doc.paragraphStyleGroups.length; g++) {
                    ps = doc.paragraphStyleGroups[g].paragraphStyles.itemByName(candidates[i]);
                    if (ps.isValid) break;
                }
            }
            if (!ps.isValid) continue;
            var info = getStyleFontInfo(ps);
            if (info && !isLatinFontName(info.name)) return info;
        }
        return null;
    }

    function hasHangulGrepStyle(ps) {
        try {
            for (var g = 0; g < ps.nestedGrepStyles.length; g++) {
                var gs = ps.nestedGrepStyles[g];
                var ex = gs.grepExpression || "";
                if (ex.indexOf("가-힣") >= 0) return true;
            }
        } catch(e) {}
        return false;
    }

    function applyKoreanFonts(doc, story, logPath) {
        var hangulInfo = detectHangulFont(doc);
        if (!hangulInfo) {
            writeLog(logPath, "[경고] 한글 폰트 감지 실패 - GREP 적용 스킵");
            return;
        }

        var hangulFont;
        try { hangulFont = app.fonts.itemByName(hangulInfo.name); } catch(e) {}
        if (!hangulFont || !hangulFont.isValid) {
            writeLog(logPath, "[경고] 한글 폰트 '" + hangulInfo.name + "' 인식 실패");
            return;
        }
        writeLog(logPath, "한글 폰트 자동 감지: " + hangulInfo.name + " / " + hangulInfo.style);

        // 영문(Latin) 단락 스타일 수집 - 한글 GREP이 이미 정의된 것은 제외
        // (예: "선지" 스타일은 원본에 [가-힣]→나눔명조OTF GREP이 있음 → 그대로 둠)
        var targetStyles = [];
        function collectStyles(styles) {
            for (var i = 0; i < styles.length; i++) {
                var ps = styles[i];
                if (ps.name === "[단락 스타일 없음]" || ps.name === "[기본 단락]") continue;
                var info = getStyleFontInfo(ps);
                if (!info || !isLatinFontName(info.name)) continue;  // 한글 단락은 건드리지 않음
                if (hasHangulGrepStyle(ps)) continue;  // 이미 한글 GREP 있는 단락은 그대로
                targetStyles.push(ps);
            }
        }
        collectStyles(doc.paragraphStyles);
        for (var gi = 0; gi < doc.paragraphStyleGroups.length; gi++) {
            collectStyles(doc.paragraphStyleGroups[gi].paragraphStyles);
        }

        var totalChanged = 0;
        for (var t = 0; t < targetStyles.length; t++) {
            var ps = targetStyles[t];

            // 한글 → 학교 한글 폰트
            resetGrep();
            app.findGrepPreferences.findWhat = "[가-힣ㄱ-ㅎㅏ-ㅣ]";
            app.findGrepPreferences.appliedParagraphStyle = ps;
            try {
                app.changeGrepPreferences.appliedFont = hangulFont;
                app.changeGrepPreferences.fontStyle = hangulInfo.style;
                var changed = story.changeGrep();
                if (changed && changed.length) totalChanged += changed.length;
            } catch(e) {}
            resetGrep();

            // 원문자 ①~⑳ → 학교 한글 폰트 (Times에 ⑥ 이상 글리프 없음)
            resetGrep();
            app.findGrepPreferences.findWhat = "[\\x{2460}-\\x{24FF}]";
            app.findGrepPreferences.appliedParagraphStyle = ps;
            try {
                app.changeGrepPreferences.appliedFont = hangulFont;
                app.changeGrepPreferences.fontStyle = hangulInfo.style;
                var changed2 = story.changeGrep();
                if (changed2 && changed2.length) totalChanged += changed2.length;
            } catch(e) {}
            resetGrep();
        }

        writeLog(logPath, "한글/원문자 폰트 적용: " + totalChanged + "곳 (" +
                          targetStyles.length + "개 영문 단락 스타일 대상)");
    }

    // ── 오버플로우 체크 ──────────────────────────────────────────────────────

    function checkOverflow(doc) {
        var count = 0;
        for (var i = 0; i < doc.stories.length; i++) {
            if (doc.stories[i].overflows) count++;
        }
        return count;
    }

    // ── 빈 trailing 페이지 정리 ──────────────────────────────────────────────
    // 본문 스토리의 모든 텍스트프레임이 비어있는 trailing 페이지 제거.
    // 마스터에서 자동 생성된 빈 페이지는 spread 단위로 처리.
    function _pageHasContent(page, mainStory) {
        try {
            for (var i = 0; i < page.textFrames.length; i++) {
                var tf = page.textFrames[i];
                // 본문 스토리에 속하지 않은 frame은 스킵 (마스터 데코레이션 등)
                if (mainStory && tf.parentStory !== mainStory) continue;
                var c = "";
                try { c = String(tf.contents || ""); } catch(e) {}
                if (c.length > 0) return true;
            }
        } catch(e) {}
        return false;
    }

    function removeEmptyTrailingPages(doc, mainStory, logPath) {
        var removed = 0;
        // 끝 spread부터 제거 (양면 spread가 모두 비었을 때만 제거)
        for (var s = doc.spreads.length - 1; s >= 1; s--) {
            var sp = doc.spreads[s];
            var allEmpty = true;
            for (var i = 0; i < sp.pages.length; i++) {
                if (_pageHasContent(sp.pages[i], mainStory)) { allEmpty = false; break; }
            }
            if (!allEmpty) break;
            try {
                sp.remove();
                removed++;
            } catch(e) {
                writeLog(logPath, "[경고] spread 제거 실패: " + (e.message || e));
                break;
            }
        }
        if (removed > 0) {
            writeLog(logPath, "빈 trailing spread " + removed + "개 제거");
        }
    }

    // ── PDF 내보내기 ─────────────────────────────────────────────────────────

    function exportPDF(doc, pdfPath) {
        var pdfFile = new File(pdfPath);
        doc.exportFile(ExportFormat.PDF_TYPE, pdfFile);
        return pdfFile.exists;
    }

    // ── 메인 ─────────────────────────────────────────────────────────────────

    try {
        var settings = readJSON(settingsPath);
        var jobs = settings.jobs;
        var outputDir = settings.output_dir;
        var logPath = outputDir + "/typeset_log.txt";

        // 또한 job_dir에도 로그 저장 (verify에서 사용)
        var jobDir = (new File(settingsPath)).parent.fsName;
        var logPath2 = jobDir + "/typeset_log.txt";

        writeLog(logPath, "동형모의고사 조판 시작: " + settings.school + " " + settings.grade);
        writeLog(logPath2, "동형모의고사 조판 시작: " + settings.school + " " + settings.grade);

        for (var ji = 0; ji < jobs.length; ji++) {
            var job = jobs[ji];
            var roundNum = job["round"] || (ji + 1);
            var inddPath = job.indd_path;
            var data = job.data;

            writeLog(logPath, "[" + roundNum + "회] 시작: " + inddPath);
            writeLog(logPath2, "[" + roundNum + "회] 시작: " + inddPath);

            // 문서 열기
            var docFile = new File(inddPath);
            if (!docFile.exists) {
                writeLog(logPath, "[오류] 파일 없음: " + inddPath);
                writeLog(logPath2, "[오류] 파일 없음: " + inddPath);
                continue;
            }
            var doc = app.open(docFile);

            app.doScript(function() {
                // 마스터 페이지 시험 정보 교체
                updateMasterInfo(doc, settings.school, data);
                writeLog(logPath, "[" + roundNum + "회] 마스터 정보 교체 완료");

                // 본문 스토리 찾기
                var mainStory = findMainStory(doc, logPath);
                if (!mainStory) {
                    writeLog(logPath, "[오류] 본문 스토리를 찾을 수 없음");
                    writeLog(logPath2, "[오류] 본문 스토리를 찾을 수 없음");
                    return;
                }
                writeLog(logPath, "[" + roundNum + "회] 본문 스토리: " + mainStory.textFrames.length + "개 프레임");

                // 기존 내용 삭제
                mainStory.contents = "";

                // 텍스트 배치 + 스타일 적용
                var questions = data.questions || [];
                placeContent(doc, mainStory, questions, logPath, settings.school);

                // 오버플로우 체크
                var overflow = checkOverflow(doc);
                writeLog(logPath, "[" + roundNum + "회] 오버플로우: " + overflow + "개");
                writeLog(logPath2, "[" + roundNum + "회] 오버플로우: " + overflow + "개");

                // 빈 trailing 페이지 제거 (오버플로우 없을 때만)
                if (overflow === 0) {
                    removeEmptyTrailingPages(doc, mainStory, logPath);
                }

            }, ScriptLanguage.JAVASCRIPT, undefined,
               UndoModes.ENTIRE_SCRIPT, "동형모의고사 " + roundNum + "회 조판");

            // PDF 내보내기
            var pdfName = inddPath.replace(/\.indd$/i, ".pdf");
            var pdfOk = exportPDF(doc, pdfName);
            writeLog(logPath, "[" + roundNum + "회] PDF: " + (pdfOk ? "성공" : "실패") + " -> " + pdfName);
            writeLog(logPath2, "[" + roundNum + "회] PDF: " + (pdfOk ? "성공" : "실패") + " -> " + pdfName);

            // 문서 저장
            doc.save();
            writeLog(logPath, "[" + roundNum + "회] 저장 완료");

            // 총 오버플로우
            var totalOverflow = checkOverflow(doc);
            writeLog(logPath2, "오버플로우: " + totalOverflow + "개");
        }

        writeLog(logPath, "동형모의고사 조판 완료");
        writeLog(logPath2, "동형모의고사 조판 완료");

    } catch(e) {
        try {
            writeLog(logPath || "/tmp/mockexam_error.txt", "[오류] " + e.message);
            writeLog(logPath2 || "/tmp/mockexam_error2.txt", "[오류] " + e.message);
        } catch(e2) {}
        alert("동형모의고사 조판 오류:\n" + e.message);
    }

    resetGrep();
})();
