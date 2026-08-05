// [ENGINE TEMPLATE] 세로 → 가로 본문 복제 JSX
// __SETTINGS_PATH__ 는 engine.py 에서 실제 경로로 치환됨.
//
// 동작:
//   1) settings.json 로드 → verti_path, output_indd, gang_code, sources_list, log_path
//   2) output_indd (가로 사본) 열기 + verti_path 열기
//   3) 세로 분석: A-마스터 첫 페이지 = 새 지문, 지문별 마스터 페이지 그룹
//   4) 엑셀(sources_list)과 세로 출처 코드 비교 → 불일치 알림 (로그)
//   5) 가로 영역 자동 감지 (사이드 라벨: 어휘 선택 1/2, 본문 O/X, 본문 정리,
//      내용 종합, 문장 배열, 빈칸 어휘, 어법 선택, 어법 O/X, 빈칸 어법,
//      영작 배열, S 실전 문제)
//   6) 영역별로 세로 마스터 페이지 → 가로 페이지 복제
//   7) output_indd 저장, 두 문서 닫기
//
// 라벨링은 하지 않음 (별도 작업)

#target indesign

(function () {

    // ───────────────────────────────────────────────────────────────
    // settings.json 로드 + 로그 헬퍼
    // ───────────────────────────────────────────────────────────────

    var SETTINGS_PATH = "__SETTINGS_PATH__";

    function readJSON(path) {
        var f = new File(path);
        f.encoding = "UTF-8";
        if (!f.open("r")) throw new Error("settings 열기 실패: " + path);
        var raw = f.read();
        f.close();
        return eval("(" + raw + ")");
    }

    function pad2(n) { return (n < 10 ? "0" : "") + n; }
    function ts() {
        var d = new Date();
        return "[" + pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" +
               pad2(d.getSeconds()) + "] ";
    }

    // settings 로드 실패 시에도 job_dir 로그에 흔적을 남긴다 — 종전에는
    // readJSON 예외가 로그 0바이트 침묵 실패로 빠져 원인 진단이 불가했다.
    var settings;
    try {
        settings = readJSON(SETTINGS_PATH);
    } catch (eBoot) {
        try {
            var _ef = new File(new File(SETTINGS_PATH).parent.fsName + "/convert_log.txt");
            _ef.encoding = "UTF-8";
            if (_ef.open("a")) {
                _ef.write(ts() + "[치명적 오류] settings 로드 실패: " +
                          (eBoot.message || eBoot) + "\n");
                _ef.close();
            }
        } catch (eEf) {}
        throw eBoot;
    }
    var LOG_PATH   = settings.log_path;
    var LOG_PATHS  = settings.log_paths || [];

    // 다이얼로그 / 알림 무시 - JSX 실행 중 사용자 인터랙션 차단
    try { app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT; } catch(e) {}

    function writeLog(msg) {
        var line = ts() + msg + "\n";
        var paths = [LOG_PATH];
        for (var i = 0; i < LOG_PATHS.length; i++) paths.push(LOG_PATHS[i]);
        for (var pi = 0; pi < paths.length; pi++) {
            try {
                var lf = new File(paths[pi]);
                lf.encoding = "UTF-8";
                if (lf.open("a")) { lf.write(line); lf.close(); }
            } catch (eL) {}
        }
    }

    function fail(msg) { writeLog("[오류] " + msg); }
    function warn(msg) { writeLog("[경고] " + msg); }
    function info(msg) { writeLog(msg); }

    // ───────────────────────────────────────────────────────────────
    // 영역 매핑 테이블 (사이드 라벨 → 세로 섹션 인덱스 + tf 위치)
    // ───────────────────────────────────────────────────────────────
    // 세로 지문의 페이지는 canonical 순서로 다음 섹션을 가짐 (O-마스터 제외):
    //   sectionIdx 0: 어휘 선택 (top + bottom 둘 다)
    //   sectionIdx 1: 본문 O/X
    //   sectionIdx 2: 본문 정리
    //   sectionIdx 3: 내용 종합
    //   sectionIdx 4: 문장 배열
    //   sectionIdx 5: 빈칸 어휘
    //   sectionIdx 6: 어법 선택
    //   sectionIdx 7: 어법 O/X
    //   sectionIdx 8: 빈칸 어법
    //   sectionIdx 9: 영작 배열
    // O-마스터 페이지는 실전 문제 (lesson_all 모드).
    //
    // labelType: 라벨 텍스트프레임 식별 방식
    //   "main_top"    = 메인 텍스트프레임 중 가장 위(y 작음)
    //   "main_bottom" = 가장 아래
    //   "main_single" = 메인이 하나
    //   "main_left"   = 가장 왼쪽 (실전 영역)
    //   "small_label" = 작은 라벨 (지문번호 박스, 예: "01")
    // mode "by_lesson":   영역의 N번째 페이지 ↔ N번째 지문 (1:1 페이지 매핑)
    // mode "two_up":      한 페이지에 2지문 (위/아래 슬롯), 슬롯 i = 지문 i+1 (어휘선택1/2 전용)
    // mode "lesson_all":  영역 페이지를 순서대로 세로 O-마스터 페이지에 매핑 (실전)
    // tfPos "all":        세로 페이지의 모든 메인 텍스트프레임 복제 (위/아래 둘 다)
    // tfPos "top"/"bottom": 일부만
    // srcMainIdx: two_up 모드에서 세로 어휘선택 페이지의 어느 main TF 가져올지 (0=위/어휘1, 1=아래/어휘2)
    var REGION_MAP = {
        "어휘 선택 1":  { sectionIdx: 0, srcMainIdx: 0, mode: "two_up",    labelType: "main_all" },
        "어휘 선택 2":  { sectionIdx: 0, srcMainIdx: 1, mode: "two_up",    labelType: "main_all" },
        "본문 O/X":     { sectionIdx: 1, tfPos: "all", mode: "by_lesson",  labelType: "main_top" },
        "본문 정리":    { sectionIdx: 2, tfPos: "all", mode: "by_lesson",  labelType: "main_top" },
        "내용 종합":    { sectionIdx: 3, tfPos: "all", mode: "by_lesson",  labelType: "main_single" },
        "문장 배열":    { sectionIdx: 4, tfPos: "all", mode: "by_lesson",  labelType: "main_top" },
        "빈칸 어휘":    { sectionIdx: 5, tfPos: "all", mode: "by_lesson",  labelType: "small_label" },
        "어법 선택":    { sectionIdx: 6, tfPos: "all", mode: "by_lesson",  labelType: "main_top" },
        "어법 O/X":     { sectionIdx: 7, tfPos: "all", mode: "by_lesson",  labelType: "small_label" },
        "빈칸 어법":    { sectionIdx: 8, tfPos: "all", mode: "by_lesson",  labelType: "small_label" },
        "영작 배열":    { sectionIdx: 9, tfPos: "all", mode: "by_lesson",  labelType: "main_single" },
        "S 실전 문제":  { sectionIdx: -1, tfPos: "all", mode: "lesson_all", labelType: null }
    };
    // 가로 사이드 라벨이 없는 영역 — 마스터 기반으로 식별
    var MASTER_REGION = {
        "O-마스터": "S 실전 문제"
    };

    // ───────────────────────────────────────────────────────────────
    // 유틸
    // ───────────────────────────────────────────────────────────────

    function trim(s) { return s.replace(/^\s+|\s+$/g, ""); }

    function parseLabel(label) {
        if (!label) return null;
        var s = label.replace(/[\{\}\[\]]/g, "");
        s = trim(s);
        var m1 = s.match(/^(?:\d+\s*강\s*)?(\d+)\s*번\s*(\d{6})/);
        if (m1) return { num: parseInt(m1[1], 10), source: m1[2] };
        var m2 = s.match(/^(?:\d+\s*강\s*)?(\d+)\s*번/);
        if (m2) return { num: parseInt(m2[1], 10), source: null };
        var m3 = s.match(/^(\d{6})$/);
        if (m3) return { num: null, source: m3[1] };
        var m4 = s.match(/^(\d{1,2})$/);
        if (m4) return { num: parseInt(m4[1], 10), source: null };
        return null;
    }

    function isSideLabel(b) {
        var h = b[2] - b[0];
        return (b[2] < 30 && h < 30);
    }

    function isMainTF(b) {
        var w = b[3] - b[1];
        var h = b[2] - b[0];
        return (h >= 30 && w >= 30);
    }

    function getSideLabel(page) {
        var spread = page.parent;
        for (var i = 0; i < spread.textFrames.length; i++) {
            var tf = spread.textFrames[i];
            if (!tf.parentPage || tf.parentPage.id !== page.id) continue;
            if (!isSideLabel(tf.geometricBounds)) continue;
            var c = tf.contents ? trim(tf.contents) : "";
            if (c.length > 0) return c;
        }
        return null;
    }

    function getMainTFs(page) {
        var spread = page.parent;
        var arr = [];
        for (var i = 0; i < spread.textFrames.length; i++) {
            var tf = spread.textFrames[i];
            if (!tf.parentPage || tf.parentPage.id !== page.id) continue;
            if (!isMainTF(tf.geometricBounds)) continue;
            arr.push(tf);
        }
        return arr;
    }

    // 메인(큰) 텍스트프레임의 시작에서만 라벨 추출
    // — 작은 라벨 텍스트프레임(예: 마더텅 문제번호 "20", "41-42")은 무시
    // — 의미 있는 라벨 형식: "[N번 출처]", "{N번 출처}", "N번 출처", "출처"(6자리)
    function findPageLabelInfo(page) {
        var spread = page.parent;
        for (var i = 0; i < spread.textFrames.length; i++) {
            var tf = spread.textFrames[i];
            if (!tf.parentPage || tf.parentPage.id !== page.id) continue;
            var b = tf.geometricBounds;
            if (!isMainTF(b)) continue;  // 메인 텍스트프레임만
            var c = tf.contents ? trim(tf.contents) : "";
            if (c.length === 0) continue;
            var headPart = c.substring(0, 30);
            var pi = parseLabelStrict(headPart);
            if (pi && (pi.num !== null || pi.source !== null)) return pi;
        }
        return null;
    }

    // 엄격한 라벨 파서: 본문 시작에 명시적 라벨이 있는 경우만 추출
    // 패턴:
    //   "[180940] | 본문..."  → source=180940
    //   "{180940} | ..."      → source=180940
    //   "[7강 4번 200324] ..."→ num=4, source=200324
    //   "{1} | (A) ..."       → num=1
    //   "[1] | ..."           → num=1
    //   "1번 200324 ..."      → num=1, source=200324
    // 본문 우연한 숫자(연도 등) 와 구분하기 위해 대괄호/중괄호/번 키워드 필수.
    function parseLabelStrict(label) {
        if (!label) return null;
        var s = trim(label);

        // 1) "[XXXXXX]" / "{XXXXXX}" — 6자리 출처 코드 (대괄호 필수)
        var m = s.match(/^[\[\{](\d{6})[\]\}]/);
        if (m) return { num: null, source: m[1] };

        // 2) "[N번 XXXXXX]" / "{N번 XXXXXX}"
        m = s.match(/^[\[\{](?:\d+\s*강\s*)?(\d+)\s*번\s*(\d{6})[\]\}]?/);
        if (m) return { num: parseInt(m[1], 10), source: m[2] };

        // 3) "[N]" / "{N}" — 1~3자리 (대괄호 필수, 본문 우연 숫자 회피)
        m = s.match(/^[\[\{](\d{1,3})[\]\}]/);
        if (m) return { num: parseInt(m[1], 10), source: null };

        // 4) "N번 XXXXXX" (대괄호 없음, "번" 키워드 필수)
        m = s.match(/^(?:\d+\s*강\s*)?(\d+)\s*번\s*(\d{6})/);
        if (m) return { num: parseInt(m[1], 10), source: m[2] };

        // 5) "N번" (대괄호 없음)
        m = s.match(/^(?:\d+\s*강\s*)?(\d+)\s*번/);
        if (m) return { num: parseInt(m[1], 10), source: null };

        // 6) 본문 시작 6자리 + 공백/구분자 (예: "180940 | ...")
        m = s.match(/^(\d{6})[\s\|]/);
        if (m) return { num: null, source: m[1] };

        return null;
    }

    function matchByPosition(srcMains, tgtMains) {
        if (srcMains.length !== tgtMains.length) return null;
        return matchByPositionLoose(srcMains, tgtMains);
    }

    // 개수 달라도 가능한 한 위치 기반 매칭 (매핑 안 된 tgt 는 그대로 둠)
    function matchByPositionLoose(srcMains, tgtMains) {
        var matches = [];
        if (srcMains.length === 0 || tgtMains.length === 0) return matches;
        var usedTgt = {};
        for (var i = 0; i < srcMains.length; i++) {
            var sb = srcMains[i].geometricBounds;
            var sCx = (sb[1] + sb[3]) / 2;
            var sCy = (sb[0] + sb[2]) / 2;
            var bestJ = -1, bestDist = Infinity;
            for (var j = 0; j < tgtMains.length; j++) {
                if (usedTgt[j]) continue;
                var tb = tgtMains[j].geometricBounds;
                var dist = Math.abs(sCx - (tb[1]+tb[3])/2) +
                           Math.abs(sCy - (tb[0]+tb[2])/2);
                if (dist < bestDist) { bestDist = dist; bestJ = j; }
            }
            if (bestJ >= 0) {
                matches.push({ srcTF: srcMains[i], tgtTF: tgtMains[bestJ] });
                usedTgt[bestJ] = true;
            }
        }
        return matches;
    }

    function getSrcTFsByPos(page, tfPos) {
        var mains = getMainTFs(page);
        if (tfPos === "all") return mains;
        if (mains.length === 0) return [];
        var sorted = mains.slice(0);
        sorted.sort(function(a, b) {
            return a.geometricBounds[0] - b.geometricBounds[0];
        });
        if (tfPos === "top") return [sorted[0]];
        if (tfPos === "bottom") return [sorted[sorted.length - 1]];
        return [];
    }

    // ───────────────────────────────────────────────────────────────
    // 라벨링 헬퍼
    // ───────────────────────────────────────────────────────────────

    // 라벨 영역 텍스트프레임 식별
    function findLabelTF(page, labelType) {
        var spread = page.parent;
        var arr = [];
        for (var i = 0; i < spread.textFrames.length; i++) {
            var tf = spread.textFrames[i];
            if (!tf.parentPage || tf.parentPage.id !== page.id) continue;
            var b = tf.geometricBounds;
            var w = b[3] - b[1];
            var h = b[2] - b[0];
            if (labelType === "small_label") {
                // 작은 라벨 (사이드 영역명 제외)
                if (h >= 30 && w >= 30) continue; // 메인 영역 제외
                if (b[2] < 30) continue; // 페이지 위쪽 사이드 라벨 제외
                if (b[1] < 5) continue;
                if (w > 100) continue;
                arr.push({tf: tf, y: b[0], x: b[1]});
            } else {
                // 메인 영역
                if (h < 30 || w < 30) continue;
                // 빈 TF (헤더 영역용 placeholder)는 라벨 후보에서 제외
                var content = tf.contents;
                if (!content || content.length === 0) continue;
                arr.push({tf: tf, y: b[0], x: b[1]});
            }
        }
        if (arr.length === 0) return null;
        if (labelType === "main_top")         arr.sort(function(a,b){return a.y-b.y;});
        else if (labelType === "main_bottom") arr.sort(function(a,b){return b.y-a.y;});
        else if (labelType === "main_left")   arr.sort(function(a,b){return a.x-b.x;});
        else if (labelType === "small_label") arr.sort(function(a,b){return a.y-b.y;});
        // main_single: 정렬 불필요 (1개만 있다고 가정)
        return arr[0].tf;
    }

    // 라벨 길이 + 형식 식별 (메인 텍스트프레임 시작 부분)
    // 반환: { len: 라벨 길이, fmt: "brace" | "bracket" | "plain" | "none" }
    // 본문 보호: 숫자로 시작 안 하고 괄호로도 시작 안 하면 라벨 없음으로 간주
    function detectLabelInfo(c) {
        if (!c || c.length === 0) return { len: 0, fmt: "none" };
        var ch0 = c.charCodeAt(0);
        if (ch0 === 123) { // {
            var endIdx = c.indexOf("}");
            if (endIdx > 0 && endIdx < 30) {
                // 괄호 안이 숫자만으로 구성됐는지 확인
                var inner = c.substring(1, endIdx);
                if (/^\d+(?:번\s*\d+)?$/.test(inner.replace(/\s/g, ""))) {
                    return { len: endIdx + 1, fmt: "brace" };
                }
            }
            return { len: 0, fmt: "none" };
        }
        if (ch0 === 91) { // [
            var endIdx = c.indexOf("]");
            if (endIdx > 0 && endIdx < 30) {
                var inner = c.substring(1, endIdx);
                if (/^\d+(?:번\s*\d+)?$/.test(inner.replace(/\s/g, ""))) {
                    return { len: endIdx + 1, fmt: "bracket" };
                }
            }
            return { len: 0, fmt: "none" };
        }
        // 숫자로 시작하는 경우만 plain 라벨로 인식 (본문 보호)
        if (ch0 < 48 || ch0 > 57) return { len: 0, fmt: "none" };
        var i = 0;
        while (i < c.length && i < 30) {
            var code = c.charCodeAt(i);
            if (code === 32 || code === 9 || code === 13 || code === 10 || code === 65532) break;
            i++;
        }
        return { len: i, fmt: "plain" };
    }

    // 호환용 (기존 호출)
    function detectLabelLength(c) {
        return detectLabelInfo(c).len;
    }

    // 새 라벨 형식 결정 — 기존 라벨 형식 유지하면서 번호만 갱신
    function makeFormattedLabel(num, fmt) {
        var pad = (num < 10 ? "0" : "") + num;
        if (fmt === "brace") return "{" + pad + "}";
        if (fmt === "bracket") return "[" + pad + "]";
        return pad;
    }

    // 메인 텍스트프레임 시작에 남아있는 원본 라벨 패턴 식별
    // (예: "[180940]", "{1}", "[1]") - 본문 첫 토큰만
    // 반환: 라벨 길이 (없으면 0)
    function detectStartLabelLen(c) {
        if (!c || c.length === 0) return 0;
        // [XXXXXX] 또는 {XXXXXX} (6자리 출처)
        var m = c.match(/^([\[\{]\d{6}[\]\}])/);
        if (m) return m[1].length;
        // [N번 XXXXXX] 또는 {N번 XXXXXX}
        m = c.match(/^([\[\{]\d+\s*번\s*\d{6}[\]\}])/);
        if (m) return m[1].length;
        // [N] 또는 {N} (1~3자리)
        m = c.match(/^([\[\{]\d{1,3}[\]\}])/);
        if (m) return m[1].length;
        // "N번 XXXXXX " 형식 (대괄호 없음)
        m = c.match(/^(\d+\s*번\s*\d{6})\s/);
        if (m) return m[1].length;
        // "N번 " 형식
        m = c.match(/^(\d+\s*번)\s/);
        if (m) return m[1].length;
        return 0;
    }

    // 페이지의 모든 메인 텍스트프레임 시작 라벨 제거 (선두 공백/구분자도 함께)
    function stripStartLabels(page) {
        var mains = getMainTFs(page);
        for (var i = 0; i < mains.length; i++) {
            var story = mains[i].parentStory;
            var c = story.contents;
            if (!c || c.length === 0) continue;
            var labelLen = detectStartLabelLen(c);
            if (labelLen === 0) continue;
            // 라벨 다음의 공백/구분자도 함께 제거 (" | ", " ", "\t", "\n")
            var ext = labelLen;
            while (ext < c.length && ext < labelLen + 10) {
                var code = c.charCodeAt(ext);
                if (code === 32 || code === 9 || code === 124 || code === 13 || code === 10 || code === 65532) ext++;
                else break;
            }
            try {
                story.texts[0].characters.itemByRange(0, ext - 1).remove();
            } catch (e) {}
        }
    }

    // 라벨 교체 + 문자스타일 적용
    // num: 마더텅 N (숫자). 기존 라벨 형식 ({…}/[…]/plain) 자동 유지
    function applyLabel(tf, num, labelType, charStyle) {
        if (!tf) return false;
        var story = tf.parentStory;
        var c = story.contents;
        if (c === undefined || c === null) return false;
        var pad = (num < 10 ? "0" : "") + num;
        var newLabel;
        var appliedLen = 0;

        if (c.length === 0) {
            if (labelType === "small_label") {
                newLabel = pad;
                story.contents = newLabel;
                appliedLen = newLabel.length;
            } else {
                // 메인 영역에 본문이 없으면 라벨만 채울 수 없음 (디자인상 라벨이 본문 일부)
                return false;
            }
        } else {
            if (labelType === "small_label") {
                // 작은 라벨 영역: 내용 전체 교체. 기존 포맷({},[]) 유지
                var oldInfo = detectLabelInfo(c);
                var smallFmt = (oldInfo.fmt !== "none") ? oldInfo.fmt : "plain";
                newLabel = makeFormattedLabel(num, smallFmt);
                story.contents = newLabel;
                appliedLen = newLabel.length;
            } else {
                // 메인 영역: 시작 라벨이 있으면 형식 유지하며 교체, 없으면 plain prepend
                var info = detectLabelInfo(c);
                try {
                    if (info.len > 0) {
                        newLabel = makeFormattedLabel(num, info.fmt);
                        story.texts[0].characters.itemByRange(0, info.len - 1).contents = newLabel;
                        appliedLen = newLabel.length;
                    } else {
                        // 시작에 라벨이 없으면 prepend (plain)
                        newLabel = pad;
                        story.insertionPoints[0].contents = newLabel + " ";
                        appliedLen = newLabel.length;
                    }
                } catch (e) {
                    return false;
                }
            }
        }
        // 문자스타일 적용
        if (charStyle && appliedLen > 0) {
            try {
                story.texts[0].characters.itemByRange(0, appliedLen - 1).appliedCharacterStyle = charStyle;
            } catch (e2) {}
        }
        return true;
    }

    // 가로/세로 페이지의 라벨에서 마더텅 N 결정 (엑셀 매칭 우선)
    function determineLessonN(page, sourcesList) {
        var info = findPageLabelInfo(page);
        if (!info) return null;
        // 1순위: 출처 코드를 엑셀에서 매칭 → 마더텅 N
        if (info.source) {
            for (var i = 0; i < sourcesList.length; i++) {
                if (String(sourcesList[i]) === info.source) return i + 1;
            }
        }
        // 2순위: 라벨 내 명시된 N번
        if (info.num !== null && info.num >= 1 && info.num <= sourcesList.length) {
            return info.num;
        }
        return null;
    }

    // 지문의 메타 추출 (지문의 모든 페이지에서 출처 코드 또는 마더텅 N 추출)
    function extractLessonMeta(lesson, verti, sourcesList) {
        for (var p = lesson.startP; p <= lesson.endP; p++) {
            var page = verti.pages[p - 1];
            var info = findPageLabelInfo(page);
            if (!info) continue;
            if (info.source) {
                for (var i = 0; i < sourcesList.length; i++) {
                    if (String(sourcesList[i]) === info.source) {
                        return { n: i + 1, source: info.source };
                    }
                }
            }
            if (info.num !== null && info.num >= 1 && info.num <= sourcesList.length) {
                return { n: info.num, source: null };
            }
        }
        return null;
    }

    function copyPageContent(srcPage, tgtPage, tfPos) {
        var srcMains = getSrcTFsByPos(srcPage, tfPos);
        var tgtMains = getMainTFs(tgtPage);
        if (srcMains.length === 0) return { ok: false, reason: "세로 매핑 대상 없음" };

        if (tgtMains.length === 0) {
            for (var i = 0; i < srcMains.length; i++) {
                srcMains[i].duplicate(tgtPage);
            }
            return { ok: true, reason: "직접 복제 (" + srcMains.length + ")" };
        }

        if (tfPos !== "all" && srcMains.length === 1 && tgtMains.length > 1) {
            var src = srcMains[0];
            var sb = src.geometricBounds;
            var sCy = (sb[0] + sb[2]) / 2;
            var bestJ = -1, bestDist = Infinity;
            for (var j = 0; j < tgtMains.length; j++) {
                var tb = tgtMains[j].geometricBounds;
                var dist = Math.abs(sCy - (tb[0]+tb[2])/2);
                if (dist < bestDist) { bestDist = dist; bestJ = j; }
            }
            if (bestJ >= 0) {
                var tgtTF = tgtMains[bestJ];
                var tgtBounds = tgtTF.geometricBounds.slice(0);
                var newTF = src.duplicate(tgtPage);
                newTF.geometricBounds = tgtBounds;
                tgtTF.remove();
                return { ok: true, reason: "1:1 (top/bottom)" };
            }
            return { ok: false, reason: "매칭 실패" };
        }

        var matches = matchByPosition(srcMains, tgtMains);
        if (!matches) {
            // tf 개수 불일치 — loose 매핑 (가능한 만큼 위치 기반)
            // 매핑되지 않은 가로 tf 는 그대로 유지(빈), 세로 tf 가 남으면 직접 복제
            matches = matchByPositionLoose(srcMains, tgtMains);
            if (matches.length === 0) {
                return { ok: false, reason: "loose 매핑 실패 (src=" + srcMains.length + ", tgt=" + tgtMains.length + ")" };
            }
        }
        if (matches.length === 0) return { ok: false, reason: "매핑 없음" };

        var ops = [];
        for (var i = 0; i < matches.length; i++) {
            ops.push({
                srcTF: matches[i].srcTF,
                tgtTF: matches[i].tgtTF,
                tgtBounds: matches[i].tgtTF.geometricBounds.slice(0)
            });
        }
        for (var i = 0; i < ops.length; i++) {
            var op = ops[i];
            var newTF = op.srcTF.duplicate(tgtPage);
            newTF.geometricBounds = op.tgtBounds;
            op.tgtTF.remove();
        }
        return { ok: true, reason: "복제 (" + ops.length + ")" };
    }

    // ───────────────────────────────────────────────────────────────
    // 세로 분석
    // ───────────────────────────────────────────────────────────────
    function analyzeVertical(verti) {
        var lessons = [];
        var lessonStarts = [];
        var prevMaster = null;
        for (var p = 0; p < verti.pages.length; p++) {
            var page = verti.pages[p];
            var mn = page.appliedMaster ? page.appliedMaster.name : null;
            if (mn === "A-마스터" && prevMaster !== "A-마스터") {
                lessonStarts.push(p + 1);
            }
            prevMaster = mn;
        }
        for (var i = 0; i < lessonStarts.length; i++) {
            var startP = lessonStarts[i];
            var endP = (i + 1 < lessonStarts.length) ? lessonStarts[i+1] - 1 : verti.pages.length;

            // O-마스터(실전) 제외하고 모든 페이지를 섹션 페이지로 (순서대로)
            // — 마스터 적용이 잘못된 페이지도 콘텐츠 순서가 일정하므로 sectionIdx 0~9 에 매핑됨
            var sections = [];
            var pracPages = [];
            for (var p = startP; p <= endP; p++) {
                var page = verti.pages[p - 1];
                var mn = page.appliedMaster ? page.appliedMaster.name : null;
                if (mn === "O-마스터") {
                    pracPages.push(p);
                } else {
                    sections.push(p);
                }
            }
            var sourceCode = null;
            for (var p = startP; p <= endP && !sourceCode; p++) {
                var info = findPageLabelInfo(verti.pages[p - 1]);
                if (info && info.source) sourceCode = info.source;
            }
            lessons.push({
                num: i + 1, startP: startP, endP: endP,
                sections: sections, pracPages: pracPages,
                sourceCode: sourceCode,
                madertungN: null  // 나중에 엑셀 매칭으로 결정
            });
        }
        return lessons;
    }

    // 세로 각 지문의 마더텅 N 결정 (엑셀 매칭). 세로 페이지에서 출처/N 추출.
    function assignMadertungN(lessons, sourcesList) {
        for (var i = 0; i < lessons.length; i++) {
            var meta = extractLessonMeta(lessons[i], verti, sourcesList);
            if (meta) {
                lessons[i].madertungN = meta.n;
                lessons[i].sourceCode = meta.source || lessons[i].sourceCode;
            } else {
                // 추출 실패 시 fallback: 세로 순서
                lessons[i].madertungN = i + 1;
            }
        }
    }

    // ───────────────────────────────────────────────────────────────
    // 가로 영역 식별
    // ───────────────────────────────────────────────────────────────
    // 가로 영역 식별
    // — 같은 라벨이 spread마다 반복되어도 한 영역으로 통합
    // — config.group 이 같은 라벨끼리도 한 영역으로 (어휘선택1/2 → "vocab")
    // — 사이드 라벨 없는 페이지 + MASTER_REGION 적용 마스터 = 마스터 기반 영역
    function detectHorizRegions(horiz) {
        var regions = [];
        var current = null;
        for (var p = 1; p <= horiz.pages.length; p++) {
            var page = horiz.pages[p - 1];
            var label = getSideLabel(page);
            var pageMaster = page.appliedMaster ? page.appliedMaster.name : null;

            // 사이드 라벨이 있고 매핑 가능한 영역
            if (label && REGION_MAP[label]) {
                var cfg = REGION_MAP[label];
                // 같은 라벨이면 같은 영역에 추가 (어휘선택1과 어휘선택2는 별개 영역)
                var sameRegion = current && (current.label === label);
                if (sameRegion) {
                    current.endP = p;
                    current.pages.push(p);
                } else {
                    current = {
                        label: label, startP: p, endP: p, pages: [p],
                        config: cfg, masterName: pageMaster,
                        labelsSeen: [label]
                    };
                    regions.push(current);
                }
                continue;
            }

            // 마스터 기반 영역 (실전 등 — 사이드 라벨 없음)
            if (!label && pageMaster && MASTER_REGION[pageMaster]) {
                var virtLabel = MASTER_REGION[pageMaster];
                if (current && current.label === virtLabel) {
                    current.endP = p;
                    current.pages.push(p);
                } else {
                    current = {
                        label: virtLabel, startP: p, endP: p, pages: [p],
                        config: REGION_MAP[virtLabel], masterName: pageMaster,
                        labelsSeen: [virtLabel]
                    };
                    regions.push(current);
                }
                continue;
            }

            // 라벨 없는 페이지: 진행 중인 영역의 같은 마스터면 포함, 아니면 영역 종료
            if (current) {
                if (pageMaster === current.masterName) {
                    current.endP = p;
                    current.pages.push(p);
                } else if (!pageMaster) {
                    // 마스터 없음 (간지/표지) = 영역 종료
                    current = null;
                } else {
                    // 다른 마스터 = 영역 종료
                    current = null;
                }
            }
        }

        // 같은 라벨의 마스터 기반 영역(실전 등)이 M페이지 등으로 쪼개져 여러 개
        // 감지되면 하나로 병합 — lesson_all 이 영역마다 처음부터 다시 부어
        // 중복 런이 생기는 것을 방지 (2026-08-05 신규 내지 실측: O런 4개 →
        // 실전 76p 중복). 런이 1개인 기존 템플릿에서는 결과 무변화.
        var merged = [];
        var byLabel = {};
        for (var mi = 0; mi < regions.length; mi++) {
            var rg = regions[mi];
            if (rg.config && rg.config.mode === "lesson_all" && byLabel[rg.label]) {
                var first = byLabel[rg.label];
                first.endP = rg.endP;
                for (var pp = 0; pp < rg.pages.length; pp++) first.pages.push(rg.pages[pp]);
                continue;
            }
            if (rg.config && rg.config.mode === "lesson_all") byLabel[rg.label] = rg;
            merged.push(rg);
        }
        return merged;
    }

    // ───────────────────────────────────────────────────────────────
    // 영역별 처리
    // ───────────────────────────────────────────────────────────────
    var verti = null;
    var horiz = null;

    function processRegion(region, lessons, sourcesList) {
        var config = region.config;
        info("\n=== [" + region.label + "] 가로 p" + region.startP + "~p" + region.endP + " (" + region.pages.length + "p) ===");

        if (config.mode === "by_lesson") {
            region.pageLessonMap = {};  // 가로 페이지 → 세로 지문 인덱스 (1-based)
            // 영역의 N번째 페이지 = 세로 N번째 지문 (엑셀 순서 = 세로 순서)
            // 단 가로 라벨에서 출처 코드를 추출할 수 있으면 엑셀로 정확히 매핑
            for (var i = 0; i < region.pages.length; i++) {
                var hp = region.pages[i];
                var hPage = horiz.pages[hp - 1];
                var pInfo = findPageLabelInfo(hPage);
                var lessonNum = null;
                if (pInfo) {
                    if (pInfo.source && sourcesList) {
                        for (var k = 0; k < sourcesList.length; k++) {
                            if (String(sourcesList[k]) === pInfo.source) { lessonNum = k + 1; break; }
                        }
                    }
                    if (!lessonNum && pInfo.num !== null && pInfo.num >= 1 && pInfo.num <= sourcesList.length) {
                        lessonNum = pInfo.num;
                    }
                }
                // fallback: 영역 내 페이지 순서 = 세로 지문 순서
                if (!lessonNum) lessonNum = i + 1;

                if (lessonNum > lessons.length) {
                    warn("  p" + hp + " : 지문" + lessonNum + " - 세로 지문 없음 (세로=" + lessons.length + ")");
                    continue;
                }
                var lesson = lessons[lessonNum - 1];
                region.pageLessonMap[hp] = lessonNum;  // 세로 지문 인덱스 저장

                // 마스터 무시 — 지문 내 섹션 페이지 순서로 매핑 (O-마스터 제외)
                if (!lesson.sections || lesson.sections.length <= config.sectionIdx) {
                    warn("  p" + hp + " : 지문" + lessonNum + " - 섹션" + config.sectionIdx + " 페이지 없음 (sections=" + (lesson.sections ? lesson.sections.length : 0) + ")");
                    continue;
                }
                var srcP = lesson.sections[config.sectionIdx];
                var r = copyPageContent(verti.pages[srcP - 1], hPage, config.tfPos);
                info("  p" + hp + " : 지문" + lessonNum + " (마더텅" + lesson.madertungN + ") 세로 p" + srcP + " [섹션" + config.sectionIdx + "] → " + (r.ok ? "OK" : "FAIL " + r.reason));
            }
        } else if (config.mode === "two_up") {
            // 한 페이지에 2지문 (위/아래 슬롯) — 어휘선택 1/2 전용
            // 영역 슬롯 인덱스 0~ → 지문 1~ (영역 i번째 슬롯 = 지문 i+1)
            // srcMainIdx (0=위/어휘1, 1=아래/어휘2) 의 세로 어휘선택 TF 만 복제
            region.slotLessonMap = {};  // "hp:slot" → 지문 N
            var globalSlot = 0;
            for (var i = 0; i < region.pages.length; i++) {
                var hp = region.pages[i];
                var hPage = horiz.pages[hp - 1];
                var tgtMains = getMainTFsSorted(hPage);
                for (var sl = 0; sl < tgtMains.length; sl++) {
                    var lessonNum = globalSlot + 1;
                    globalSlot++;
                    if (lessonNum > lessons.length) {
                        info("  p" + hp + " slot" + sl + " : 지문 범위 초과 (세로=" + lessons.length + ") - 스킵");
                        continue;
                    }
                    var lesson = lessons[lessonNum - 1];
                    region.slotLessonMap[hp + ":" + sl] = lessonNum;

                    // 세로 어휘선택 페이지 (sections[0]) 의 srcMainIdx TF
                    if (!lesson.sections || lesson.sections.length <= config.sectionIdx) {
                        warn("  p" + hp + " slot" + sl + " : 지문" + lessonNum + " 섹션" + config.sectionIdx + " 없음");
                        continue;
                    }
                    var srcP = lesson.sections[config.sectionIdx];
                    var srcPage = verti.pages[srcP - 1];
                    var srcMains = getMainTFsSorted(srcPage);
                    if (srcMains.length <= config.srcMainIdx) {
                        warn("  p" + hp + " slot" + sl + " : 세로 p" + srcP + " main[" + config.srcMainIdx + "] 없음");
                        continue;
                    }
                    var srcTF = srcMains[config.srcMainIdx];
                    var tgtTF = tgtMains[sl];
                    var tgtBounds = tgtTF.geometricBounds.slice(0);
                    try {
                        var newTF = srcTF.duplicate(hPage);
                        newTF.geometricBounds = tgtBounds;
                        tgtTF.remove();
                        info("  p" + hp + " slot" + sl + " : 지문" + lessonNum + " (마더텅" + lesson.madertungN + ") 세로 p" + srcP + " main[" + config.srcMainIdx + "] → OK");
                    } catch (e) {
                        warn("  p" + hp + " slot" + sl + " : 실패 - " + e.message);
                    }
                }
            }
        } else if (config.mode === "lesson_all") {
            // 병합 region 대응: 페이지 번호 연속 증가 대신 region.pages(O페이지
            // 목록)를 순회 — 사이에 낀 M/간지/판권 페이지를 침범하지 않는다.
            // 목록 소진 시 문서 끝에 O-마스터 페이지 추가 (기존 동작 유지).
            var slotIdx = 0;
            region.pageLessonMap = {};  // 가로 페이지 → 지문 N 매핑 (라벨링 시 사용)
            for (var n = 0; n < lessons.length; n++) {
                var lesson = lessons[n];
                var srcPages = lesson.pracPages;
                if (!srcPages || srcPages.length === 0) {
                    info("  지문" + lesson.num + " : 실전 없음 - 스킵");
                    continue;
                }
                for (var s = 0; s < srcPages.length; s++) {
                    var horizP;
                    if (slotIdx < region.pages.length) {
                        horizP = region.pages[slotIdx];
                    } else {
                        var newPage = horiz.pages.add(LocationOptions.AT_END);
                        try {
                            for (var m = 0; m < horiz.masterSpreads.length; m++) {
                                if (horiz.masterSpreads[m].name === "O-마스터") {
                                    newPage.appliedMaster = horiz.masterSpreads[m];
                                    break;
                                }
                            }
                        } catch (e) {}
                        info("  (페이지 추가) p" + newPage.name);
                        horizP = horiz.pages.length;
                        region.pages.push(horizP);
                    }
                    slotIdx++;
                    var srcP = srcPages[s];
                    var r = copyPageContent(verti.pages[srcP - 1], horiz.pages[horizP - 1], config.tfPos);
                    info("  p" + horizP + " : 지문" + lesson.num + " 세로 p" + srcP + " (실전) → " + (r.ok ? "OK" : "FAIL " + r.reason));
                    region.pageLessonMap[horizP] = lesson.num;
                }
            }
        }
    }

    // 메인 TF y 오름차순 정렬 (위 → 아래)
    function getMainTFsSorted(page) {
        var arr = getMainTFs(page);
        arr.sort(function(a, b) { return a.geometricBounds[0] - b.geometricBounds[0]; });
        return arr;
    }

    function validateAgainstExcel(lessons, sourcesList) {
        info("\n=== 세로 ↔ 엑셀 매칭 (마더텅 N 결정) ===");
        for (var i = 0; i < lessons.length; i++) {
            var l = lessons[i];
            if (l.sourceCode) {
                info("  지문" + l.num + " 세로 p" + l.startP + " 출처=" + l.sourceCode + " → 마더텅" + l.madertungN);
            } else if (l.madertungN === i + 1) {
                warn("  지문" + l.num + " 세로 p" + l.startP + " : 출처 추출 불가, fallback 마더텅" + l.madertungN + "(세로 순서)");
            } else {
                info("  지문" + l.num + " 세로 p" + l.startP + " : 라벨 N=" + l.madertungN);
            }
        }
    }

    // ───────────────────────────────────────────────────────────────
    // 자동 페이지 확장 — 강 지문 수 > 영역 슬롯 수일 때 영역 뒤에 페이지 추가
    // ───────────────────────────────────────────────────────────────
    function regionSlotCount(region) {
        var cfg = region.config;
        if (cfg.mode === "two_up") {
            // 페이지마다 main TF 수 합산
            var n = 0;
            for (var i = 0; i < region.pages.length; i++) {
                n += getMainTFs(horiz.pages[region.pages[i] - 1]).length;
            }
            return n;
        }
        if (cfg.mode === "by_lesson") return region.pages.length;
        return 0;
    }

    function expandRegionPagesIfNeeded(regions, totalLessons) {
        // 영역 슬롯 부족 시 영역 마지막 페이지를 duplicate (뒤에서 앞으로 처리해서 페이지 번호 안 밀리게)
        info("\n=== 영역 슬롯 확장 (목표 지문 " + totalLessons + "개) ===");
        // by_lesson + two_up 영역만 처리 (lesson_all 은 별도)
        var targets = [];
        for (var i = 0; i < regions.length; i++) {
            var r = regions[i];
            if (r.config.mode !== "by_lesson" && r.config.mode !== "two_up") continue;
            targets.push(r);
        }
        // 뒤에서 앞으로
        for (var i = targets.length - 1; i >= 0; i--) {
            var r = targets[i];
            var current = regionSlotCount(r);
            if (current >= totalLessons) {
                info("  [" + r.label + "] 슬롯 " + current + " ≥ " + totalLessons + " - 확장 불필요");
                continue;
            }
            var slotsPerPage = (r.config.mode === "two_up") ? 2 : 1;
            var slotsToAdd = totalLessons - current;
            var pagesToAdd = Math.ceil(slotsToAdd / slotsPerPage);

            var lastPage = horiz.pages[r.endP - 1];
            var lastMaster = lastPage.appliedMaster;
            var lastMains = getMainTFsSorted(lastPage);
            var lastSmallTF = getSmallLabelTFRef(lastPage);

            info("  [" + r.label + "] 슬롯 " + current + " → " + (current + pagesToAdd * slotsPerPage) + ", " + pagesToAdd + "p 추가");
            // 반대 파리티 페이지로 duplicate 하면 스프레드 좌표계에서 프레임이
            // 페이지 밖으로 나가 parentPage 를 잃는다 (2026-08-05 실측: 신규
            // 내지 어휘2 확장 페이지의 main TF 소실 → 문항 7개 누락).
            // 원점을 페이지 기준으로 임시 전환해 bounds 를 페이지 로컬로 재설정.
            var savedOrigin = null;
            try {
                savedOrigin = horiz.viewPreferences.rulerOrigin;
                horiz.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
            } catch (eOr) {}
            var mainBounds = [];
            for (var mb = 0; mb < lastMains.length; mb++) mainBounds.push(lastMains[mb].geometricBounds.slice(0));
            var smallBounds = lastSmallTF ? lastSmallTF.geometricBounds.slice(0) : null;
            var prev = lastPage;
            for (var pa = 0; pa < pagesToAdd; pa++) {
                var newPage = horiz.pages.add(LocationOptions.AFTER, prev);
                try { newPage.appliedMaster = lastMaster; } catch (e) {}
                for (var mi = 0; mi < lastMains.length; mi++) {
                    var src = lastMains[mi];
                    var dup = src.duplicate(newPage);
                    dup.geometricBounds = mainBounds[mi];
                    try { dup.contents = ""; } catch (e) {}
                }
                if (lastSmallTF) {
                    var dupSmall = lastSmallTF.duplicate(newPage);
                    dupSmall.geometricBounds = smallBounds;
                    try { dupSmall.contents = ""; } catch (e) {}
                }
                prev = newPage;
            }
            if (savedOrigin !== null) {
                try { horiz.viewPreferences.rulerOrigin = savedOrigin; } catch (eOr2) {}
            }
            // endP/pages 갱신
            var oldEnd = r.endP;
            r.endP += pagesToAdd;
            for (var x = oldEnd + 1; x <= r.endP; x++) r.pages.push(x);
        }
        // 페이지 번호가 바뀌었으므로 후속 영역의 startP/endP/pages 도 shift
        // 영역 순회: 페이지 추가된 영역 이후의 모든 영역 페이지 번호 +pagesAdded
        // 단순 처리: 영역들을 다시 식별 (재호출)
    }

    function getSmallLabelTFRef(page) {
        var spread = page.parent;
        var arr = [];
        for (var i = 0; i < spread.textFrames.length; i++) {
            var tf = spread.textFrames[i];
            if (!tf.parentPage || tf.parentPage.id !== page.id) continue;
            var b = tf.geometricBounds;
            var w = b[3] - b[1], h = b[2] - b[0];
            if (h >= 30 && w >= 30) continue;
            if (b[2] < 30) continue;
            if (b[1] < 5) continue;
            if (w > 100) continue;
            arr.push({ tf: tf, y: b[0] });
        }
        if (arr.length === 0) return null;
        arr.sort(function(a, b) { return a.y - b.y; });
        return arr[0].tf;
    }

    // ───────────────────────────────────────────────────────────────
    // 자동 검수 (세로 본문 fingerprint ↔ 가로 슬롯 본문)
    // ───────────────────────────────────────────────────────────────
    function fingerprint(c) {
        if (!c) return "";
        var s = c;
        // 시작 라벨 ([N], {N}, N) 제거
        s = s.replace(/^[\[\{]?\d+[\]\}]?\s*/, "");
        s = s.replace(/^\|\s*/, "");
        // 컨트롤/anchor 제거
        var buf = "";
        for (var i = 0; i < s.length; i++) {
            var code = s.charCodeAt(i);
            if (code === 65532 || code < 32) buf += " ";
            else buf += s.charAt(i);
        }
        buf = buf.replace(/\s+/g, " ");
        return trim(buf).substring(0, 50);
    }

    function auditResults(regions, lessons) {
        info("\n=== 자동 검수 (세로 본문 fingerprint 매칭) ===");
        var totalSlot = 0, totalOK = 0, totalWarn = 0;

        for (var ri = 0; ri < regions.length; ri++) {
            var r = regions[ri];
            var cfg = r.config;
            if (cfg.mode === "lesson_all" || cfg.sectionIdx < 0) continue;  // 실전 제외

            var warns = [];

            if (cfg.mode === "two_up") {
                // 영역 i번째 슬롯 = 지문 i+1
                var slot = 0;
                for (var i = 0; i < r.pages.length; i++) {
                    var hp = r.pages[i];
                    var hPage = horiz.pages[hp - 1];
                    var tgtMains = getMainTFsSorted(hPage);
                    for (var s = 0; s < tgtMains.length; s++) {
                        slot++;
                        var lessonN = slot;
                        if (lessonN > lessons.length) continue;
                        var lesson = lessons[lessonN - 1];
                        if (!lesson.sections || lesson.sections.length <= cfg.sectionIdx) continue;
                        var srcP = lesson.sections[cfg.sectionIdx];
                        var srcMains = getMainTFsSorted(verti.pages[srcP - 1]);
                        if (srcMains.length <= cfg.srcMainIdx) continue;
                        var srcFP = fingerprint(srcMains[cfg.srcMainIdx].contents);
                        var hFP = fingerprint(tgtMains[s].contents);
                        totalSlot++;
                        if (srcFP.length > 5 && hFP.indexOf(srcFP.substring(0, 30)) >= 0) {
                            totalOK++;
                        } else if (hFP.length > 5 && srcFP.indexOf(hFP.substring(0, 30)) >= 0) {
                            totalOK++;
                        } else {
                            warns.push("슬롯" + slot + "(p" + hp + " s" + s + "): 가로[" + hFP.substring(0,30) + "] ≠ 세로지문" + lessonN + "[" + srcFP.substring(0,30) + "]");
                            totalWarn++;
                        }
                    }
                }
            } else {
                // by_lesson — 영역 i번째 페이지 = 지문 i+1
                for (var i = 0; i < r.pages.length; i++) {
                    var hp = r.pages[i];
                    var hPage = horiz.pages[hp - 1];
                    var tgtMains = getMainTFsSorted(hPage);
                    if (tgtMains.length === 0) continue;
                    var lessonN = i + 1;
                    if (lessonN > lessons.length) continue;
                    var lesson = lessons[lessonN - 1];
                    if (!lesson.sections || lesson.sections.length <= cfg.sectionIdx) continue;
                    var srcP = lesson.sections[cfg.sectionIdx];
                    var srcMains = getMainTFsSorted(verti.pages[srcP - 1]);
                    if (srcMains.length === 0) continue;

                    // 가로/세로 모든 main TF 페어와이즈로 비교 — 하나라도 매칭되면 OK
                    var ok = false;
                    for (var sm = 0; sm < srcMains.length && !ok; sm++) {
                        var srcFP = fingerprint(srcMains[sm].contents);
                        if (srcFP.length < 5) continue;
                        for (var tm = 0; tm < tgtMains.length && !ok; tm++) {
                            var hFP = fingerprint(tgtMains[tm].contents);
                            if (hFP.length < 5) continue;
                            // 양방향 substring 매칭 (라벨 차이 흡수)
                            if (hFP.indexOf(srcFP.substring(0, 25)) >= 0 || srcFP.indexOf(hFP.substring(0, 25)) >= 0) {
                                ok = true;
                            }
                        }
                    }
                    totalSlot++;
                    if (ok) {
                        totalOK++;
                    } else {
                        var hFPHead = (tgtMains[0].contents) ? fingerprint(tgtMains[0].contents).substring(0, 30) : "(empty)";
                        var srcFPHead = fingerprint(srcMains[0].contents).substring(0, 30);
                        warns.push("p" + hp + ": 가로[" + hFPHead + "] ≠ 세로지문" + lessonN + " p" + srcP + "[" + srcFPHead + "]");
                        totalWarn++;
                    }
                }
            }

            if (warns.length === 0) {
                info("  [" + r.label + "] OK (전체 슬롯 일치)");
            } else {
                warn("  [" + r.label + "] 불일치 " + warns.length + "건:");
                for (var w = 0; w < warns.length; w++) warn("    " + warns[w]);
            }
        }

        info("\n총 " + totalSlot + " 슬롯 검수 - OK " + totalOK + " / 불일치 " + totalWarn);
    }

    // ───────────────────────────────────────────────────────────────
    // 메인
    // ───────────────────────────────────────────────────────────────

    function openOrFind(filePath) {
        // 이미 열려있으면 reuse
        var f = new File(filePath);
        for (var d = 0; d < app.documents.length; d++) {
            try {
                if (app.documents[d].fullName.toString() === f.toString()) {
                    return { doc: app.documents[d], opened: false };
                }
            } catch (e) {}
        }
        var doc = app.open(f, false);
        return { doc: doc, opened: true };
    }

    try {
        info("=== 세로 → 가로 본문 복제 시작 ===");
        info("강 코드: " + settings.gang_code + " (지문 " + settings.sources_list.length + "개)");

        // 1. 가로 (output_indd) 와 세로 열기
        var horizFile = new File(settings.output_indd);
        var vertiFile = new File(settings.verti_path);
        if (!horizFile.exists) throw new Error("가로 사본 없음: " + settings.output_indd);
        if (!vertiFile.exists) throw new Error("세로 파일 없음: " + settings.verti_path);

        var hRes = openOrFind(horizFile.toString());
        var vRes = openOrFind(vertiFile.toString());
        horiz = hRes.doc;
        verti = vRes.doc;
        info("가로 열기: " + horiz.name + " (" + horiz.pages.length + "p)");
        info("세로 열기: " + verti.name + " (" + verti.pages.length + "p)");

        // 2. 세로 분석
        var lessons = analyzeVertical(verti);
        info("\n세로 지문 수: " + lessons.length);

        // 2b. 각 지문의 마더텅 N 결정 (세로 페이지 내 출처/N 추출 → 엑셀 매칭)
        assignMadertungN(lessons, settings.sources_list);

        // 3. 엑셀 검증
        validateAgainstExcel(lessons, settings.sources_list);

        // 4. 가로 영역 식별
        var regions = detectHorizRegions(horiz);
        info("\n가로 영역 감지: " + regions.length + "개");
        for (var i = 0; i < regions.length; i++) {
            info("  [" + regions[i].label + "] p" + regions[i].startP + "~p" + regions[i].endP);
        }

        // 4b. 자동 페이지 확장 — 강 지문 수 > 슬롯 수일 때 영역 뒤에 페이지 추가
        app.doScript(function() {
            expandRegionPagesIfNeeded(regions, lessons.length);
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "expand_pages");
        // 영역 재식별 (페이지 번호 갱신)
        regions = detectHorizRegions(horiz);
        info("\n페이지 확장 후 영역 재감지:");
        for (var i = 0; i < regions.length; i++) {
            info("  [" + regions[i].label + "] p" + regions[i].startP + "~p" + regions[i].endP + " (" + regions[i].pages.length + "p)");
        }

        // 5. 영역별 처리 (Undo 그룹 1개)
        app.doScript(function() {
            for (var i = 0; i < regions.length; i++) {
                processRegion(regions[i], lessons, settings.sources_list);
            }
        }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "vert_to_horiz");

        // 5b. 라벨링 (do_label = true 이면 본문 복제 후 라벨 일괄 변경)
        if (settings.do_label) {
            info("\n=== 라벨링 시작 ===");
            // 문자스타일 찾기 (STEP 01 그룹의 "A_지문 번호B")
            var charStyle = null;
            try {
                var step01Group = horiz.characterStyleGroups.itemByName("STEP 01");
                if (step01Group && step01Group.isValid) {
                    var cs = step01Group.characterStyles.itemByName("A_지문 번호B");
                    if (cs && cs.isValid) charStyle = cs;
                }
            } catch (eCS) {}
            if (!charStyle) {
                warn("문자스타일 'A_지문 번호B' (STEP 01 그룹) 없음 — 스타일 적용 스킵");
            }

            app.doScript(function() {
                for (var ri = 0; ri < regions.length; ri++) {
                    var region = regions[ri];
                    var cfg = region.config;
                    if (!cfg.labelType) continue;  // labelType 없으면 라벨링 안 함 (실전 등)
                    info("\n--- [" + region.label + "] 라벨링 ---");

                    if (cfg.mode === "two_up") {
                        // 페이지의 각 main TF (위/아래 슬롯)에 슬롯별 라벨
                        var globalSlot = 0;
                        for (var pi = 0; pi < region.pages.length; pi++) {
                            var hp = region.pages[pi];
                            var hPage = horiz.pages[hp - 1];
                            var mains = getMainTFsSorted(hPage);
                            for (var si = 0; si < mains.length; si++) {
                                var lessonN_idx = globalSlot;
                                globalSlot++;
                                if (lessonN_idx >= lessons.length) continue;
                                var n = lessons[lessonN_idx].madertungN;
                                if (!n) continue;
                                var displayLabel = (n < 10 ? "0" : "") + n;
                                var ok = applyLabel(mains[si], n, "main_top", charStyle);
                                info("  p" + hp + " slot" + si + " : " + displayLabel + (ok ? " OK" : " FAIL"));
                            }
                        }
                        continue;
                    }

                    // by_lesson — 한 페이지 = 한 지문
                    for (var pi = 0; pi < region.pages.length; pi++) {
                        var hp = region.pages[pi];
                        var hPage = horiz.pages[hp - 1];

                        var n = null;

                        // 1순위: processRegion 에서 저장한 가로 → 세로 지문 매핑 → 마더텅 N
                        if (region.pageLessonMap && region.pageLessonMap[hp]) {
                            var srcLessonIdx = region.pageLessonMap[hp]; // 세로 지문 1-based
                            if (srcLessonIdx >= 1 && srcLessonIdx <= lessons.length) {
                                n = lessons[srcLessonIdx - 1].madertungN;
                            }
                        }
                        // 2순위: 가로 페이지 라벨에서 직접 추출 (출처 → 엑셀 N)
                        if (!n) {
                            n = determineLessonN(hPage, settings.sources_list);
                        }
                        // 3순위: 영역 내 순서 → 같은 인덱스의 세로 지문의 마더텅 N
                        if (!n) {
                            if (pi < lessons.length) {
                                n = lessons[pi].madertungN;
                            }
                        }
                        if (!n) {
                            warn("  p" + hp + " : 마더텅 N 결정 불가 - 스킵");
                            continue;
                        }
                        var labelTF = findLabelTF(hPage, cfg.labelType);
                        if (!labelTF) {
                            warn("  p" + hp + " : 라벨 텍스트프레임 없음");
                            continue;
                        }
                        var displayLabel = (n < 10 ? "0" : "") + n;
                        var ok = applyLabel(labelTF, n, cfg.labelType, charStyle);
                        info("  p" + hp + " : " + displayLabel + (ok ? " OK" : " FAIL"));
                    }
                }
            }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "vert_to_horiz_label");
            info("=== 라벨링 완료 ===");
        }

        // 5c. 자동 검수 (세로 본문 fingerprint ↔ 가로 슬롯 본문)
        try {
            auditResults(regions, lessons);
        } catch (eAudit) {
            warn("자동 검수 실패: " + eAudit.message);
        }

        // 6. 저장
        horiz.save();
        info("\n[저장] " + horiz.fullName);

        // 7. 닫기 (저장 후)
        if (hRes.opened) horiz.close(SaveOptions.YES);
        if (vRes.opened) verti.close(SaveOptions.NO);

        info("=== 작업 완료 ===");

    } catch (e) {
        fail(e.message);
        try { if (horiz) horiz.save(); } catch (e2) {}
    }

})();
