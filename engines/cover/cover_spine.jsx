#target illustrator

// 비대화형 표지 세네카 조정 스크립트
// settings.json에서 파라미터를 읽어 실행
(function () {
    app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;

    var MM = 2.834645669;
    var COVER_W = 210 * MM;
    var BLEED = 3 * MM;

    // 설정 파일 읽기
    var settingsPath = "%%SETTINGS_PATH%%";
    var sf = new File(settingsPath);
    if (!sf.exists) { $.writeln("ERROR: settings not found: " + settingsPath); return; }
    sf.open("r"); sf.encoding = "UTF-8";
    var raw = sf.read(); sf.close();

    // 간이 JSON 파서 (ExtendScript에는 JSON.parse 없음)
    var cfg;
    try {
        cfg = eval("(" + raw + ")");
    } catch (e) { $.writeln("ERROR: JSON parse: " + e); return; }

    var aiPath = cfg.ai_path;
    var newSpineMM = cfg.spine_mm;
    var outPdfPath = cfg.pdf_path;
    var aiOutPath = cfg.ai_out_path;      // AI 저장 경로 (아웃라인 전)
    var deleteSpine = cfg.delete_spine;   // true/false
    var doOutline = cfg.outline;          // true/false
    var logPath = cfg.log_path;
    var issueNum = cfg.issue_num;         // 새 주차수 (null이면 안 함)
    var oldIssue = cfg.old_issue;         // 파일명에서 추출한 기존 주차수 (예: "03")

    // 로그 헬퍼
    var logLines = [];
    function log(msg) { logLines.push(msg); }

    function writeLog() {
        if (!logPath) return;
        var lf = new File(logPath);
        lf.open("w"); lf.encoding = "UTF-8";
        lf.write(logLines.join("\r"));
        lf.close();
    }

    // 파일 열기
    var aiFile = new File(aiPath);
    if (!aiFile.exists) { log("ERROR: AI file not found: " + aiPath); writeLog(); return; }

    log("파일 열기: " + aiFile.name);
    var doc = app.open(aiFile);
    var ab = doc.artboards[0];
    var rect = ab.artboardRect;

    var abLeft = rect[0], abTop = rect[1], abRight = rect[2], abBottom = rect[3];
    var currentWidth = abRight - abLeft;
    var currentSpine = currentWidth - (2 * COVER_W);
    var currentSpineMM = Math.round(currentSpine / MM * 10) / 10;

    log("현재 세네카: " + currentSpineMM + "mm");
    log("목표 세네카: " + newSpineMM + "mm");

    var newSpine = newSpineMM * MM;
    var diff = newSpine - currentSpine;
    var hasSpineChange = Math.abs(diff) >= 0.01;

    // 레이어 잠금 해제
    var layerLocks = [];
    for (var li = 0; li < doc.layers.length; li++) {
        layerLocks[li] = doc.layers[li].locked;
        doc.layers[li].locked = false;
    }

    var movedFront = 0, movedSpine = 0, deletedSpine = 0, skippedBG = 0;

    if (hasSpineChange) {
        var spineLeftX = abLeft + COVER_W;
        var spineRightX = spineLeftX + currentSpine;
        var spineShift = diff / 2;

        // 작업 대상 수집
        var topItems = [];
        for (var i = 0; i < doc.pageItems.length; i++) {
            if (doc.pageItems[i].parent.typename === "Layer") {
                topItems.push(doc.pageItems[i]);
            }
        }

        var realItems = [], guideItems = [];
        for (var i = 0; i < topItems.length; i++) {
            var b = topItems[i].geometricBounds;
            if ((b[2] - b[0]) < 0.1) guideItems.push(topItems[i]);
            else realItems.push(topItems[i]);
        }

        var workItems = [];
        if (realItems.length === 1 && realItems[0].typename === "GroupItem") {
            var mainGroup = realItems[0];
            for (var i = 0; i < mainGroup.pageItems.length; i++) workItems.push(mainGroup.pageItems[i]);
            for (var i = 0; i < guideItems.length; i++) workItems.push(guideItems[i]);
            log("구조: 단일 그룹 (" + workItems.length + "개)");
        } else {
            for (var i = 0; i < topItems.length; i++) workItems.push(topItems[i]);
            log("구조: 플랫 (" + workItems.length + "개)");
        }

        for (var i = workItems.length - 1; i >= 0; i--) {
            var item = workItems[i];
            var wasLocked = item.locked;
            if (wasLocked) item.locked = false;

            var bounds = item.geometricBounds;
            var itemLeft = bounds[0], itemRight = bounds[2];
            var itemWidth = itemRight - itemLeft;
            var itemCenterX = (itemLeft + itemRight) / 2;

            if (itemWidth > COVER_W * 0.9) {
                if (itemCenterX >= spineRightX) {
                    // 앞표지 쪽 배경 → 이동
                    item.translate(diff, 0);
                    movedFront++;
                } else if (diff > 0) {
                    // 뒤표지/전체 배경 + 세네카 넓어짐 → 오른쪽으로 확장
                    var scaleX = (itemWidth + diff) / itemWidth * 100;
                    item.resize(scaleX, 100, true, true, true, true, true, Transformation.TOPLEFT);
                    skippedBG++;
                } else {
                    skippedBG++;
                }
                if (wasLocked) item.locked = true;
                continue;
            }

            if (itemCenterX >= spineLeftX && itemCenterX < spineRightX) {
                if (deleteSpine && newSpineMM <= 3) {
                    item.remove(); deletedSpine++;
                } else {
                    // 세네카 오브젝트: 배경 vs 텍스트/로고 구분
                    // 배경 판별: 대지 높이의 90% 이상 + 단순 도형(앵커 6개 이하) 또는 이미지
                    var itemHeight = bounds[1] - bounds[3]; // top - bottom
                    var abHeight = abTop - abBottom;
                    var isSpineBG = false;

                    if (itemHeight >= abHeight * 0.9) {
                        // 높이가 대지 전체를 채움 → 후보
                        if (item.typename === "PathItem" && item.pathPoints.length <= 6) {
                            isSpineBG = true; // 단순 도형 (사각형 등)
                        } else if (item.typename === "PlacedItem" || item.typename === "RasterItem") {
                            isSpineBG = true; // 이미지
                        } else if (item.typename === "GroupItem") {
                            // 그룹 내부가 단순한지 확인 (자식 3개 이하 + 첫 자식이 단순 도형)
                            if (item.pageItems.length <= 3) {
                                var first = item.pageItems[0];
                                if (first && first.typename === "PathItem" && first.pathPoints.length <= 6) {
                                    isSpineBG = true;
                                }
                                if (first && (first.typename === "PlacedItem" || first.typename === "RasterItem")) {
                                    isSpineBG = true;
                                }
                            }
                        }
                    }

                    if (isSpineBG && currentSpine > 0) {
                        // 배경 → 세네카 폭 비율로 리사이즈 + 새 중앙 정렬
                        var spineScale = newSpine / currentSpine * 100;
                        var newSpineCenter = spineLeftX + newSpine / 2;
                        item.resize(spineScale, 100, true, true, true, true, true, Transformation.CENTER);
                        var nb = item.geometricBounds;
                        item.translate(newSpineCenter - (nb[0] + nb[2]) / 2, 0);
                        log("  세네카 배경 리사이즈: " + item.typename);
                    } else {
                        // 텍스트/로고 → 중앙 이동만
                        item.translate(spineShift, 0);
                    }
                    movedSpine++;
                    if (wasLocked) item.locked = true;
                }
            } else if (itemCenterX >= spineRightX) {
                item.translate(diff, 0); movedFront++;
                if (wasLocked) item.locked = true;
            } else {
                if (wasLocked) item.locked = true;
            }
        }

        var newRight = abLeft + (2 * COVER_W) + newSpine;
        ab.artboardRect = [abLeft, abTop, newRight, abBottom];
        log("대지 변경: " + Math.round(currentWidth / MM) + "mm -> " + Math.round((newRight - abLeft) / MM) + "mm");
    }

    log("앞표지 이동: " + movedFront + "개, 세네카: " + movedSpine + "개, 삭제: " + deletedSpine + "개, 배경: " + skippedBG + "개");

    // 주차수 변경 (아웃라인 전에 실행)
    // 글자 단위 교체로 폰트/스타일 보존
    // 제외: 4자리 년도(2026), 학기(1학기), 학교 학년 등
    if (issueNum !== null && issueNum !== undefined) {
        var tf = doc.textFrames;
        var changed = 0;
        var newNum = String(issueNum);  // "5"

        log("텍스트 프레임 수: " + tf.length);
        for (var i = 0; i < tf.length; i++) {
            var content = tf[i].contents;
            var trimmed = content.replace(/\s/g, "");
            log("  TF[" + i + "]: \"" + content + "\"");

            // 제외: 4자리 년도, N학기, 빈 텍스트
            if (trimmed.match(/^\d{4}$/)) continue;
            if (trimmed.match(/\d\uD559\uAE30/)) continue;
            if (trimmed.length === 0) continue;

            // 단독 1-2자리 숫자인 경우 교체
            if (trimmed.match(/^\d{1,2}$/)) {
                // 자리수 맞추기: 기존이 2자리("03")면 새 값도 2자리("05")로
                var newTarget = (trimmed.length === 2 && newNum.length === 1) ? "0" + newNum : newNum;

                if (trimmed === newTarget) {
                    log("  → skip: 이미 같은 값 \"" + trimmed + "\"");
                    continue;
                }

                if (trimmed.length === newTarget.length) {
                    for (var c = 0; c < newTarget.length; c++) {
                        tf[i].characters[c].contents = newTarget.charAt(c);
                    }
                    changed++;
                    log("  변경: \"" + content + "\" → \"" + newTarget + "\"");
                } else {
                    log("  주의: \"" + content + "\" 자리수 불일치 (" + trimmed.length + " → " + newTarget.length + ") 스킵");
                }
                continue;
            }

            // VOL.XX / WEEKXX 패턴
            // "배재고2VOL.01" → "배재고2VOL.05", "WEEK03" → "WEEK05"
            var prefixes = ["VOL.", "WEEK"];
            for (var pi = 0; pi < prefixes.length; pi++) {
                var prefix = prefixes[pi];
                var pPos = content.toUpperCase().indexOf(prefix);
                if (pPos < 0) continue;
                var numStart = pPos + prefix.length;
                // 개행/공백 건너뛰기 (WEEK\n03 같은 경우)
                while (numStart < content.length && content.charAt(numStart).match(/[\r\n\s]/)) {
                    numStart++;
                }
                var numStr = "";
                var ni = numStart;
                while (ni < content.length && content.charAt(ni).match(/\d/)) {
                    numStr += content.charAt(ni);
                    ni++;
                }
                if (numStr.length > 0) {
                    var newVal = (numStr.length === 2 && newNum.length === 1) ? "0" + newNum : newNum;
                    if (numStr !== newVal && numStr.length === newVal.length) {
                        for (var c = 0; c < newVal.length; c++) {
                            tf[i].characters[numStart + c].contents = newVal.charAt(c);
                        }
                        changed++;
                        log("  변경(" + prefix + "): \"" + content + "\" " + prefix + numStr + " → " + prefix + newVal);
                    } else if (numStr === newVal) {
                        log("  → skip: 이미 같은 값 " + prefix + numStr);
                    } else {
                        log("  주의: " + prefix + numStr + " 자리수 불일치 스킵");
                    }
                }
                break;
            }
        }
        if (changed > 0) log("주차수 변경: " + changed + "개 텍스트");
        else log("주차수: 변경 대상 텍스트 없음 (아웃라인 처리됨)");
    }

    // AI 파일 저장 (아웃라인 전 — 편집 가능한 상태 보존)
    if (aiOutPath) {
        var aiFile = new File(aiOutPath);
        var aiOpts = new IllustratorSaveOptions();
        aiOpts.compatibility = Compatibility.ILLUSTRATOR17;
        aiOpts.pdfCompatible = true;
        doc.saveAs(aiFile, aiOpts);
        log("AI 저장: " + aiFile.name);
    }

    // 텍스트 아웃라인
    if (doOutline) {
        var tf = doc.textFrames;
        var outlineCount = 0;
        for (var i = tf.length - 1; i >= 0; i--) {
            try { tf[i].createOutline(); outlineCount++; } catch (e) {}
        }
        log("아웃라인: " + outlineCount + "개");
    }

    // PDF 저장 — 고품질 인쇄 프리셋 + 도련 3mm
    var pdfFile = new File(outPdfPath);
    var pdfOpts = new PDFSaveOptions();
    try {
        pdfOpts.pDFPreset = "[고품질 인쇄]";
    } catch (e1) {
        try {
            pdfOpts.pDFPreset = "[High Quality Print]";
        } catch (e2) {
            // 프리셋 없으면 기본값 사용
        }
    }
    pdfOpts.preserveEditability = false;
    pdfOpts.generateThumbnails = true;
    pdfOpts.viewAfterSaving = false;
    pdfOpts.bleedOffsetRect = [BLEED, BLEED, BLEED, BLEED];
    doc.saveAs(pdfFile, pdfOpts);
    log("PDF: " + pdfFile.fsName);

    // 레이어 잠금 복원 후 닫기
    for (var li = 0; li < doc.layers.length; li++) {
        doc.layers[li].locked = layerLocks[li];
    }
    doc.close(SaveOptions.DONOTSAVECHANGES);

    app.userInteractionLevel = UserInteractionLevel.DISPLAYALERTS;
    log("완료");
    writeLog();
})();
