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

    var movedFront = 0, movedSpine = 0, resizedSpine = 0, deletedSpine = 0, skippedBG = 0;
    var SPINE_BOX_WIDTH_TOL = 5 * MM;       // 세네카 박스 폭 허용오차 (5mm — 박스가 currentSpine과 다소 달라도 인식)
    var SPINE_BOX_HEIGHT_RATIO = 0.6;       // 박스로 인정할 최소 높이 (대지 대비)

    var spineLeftX = abLeft + COVER_W;
    var spineRightX = spineLeftX + currentSpine;
    var newSpineCenterX = spineLeftX + newSpine / 2;
    var abHeight = abTop - abBottom;

    // 그룹 안에 세네카 박스 후보(폭이 현재 세네카와 비슷하고 높이가 충분한 path/image)가 있는지 검사.
    // 컨테이너 그룹(BG + 텍스트 묶음) → true: 재귀해서 박스 리사이즈, 텍스트 개별 정렬
    // 단위 그룹(로고/장식) → false: 그룹째 중앙정렬, 내부 분해 안 함
    function hasSpineBGCandidate(group) {
        if (!group.pageItems || group.pageItems.length === 0) return false;
        for (var hi = 0; hi < group.pageItems.length; hi++) {
            var hc = group.pageItems[hi];
            var hb = hc.geometricBounds;
            var hw = hb[2] - hb[0];
            var hh = hb[1] - hb[3];
            var hisPath = (hc.typename === "PathItem"
                           || hc.typename === "CompoundPathItem"
                           || hc.typename === "PlacedItem"
                           || hc.typename === "RasterItem");
            if (hisPath
                && Math.abs(hw - currentSpine) < SPINE_BOX_WIDTH_TOL
                && hh > abHeight * SPINE_BOX_HEIGHT_RATIO) {
                return true;
            }
            if (hc.typename === "GroupItem" && hasSpineBGCandidate(hc)) {
                return true;
            }
        }
        return false;
    }

    // 그룹의 자식들이 여러 영역(앞/세네카/뒤)에 걸쳐 있는지 검사.
    // 다영역 그룹 → 자식 재귀해서 영역별 분류
    // 한 영역에 몰린 그룹 → 통째 처리 (그림/디자인 분해 방지)
    function spansMultipleRegions(group) {
        if (!group.pageItems || group.pageItems.length === 0) return false;
        var regions = {};
        for (var i = 0; i < group.pageItems.length; i++) {
            var ch = group.pageItems[i];
            var b = ch.geometricBounds;
            var cx = (b[0] + b[2]) / 2;
            var r;
            if (cx < spineLeftX) r = "back";
            else if (cx < spineRightX) r = "spine";
            else r = "front";
            regions[r] = true;
        }
        var count = 0;
        for (var k in regions) count++;
        return count >= 2;
    }

    // 그룹 자식 중 폭이 currentSpine과 비슷한 path를 찾아 newSpine 폭으로 리사이즈.
    // 단위 그룹 안의 세네카 배경 박스 처리 — height 조건 필수 (글자/장식 path 제외).
    function resizeSpineBoxesInGroup(group) {
        if (!group.pageItems || group.pageItems.length === 0) return 0;
        var count = 0;
        for (var bi = 0; bi < group.pageItems.length; bi++) {
            var bc = group.pageItems[bi];
            var bb = bc.geometricBounds;
            var bw = bb[2] - bb[0];
            var bh = bb[1] - bb[3];
            var bisPath = (bc.typename === "PathItem"
                           || bc.typename === "CompoundPathItem"
                           || bc.typename === "PlacedItem"
                           || bc.typename === "RasterItem");
            // 박스 인정: widthMatches + height >= 표지 절반 (글자/장식 path 비율 깨짐 방지)
            if (bisPath
                && Math.abs(bw - currentSpine) < SPINE_BOX_WIDTH_TOL
                && bh > abHeight * 0.5) {
                // 박스 발견 → 새 세네카 중앙 + newSpine 폭으로 리사이즈
                var bcx = (bb[0] + bb[2]) / 2;
                var bdx = newSpineCenterX - bcx;
                if (Math.abs(bdx) > 0.001) bc.translate(bdx, 0);
                var bsx = (newSpine / bw) * 100;
                bc.resize(bsx, 100, true, true, true, true, false, Transformation.CENTER);
                count++;
            } else if (bc.typename === "GroupItem") {
                count += resizeSpineBoxesInGroup(bc);
            }
        }
        return count;
    }

    // 재귀 처리:
    //   - 와이드(>189mm) 그룹 → 자식 재귀 (각 영역 개별 분류)
    //   - 세네카 영역 컨테이너 그룹(BG 포함) → 자식 재귀
    //   - 세네카 영역 단위 그룹(로고/장식) → 그룹째 중앙정렬
    //   - 앞표지 그룹 / 뒤표지 그룹 → 통째로 이동 (또는 고정)
    //   - 단일 아이템 → 세네카 박스 감지 후 리사이즈 또는 강제 중앙정렬
    function processItemRecursive(item) {
        var wasLocked = item.locked;
        if (wasLocked) item.locked = false;

        var bounds = item.geometricBounds;
        var itemLeft = bounds[0];
        var itemRight = bounds[2];
        var itemWidth = itemRight - itemLeft;
        var itemHeight = bounds[1] - bounds[3];
        var itemCenterX = (itemLeft + itemRight) / 2;
        var isGroup = (item.typename === "GroupItem" && item.pageItems.length > 0);

        // 와이드 (>189mm) — 전폭 배경 또는 다중 영역 그룹
        if (itemWidth > COVER_W * 0.9) {
            if (isGroup && spansMultipleRegions(item)) {
                // 다영역 와이드 그룹 (예: 표지 전체 컨테이너) → 자식 재귀로 영역별 분류
                // 각 자식은 자기 영역에서 처리됨 (세네카 박스 리사이즈, 텍스트 정렬, 앞표지 평행이동 등)
                var wcs = [];
                for (var ci = 0; ci < item.pageItems.length; ci++) wcs.push(item.pageItems[ci]);
                for (var cj = wcs.length - 1; cj >= 0; cj--) processItemRecursive(wcs[cj]);
            } else {
                // 한 영역에 몰린 와이드 그룹 또는 단일 와이드 path → 통째 처리
                if (itemCenterX >= spineRightX) {
                    // 앞표지 영역: 통째로 이동
                    item.translate(diff, 0);
                    movedFront++;
                } else if (diff > 0) {
                    if (isGroup) {
                        // 그룹 가로 확대는 자식 모두 같이 확대돼 디자인 깨짐 → 스킵
                        skippedBG++;
                    } else {
                        var bgScale = (itemWidth + diff) / itemWidth * 100;
                        item.resize(bgScale, 100, true, true, true, true, true, Transformation.TOPLEFT);
                        skippedBG++;
                    }
                } else {
                    skippedBG++;
                }
            }
            if (wasLocked) item.locked = true;
            return;
        }

        // 분류 (OLD 세네카 경계 기준)
        if (itemCenterX >= spineLeftX && itemCenterX < spineRightX) {
            // ── 세네카 영역 ──
            if (deleteSpine && newSpineMM <= 3) {
                item.remove();
                deletedSpine++;
                return;
            }
            if (isGroup) {
                if (hasSpineBGCandidate(item)) {
                    // 컨테이너 그룹 (BG + 텍스트 묶음): 자식 재귀
                    var scs = [];
                    for (var ck = 0; ck < item.pageItems.length; ck++) scs.push(item.pageItems[ck]);
                    for (var cl = scs.length - 1; cl >= 0; cl--) processItemRecursive(scs[cl]);
                } else {
                    // 단위 그룹 (로고/장식 또는 박스+텍스트): 그룹째 중앙정렬 (내부 분해 X)
                    var udx = newSpineCenterX - itemCenterX;
                    if (Math.abs(udx) > 0.001) item.translate(udx, 0);
                    movedSpine++;
                    log("  세네카 단위 그룹 중앙정렬: " + item.typename
                         + " (" + item.pageItems.length + "개 자식)");
                    // 그룹 안에 widthMatches인 박스 path가 있으면 newSpine 폭으로 리사이즈
                    if (hasSpineChange) {
                        var groupBoxes = resizeSpineBoxesInGroup(item);
                        if (groupBoxes > 0) {
                            resizedSpine += groupBoxes;
                            log("  단위 그룹 안 박스 리사이즈: " + groupBoxes + "개");
                        }
                    }
                }
            } else {
                // 단일 아이템: 세네카 박스(바탕) 감지
                var isPath = (item.typename === "PathItem"
                              || item.typename === "CompoundPathItem"
                              || item.typename === "PlacedItem"
                              || item.typename === "RasterItem");
                // width tol 5mm — currentSpine과 가까우면 박스로 인정 (좁은 박스도 포함)
                var widthMatchesSpine = Math.abs(itemWidth - currentSpine) < SPINE_BOX_WIDTH_TOL;
                var heightMatchesCover = itemHeight > abHeight * SPINE_BOX_HEIGHT_RATIO;
                var isSpineBox = isPath && widthMatchesSpine && heightMatchesCover;

                if (isSpineBox && hasSpineChange) {
                    // 세네카 박스 → 새 세네카 중앙에 맞추고 newSpine 폭으로 리사이즈
                    var boxCenterDx = newSpineCenterX - itemCenterX;
                    if (Math.abs(boxCenterDx) > 0.001) item.translate(boxCenterDx, 0);
                    var sx = (newSpine / itemWidth) * 100;
                    item.resize(sx, 100, true, true, true, true, false, Transformation.CENTER);
                    resizedSpine++;
                    log("  세네카 박스 리사이즈: " + item.typename
                         + " (" + Math.round(itemWidth/MM*10)/10 + "mm → " + Math.round(newSpine/MM*10)/10 + "mm)");
                } else {
                    // 일반 세네카 아이템(텍스트/로고/장식) → 새 세네카 중앙으로 강제 정렬
                    var dx = newSpineCenterX - itemCenterX;
                    if (Math.abs(dx) > 0.001) item.translate(dx, 0);
                    movedSpine++;
                }
            }
        } else if (itemCenterX >= spineRightX) {
            // ── 앞표지: 통째로 이동 ──
            item.translate(diff, 0);
            movedFront++;
        }
        // ── 뒤표지: 고정 ──

        if (wasLocked) item.locked = true;
    }

    // 아웃라인 후 재중앙정렬 (PDF 출력 직전에 호출) — 글리프 바운드 기준 정확 정렬
    function recenterSpineItemsRecursive(newLeft, newRight, newCenter) {
        function recurse(item) {
            var wasLocked = item.locked;
            if (wasLocked) item.locked = false;

            var bounds = item.geometricBounds;
            var iw = bounds[2] - bounds[0];
            var icx = (bounds[0] + bounds[2]) / 2;
            var isGroup = (item.typename === "GroupItem" && item.pageItems.length > 0);

            // 와이드: 다영역 그룹만 자식 재귀, 그 외는 통째 유지 (메인 패스에서 위치 처리됨)
            if (iw > COVER_W * 0.9) {
                if (isGroup && spansMultipleRegions(item)) {
                    var wch = [];
                    for (var ri = 0; ri < item.pageItems.length; ri++) wch.push(item.pageItems[ri]);
                    for (var rj = wch.length - 1; rj >= 0; rj--) recurse(wch[rj]);
                }
                if (wasLocked) item.locked = true;
                return;
            }

            // 새 세네카 영역 안: 재중앙정렬 또는 그룹 재귀
            if (icx >= newLeft && icx < newRight) {
                if (isGroup) {
                    if (hasSpineBGCandidate(item)) {
                        // 컨테이너 그룹: 자식 재귀
                        var sch = [];
                        for (var rk = 0; rk < item.pageItems.length; rk++) sch.push(item.pageItems[rk]);
                        for (var rl = sch.length - 1; rl >= 0; rl--) recurse(sch[rl]);
                    } else {
                        // 단위 그룹 (로고/아웃라인된 텍스트): 그룹째 재중앙정렬
                        var rgdx = newCenter - icx;
                        if (Math.abs(rgdx) > 0.001) item.translate(rgdx, 0);
                    }
                } else {
                    var rdx = newCenter - icx;
                    if (Math.abs(rdx) > 0.001) item.translate(rdx, 0);
                }
            }
            // 앞표지/뒤표지 영역: 메인 패스에서 처리 완료, 건드리지 않음

            if (wasLocked) item.locked = true;
        }

        var rti = [];
        for (var ri2 = 0; ri2 < doc.pageItems.length; ri2++) {
            if (doc.pageItems[ri2].parent.typename === "Layer") {
                rti.push(doc.pageItems[ri2]);
            }
        }
        for (var rj2 = rti.length - 1; rj2 >= 0; rj2--) {
            recurse(rti[rj2]);
        }
    }

    // 최상위 아이템 (Layer 직속) 수집 후 재귀 처리
    // hasSpineChange와 무관하게 항상 실행 (세네카 변경 없을 때도 중앙정렬 보정)
    var topLevelItems = [];
    for (var ti = 0; ti < doc.pageItems.length; ti++) {
        if (doc.pageItems[ti].parent.typename === "Layer") {
            topLevelItems.push(doc.pageItems[ti]);
        }
    }
    log("최상위 아이템: " + topLevelItems.length + "개");
    for (var tj = topLevelItems.length - 1; tj >= 0; tj--) {
        processItemRecursive(topLevelItems[tj]);
    }

    // 대지 크기 변경
    if (hasSpineChange) {
        var newRight = abLeft + (2 * COVER_W) + newSpine;
        ab.artboardRect = [abLeft, abTop, newRight, abBottom];
        log("대지 변경: " + Math.round(currentWidth / MM) + "mm -> " + Math.round((newRight - abLeft) / MM) + "mm");
    }

    log("앞표지 이동: " + movedFront + "개, 세네카 정렬: " + movedSpine + "개, 박스 리사이즈: " + resizedSpine + "개, 삭제: " + deletedSpine + "개, 배경: " + skippedBG + "개");

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

            // VOL.XX / WEEKXX / 워크북XX 패턴
            // "배재고2VOL.01" → "배재고2VOL.05", "WEEK03" → "WEEK05", "워크북 01" → "워크북 02"
            var prefixes = ["VOL.", "WEEK", "워크북"];
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

        // 아웃라인 후 재중앙정렬 — 글리프 바운드 기준으로 PDF에서 정확한 중앙정렬
        var newSpineLeftXout = abLeft + COVER_W;
        var newSpineRightXout = newSpineLeftXout + newSpine;
        recenterSpineItemsRecursive(newSpineLeftXout, newSpineRightXout, newSpineCenterX);
        log("아웃라인 후 재중앙정렬 완료");
    }

    // PDF 저장 — PDF/X-1a:2001 (Japan) 인쇄용 출력
    // CMYK 강제 + 3mm 도련 (bleedOffsetRect) + OutputIntent (프리셋이 자동 삽입)
    // TrimBox = 원본 artboard, BleedBox = TrimBox + 3mm
    var pdfFile = new File(outPdfPath);

    // 색상 모드 CMYK 강제 변환 (RGB AI 업로드 시 인쇄용 변환)
    if (doc.documentColorSpace !== DocumentColorSpace.CMYK) {
        try {
            doc.documentColorSpace = DocumentColorSpace.CMYK;
            log("색상 모드: RGB → CMYK 변환");
        } catch (e) {
            log("[경고] CMYK 변환 실패: " + e);
        }
    }

    var pdfOpts = new PDFSaveOptions();
    try {
        pdfOpts.pDFPreset = "[PDF/X-1a:2001 (Japan)]";
    } catch (e1) {
        try {
            pdfOpts.pDFPreset = "[PDF/X-1a:2001]";
        } catch (e2) {
            log("[경고] PDF/X-1a 프리셋 없음 — 고품질 인쇄로 폴백");
            try { pdfOpts.pDFPreset = "[고품질 인쇄]"; } catch (e3) {
                try { pdfOpts.pDFPreset = "[High Quality Print]"; } catch (e4) {}
            }
        }
    }
    pdfOpts.preserveEditability = false;
    pdfOpts.generateThumbnails = true;
    pdfOpts.viewAfterSaving = false;
    // 도련 3mm. 원본 AI 아트워크가 3mm(=8.5039pt)까지만 확장되어 있으므로
    // BleedBox를 그보다 크게 잡으면(예: 9pt) 아트워크 외곽에 0.5pt 흰 띠가 노출됨.
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
