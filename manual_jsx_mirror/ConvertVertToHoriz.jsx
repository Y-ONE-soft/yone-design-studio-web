// ConvertVertToHoriz.jsx
// 세로버전 InDesign 파일의 본문을 가로버전 파일로 옮김
//
// 동작:
//   1. 사용자가 세로 .indd + 가로 .indd 열어두고 스크립트 실행
//   2. 파일명에서 마더텅 강(예: "마더텅7강" → "07") 추출
//   3. madertung_sources.json (엑셀 출처) 로드 → 해당 강의 지문 출처 코드 목록
//   4. 세로 파일 분석: 지문별 마스터 페이지 그룹 + 출처 코드 추출
//   5. 엑셀 vs 세로 순서 검증 (불일치 알림). 엑셀이 정본.
//   6. 가로 영역 자동 감지 (사이드 라벨: "어휘 선택 1", "본문 O/X", "문장 배열" 등)
//   7. 영역마다: 가로 페이지의 라벨에서 마더텅 N번 추출 → 엑셀로 지문 식별 →
//      세로의 해당 지문의 매핑 마스터 페이지를 가로 페이지에 복제
//   8. 라벨링은 안 함 (별도)
//
// 영역 매핑:
//   "어휘 선택 1" → 세로 A-마스터 1번째, 상단 텍스트프레임
//   "어휘 선택 2" → 세로 A-마스터 1번째, 하단 텍스트프레임
//   "본문 O/X"    → 세로 A-마스터 2번째, 전체
//   "본문 정리"   → 세로 B-마스터 1번째
//   "내용 종합"   → 세로 B-마스터 2번째
//   "문장 배열"   → 세로 C-마스터 1번째
//   "빈칸 어휘"   → 세로 C-마스터 2번째
//   "어법 선택"   → 세로 D-마스터 1번째
//   "어법 O/X"    → 세로 D-마스터 2번째
//   "빈칸 어법"   → 세로 E-마스터 1번째
//   "영작 배열"   → 세로 E-마스터 2번째
//   "S 실전 문제" → 세로 O-마스터 (지문당 다수 페이지)

#target indesign

// =====================================================
// 설정
// =====================================================
var JSON_PATH = "/Users/nhj/Documents/작업/Y.ONE STUDIO/조판/인디자인 스크립트/madertung_sources.json";

var REGION_MAP = {
    "어휘 선택 1":  { master: "A-마스터", mIdx: 0, tfPos: "top",    mode: "by_lesson" },
    "어휘 선택 2":  { master: "A-마스터", mIdx: 0, tfPos: "bottom", mode: "by_lesson" },
    "본문 O/X":     { master: "A-마스터", mIdx: 1, tfPos: "all",    mode: "by_lesson" },
    "본문 정리":    { master: "B-마스터", mIdx: 0, tfPos: "all",    mode: "by_lesson" },
    "내용 종합":    { master: "B-마스터", mIdx: 1, tfPos: "all",    mode: "by_lesson" },
    "문장 배열":    { master: "C-마스터", mIdx: 0, tfPos: "all",    mode: "by_lesson" },
    "빈칸 어휘":    { master: "C-마스터", mIdx: 1, tfPos: "all",    mode: "by_lesson" },
    "어법 선택":    { master: "D-마스터", mIdx: 0, tfPos: "all",    mode: "by_lesson" },
    "어법 O/X":     { master: "D-마스터", mIdx: 1, tfPos: "all",    mode: "by_lesson" },
    "빈칸 어법":    { master: "E-마스터", mIdx: 0, tfPos: "all",    mode: "by_lesson" },
    "영작 배열":    { master: "E-마스터", mIdx: 1, tfPos: "all",    mode: "by_lesson" },
    "S 실전 문제":  { master: "O-마스터", mIdx: -1, tfPos: "all",   mode: "lesson_all" }
};

// =====================================================
// 유틸
// =====================================================
function trim(s) { return s.replace(/^\s+|\s+$/g, ""); }

function loadJSON(path) {
    var f = File(path);
    if (!f.exists) return null;
    f.encoding = "UTF-8";
    f.open("r");
    var content = f.read();
    f.close();
    return eval("(" + content + ")");
}

// "한영1_워크북02(마더텅7강)_내지(가로).indd" → "07"
function extractGangCode(name) {
    var m = name.match(/마더텅\s*(\d+)\s*강/);
    if (m) {
        var n = parseInt(m[1]);
        return n < 10 ? "0" + n : "" + n;
    }
    m = name.match(/(\d+)\s*강/);
    if (m) {
        var n = parseInt(m[1]);
        return n < 10 ? "0" + n : "" + n;
    }
    return null;
}

// 라벨 텍스트에서 마더텅 N번 또는 출처 코드 추출
function parseLabel(label) {
    if (!label) return null;
    var s = label.replace(/[\{\}\[\]]/g, "");
    s = trim(s);
    // "7강 4번 200324" 또는 "4번 200324"
    var m1 = s.match(/^(?:\d+\s*강\s*)?(\d+)\s*번\s*(\d{6})/);
    if (m1) return { num: parseInt(m1[1]), source: m1[2] };
    // "N번"만
    var m2 = s.match(/^(?:\d+\s*강\s*)?(\d+)\s*번/);
    if (m2) return { num: parseInt(m2[1]), source: null };
    // 6자리 출처 코드
    var m3 = s.match(/^(\d{6})$/);
    if (m3) return { num: null, source: m3[1] };
    // 1-2자리 숫자
    var m4 = s.match(/^(\d{1,2})$/);
    if (m4) return { num: parseInt(m4[1]), source: null };
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

// 페이지 내 모든 텍스트프레임 (사이드 + 메인) 에서 라벨 추출
function findPageLabelInfo(page) {
    var spread = page.parent;
    var candidates = [];
    for (var i = 0; i < spread.textFrames.length; i++) {
        var tf = spread.textFrames[i];
        if (!tf.parentPage || tf.parentPage.id !== page.id) continue;
        var b = tf.geometricBounds;
        if (isSideLabel(b)) continue; // 영역명 사이드 라벨 제외
        var c = tf.contents ? trim(tf.contents) : "";
        if (c.length === 0) continue;
        // 시작 부분 30자에서 라벨 추출
        var headPart = c.substring(0, 30);
        var info = parseLabel(headPart);
        if (info && (info.num !== null || info.source !== null)) {
            candidates.push(info);
        }
    }
    return candidates.length > 0 ? candidates[0] : null;
}

// 좌표 중심 기반 1:1 매칭
function matchByPosition(srcMains, tgtMains) {
    if (srcMains.length !== tgtMains.length) return null;
    var matches = [];
    var usedTgt = {};
    for (var i = 0; i < srcMains.length; i++) {
        var sb = srcMains[i].geometricBounds;
        var sCx = (sb[1] + sb[3]) / 2;
        var sCy = (sb[0] + sb[2]) / 2;
        var bestJ = -1, bestDist = Infinity;
        for (var j = 0; j < tgtMains.length; j++) {
            if (usedTgt[j]) continue;
            var tb = tgtMains[j].geometricBounds;
            var dist = Math.abs(sCx - (tb[1]+tb[3])/2) + Math.abs(sCy - (tb[0]+tb[2])/2);
            if (dist < bestDist) { bestDist = dist; bestJ = j; }
        }
        if (bestJ >= 0) {
            matches.push({ srcTF: srcMains[i], tgtTF: tgtMains[bestJ] });
            usedTgt[bestJ] = true;
        }
    }
    return matches;
}

// 세로 페이지의 일부 텍스트프레임만 가져옴 (tfPos: all|top|bottom)
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

// 한 페이지의 본문 복제
function copyPageContent(srcPage, tgtPage, tfPos) {
    var srcMains = getSrcTFsByPos(srcPage, tfPos);
    var tgtMains = getMainTFs(tgtPage);
    if (srcMains.length === 0) return { ok: false, reason: "세로 매핑 대상 텍스트프레임 없음" };

    // 가로 페이지가 빈 - 직접 복제
    if (tgtMains.length === 0) {
        for (var i = 0; i < srcMains.length; i++) {
            srcMains[i].duplicate(tgtPage);
        }
        return { ok: true, reason: "직접 복제 (" + srcMains.length + ")" };
    }

    // 가로에 너무 많은 메인이 있고 매핑 대상이 1개면, 가장 가까운 가로 메인 1개와 매핑
    if (tfPos !== "all" && srcMains.length === 1 && tgtMains.length > 1) {
        // 좌표 가장 가까운 가로 메인 선택
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
            return { ok: true, reason: "1:1 매핑 (top/bottom)" };
        }
        return { ok: false, reason: "매칭 실패" };
    }

    // 일반: 좌표 기반 1:1
    var matches = matchByPosition(srcMains, tgtMains);
    if (!matches) {
        return { ok: false, reason: "텍스트프레임 개수 불일치 (src=" + srcMains.length + ", tgt=" + tgtMains.length + ")" };
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

// =====================================================
// 세로 파일 분석
// =====================================================
function analyzeVertical(verti) {
    // 지문 = A-마스터 첫 페이지 기준
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
        var byMaster = { "A-마스터": [], "B-마스터": [], "C-마스터": [], "D-마스터": [], "E-마스터": [], "O-마스터": [] };
        for (var p = startP; p <= endP; p++) {
            var page = verti.pages[p - 1];
            var mn = page.appliedMaster ? page.appliedMaster.name : null;
            if (byMaster[mn]) byMaster[mn].push(p);
        }
        // 세로 지문의 출처 코드 추출 (지문의 어느 페이지에서든 라벨 발견)
        var sourceCode = null;
        for (var p = startP; p <= endP && !sourceCode; p++) {
            var info = findPageLabelInfo(verti.pages[p - 1]);
            if (info && info.source) sourceCode = info.source;
        }
        lessons.push({ num: i + 1, startP: startP, endP: endP, byMaster: byMaster, sourceCode: sourceCode });
    }
    return lessons;
}

// =====================================================
// 가로 영역 식별
// =====================================================
function detectHorizRegions(horiz) {
    var regions = [];
    var current = null;
    var prevPageMaster = null;

    for (var p = 1; p <= horiz.pages.length; p++) {
        var page = horiz.pages[p - 1];
        var label = getSideLabel(page);
        var pageMaster = page.appliedMaster ? page.appliedMaster.name : null;

        if (label && REGION_MAP[label]) {
            // 새 영역 시작
            current = {
                label: label,
                startP: p,
                endP: p,
                pages: [p],
                config: REGION_MAP[label],
                masterName: pageMaster
            };
            regions.push(current);
        } else if (current && pageMaster === current.masterName) {
            // 같은 마스터 + 라벨 없음 = 같은 영역 연속
            current.endP = p;
            current.pages.push(p);
        } else {
            current = null;
        }
        prevPageMaster = pageMaster;
    }
    return regions;
}

// =====================================================
// 영역별 처리
// =====================================================
function processRegion(region, lessons, horiz, sourcesList, log) {
    var config = region.config;
    var label = region.label;
    log("\n=== [" + label + "] 가로 p" + region.startP + "~p" + region.endP + " (" + region.pages.length + "p) ===");

    if (config.mode === "by_lesson") {
        // 각 가로 페이지 → 라벨에서 N 추출 → 해당 지문의 마스터 페이지 복제
        for (var i = 0; i < region.pages.length; i++) {
            var hp = region.pages[i];
            var hPage = horiz.pages[hp - 1];

            // 가로 페이지에서 라벨 정보 추출
            var info = findPageLabelInfo(hPage);
            var lessonNum = null;
            if (info) {
                if (info.num !== null) lessonNum = info.num;
                else if (info.source !== null && sourcesList) {
                    // 출처 코드로 N 찾기
                    for (var k = 0; k < sourcesList.length; k++) {
                        if (sourcesList[k] === info.source) { lessonNum = k + 1; break; }
                    }
                }
            }
            // fallback: 영역 내 페이지 순서 = 지문 순서
            if (!lessonNum) lessonNum = i + 1;

            if (lessonNum > lessons.length) {
                log("  p" + hp + " : 지문" + lessonNum + " - 세로에 없음 (지문 수=" + lessons.length + ")");
                continue;
            }
            var lesson = lessons[lessonNum - 1];
            var srcPages = lesson.byMaster[config.master];
            if (!srcPages || srcPages.length <= config.mIdx) {
                log("  p" + hp + " : 지문" + lessonNum + " - 세로 " + config.master + " idx=" + config.mIdx + " 없음");
                continue;
            }
            var srcP = srcPages[config.mIdx];
            var r = copyPageContent(verti.pages[srcP - 1], hPage, config.tfPos);
            log("  p" + hp + " : 지문" + lessonNum + " 세로 p" + srcP + " " + config.tfPos + " : " + (r.ok ? "OK" : "FAIL - " + r.reason));
        }
    } else if (config.mode === "lesson_all") {
        // 실전: 각 지문의 O 페이지 모두를 순서대로 가로 페이지에 매핑
        var horizP = region.startP;
        for (var n = 0; n < lessons.length; n++) {
            var lesson = lessons[n];
            var srcPages = lesson.byMaster[config.master];
            if (!srcPages || srcPages.length === 0) {
                log("  지문" + lesson.num + " : 세로 O 없음 - 스킵");
                continue;
            }
            for (var s = 0; s < srcPages.length; s++) {
                while (horizP > horiz.pages.length) {
                    var newPage = horiz.pages.add(LocationOptions.AT_END);
                    try {
                        for (var m = 0; m < horiz.masterSpreads.length; m++) {
                            if (horiz.masterSpreads[m].name === config.master) {
                                newPage.appliedMaster = horiz.masterSpreads[m];
                                break;
                            }
                        }
                    } catch (e) {}
                    log("  (페이지 추가) 가로 p" + newPage.name);
                }
                var srcP = srcPages[s];
                var r = copyPageContent(verti.pages[srcP - 1], horiz.pages[horizP - 1], config.tfPos);
                log("  p" + horizP + " : 지문" + lesson.num + " 세로 p" + srcP + " : " + (r.ok ? "OK" : "FAIL - " + r.reason));
                horizP++;
            }
        }
    }
}

// =====================================================
// 엑셀 vs 세로 순서 검증
// =====================================================
function validateAgainstExcel(lessons, sourcesList, log) {
    var warnings = [];
    log("\n=== 세로 ↔ 엑셀 순서 검증 ===");
    for (var i = 0; i < lessons.length; i++) {
        var l = lessons[i];
        var expected = (i < sourcesList.length) ? sourcesList[i] : null;
        if (!l.sourceCode) {
            log("  지문" + l.num + " 세로 p" + l.startP + " : 출처 코드 추출 불가, 엑셀 기댓값=" + expected);
        } else if (expected && l.sourceCode !== expected) {
            var msg = "지문" + l.num + " 세로 p" + l.startP + " 출처=" + l.sourceCode + ", 엑셀 기댓값=" + expected;
            log("  ⚠️ " + msg);
            warnings.push(msg);
        } else {
            log("  지문" + l.num + " 세로 p" + l.startP + " 출처=" + l.sourceCode + " ✓");
        }
    }
    return warnings;
}

// =====================================================
// 다이얼로그
// =====================================================
function selectDocuments() {
    if (app.documents.length < 2) {
        alert("가로 .indd와 세로 .indd 두 파일을 모두 열어주세요.");
        return null;
    }
    var dlg = new Window("dialog", "세로 → 가로 본문 복제");
    dlg.alignChildren = "left";
    dlg.add("statictext", undefined, "가로 파일 (대상):");
    var horizDD = dlg.add("dropdownlist");
    horizDD.preferredSize.width = 400;
    for (var i = 0; i < app.documents.length; i++) horizDD.add("item", app.documents[i].name);

    dlg.add("statictext", undefined, "세로 파일 (소스):");
    var vertiDD = dlg.add("dropdownlist");
    vertiDD.preferredSize.width = 400;
    for (var i = 0; i < app.documents.length; i++) vertiDD.add("item", app.documents[i].name);

    var hG = -1, vG = -1;
    for (var i = 0; i < app.documents.length; i++) {
        var n = app.documents[i].name;
        if (n.indexOf("(가로)") >= 0 || n.indexOf("가로)") >= 0) hG = i;
    }
    if (hG < 0) hG = 0;
    vG = (hG === 0) ? Math.min(1, app.documents.length - 1) : 0;
    horizDD.selection = hG;
    vertiDD.selection = vG;

    var btn = dlg.add("group");
    btn.add("button", undefined, "실행", { name: "ok" });
    btn.add("button", undefined, "취소", { name: "cancel" });

    if (dlg.show() !== 1) return null;
    if (horizDD.selection.index === vertiDD.selection.index) {
        alert("가로와 세로는 다른 파일이어야 합니다.");
        return null;
    }
    return {
        horiz: app.documents[horizDD.selection.index],
        verti: app.documents[vertiDD.selection.index]
    };
}

// =====================================================
// 메인
// =====================================================
var verti = null;
var horiz = null;

function main() {
    var docs = selectDocuments();
    if (!docs) return;
    horiz = docs.horiz;
    verti = docs.verti;

    // JSON 로드
    var sourcesData = loadJSON(JSON_PATH);
    if (!sourcesData) {
        alert("엑셀 출처 JSON 로드 실패: " + JSON_PATH);
        return;
    }

    // 강 추출 (세로 파일명에서, 없으면 가로에서, 그도 없으면 01)
    var gangCode = extractGangCode(verti.name) || extractGangCode(horiz.name) || "01";
    var sourcesList = sourcesData[gangCode];
    if (!sourcesList) {
        alert("엑셀에 강 '" + gangCode + "' 데이터 없음. JSON 확인: " + JSON_PATH);
        return;
    }

    var debugLog = "";
    function log(s) { debugLog += s + "\n"; }

    app.doScript(function() {
        log("■ 세로: " + verti.name + " (" + verti.pages.length + "p)");
        log("■ 가로: " + horiz.name + " (" + horiz.pages.length + "p)");
        log("■ 강: " + gangCode + " (" + sourcesList.length + "개 지문)");

        var lessons = analyzeVertical(verti);
        log("\n세로 분석: " + lessons.length + " 지문");

        // 엑셀 검증
        validateAgainstExcel(lessons, sourcesList, log);

        // 가로 영역 식별
        var regions = detectHorizRegions(horiz);
        log("\n가로 영역 감지: " + regions.length + "개");
        for (var i = 0; i < regions.length; i++) {
            log("  [" + regions[i].label + "] p" + regions[i].startP + "~p" + regions[i].endP);
        }

        // 영역별 처리
        for (var i = 0; i < regions.length; i++) {
            processRegion(regions[i], lessons, horiz, sourcesList, log);
        }
        log("\n=== 작업 완료 ===");
    }, ScriptLanguage.JAVASCRIPT, undefined, UndoModes.ENTIRE_SCRIPT, "세로→가로 본문 복제");

    var f = File("/tmp/ConvertVertToHoriz_log.txt");
    f.encoding = "UTF-8";
    f.open("w");
    f.write(debugLog);
    f.close();

    alert("작업 완료\n로그: /tmp/ConvertVertToHoriz_log.txt");
}

main();
