/* [ENGINE TEMPLATE] PocketbookBuilder.jsx -- 포켓북 내지 자동 조판 (서식 유지 스토리 복제)

   분석본 .indd에서 영어/한글 스토리를 서식(단락스타일, 문자스타일) 유지한 채
   포켓북 내지 파일의 왼쪽 페이지 프레임으로 복제한다.

   범위 기반 로직:
   1) [완] 파일에서 이미 완성된 passageNo 맵 구축
   2) 분석본 순회: 맵에 있으면 스프레드 통째 복제, 없으면 새로 생성

   settings.json:
   {
       "template_path": "포켓북 내지 템플릿 .indd 경로",
       "output_path": "결과 .indd 저장 경로",
       "output_dir": "작업 디렉터리 (로그 저장)",
       "analysis_files": [ "분석본01.indd", "분석본02.indd", ... ],
       "file_types": [ "textbook", "ebs", ... ],
       "categories": [ "교과서 4과", "올포 11,12강", ... ],
       "memtest": [ { "answer_text": "...", "blank_text": "..." }, ... ],
       "completed_files": [ "[완] 포켓북.indd", ... ]
   }
*/
var settingsPath = "__SETTINGS_PATH__";

(function() {
    var sf = new File(settingsPath);
    if (!sf.exists) return;
    sf.open("r"); sf.encoding = "UTF-8";
    var S = eval("(" + sf.read() + ")");
    sf.close();

    var logLines = [];
    var _logFile = S.output_dir + "/typeset_log.txt";
    function log(msg) { logLines.push(msg); }
    function saveLog() {
        var lf = new File(_logFile);
        lf.open("w"); lf.encoding = "UTF-8";
        lf.write(logLines.join("\n"));
        lf.close();
    }
    // 즉시 로그 파일 생성 — runner.py delivery detection 신호
    (function() {
        var lf = new File(_logFile);
        lf.open("w"); lf.encoding = "UTF-8";
        lf.write("=== 포켓북 JSX 시작 ===");
        lf.close();
    })();

    try { main(); } catch(e) { log("[오류] " + e.message + " line:" + e.line); }
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
    saveLog();

    // ════════════════════════════════════════════════════════════════════
    // passageNo 정규화 + 확장: "230341~42" -> ["230341","230342"], "230341-42" 동일
    // "23034142" -> ["23034142","230341","230342"] (8자리=연번 가능성)
    // ════════════════════════════════════════════════════════════════════
    function expandPassageNo(raw) {
        if (!raw) return [];
        var s = raw.replace(/[\r\n\s]/g, "");
        // ~, - 구분자로 범위 처리
        var rangeMatch = s.match(/^(\d{4,6})[~\-](\d{1,6})$/);
        if (rangeMatch) {
            var prefix = rangeMatch[1];
            var suffix = rangeMatch[2];
            // suffix가 짧으면 prefix 앞부분 이어붙이기: 230341~42 -> 230341, 230342
            if (suffix.length < prefix.length) {
                suffix = prefix.substring(0, prefix.length - suffix.length) + suffix;
            }
            var start = parseInt(prefix, 10);
            var end = parseInt(suffix, 10);
            var result = [];
            if (end >= start && end - start < 20) {
                for (var n = start; n <= end; n++) {
                    result.push(String(n));
                }
            } else {
                result.push(prefix);
                result.push(suffix);
            }
            return result;
        }
        // 순수 숫자 8자리: 앞6+뒤2 가능성 (23034142 -> 230341, 230342 시도)
        if (/^\d{8}$/.test(s)) {
            var a = s.substring(0, 6);
            var b = s.substring(0, 4) + s.substring(6, 8);
            var aNum = parseInt(a, 10);
            var bNum = parseInt(b, 10);
            var result2 = [s];
            if (bNum > aNum && bNum - aNum < 20) {
                for (var n2 = aNum; n2 <= bNum; n2++) {
                    result2.push(String(n2));
                }
            } else {
                result2.push(a);
            }
            return result2;
        }
        return [s];
    }

    // passageNo 매칭: pnoMap에서 raw를 여러 변형으로 찾기
    function findInPnoMap(pnoMap, raw) {
        if (!raw) return null;
        var keys = expandPassageNo(raw);
        for (var i = 0; i < keys.length; i++) {
            if (pnoMap[keys[i]]) return pnoMap[keys[i]];
        }
        return null;
    }

    // ════════════════════════════════════════════════════════════════════
    // 문자스타일 검색 (스타일 그룹 내부까지 탐색)
    // ════════════════════════════════════════════════════════════════════
    function findCharStyle(theDoc, name) {
        try { var s = theDoc.characterStyles.itemByName(name); if (s.isValid) return s; } catch(e) {}
        for (var g = 0; g < theDoc.characterStyleGroups.length; g++) {
            try {
                var gs = theDoc.characterStyleGroups[g].characterStyles.itemByName(name);
                if (gs.isValid) return gs;
            } catch(e) {}
        }
        return null;
    }

    // ════════════════════════════════════════════════════════════════════
    // 단락스타일 적용 + 지정된 크기/행간으로 오버라이드 (문자스타일 보존)
    // ════════════════════════════════════════════════════════════════════
    function applyStyleWithSize(tf, pStyle, size, leading) {
        if (!pStyle) return;
        try {
            // 문자 수준 로컬 fillColor 오버라이드 보존
            var savedColors = [];
            try {
                var chars = tf.characters.everyItem().getElements();
                for (var ci = 0; ci < chars.length; ci++) {
                    var cc = null;
                    try { cc = chars[ci].fillColor; } catch(e) {}
                    if (cc && cc.name !== "Black" && cc.name !== "[Black]") {
                        savedColors.push({ idx: ci, color: cc });
                    }
                }
            } catch(e) {}

            tf.paragraphs.everyItem().appliedParagraphStyle = pStyle;
            var paras = tf.paragraphs.everyItem().getElements();
            for (var pi = 0; pi < paras.length; pi++) {
                var p = paras[pi];
                try { p.pointSize = size; } catch(e) {}
                try { p.leading = leading; } catch(e) {}
                try { p.firstLineIndent = 0; } catch(e) {}
                try { p.leftIndent = 0; } catch(e) {}
                try { p.rightIndent = 0; } catch(e) {}
                try { p.spaceBefore = 0; } catch(e) {}
                try { p.spaceAfter = 0; } catch(e) {}
            }

            // 로컬 fillColor 복원
            if (savedColors.length > 0) {
                var chars2 = tf.characters.everyItem().getElements();
                for (var ri = 0; ri < savedColors.length; ri++) {
                    var sc = savedColors[ri];
                    if (sc.idx < chars2.length) {
                        try { chars2[sc.idx].fillColor = sc.color; } catch(e) {}
                    }
                }
            }
        } catch(e) {}
    }

    // 오버플로우 해소: 행간 축소 -> 글자 축소 -> 프레임 확장
    function resolveOverflow(engTF, korTF, pageBottom) {
        var maxExtend = 10;
        var leadStep = 0.5;
        var sizeStep = 0.25;

        // 영어: 행간 축소 (하한 14pt)
        for (var i = 0; i < 20 && engTF.overflows; i++) {
            try {
                var p0 = engTF.paragraphs[0];
                if (p0.leading <= 14) break;
                var paras = engTF.paragraphs.everyItem().getElements();
                for (var pi = 0; pi < paras.length; pi++) paras[pi].leading -= leadStep;
            } catch(e) { break; }
        }
        // 영어: 글자 축소 (하한 7.5pt)
        for (var i = 0; i < 8 && engTF.overflows; i++) {
            try {
                var p0 = engTF.paragraphs[0];
                if (p0.pointSize <= 7.5) break;
                var paras = engTF.paragraphs.everyItem().getElements();
                for (var pi = 0; pi < paras.length; pi++) paras[pi].pointSize -= sizeStep;
            } catch(e) { break; }
        }

        // 한글: 행간 축소 (하한 6pt)
        for (var i = 0; i < 12 && korTF.overflows; i++) {
            try {
                var p0 = korTF.paragraphs[0];
                if (p0.leading <= 6) break;
                var paras = korTF.paragraphs.everyItem().getElements();
                for (var pi = 0; pi < paras.length; pi++) paras[pi].leading -= leadStep;
            } catch(e) { break; }
        }
        // 한글: 글자 축소 (하한 5pt)
        for (var i = 0; i < 4 && korTF.overflows; i++) {
            try {
                var p0 = korTF.paragraphs[0];
                if (p0.pointSize <= 5) break;
                var paras = korTF.paragraphs.everyItem().getElements();
                for (var pi = 0; pi < paras.length; pi++) paras[pi].pointSize -= sizeStep;
            } catch(e) { break; }
        }

        // 프레임 확장 (한글 아래로)
        if (korTF.overflows) {
            var korGb = korTF.geometricBounds;
            korTF.geometricBounds = [korGb[0], korGb[1], Math.min(korGb[2] + maxExtend, pageBottom + maxExtend), korGb[3]];
        }
        // 영어 프레임 확장 + 한글 밀기
        if (engTF.overflows) {
            var engGb = engTF.geometricBounds;
            var korGb = korTF.geometricBounds;
            engTF.geometricBounds = [engGb[0], engGb[1], engGb[2] + 15, engGb[3]];
            korTF.geometricBounds = [korGb[0] + 15, korGb[1], korGb[2] + maxExtend, korGb[3]];
        }
    }

    // ════════════════════════════════════════════════════════════════════
    // 단락스타일 검색 유틸리티
    // ════════════════════════════════════════════════════════════════════
    function findPStyle(theDoc, name) {
        try { var s = theDoc.paragraphStyles.itemByName(name); if (s.isValid) return s; } catch(e) {}
        return null;
    }

    // ════════════════════════════════════════════════════════════════════
    function main() {
        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
        app.scriptPreferences.enableRedraw = false;
        log("=== 포켓북 조판 시작 ===");

        // -- 1. 포켓북 템플릿 열기 -> 다른이름으로 저장 --
        var tmplFile = new File(S.template_path);
        if (!tmplFile.exists) { log("[오류] 템플릿 없음: " + S.template_path); return; }
        var doc = app.open(tmplFile);
        doc.save(new File(S.output_path));
        log("[내지] " + new File(S.output_path).name);
        saveLog();

        // 템플릿 원본을 참조용으로 재오픈 (스프레드 복제 원본)
        var refDoc = app.open(tmplFile);
        var templateSpreads = {};
        for (var tsi = 0; tsi < refDoc.spreads.length; tsi++) {
            var tsSp = refDoc.spreads[tsi];
            for (var tsj = 0; tsj < tsSp.pages.length; tsj++) {
                if (tsSp.pages[tsj].side == 1818653800) {
                    var tsMn = "none";
                    try { tsMn = tsSp.pages[tsj].appliedMaster.name; } catch(e) {}
                    if (tsMn !== "none" && !templateSpreads[tsMn]) {
                        templateSpreads[tsMn] = tsi;
                    }
                    break;
                }
            }
        }

        // 기존 예시 페이지 모두 제거 (1페이지 표지만 남김)
        while (doc.pages.length > 1) {
            try { doc.pages[-1].remove(); } catch(e) { break; }
        }

        // 표지(1P) 이미지 배치
        var firstPageImg = S.first_page_image || "";
        if (firstPageImg) {
            var fpImgFile = new File(firstPageImg);
            if (fpImgFile.exists) {
                var coverPage = doc.pages[0];
                try { coverPage.appliedMaster = NothingEnum.NOTHING; } catch(e) {}
                // 기존 개체 제거
                try {
                    var cpItems = coverPage.pageItems.everyItem().getElements();
                    for (var ci = cpItems.length - 1; ci >= 0; ci--) {
                        try { cpItems[ci].remove(); } catch(e) {}
                    }
                } catch(e) {}
                var cpBounds = coverPage.bounds;
                var fpRect = coverPage.rectangles.add({
                    geometricBounds: [cpBounds[0] - 3, cpBounds[1] - 3, cpBounds[2] + 3, cpBounds[3] + 3]
                });
                fpRect.place(fpImgFile);
                try { fpRect.fit(FitOptions.PROPORTIONALLY); } catch(e) {}
            }
        }

        // -- 마스터/스타일 참조 캐시 --
        var masters = {};
        for (var m = 0; m < doc.masterSpreads.length; m++) {
            masters[doc.masterSpreads[m].name] = doc.masterSpreads[m];
        }

        // ── sourceType별 마스터 매핑 ──
        // 교과서: A(본문), F(암기테스트)
        // EBS/올림포스: I(본문), L(암기테스트), H(짤지문/양쪽본문)
        // 모의고사: C(삽화), D(암기테스트), G(짤지문/삽화없음)
        // 어휘: J, 듣기: K
        var masterMap = {
            textbook: { content: "A-\uB9C8\uC2A4\uD130", memtest: "F-\uB9C8\uC2A4\uD130", pair: "A-\uB9C8\uC2A4\uD130" },
            ebs:      { content: "I-\uB9C8\uC2A4\uD130", memtest: "L-\uB9C8\uC2A4\uD130", pair: "H-\uB9C8\uC2A4\uD130" },
            mockexam: { content: "C-\uB9C8\uC2A4\uD130", memtest: "D-\uB9C8\uC2A4\uD130", pair: "G-\uB9C8\uC2A4\uD130" }
        };

        // 스프레드가 리뷰테스트(암기테스트)인지 판별: 마스터명 기준
        function isMemtestMaster(mName) {
            return mName.indexOf("B-") === 0 || mName.indexOf("D-") === 0 ||
                   mName.indexOf("F-") === 0 || mName.indexOf("L-") === 0;
        }
        // 스프레드가 짤지문(pair)인지 판별: 마스터명 기준
        function isPairMaster(mName) {
            return mName.indexOf("G-") === 0 || mName.indexOf("H-") === 0;
        }

        // 복제된 스프레드에 올바른 마스터 적용
        function correctCopiedMasters(startIdx, endIdx, sourceType) {
            var map = masterMap[sourceType] || masterMap.textbook;
            var fixCount = 0;
            var removeList = [];
            for (var fsi = startIdx; fsi < endIdx; fsi++) {
                try {
                    var sp = doc.spreads[fsi];
                    var spPages = sp.pages.everyItem().getElements();
                    var isMemtest = false;
                    var isPair = false;
                    for (var fpi = 0; fpi < spPages.length; fpi++) {
                        var curMaster = spPages[fpi].appliedMaster;
                        var curName = curMaster ? curMaster.name : "";
                        if (isMemtestMaster(curName)) isMemtest = true;
                        if (isPairMaster(curName)) isPair = true;
                    }
                    // 리뷰테스트 제외 모드: 삭제 대상
                    if (!includeReviewTest && isMemtest) {
                        removeList.push(sp);
                        continue;
                    }
                    // 올바른 마스터 결정
                    if (isMemtest) {
                        var targetMaster = masters[map.memtest];
                        if (targetMaster) {
                            for (var fpi = 0; fpi < spPages.length; fpi++) {
                                spPages[fpi].appliedMaster = targetMaster;
                                fixCount++;
                            }
                        }
                    } else if (isPair) {
                        // G-마스터 스프레드: 양쪽 본문 있으면 짤지문(양쪽 G), 아니면 삽화없는 모의고사(왼G 오C)
                        var hasRightBody = false;
                        for (var fpi = 0; fpi < spPages.length; fpi++) {
                            if (spPages[fpi].side != 1818653800) {
                                var rtfs = spPages[fpi].textFrames.everyItem().getElements();
                                for (var rti = 0; rti < rtfs.length; rti++) {
                                    var rgb = rtfs[rti].geometricBounds;
                                    if (rgb[2] - rgb[0] > 50 && rgb[0] > 20 && rtfs[rti].characters.length > 30) {
                                        hasRightBody = true; break;
                                    }
                                }
                            }
                        }
                        if (hasRightBody) {
                            // 짤지문: 양쪽 G-마스터
                            var pairMaster = masters[map.pair];
                            if (pairMaster) {
                                for (var fpi = 0; fpi < spPages.length; fpi++) {
                                    spPages[fpi].appliedMaster = pairMaster;
                                    fixCount++;
                                }
                            }
                        } else {
                            // 삽화 없는 모의고사: 왼쪽 G, 오른쪽 C
                            for (var fpi = 0; fpi < spPages.length; fpi++) {
                                if (spPages[fpi].side == 1818653800) {
                                    var gm = masters[map.pair];
                                    if (gm) { spPages[fpi].appliedMaster = gm; fixCount++; }
                                } else {
                                    var cm = masters[map.content];
                                    if (cm) { spPages[fpi].appliedMaster = cm; fixCount++; }
                                }
                            }
                        }
                    } else {
                        var targetMaster = masters[map.content];
                        if (targetMaster) {
                            for (var fpi = 0; fpi < spPages.length; fpi++) {
                                spPages[fpi].appliedMaster = targetMaster;
                                fixCount++;
                            }
                        }
                    }
                } catch(e) {}
            }
            // 리뷰테스트 스프레드 삭제 (역순)
            for (var rmi = removeList.length - 1; rmi >= 0; rmi--) {
                try { removeList[rmi].remove(); } catch(e) {}
            }
            if (removeList.length > 0) log("  [\uB9AC\uBDF0] " + removeList.length + "\uAC1C \uB9AC\uBDF0\uD14C\uC2A4\uD2B8 \uC2A4\uD504\uB808\uB4DC \uC81C\uAC70");
            return fixCount;
        }

        var stBody    = findPStyle(doc, "\uBCF8\uBB38");
        var stKorean  = findPStyle(doc, "\uD55C\uAE00");
        var stMemtest = findPStyle(doc, "\uC554\uAE30\uD14C\uC2A4\uD2B8");
        var stMemCopy = findPStyle(doc, "\uC554\uAE30\uD14C\uC2A4\uD2B8_\uBB38\uC81C \uC0AC\uBCF8");
        var stTopic   = findPStyle(doc, "\uBCF8\uBB38 \uC8FC\uC81C");
        if (!stTopic) {
            try {
                stTopic = doc.paragraphStyles.add({
                    name: "\uBCF8\uBB38 \uC8FC\uC81C",
                    pointSize: 8.5, leading: 10, justification: Justification.LEFT_ALIGN
                });
            } catch(e) {
                stTopic = findPStyle(doc, "\uC8FC\uC81C/\uC694\uC57D\uBB38");
            }
        }

        var basicPara = null;
        var basicNames = ["$ID/NormalParagraphStyle", "[\uAE30\uBCF8 \uB2E8\uB77D]", "[Basic Paragraph]"];
        for (var bn = 0; bn < basicNames.length; bn++) {
            try {
                var bp = doc.paragraphStyles.itemByName(basicNames[bn]);
                if (bp.isValid) { basicPara = bp; break; }
            } catch(e) {}
        }

        var styleMap = {
            textbook:  { engSize: 9, engLead: 24, korSize: 6, korLead: 9 },
            ebs:       { engSize: 9, engLead: 20, korSize: 6, korLead: 9 },
            mockexam:  { engSize: 9, engLead: 20, korSize: 6, korLead: 9 }
        };

        var csLesson = findCharStyle(doc, "\uB808\uC2A8");
        var csPassNo = findCharStyle(doc, "\uC9C0\uBB38 \uBC88\uD638");

        // 서술형아이콘: 템플릿에 label="서술형아이콘" 객체가 있으면 자동 삽입
        var iconSrc = null;
        var csYellow = null; // 텍스트 복제 후 지연 탐색 (분석본 스타일이 복제돼야 존재)
        try {
            var allItems = doc.allPageItems;
            for (var ii = 0; ii < allItems.length; ii++) {
                try { if (allItems[ii].label === "\uC11C\uC220\uD615\uC544\uC774\uCF58") { iconSrc = allItems[ii]; break; } } catch(e) {}
            }
        } catch(e) {}
        if (iconSrc) {
            log("[아이콘] 서술형아이콘 감지 (형광펜 스타일은 복제 후 탐색)");
        }

        // -- copy_sources를 analysis_idx별로 그룹화 --
        var copySources = S.copy_sources || [];
        var copyByAnalysis = {}; // { idx: [src, ...] }
        for (var cs = 0; cs < copySources.length; cs++) {
            var aidx = copySources[cs].analysis_idx !== undefined ? copySources[cs].analysis_idx : 0;
            if (!copyByAnalysis[aidx]) copyByAnalysis[aidx] = [];
            copyByAnalysis[aidx].push(copySources[cs]);
        }

        // 완성본 스프레드 복제 함수
        function copySpreadsFromSource(src) {
            var srcFile = new File(src.file);
            if (!srcFile.exists) { log("  [경고] 없음: " + src.file); return 0; }
            var srcDoc = null;
            var srcName = srcFile.name;
            for (var dd = 0; dd < app.documents.length; dd++) {
                if (app.documents[dd].name === srcName) { srcDoc = app.documents[dd]; break; }
            }
            if (!srcDoc) {
                var prevInteraction = app.scriptPreferences.userInteractionLevel;
                try {
                    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
                    srcDoc = app.open(srcFile);
                } catch(e) {
                    log("  [경고] 열기 실패: " + srcName + " - " + e.message);
                    app.scriptPreferences.userInteractionLevel = prevInteraction;
                    return 0;
                }
                app.scriptPreferences.userInteractionLevel = prevInteraction;
            }
            var spreadCount = srcDoc.spreads.length;
            var startIdx = 0, endIdx = spreadCount;
            if (spreadCount > 1) {
                try {
                    var fpTFs = srcDoc.spreads[0].pages[0].textFrames.everyItem().getElements();
                    if (fpTFs.length <= 1) startIdx = 1;
                } catch(e) { startIdx = 1; }
            }
            while (endIdx > startIdx) {
                var lastSpread = srcDoc.spreads[endIdx - 1];
                var hasContent = false;
                try {
                    var lastPages = lastSpread.pages.everyItem().getElements();
                    for (var lpi = 0; lpi < lastPages.length; lpi++) {
                        if (lastPages[lpi].textFrames.everyItem().getElements().length > 0) { hasContent = true; break; }
                    }
                } catch(e) {}
                if (hasContent) break;
                endIdx--;
            }
            var neededLessons = src.needed_lessons || [];
            var hasFilter = neededLessons.length > 0;
            var neededMap = {};
            for (var nl = 0; nl < neededLessons.length; nl++) neededMap[String(neededLessons[nl])] = true;

            var copiedSpreads = 0, skippedSpreads = 0;
            for (var si = startIdx; si < endIdx; si++) {
                if (hasFilter) {
                    var spreadMatch = false;
                    try {
                        var spPages = srcDoc.spreads[si].pages.everyItem().getElements();
                        for (var spi = 0; spi < spPages.length && !spreadMatch; spi++) {
                            var spTFs = spPages[spi].textFrames.everyItem().getElements();
                            for (var sti = 0; sti < spTFs.length; sti++) {
                                var spGb = spTFs[sti].geometricBounds;
                                if (spGb[0] >= 13 && spGb[0] <= 17 && spGb[2] <= 22 && spGb[1] >= 13 && spGb[1] <= 17) {
                                    var pnoText = spTFs[sti].contents.replace(/[\r\n\s]/g, "");
                                    var lessonMatch = pnoText.match(/(\d+)\uAC15/);
                                    if (lessonMatch && neededMap[lessonMatch[1]]) spreadMatch = true;
                                    break;
                                }
                            }
                        }
                    } catch(e) {}
                    if (!spreadMatch) { skippedSpreads++; continue; }
                }
                // 리뷰테스트 제외 모드: B/D/F-마스터 스프레드 스킵
                if (!includeReviewTest) {
                    var isRT = false;
                    try {
                        var rtPages = srcDoc.spreads[si].pages.everyItem().getElements();
                        for (var rpi = 0; rpi < rtPages.length; rpi++) {
                            var rtm = rtPages[rpi].appliedMaster;
                            var rtName = (rtm && rtm.isValid) ? rtm.name : "";
                            if (rtName.indexOf("B-") === 0 || rtName.indexOf("D-") === 0 || rtName.indexOf("F-") === 0) {
                                isRT = true; break;
                            }
                        }
                    } catch(e) {}
                    if (isRT) { skippedSpreads++; continue; }
                }
                try {
                    srcDoc.spreads[si].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
                    copiedSpreads++;
                } catch(e) { log("  [경고] 스프레드 복제 실패 " + si + ": " + e.message); }
            }
            var filterInfo = hasFilter ? " (필터: " + neededLessons.join(",") + "강, 스킵: " + skippedSpreads + ")" : "";
            log("  [복제] " + src.category + " <- " + srcName + " (" + copiedSpreads + "개 스프레드)" + filterInfo);
            try { srcDoc.close(SaveOptions.NO); } catch(e) {}
            return copiedSpreads;
        }

        // passageNo 수집 함수 (현재 doc에서)
        function collectExistingPassageNos() {
            var pnos = {};
            for (var pi = 0; pi < doc.pages.length; pi++) {
                try {
                    var tfs = doc.pages[pi].textFrames.everyItem().getElements();
                    for (var ti = 0; ti < tfs.length; ti++) {
                        var gb = tfs[ti].geometricBounds;
                        if (gb[0] >= 13 && gb[0] <= 17 && gb[2] <= 22 && gb[1] >= 13 && gb[1] <= 17) {
                            var pno = tfs[ti].contents.replace(/[\r\n\s]/g, "");
                            if (pno) {
                                var epKeys = expandPassageNo(pno);
                                for (var epi = 0; epi < epKeys.length; epi++) pnos[epKeys[epi]] = true;
                            }
                        }
                    }
                } catch(e) {}
            }
            return pnos;
        }

        // passageNo 기반 완성본 스프레드 복사 (마더텅 등 모의고사 편집본)
        var pnoLookupFiles = S.pno_lookup_files || [];
        var pnoLookupDocCache = {}; // ym -> Document (열린 문서 캐시)
        var pnoLookupSpreadCache = {}; // ym -> { pno: spreadIdx, ... }
        var pnoLookupCanonCache = {}; // ym -> { canonKey: spreadIdx } (올림포스 정규화 매칭)

        function buildSpreadPnoMap(srcDoc) {
            var map = {};
            for (var si = 0; si < srcDoc.spreads.length; si++) {
                try {
                    var spPages = srcDoc.spreads[si].pages.everyItem().getElements();
                    var pnoText = "";
                    var fallbackText = "";
                    for (var spi = 0; spi < spPages.length && !pnoText; spi++) {
                        var spTFs = spPages[spi].textFrames.everyItem().getElements();
                        for (var sti = 0; sti < spTFs.length; sti++) {
                            var gb = spTFs[sti].geometricBounds;
                            var t = spTFs[sti].contents.replace(/[\r\n\s]/g, "");
                            if (gb[0] >= 13 && gb[0] <= 17 && gb[2] <= 22 && gb[1] >= 13 && gb[1] <= 17) {
                                if (t) { pnoText = t; break; }
                            }
                            // 폴백: 긴 범위 라벨("230941-42" 등)은 장문이라 지문번호 박스가
                            //       위로 밀려(top<13) 엄격 윈도우를 벗어나 못 잡힘 → 좌측
                            //       번호칼럼(left<=20, 상단 bottom<=22) + YYMMQQ(+선택 범위)
                            //       내용 패턴으로 인식 (scanCompletedLesson과 동일 방식).
                            if (!fallbackText && gb[1] <= 20 && gb[2] <= 22 && /^\d{6}([~\-]\d{1,2})?$/.test(t)) {
                                fallbackText = t;
                            }
                        }
                    }
                    if (!pnoText && fallbackText) pnoText = fallbackText;
                    if (pnoText) {
                        map[pnoText] = si;
                        // 범위 passageNo 확장: "260341~42" -> "260341","260342" 모두 등록
                        var expanded = expandPassageNo(pnoText);
                        for (var exi = 0; exi < expanded.length; exi++) {
                            if (!map[expanded[exi]]) map[expanded[exi]] = si;
                        }
                    }
                } catch(e) {}
            }
            return map;
        }

        // ── 올림포스 정규화 매칭 헬퍼 ──
        // 분석본 라벨 "11강 짧은 어구 빈칸 추론 1번" 과
        // 완성본 라벨 "올포 11강 01" 의 표기가 달라도 같은 지문을 매칭하기 위해
        // "강번호-유형"(예: "11-01", "16-서술") 정규화 키로 환원한다.
        function olymposCanonKey(label) {
            if (!label) return null;
            var s = String(label);
            var gm = s.match(/(\d+)\s*강/); // 올림포스 "11강"
            var matched;
            if (gm) { matched = gm[0]; }
            else { gm = s.match(/Unit\s*(\d+)/i); if (!gm) return null; matched = gm[0]; } // 리딩파워 "Unit 17"
            var gang = parseInt(gm[1], 10);
            var rest = s.substring(s.indexOf(matched) + matched.length);
            var t;
            if (rest.indexOf("분석") >= 0) t = "분석";              // 분석
            else if (rest.indexOf("서술형") >= 0) t = "서술"; // 서술형 -> 서술
            else if (rest.indexOf("논술형") >= 0) t = "논술"; // 논술형 -> 논술
            else if (rest.indexOf("Ex") >= 0) t = "Ex"; // 리딩파워 "Unit N Ex" -> Ex
            else {
                // 첫 번호 사용: "1번"→1, 범위 "1~2번"→1, 완성본 "1~2"/"01"→1.
                // (장문 "장문Ⅰ 1~2번"에서 끝 숫자(2)를 잡아 17-02로 만들면
                //  완성본 "17강 1~2"(17-01)와 어긋나 매칭 실패 → 빈 페이지가 됐음)
                var nm = rest.match(/(\d+)/);
                if (!nm) return null;
                var n = parseInt(nm[1], 10);
                t = (n < 10 ? "0" : "") + n;
            }
            return gang + "-" + t;
        }

        // 완성본 문서의 지문번호 프레임 -> 정규화 키 -> 스프레드 인덱스 맵.
        // 일부 완성본은 지문번호 태그가 비어 있는 스프레드가 있음(데이터 누락).
        // 그 경우 같은 스프레드의 "올포 N강 ..." 헤딩(짧은 라벨)으로 폴백 매칭한다.
        function buildCanonMap(srcDoc) {
            var map = {};
            for (var si = 0; si < srcDoc.spreads.length; si++) {
                try {
                    var primary = null;  // 지문번호 위치 프레임
                    var fallback = null; // "올포 N강 ..." 헤딩 (지문번호 비었을 때만)
                    var spPages = srcDoc.spreads[si].pages.everyItem().getElements();
                    for (var spi = 0; spi < spPages.length; spi++) {
                        var spTFs = spPages[spi].textFrames.everyItem().getElements();
                        for (var sti = 0; sti < spTFs.length; sti++) {
                            var raw = String(spTFs[sti].contents).replace(/[\r\n]/g, " ");
                            if (raw.replace(/\s/g, "") === "") continue;
                            var gb = spTFs[sti].geometricBounds;
                            if (gb[0] >= 13 && gb[0] <= 17 && gb[2] <= 22 && gb[1] >= 13 && gb[1] <= 17) {
                                if (primary === null) primary = raw;
                            } else if (fallback === null) {
                                // 짧은 "올포..." 라벨만 폴백 후보 (본문/긴 텍스트 제외 → 오매칭 방지)
                                var st = raw.replace(/\s/g, "");
                                if (st.length <= 25 && st.indexOf("올포") === 0 && olymposCanonKey(raw)) {
                                    fallback = raw;
                                }
                            }
                        }
                    }
                    var ck = olymposCanonKey(primary);
                    if (!ck && fallback) ck = olymposCanonKey(fallback);
                    if (ck && map[ck] === undefined) map[ck] = si;
                } catch(e) {}
            }
            return map;
        }

        // ym 키("11-16강","11강" 등)가 해당 강 번호를 포함하는지
        function ymRangeHasGang(lym, gNum) {
            if (!lym) return false;
            var rng = String(lym).match(/(\d+)\s*[~\-]\s*(\d+)\s*강/); // "11-16강"
            if (rng) return gNum >= parseInt(rng[1], 10) && gNum <= parseInt(rng[2], 10);
            var one = String(lym).match(/(\d+)\s*강/); // "11강"
            if (one) return parseInt(one[1], 10) === gNum;
            return false;
        }

        // ym으로 완성본 파일을 찾아 연다 (이미 열려 있으면 재사용)
        function openLookupDocByYm(ym) {
            var targetFile = null;
            for (var li = 0; li < pnoLookupFiles.length; li++) {
                if (pnoLookupFiles[li].ym === ym) { targetFile = pnoLookupFiles[li].file; break; }
            }
            if (!targetFile) return null;
            var f = new File(targetFile);
            if (!f.exists) return null;
            for (var dd = 0; dd < app.documents.length; dd++) {
                if (app.documents[dd].name === f.name) return app.documents[dd];
            }
            var prevIA = app.scriptPreferences.userInteractionLevel;
            try {
                app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
                var sd = app.open(f);
                app.scriptPreferences.userInteractionLevel = prevIA;
                return sd;
            } catch(e) {
                app.scriptPreferences.userInteractionLevel = prevIA;
                return null;
            }
        }

        // 완성본 스프레드를 결과 문서로 복제 (+리뷰테스트 동반 복제). 반환: 2/1/false
        function copySpreadAt(srcDoc, spreadIdx, pno) {
            try {
                srcDoc.spreads[spreadIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
                existingPassageNos[pno] = true;
                var nextIdx = spreadIdx + 1;
                var isMemtest = false;
                var srcSpreadCount = srcDoc.spreads.length;
                if (includeReviewTest && nextIdx < srcSpreadCount) {
                    try {
                        var nextPages = srcDoc.spreads[nextIdx].pages.everyItem().getElements();
                        for (var npi = 0; npi < nextPages.length; npi++) {
                            var am = nextPages[npi].appliedMaster;
                            var mName = (am && am.isValid) ? am.name : "";
                            if (mName.length > 0 && (mName.charAt(0) === "B" || mName.charAt(0) === "D") && mName.charAt(1) === "-") {
                                isMemtest = true; break;
                            }
                        }
                    } catch(e) {}
                    if (isMemtest) {
                        try { srcDoc.spreads[nextIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]); }
                        catch(e2) { isMemtest = false; }
                    }
                }
                return isMemtest ? 2 : 1;
            } catch(e) {
                return false;
            }
        }

        // 미래엔 DL(딥러닝 장문): "N과 DL" 지문/리뷰를 미래엔N과 완성본에서 찾는다.
        // 반환: {doc, passageIdx, reviewIdx} 또는 null. (reviewIdx = 마지막 F-마스터)
        function findDLInTextbook(lessonNum) {
            for (var di = 0; di < pnoLookupFiles.length; di++) {
                var dym = pnoLookupFiles[di].ym;
                if (!dym || dym.indexOf("미래") < 0) continue;       // 미래엔/미래앤 완성본만
                var dm = dym.match(/(\d+)과$/);                       // "...N과"
                if (!dm || dm[1] !== String(lessonNum)) continue;
                var dd = openLookupDocByYm(dym);
                if (!dd) continue;
                if (!pnoLookupSpreadCache[dym]) pnoLookupSpreadCache[dym] = buildSpreadPnoMap(dd);
                var pIdx = pnoLookupSpreadCache[dym][lessonNum + "과DL"];
                if (pIdx === undefined) continue;
                var rIdx = -1; // DL 리뷰 = 마지막 F-마스터 스프레드
                for (var si = 0; si < dd.spreads.length; si++) {
                    try {
                        var pgs = dd.spreads[si].pages.everyItem().getElements();
                        for (var pi = 0; pi < pgs.length; pi++) {
                            var am = pgs[pi].appliedMaster;
                            var mn = (am && am.isValid) ? am.name : "";
                            if (mn.charAt(0) === "F" && mn.charAt(1) === "-") { rIdx = si; break; }
                        }
                    } catch(e) {}
                }
                pnoLookupDocCache[dym] = dd;
                return { doc: dd, passageIdx: pIdx, reviewIdx: rIdx };
            }
            return null;
        }

        function copySpreadByPassageNo(pno, fileCategory) {
            if (!pno || pnoLookupFiles.length === 0) return false;

            // ══ 미래엔 DL: "N과 DL" → 미래엔N과 완성본의 "N과 DL" 스프레드 복사 ══
            var _dlm = pno.match(/^(\d+)과\s*DL/i);
            if (_dlm) {
                var _dlInfo = findDLInTextbook(parseInt(_dlm[1], 10));
                if (_dlInfo) return copySpreadAt(_dlInfo.doc, _dlInfo.passageIdx, pno);
                return false;
            }

            // ══ 올림포스(강 기반) 정규화 매칭 ══
            // 분석본 "11강 ... 1번" 과 완성본 "올포 11강 01" 은 표기 규칙이 달라
            // 공백 제거 문자열 비교로는 매칭 불가. 강번호+유형 정규화 키로 매칭한다.
            // 책 구분(독해기본1/2)은 engine.py가 학기에 맞는 파일만 pno_lookup에 넣어 보장.
            // 올림포스·리딩파워(Unit 라벨) EBS에 적용 (모의고사/교과서 경로는 영향 없음).
            // 리딩파워 완성본도 지문번호 배지가 "Unit N Ex/01/02"라 canon("N-Ex"/"N-01")으로 매칭.
            if (fileCategory && (fileCategory.indexOf("올림") >= 0 || fileCategory.indexOf("올포") >= 0 || fileCategory.indexOf("리딩파워") >= 0 || fileCategory.indexOf("리파") >= 0)) {
                var _g = pno.match(/(\d+)\s*강/) || pno.match(/Unit\s*(\d+)/i);
                var _isMock6 = (pno.length >= 6 && /^\d{6}/.test(pno));
                if (_g && !_isMock6) {
                    var _ck = olymposCanonKey(pno);
                    if (!_ck) return false;
                    var _gNum = parseInt(_g[1], 10);
                    // 리딩파워 완성본은 파일명 범위("13~20강")가 실제 내용(+21,22강)을 과소표기할 수 있어
                    // 강-범위 완성본이면 범위 무관하게 canon 매칭 시도(buildCanonMap이 실제 보유분으로 판정).
                    var _isRP = fileCategory && (fileCategory.indexOf("리딩파워") >= 0 || fileCategory.indexOf("리파") >= 0);
                    for (var _oi = 0; _oi < pnoLookupFiles.length; _oi++) {
                        var _lym = pnoLookupFiles[_oi].ym;
                        if (_isRP) { if (!/\d+\s*강/.test(String(_lym))) continue; }
                        else if (!ymRangeHasGang(_lym, _gNum)) continue;
                        if (!pnoLookupDocCache[_lym]) {
                            var _od = openLookupDocByYm(_lym);
                            if (!_od) continue;
                            pnoLookupDocCache[_lym] = _od;
                            pnoLookupCanonCache[_lym] = buildCanonMap(_od);
                        }
                        var _sidx = pnoLookupCanonCache[_lym] ? pnoLookupCanonCache[_lym][_ck] : undefined;
                        if (_sidx !== undefined) {
                            return copySpreadAt(pnoLookupDocCache[_lym], _sidx, pno);
                        }
                    }
                    return false; // 완성본에 없는 강 지문 -> 안전하게 신규 조판
                }
            }

            // ym 키 결정: 모의고사(6자리)는 앞 4자리(YYMM), 교과서/EBS는 fileCategory
            var ym = "";
            if (pno.length >= 6 && /^\d{6}/.test(pno)) {
                ym = pno.substring(0, 4);  // "2503" 등
            } else if (fileCategory) {
                // 교과서: pno에서 과 번호 추출 ("1과 01" -> "1") 후 개별 완성본 키 생성
                // fileCategory가 "YBM박1,2,3과"면 "YBM박" + pno의 과번호 + "과" 로 개별 키 시도
                var lessonMatch = pno.match(/^(\d+)\uACFC/);  // "1과", "2과" 등
                if (lessonMatch) {
                    // 복수과 카테고리에서 접두어 추출: "YBM박1,2,3과" -> "YBM박"
                    // \uD63C\uD569 \uCE74\uD14C\uACE0\uB9AC("26\uB1446\uC6D4,YBM\uBC152\uACFC")\uB294 \uC55E\uCABD \uBAA8\uC758\uACE0\uC0AC \uB0A0\uC9DC \uC138\uADF8\uBA3C\uD2B8\uB97C
                    // \uBA3C\uC800 \uC81C\uAC70\uD574\uC57C \uAD50\uACFC\uC11C \uC811\uB450\uC5B4\uAC00 \uC624\uC5FC\uB418\uC9C0 \uC54A\uB294\uB2E4. (\uB0A0\uC9DC \uC5C6\uC73C\uBA74 \uBB34\uB3D9\uC791)
                    var tbCat = fileCategory.replace(/^\d{2}\uB144\s*\d{1,2}\uC6D4\s*,?\s*/, "");
                    var catPrefix = tbCat.replace(/\d[\d,]*\uACFC.*$/, "");
                    var singleKey = catPrefix + lessonMatch[1] + "\uACFC";
                    // 개별 키로 먼저 시도
                    var found = false;
                    for (var li = 0; li < pnoLookupFiles.length; li++) {
                        if (pnoLookupFiles[li].ym === singleKey) { found = true; break; }
                    }
                    if (found) {
                        ym = singleKey;
                    } else {
                        ym = fileCategory;
                    }
                } else {
                    ym = fileCategory;  // "능률민1과" 등
                }
            }
            if (!ym) return false;

            // 캐시에서 문서 찾기
            if (!pnoLookupDocCache[ym]) {
                // ym에 해당하는 파일 찾기
                var targetFile = null;
                for (var li = 0; li < pnoLookupFiles.length; li++) {
                    if (pnoLookupFiles[li].ym === ym) {
                        targetFile = pnoLookupFiles[li].file;
                        break;
                    }
                }
                if (!targetFile) return false;

                var f = new File(targetFile);
                // NFD/NFC 파일명 불일치 대응: File이 없으면 폴더에서 직접 탐색
                if (!f.exists) {
                    var parentFolder = new Folder(f.path);
                    if (parentFolder.exists) {
                        var ymYY = ym.substring(0, 2);  // "24"
                        var ymMM = String(parseInt(ym.substring(2), 10));  // "09" -> "9"
                        var candidates = parentFolder.getFiles("*.indd");
                        for (var ci = 0; ci < candidates.length; ci++) {
                            var cn = decodeURI(candidates[ci].name);
                            if (cn.indexOf(ymYY) >= 0 && cn.indexOf(ymMM + "\uC6D4") >= 0) {  // "24" + "9월"
                                f = candidates[ci];
                                break;
                            }
                        }
                    }
                }
                if (!f.exists) return false;

                var srcDoc = null;
                var srcName = f.name;
                for (var dd = 0; dd < app.documents.length; dd++) {
                    if (app.documents[dd].name === srcName) { srcDoc = app.documents[dd]; break; }
                }
                if (!srcDoc) {
                    var prevIA = app.scriptPreferences.userInteractionLevel;
                    try {
                        app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
                        srcDoc = app.open(f);
                    } catch(e) {
                        app.scriptPreferences.userInteractionLevel = prevIA;
                        return false;
                    }
                    app.scriptPreferences.userInteractionLevel = prevIA;
                }
                pnoLookupDocCache[ym] = srcDoc;
                pnoLookupSpreadCache[ym] = buildSpreadPnoMap(srcDoc);
            }

            var spreadMap = pnoLookupSpreadCache[ym];
            var srcDoc = pnoLookupDocCache[ym];
            // 공백 제거하여 매칭 (분석본 "1과 01" vs 완성본 "1과01")
            var pnoNorm = pno.replace(/\s/g, "");
            var spreadIdx = spreadMap[pnoNorm];
            if (spreadIdx === undefined) spreadIdx = spreadMap[pno]; // 원본으로도 시도
            if (spreadIdx === undefined) return false;

            try {
                srcDoc.spreads[spreadIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
                existingPassageNos[pno] = true;

                // 다음 스프레드가 리뷰테스트(B/D-마스터)이면 함께 복사 (리뷰테스트 포함 시만)
                var nextIdx = spreadIdx + 1;
                var isMemtest = false;
                var srcSpreadCount = srcDoc.spreads.length;
                if (includeReviewTest && nextIdx < srcSpreadCount) {
                    try {
                        var nextSpread = srcDoc.spreads[nextIdx];
                        var nextPages = nextSpread.pages.everyItem().getElements();
                        for (var npi = 0; npi < nextPages.length; npi++) {
                            var am = nextPages[npi].appliedMaster;
                            var mName = (am && am.isValid) ? am.name : "";
                            if (mName.length > 0 && (mName.charAt(0) === "B" || mName.charAt(0) === "D") && mName.charAt(1) === "-") {
                                isMemtest = true; break;
                            }
                        }
                    } catch(e) {
                        log("    [debug] memtest check err: " + e.message);
                    }
                    if (isMemtest) {
                        try {
                            srcDoc.spreads[nextIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
                        } catch(e2) {
                            isMemtest = false;
                        }
                    }
                }
                return isMemtest ? 2 : 1; // 2 = 지문+리뷰테스트, 1 = 지문만
            } catch(e) {
                return false;
            }
        }

        // ─────────────────────────────────────────────────────────
        // 교과서 과(lesson) 단위 처리
        // 분석본에 있는 지문만 기준으로, 각 지문의 본문 + 위치대응 리뷰테스트를
        // 완성본에서 선별 복사한다(완성본 통째 복제가 아님).
        // 완성본 구조: [표지] 본문들(content 마스터, 지문번호 있음)
        //              리뷰들(memtest 마스터 B/D/F/L, 지문번호 없음) [끝]
        // 본문 N개 ↔ 리뷰 N개가 스프레드 순서로 1:1 대응하므로,
        // 리뷰 마스터 종류(F/D 등)와 무관하게 같은 순번끼리 짝짓는다.
        // ─────────────────────────────────────────────────────────

        // catPrefix+token 으로 완성본 ym 키 찾기 ("능률민"+"3과"→"능률민3과")
        function findLessonYm(catPrefix, token) {
            if (!token) return null;
            var want = catPrefix + token;
            for (var i = 0; i < pnoLookupFiles.length; i++) {
                if (pnoLookupFiles[i].ym === want) return want;
            }
            // 폴백: catPrefix로 시작하고 token으로 끝나는 ym
            for (var fi = 0; fi < pnoLookupFiles.length; fi++) {
                var y = pnoLookupFiles[fi].ym;
                if (catPrefix && y.indexOf(catPrefix) === 0 &&
                    y.length >= token.length &&
                    y.substring(y.length - token.length) === token) return y;
            }
            return null;
        }

        // 완성본 한 스프레드의 지문번호 텍스트 (buildSpreadPnoMap과 동일한 위치 규칙)
        function getSpreadPnoText(srcDoc, si) {
            // 1순위: 위치 윈도우(top/left 13~17)의 지문번호 프레임.
            // 폴백: 긴 범위 라벨("230941-42" 등)은 프레임이 위로 밀려 윈도우를 벗어나
            //       못 잡히던 버그가 있었음 → YYMMQQ(+선택적 범위) 패턴 + 좌측 번호
            //       칼럼(left<=20)인 프레임을 내용기반으로 폴백 인식한다.
            var fallback = "";
            try {
                var spPages = srcDoc.spreads[si].pages.everyItem().getElements();
                for (var spi = 0; spi < spPages.length; spi++) {
                    var tfs = spPages[spi].textFrames.everyItem().getElements();
                    for (var ti = 0; ti < tfs.length; ti++) {
                        var gb = tfs[ti].geometricBounds;
                        var t = String(tfs[ti].contents).replace(/[\r\n\s]/g, "");
                        if (gb[0] >= 13 && gb[0] <= 17 && gb[2] <= 22 && gb[1] >= 13 && gb[1] <= 17) {
                            if (t) return t;
                        }
                        if (!fallback && gb[1] <= 20 && /^\d{6}([~\-]\d{1,2})?$/.test(t)) {
                            fallback = t;
                        }
                    }
                }
            } catch(e) {}
            return fallback;
        }

        // 완성본을 본문/리뷰 스프레드 배열로 분류 (스프레드 순서 보존)
        function scanCompletedLesson(srcDoc) {
            var bodies = [];   // [{idx, pno}]
            var reviews = [];  // [스프레드 idx]
            for (var s = 0; s < srcDoc.spreads.length; s++) {
                try {
                    var pgs = srcDoc.spreads[s].pages.everyItem().getElements();
                    var hasMaster = false, isRev = false;
                    for (var pi = 0; pi < pgs.length; pi++) {
                        var am = pgs[pi].appliedMaster;
                        var nm = (am && am.isValid) ? am.name : "";
                        if (nm) { hasMaster = true; if (isMemtestMaster(nm)) isRev = true; }
                    }
                    if (!hasMaster) continue;   // 표지/끝 등 마스터 없는 스프레드 제외
                    if (isRev) reviews.push(s);
                    else bodies.push({ idx: s, pno: getSpreadPnoText(srcDoc, s) });
                } catch(e) {}
            }
            return { bodies: bodies, reviews: reviews };
        }

        // 지문 하나 신규 조판 (짤지문/일반 분기)
        function buildOneNew(passage, fileCategory) {
            var npno = (passage.passageNo || "").replace(/\s/g, "");
            var catR;
            if (passage.isPair) {
                catR = createPairSpread(doc, refDoc, templateSpreads, passage, "textbook", fileCategory, masters, styleMap, stBody, stMemtest, basicPara, iconSrc, csYellow);
                if (passage.rightPassage && passage.rightPassage.passageNo) {
                    existingPassageNos[passage.rightPassage.passageNo] = true;
                }
            } else {
                catR = createNewSpread(doc, refDoc, templateSpreads, passage, "textbook", fileCategory, (masterMap.textbook).content, masters, styleMap, stBody, stKorean, stMemtest, stTopic, basicPara, csLesson, csPassNo, illustBase, grade, iconSrc, csYellow);
            }
            if (catR && catR.illustPlaced) illustCount++;
            if (npno) existingPassageNos[npno] = true;
            newCount++;
        }

        // ── 본문↔리뷰 지문 일치 검사 (완성본 파일의 리뷰가 엉뚱한 과인 경우 감지) ──
        // 스프레드에서 가장 긴 영문 텍스트의 시그니처(소문자 영문자만) 추출.
        function _spreadEngSig(sdoc, spIdx) {
            var sig = "";
            try {
                var pgs = sdoc.spreads[spIdx].pages.everyItem().getElements();
                for (var i=0;i<pgs.length;i++){
                    var tfs = pgs[i].textFrames.everyItem().getElements();
                    for (var j=0;j<tfs.length;j++){
                        var t = String(tfs[j].contents).toLowerCase().replace(/[^a-z]/g,"");
                        if (t.length > sig.length) sig = t;
                    }
                }
            } catch(e){}
            return sig.length > 300 ? sig.substring(0,300) : sig;
        }
        function _textEngSig(str) { return String(str||"").toLowerCase().replace(/[^a-z]/g,""); }
        // 본문 시그니처의 중간 청크가 리뷰 시그니처에 포함되면 같은 지문으로 판단.
        function _samePassage(aSig, bSig) {
            if (!aSig || !bSig || aSig.length < 40 || bSig.length < 40) return true; // 정보부족→보수적 일치
            for (var f=0.3; f<=0.61; f+=0.3) {
                var st = Math.floor(aSig.length*f);
                if (st+25 > aSig.length) st = aSig.length-25;
                if (st < 0) st = 0;
                if (bSig.indexOf(aSig.substring(st, st+25)) >= 0) return true;
            }
            return false;
        }

        // 완성본이 있는 과: 분석본 지문 본문 복사 + 같은 순번 리뷰 복사
        function copyLessonFromCompleted(grp, ym, fileCategory) {
            var srcDoc = openLookupDocByYm(ym);
            if (!srcDoc) { buildLessonNew(grp, fileCategory); return; }
            var scan = scanCompletedLesson(srcDoc);
            var bodies = scan.bodies;
            var nItems = grp.items.length, mBodies = bodies.length;

            // ── 분석본 항목 ↔ 완성본 본문 정렬 (지문번호 표기 차이에 robust) ──
            // 1단계: 지문번호 정규화(공백 제거) exact 매칭.
            // 2단계: 표기가 달라 1단계에서 못 잡힌 항목을, 좌우 매칭이 정한 본문 구간의
            //        미사용 본문에 "순서 보존"으로 배정한다(구간의 미사용 본문 수가 미매칭
            //        항목 수와 정확히 같을 때만; 모호하면 신규조판 유지).
            //        분석본은 완성본 레슨의 부분집합(동일 순서)이라는 워크플로 전제에서 안전.
            //        2단계 배정은 모두 [위치복구] 로그로 남겨 가시화한다(완성본 태그가
            //        비어있거나 표기가 달라도 위치로 복구 — 침묵 신규조판 방지).
            function _canonPno(s) { return (s || "").replace(/\s/g, ""); }
            // 범위 지문번호(41~42 / 41-42 / 41 / 42 는 모두 같은 지문)를 동일하게
            // 매칭하기 위해 expandPassageNo로 모든 변형 키를 등록/조회한다.
            // (예: 완성본 "230941-42" → 키 230941, 230942 등록 → 신규 "230941~42"/
            //  "230941"/"230942" 어느 표기로 와도 같은 본문에 매칭)
            var pnoToBody = {};
            for (var jb = 0; jb < mBodies; jb++) {
                var keysJ = expandPassageNo(bodies[jb].pno);
                for (var kj = 0; kj < keysJ.length; kj++) {
                    if (keysJ[kj] && pnoToBody[keysJ[kj]] === undefined) pnoToBody[keysJ[kj]] = jb;
                }
            }
            var assign = [], usedBody = [];
            for (var ub = 0; ub < mBodies; ub++) usedBody[ub] = false;
            for (var ia = 0; ia < nItems; ia++) {
                var keysI = expandPassageNo(grp.items[ia].passageNo);
                var mb = -1;
                for (var ki = 0; ki < keysI.length; ki++) {
                    if (pnoToBody[keysI[ki]] !== undefined) { mb = pnoToBody[keysI[ki]]; break; }
                }
                if (mb >= 0 && usedBody[mb]) mb = -1;   // 같은 본문 중복배정 방지
                assign[ia] = mb;
                if (mb >= 0) usedBody[mb] = true;
            }
            // 2단계: 연속 미매칭 런 단위로 순서보존 갭필
            var rs = 0;
            while (rs < nItems) {
                if (assign[rs] >= 0) { rs++; continue; }
                var re2 = rs; while (re2 < nItems && assign[re2] < 0) re2++;
                var loB = (rs > 0) ? assign[rs - 1] : -1;
                var hiB = (re2 < nItems) ? assign[re2] : mBodies;
                var gap = [];
                for (var gpb = loB + 1; gpb < hiB; gpb++) if (!usedBody[gpb]) gap.push(gpb);
                if (gap.length === (re2 - rs)) {
                    for (var rr = 0; rr < gap.length; rr++) { assign[rs + rr] = gap[rr]; usedBody[gap[rr]] = true; }
                }
                rs = re2;
            }

            // 1) 본문(분석본 순서대로) 복사/조판 + 각 지문의 리뷰소스(revPlan) 기록
            var bodyStart = doc.spreads.length;
            var revPlan = [];   // 본문 순서대로의 리뷰 스프레드 idx (-1 = 빈 페이지)
            var copyCnt = 0, newCnt = 0, fillCnt = 0;
            for (var p2 = 0; p2 < nItems; p2++) {
                var pno2 = _canonPno(grp.items[p2].passageNo);
                var bj = assign[p2];
                if (bj >= 0) {
                    try {
                        srcDoc.spreads[bodies[bj].idx].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
                        if (pno2) existingPassageNos[pno2] = true;
                        pnoCopyCount++; copyCnt++;
                        // 수록 지문 목록 집계용 — 완성본 레슨 복사도 지문마다 기록 (신규/복사와 동일 마커)
                        log("  [pno복사] " + (grp.items[p2].passageNo || ""));
                        if (_canonPno(bodies[bj].pno) !== pno2) {   // 표기 달랐는데 위치로 복구
                            fillCnt++;
                            log("    [위치복구] " + grp.token + " 분석본'" + (grp.items[p2].passageNo || "?") + "' = 완성본'" + (bodies[bj].pno || "(번호없음)") + "'");
                        }
                        revPlan.push(bj < scan.reviews.length ? scan.reviews[bj] : -1);
                    } catch(e) { revPlan.push(-1); }
                } else {
                    buildOneNew(grp.items[p2], fileCategory);
                    newCnt++;
                    revPlan.push(-1);
                }
            }
            // 매칭 못한 항목이 남았는데 완성본에 미사용 본문이 있으면 경고(침묵 실패 가시화)
            var unusedBodies = 0;
            for (var ux = 0; ux < mBodies; ux++) if (!usedBody[ux]) unusedBodies++;
            if (newCnt > 0 && unusedBodies > 0) {
                log("  [경고:매칭미해결] " + grp.token + ": 신규조판 " + newCnt + "개, 완성본 미사용 본문 " + unusedBodies + "개 — 지문번호 표기 확인 필요");
            }
            if (doc.spreads.length > bodyStart) correctCopiedMasters(bodyStart, doc.spreads.length, "textbook");

            // 2) 리뷰테스트: 본문과 같은 순번으로 복사 (포함 모드일 때만)
            if (includeReviewTest) {
                var revStart = doc.spreads.length;
                var revCopied = 0, revEmpty = 0, revFixed = 0;
                var _rtMapTB = S.review_test_map || {};
                var _rtDataTB = _rtMapTB[fileCategory] || _rtMapTB[grp.token] || null;
                var _rtPassTB = (_rtDataTB && _rtDataTB.passages) ? _rtDataTB.passages : [];
                var _docxSig = [];
                for (var _di=0; _di<_rtPassTB.length; _di++) _docxSig.push(_textEngSig(_rtPassTB[_di].answer_text));
                for (var r = 0; r < revPlan.length; r++) {
                    if (revPlan[r] >= 0) {
                        // 본문↔완성본리뷰 일치 검사 (불일치 = 완성본 파일 오류 → docx 리뷰로 대체)
                        var _bjr = assign[r];
                        var _bodySig = (_bjr >= 0) ? _spreadEngSig(srcDoc, bodies[_bjr].idx) : "";
                        var _revSig = _spreadEngSig(srcDoc, revPlan[r]);
                        if (_bodySig && _revSig && !_samePassage(_bodySig, _revSig)) {
                            var _pick = -1;
                            for (var _ds=0; _ds<_docxSig.length; _ds++){
                                if (_docxSig[_ds].length>=40 && _samePassage(_bodySig, _docxSig[_ds])) { _pick=_ds; break; }
                            }
                            if (_pick < 0 && r < _rtPassTB.length) _pick = r;
                            if (_pick >= 0 && _rtPassTB[_pick] && _rtPassTB[_pick].blank_text) {
                                createMemtestSpread(doc, refDoc, templateSpreads, _rtPassTB[_pick], masters, stMemtest, stMemCopy, "F");
                                revFixed++;
                                log("    [리뷰교정] " + grp.token + " " + (r+1) + "번: 완성본 리뷰가 본문과 불일치 → docx로 대체");
                            } else {
                                createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, "F"); revEmpty++;
                                log("    [리뷰교정] " + grp.token + " " + (r+1) + "번: 완성본 리뷰 불일치, docx 없음 → 빈 페이지");
                            }
                            continue;
                        }
                        try { srcDoc.spreads[revPlan[r]].duplicate(LocationOptions.AFTER, doc.spreads[-1]); revCopied++; }
                        catch(e) { createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, "F"); revEmpty++; }
                    } else {
                        createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, "F"); revEmpty++;
                    }
                }
                if (doc.spreads.length > revStart) correctCopiedMasters(revStart, doc.spreads.length, "textbook");
                log("  [리뷰] " + grp.token + ": 본문 " + copyCnt + (fillCnt > 0 ? ("(위치복구" + fillCnt + ")") : "") + (newCnt > 0 ? ("+신규" + newCnt) : "") + ", 리뷰 " + revCopied + (revFixed > 0 ? ("+교정" + revFixed) : "") + (revEmpty > 0 ? ("+빈" + revEmpty) : "") + " (F-마스터)");
            } else {
                log("  [본문] " + grp.token + ": " + copyCnt + (fillCnt > 0 ? ("(위치복구" + fillCnt + ")") : "") + (newCnt > 0 ? ("+신규" + newCnt) : "") + "개");
            }
        }

        // 완성본이 없는 과: 전부 신규 조판 + docx/빈 리뷰
        function buildLessonNew(grp, fileCategory) {
            var rtMap = S.review_test_map || {};
            var rtData = rtMap[fileCategory] || rtMap[grp.token] || null;
            var rtPassages = (rtData && rtData.passages) ? rtData.passages : [];
            for (var bi = 0; bi < grp.items.length; bi++) {
                buildOneNew(grp.items[bi], fileCategory);
            }
            if (includeReviewTest) {
                for (var k = 0; k < grp.items.length; k++) {
                    if (k < rtPassages.length && rtPassages[k].blank_text) {
                        createMemtestSpread(doc, refDoc, templateSpreads, rtPassages[k], masters, stMemtest, stMemCopy, "F");
                    } else {
                        createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, "F");
                    }
                }
            }
            log("  [신규] " + grp.token + ": 본문 " + grp.items.length + "개 조판 (완성본 없음)");
        }

        // 지문번호에서 레슨(과/강) 식별자만 분리.
        // [근본 원인] 기존 "뒤 1~2자리 숫자 제거"(rawNo.replace(/\d{1,2}$/))는 접미사가
        // 숫자인 지문("3과01"→"3과")만 처리한다. "3과 추가"는 뒤가 숫자가 아니라
        // "3과추가"로 남아 레슨에서 떨어져 나가 별도 그룹이 되고, 완성본 키("YBM김3과")와
        // 못 만나 통째로 신규조판되던 버그가 있었다(본문 01~05는 매칭, "추가"만 누락).
        // → "N과/N강" 마커를 앵커로 잡아 접미사가 숫자든 아니든("01"/"추가"/"추가본문")
        //    같은 레슨으로 묶는다. 마커가 없는 SL/L 형식은 기존처럼 뒤 1~2자리 숫자만 제거.
        //    (과=과, 강=강 — 코드베이스 NFC 규약. line 773 동일 가정)
        function lessonToken(rawNo) {
            if (!rawNo) return "__misc__";
            var m = rawNo.match(/^(.*?\d+\s*(?:과|강))/);  // 과=과 강=강 (NFC, line 773과 동일 규약)
            if (m) return m[1].replace(/\s/g, "");
            var t = rawNo.replace(/\d{1,2}$/, "");
            return t || "__misc__";
        }

        // 교과서 분석본을 과(lesson) 단위로 처리하는 진입점
        function processTextbookLessons(passages, fileCategory) {
            var catPrefix = fileCategory.replace(/\d.*$/, "");
            // 과(token)별 그룹화: "3과01"→"3과", "3과추가"→"3과", "SL201"→"SL2"
            var groups = [];
            var groupMap = {};
            for (var i = 0; i < passages.length; i++) {
                var rawNo = (passages[i].passageNo || "").replace(/\s/g, "");
                var token = lessonToken(rawNo);
                if (!groupMap[token]) { groupMap[token] = { token: token, items: [] }; groups.push(groupMap[token]); }
                groupMap[token].items.push(passages[i]);
            }
            for (var g = 0; g < groups.length; g++) {
                var grp = groups[g];
                var lym = (grp.token === "__misc__") ? null : findLessonYm(catPrefix, grp.token);
                if (lym) copyLessonFromCompleted(grp, lym, fileCategory);
                else buildLessonNew(grp, fileCategory);
            }
        }

        function closePnoLookupDocs() {
            for (var ym in pnoLookupDocCache) {
                try { pnoLookupDocCache[ym].close(SaveOptions.NO); } catch(e) {}
            }
            pnoLookupDocCache = {};
        }

        // 혼합(mixed) 카테고리 문자열을 교과서/모의고사 부분으로 분리.
        // "동아박4과,21년11월" → {textbook:"동아박4과", mockexam:"21년11월"}
        // 날짜(YY년 M월) 또는 "마더텅"이 든 토큰은 모의고사, 나머지는 교과서.
        function splitMixedCategory(cat) {
            var parts = (cat || "").split(",");
            var tb = [], mk = [];
            for (var i = 0; i < parts.length; i++) {
                var p = parts[i].replace(/^\s+|\s+$/g, "");
                if (!p) continue;
                var hasYear = (p.indexOf("\uB144") >= 0);             // year
                var hasMonth = (p.indexOf("\uC6D4") >= 0);            // month
                var isMother = (p.indexOf("\uB9C8\uB354\uD140") >= 0); // matertongue
                if ((hasYear && hasMonth) || isMother) mk.push(p); else tb.push(p);
            }
            return { textbook: tb.join(","), mockexam: mk.join(",") };
        }

        var existingPassageNos = {};
        var copyCount = 0;
        var pnoCopyCount = 0;
        var includeReviewTest = (S.include_review_test !== false); // 기본값: 포함

        // -- 분석본 순서대로 처리 (복제 + 신규 인터리브) --
        var analysisFiles = S.analysis_files || [];
        var fileTypes = S.file_types || [];
        var categories = S.categories || [];
        var illustBase = S.illustrations_base || "";
        var grade = S.grade || "";
        var newCount = 0;
        var skipCount = 0;
        var illustCount = 0;

        if (analysisFiles.length > 0) {
            log("[처리] " + analysisFiles.length + "개 분석본 + " + copySources.length + "개 완성본");

            for (var af = 0; af < analysisFiles.length; af++) {
                var analPath = analysisFiles[af];
                var analFile = new File(analPath);
                if (!analFile.exists) { log("[경고] 없음: " + analPath); continue; }

                var analDoc = null;
                var analName = analFile.name;
                for (var dd = 0; dd < app.documents.length; dd++) {
                    if (app.documents[dd].name === analName) { analDoc = app.documents[dd]; break; }
                }
                if (!analDoc) {
                    try { analDoc = app.open(analFile); } catch(e) {
                        log("[경고] 열기 실패: " + analName); continue;
                    }
                }

                var sourceType = fileTypes[af] || "textbook";
                var fileCategory = categories[af] || "";

                // 이 분석본에 매칭된 완성본 먼저 복제
                var afCopySources = copyByAnalysis[af] || [];
                var spreadsBefore = doc.spreads.length;
                for (var acs = 0; acs < afCopySources.length; acs++) {
                    copyCount += copySpreadsFromSource(afCopySources[acs]);
                }
                if (afCopySources.length > 0) {
                    // 모든 sourceType: 복제된 스프레드에 올바른 마스터 적용
                    var fixedCount = correctCopiedMasters(spreadsBefore, doc.spreads.length, sourceType);
                    if (fixedCount > 0) log("  [\uB9C8\uC2A4\uD130] " + fixedCount + "\uAC1C \uD398\uC774\uC9C0 \uB9C8\uC2A4\uD130 \uBCF4\uC815");
                    // 복제된 passageNo 수집 갱신
                    existingPassageNos = collectExistingPassageNos();
                    saveLog();
                }

                log("[분석본] " + analName + " (" + sourceType + ")");
                saveLog();

                var baseMasterName = (masterMap[sourceType] || masterMap.textbook).content;

                var passages = extractPassages(analDoc, sourceType, fileCategory);
                log("  " + passages.length + "개 지문");
                saveLog();

                // [혼합] 한 분석본에 교과서+모의고사 지문이 공존 (예: "동아박4과,21년 11월").
                // extractPassages가 지문별 sourceType을 부여 → 부분집합으로 나눠 각 경로로 처리.
                // 교과서 지문은 processTextbookLessons로, 모의고사 지문은 아래 기존 루프로.
                if (sourceType === "mixed") {
                    var splitCat = splitMixedCategory(fileCategory);
                    var tbP = [], mkP = [];
                    for (var mxi = 0; mxi < passages.length; mxi++) {
                        if (passages[mxi].sourceType === "mockexam") mkP.push(passages[mxi]);
                        else tbP.push(passages[mxi]);
                    }
                    log("  [\uD63C\uD569] \uAD50\uACFC\uC11C " + tbP.length + "\uAC1C(" + splitCat.textbook + ") + \uBAA8\uC758\uACE0\uC0AC " + mkP.length + "\uAC1C(" + splitCat.mockexam + ")");
                    saveLog();
                    if (tbP.length > 0) processTextbookLessons(tbP, splitCat.textbook);
                    // 모의고사 부분은 아래 기존 모의고사 루프가 처리하도록 변수 재설정
                    passages = mkP;
                    sourceType = "mockexam";
                    fileCategory = splitCat.mockexam;
                    baseMasterName = (masterMap.mockexam).content;
                }

                // [교과서] 과 단위로 완성본에서 본문+대응 리뷰만 선별 복사 (분석본 지문 기준)
                // 모의고사/EBS/올림포스는 아래 기존 경로를 그대로 사용
                if (sourceType === "textbook" && pnoLookupFiles.length > 0) {
                    processTextbookLessons(passages, fileCategory);
                    try { analDoc.close(SaveOptions.NO); } catch(e) {}
                    continue;
                }

                for (var p = 0; p < passages.length; p++) {
                    var pno = passages[p].passageNo || "";

                    // 1) 이미 복제된 passageNo면 스킵 (확장 매칭)
                    var pnoExpanded = expandPassageNo(pno);
                    var alreadyExists = false;
                    for (var ei = 0; ei < pnoExpanded.length; ei++) {
                        if (existingPassageNos[pnoExpanded[ei]]) { alreadyExists = true; break; }
                    }
                    if (pno && alreadyExists) {
                        skipCount++;
                        continue;
                    }

                    // 1.5) passageNo 기반 완성본 복사 시도 (마더텅 등)
                    // 반환값: false=실패, 1=지문만, 2=지문+리뷰테스트
                    var pnoCopyResult = 0;
                    if (pno && pnoLookupFiles.length > 0) {
                        pnoCopyResult = copySpreadByPassageNo(pno, fileCategory);
                    }
                    if (pnoCopyResult) {
                        var pnoLabel = pnoCopyResult === 2 ? " (+\uB9AC\uBDF0)" : "";
                        log("  [pno\uBCF5\uC0AC] " + pno + pnoLabel);
                        pnoCopyCount++;
                        if (pnoCopyCount % 5 === 0) saveLog();
                        passages[p]._pnoCopied = pnoCopyResult;
                        // pno 복사된 스프레드에 올바른 마스터 적용
                        var pnoSpreadEnd = doc.spreads.length;
                        var pnoSpreadStart = pnoSpreadEnd - (pnoCopyResult === 2 ? 2 : 1);
                        correctCopiedMasters(pnoSpreadStart, pnoSpreadEnd, sourceType);
                        // pno 복사된 스프레드의 noTF 프레임 크기/자동크기조정 보정
                        for (var psi = pnoSpreadStart; psi < pnoSpreadEnd; psi++) {
                            try {
                                var psPages = doc.spreads[psi].pages.everyItem().getElements();
                                for (var ppi = 0; ppi < psPages.length; ppi++) {
                                    if (psPages[ppi].side != 1818653800) continue; // 왼쪽만
                                    var psTFs = psPages[ppi].textFrames.everyItem().getElements();
                                    for (var pti = 0; pti < psTFs.length; pti++) {
                                        var pgb = psTFs[pti].geometricBounds;
                                        var pfh = pgb[2] - pgb[0];
                                        var pfw = pgb[3] - pgb[1];
                                        if (pfh < 10 && pfw < 40 && pgb[0] >= 13 && pgb[0] <= 17) {
                                            psTFs[pti].textFramePreferences.autoSizingType = AutoSizingTypeEnum.OFF;
                                            psTFs[pti].textFramePreferences.autoSizingType = AutoSizingTypeEnum.WIDTH_ONLY;
                                            psTFs[pti].textFramePreferences.autoSizingReferencePoint = AutoSizingReferenceEnum.LEFT_CENTER_POINT;
                                            psTFs[pti].textFramePreferences.useMinimumWidthForAutoSizing = true;
                                            psTFs[pti].textFramePreferences.minimumWidthForAutoSizing = 18;
                                            psTFs[pti].geometricBounds = [15, 15, 20.5, 33];
                                        }
                                    }
                                }
                            } catch(e) {}
                        }
                    }

                    // 2) 새로 조판 (pno복사된 지문은 스킵)
                    if (!passages[p]._pnoCopied) {
                        var catResult;
                        if (passages[p].isPair) {
                            catResult = createPairSpread(doc, refDoc, templateSpreads, passages[p], sourceType, fileCategory, masters, styleMap, stBody, stMemtest, basicPara, iconSrc, csYellow);
                            // 오른쪽 passageNo도 등록
                            if (passages[p].rightPassage && passages[p].rightPassage.passageNo) {
                                existingPassageNos[passages[p].rightPassage.passageNo] = true;
                            }
                        } else {
                            catResult = createNewSpread(doc, refDoc, templateSpreads, passages[p], sourceType, fileCategory, baseMasterName, masters, styleMap, stBody, stKorean, stMemtest, stTopic, basicPara, csLesson, csPassNo, illustBase, grade, iconSrc, csYellow);
                        }
                        if (catResult && catResult.illustPlaced) illustCount++;
                        existingPassageNos[pno] = true;
                        newCount++;
                        if (newCount % 3 === 0) saveLog(); // 3개마다 중간 저장
                    }

                    // 4) 모의고사: 지문 바로 뒤에 리뷰테스트 삽입 (짤지문 제외)
                    // pno복사에서 리뷰테스트도 함께 복사됐으면 스킵
                    var isShortPassage = analName.indexOf("\uC9E4") >= 0;  // "짤"
                    if (!includeReviewTest) {
                        // 리뷰테스트 제외 모드 — 스킵
                    } else if (passages[p]._pnoCopied === 2) {
                        // 리뷰테스트 이미 완성본에서 복사됨 — 스킵
                    } else if (sourceType === "mockexam" && !isShortPassage && pno && pno.length >= 4) {
                        var rtKey = pno.substring(0, 4); // "YYMM"
                        var rtMap = S.review_test_map || {};
                        var rtData = rtMap[rtKey] || null;
                        // 마더텅: YYMM으로 못 찾으면 fileCategory(마더텅3 등)로 재시도
                        if (!rtData && fileCategory) {
                            rtData = rtMap[fileCategory] || null;
                        }
                        if (rtData && rtData.passages && rtData.passages.length > 0) {
                            var rtPassage = findReviewTestPassage(rtData.passages, pno);
                            if (rtPassage) {
                                createMemtestSpread(doc, refDoc, templateSpreads, rtPassage, masters, stMemtest, stMemCopy, "D");
                                log("  [리뷰] " + pno + " 리뷰테스트 삽입");
                            } else {
                                createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, "D");
                                log("  [리뷰] " + pno + " 빈 리뷰테스트 페이지");
                            }
                        } else {
                            createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, "D");
                            log("  [리뷰] " + pno + " 빈 리뷰테스트 페이지 (해설지 없음)");
                        }
                    }
                }

                // 5) 교과서/EBS: 해당 분석본의 지문 전부 끝난 후 리뷰테스트 몰아서 삽입
                //    과(lesson)별로 그룹화하여, pno복사된 과는 완성본에서 복사, 아닌 과는 docx/빈 페이지
                if (includeReviewTest && (sourceType === "textbook" || sourceType === "ebs") && passages.length > 0) {
                    var rtMap = S.review_test_map || {};
                    var rtData = rtMap[fileCategory] || null;
                    var rtPassages = (rtData && rtData.passages) ? rtData.passages : [];
                    var rtTypeLabel = sourceType === "ebs" ? "EBS" : "\uAD50\uACFC\uC11C";
                    var rtMasterKey = sourceType === "ebs" ? "L" : "F";
                    var rtMasterChar = rtMasterKey.charAt(0); // "F" or "L"

                    var totalRtCopied = 0;
                    var totalRtFilled = 0;
                    var totalRtEmpty = 0;

                    // ── 올림포스(EBS): 리뷰를 canon 키(강-유형)로 지문과 매칭 ──
                    // 완성본 10-16강엔 리뷰가 없어 docx에서 가져오는데, 위치(index)로
                    // 끼우면 강/번호가 어긋나 엉뚱한 지문에 붙는다(예: "With technology").
                    // engine.py가 부여한 canon("15-01" 등)으로 지문과 정확히 매칭한다.
                    var olpoCat = fileCategory && (fileCategory.indexOf("올림") >= 0 || fileCategory.indexOf("올포") >= 0 || fileCategory.indexOf("리딩파워") >= 0 || fileCategory.indexOf("리파") >= 0);
                    var canonMap = null;
                    if (olpoCat) {
                        for (var rci = 0; rci < rtPassages.length; rci++) {
                            var rck = rtPassages[rci].canon;
                            if (rck) {
                                if (!canonMap) canonMap = {};
                                if (canonMap[rck] === undefined) canonMap[rck] = rtPassages[rci];
                            }
                        }
                    }

                    if (canonMap) {
                        // 지문 순서대로 canon 매칭 리뷰 삽입 (매칭 실패 시 빈 페이지)
                        for (var opi = 0; opi < passages.length; opi++) {
                            // 미래엔 DL: 리뷰도 미래엔N과 완성본의 DL 리뷰(F-마스터)에서 복사
                            if (passages[opi].isDL) {
                                var _dlrm = (passages[opi].passageNo || "").match(/^(\d+)과/);
                                var _dlr = _dlrm ? findDLInTextbook(parseInt(_dlrm[1], 10)) : null;
                                var _dlrOk = false;
                                if (_dlr && _dlr.reviewIdx >= 0) {
                                    try { _dlr.doc.spreads[_dlr.reviewIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]); _dlrOk = true; } catch(e) {}
                                }
                                if (_dlrOk) totalRtFilled++;
                                else { createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, rtMasterKey); totalRtEmpty++; }
                                continue;
                            }
                            var opck = olymposCanonKey(passages[opi].passageNo || "");
                            var orev = opck ? canonMap[opck] : null;
                            if (orev && orev.blank_text) {
                                createMemtestSpread(doc, refDoc, templateSpreads, orev, masters, stMemtest, stMemCopy, rtMasterKey);
                                totalRtFilled++;
                            } else {
                                createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, rtMasterKey);
                                totalRtEmpty++;
                            }
                        }
                    } else {

                    // 과(lesson)별 그룹 생성
                    var lessonGroups = []; // [{ym, startIdx, count, allCopied}]
                    var lgCurYm = null;
                    var lgCurStart = 0;
                    var lgCurAllCopied = true;

                    for (var gi = 0; gi <= passages.length; gi++) {
                        var gYm = fileCategory;
                        if (gi < passages.length) {
                            var gPno = passages[gi].passageNo || "";
                            var gLM = gPno.match(/^(\d+)\uACFC/);
                            if (gLM) {
                                var gPfx = fileCategory.replace(/\d[\d,]*\uACFC.*$/, "");
                                var gKey = gPfx + gLM[1] + "\uACFC";
                                var gFound = false;
                                for (var gli = 0; gli < pnoLookupFiles.length; gli++) {
                                    if (pnoLookupFiles[gli].ym === gKey) { gFound = true; break; }
                                }
                                if (gFound) gYm = gKey;
                            }
                        }
                        if (gi === passages.length || (lgCurYm !== null && gYm !== lgCurYm)) {
                            lessonGroups.push({ym: lgCurYm, startIdx: lgCurStart, count: gi - lgCurStart, allCopied: lgCurAllCopied});
                            lgCurStart = gi;
                            lgCurAllCopied = true;
                        }
                        if (gi < passages.length) {
                            lgCurYm = gYm;
                            if (!passages[gi]._pnoCopied) lgCurAllCopied = false;
                        }
                    }

                    for (var lgi = 0; lgi < lessonGroups.length; lgi++) {
                        var lg = lessonGroups[lgi];
                        var lgCopied = 0;

                        // pno복사된 과 -> 완성본에서 리뷰테스트 스프레드 복사
                        if (lg.allCopied && pnoLookupFiles.length > 0 && pnoLookupDocCache[lg.ym]) {
                            var rtSrcDoc = pnoLookupDocCache[lg.ym];
                            for (var rsi = 0; rsi < rtSrcDoc.spreads.length; rsi++) {
                                try {
                                    var rsPages = rtSrcDoc.spreads[rsi].pages.everyItem().getElements();
                                    var isRT = false;
                                    for (var rpi2 = 0; rpi2 < rsPages.length; rpi2++) {
                                        var ram = rsPages[rpi2].appliedMaster;
                                        var rmName = (ram && ram.isValid) ? ram.name : "";
                                        if (rmName.length > 0 && rmName.charAt(0) === rtMasterChar && rmName.charAt(1) === "-") {
                                            isRT = true; break;
                                        }
                                    }
                                    if (isRT) {
                                        rtSrcDoc.spreads[rsi].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
                                        lgCopied++;
                                    }
                                } catch(e) {}
                            }
                            if (lgCopied > 0) {
                                log("  [\uB9AC\uBDF0] " + lg.ym + " \uB9AC\uBDF0\uD14C\uC2A4\uD2B8 " + lgCopied + "\uAC1C \uC644\uC131\uBCF8\uC5D0\uC11C \uBCF5\uC0AC (" + rtMasterKey + "-\uB9C8\uC2A4\uD130)");
                                totalRtCopied += lgCopied;
                            }
                        }

                        // 완성본에서 복사 못 한 과 -> docx 파서 데이터 또는 빈 페이지
                        if (lgCopied === 0) {
                            for (var mti = lg.startIdx; mti < lg.startIdx + lg.count; mti++) {
                                if (mti < rtPassages.length && rtPassages[mti].blank_text) {
                                    createMemtestSpread(doc, refDoc, templateSpreads, rtPassages[mti], masters, stMemtest, stMemCopy, rtMasterKey);
                                    totalRtFilled++;
                                } else {
                                    createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, rtMasterKey);
                                    totalRtEmpty++;
                                }
                            }
                        }
                    }
                    }

                    // 로그 출력
                    if (totalRtCopied > 0 && (totalRtFilled + totalRtEmpty) > 0) {
                        log("  [\uB9AC\uBDF0] " + rtTypeLabel + " \uB9AC\uBDF0\uD14C\uC2A4\uD2B8: \uC644\uC131\uBCF8 " + totalRtCopied + "\uAC1C + \uC0C8\uB85C " + (totalRtFilled + totalRtEmpty) + "\uAC1C (" + rtMasterKey + "-\uB9C8\uC2A4\uD130)");
                    } else if (totalRtCopied > 0) {
                        log("  [\uB9AC\uBDF0] " + rtTypeLabel + " \uB9AC\uBDF0\uD14C\uC2A4\uD2B8 " + totalRtCopied + "\uAC1C \uC644\uC131\uBCF8\uC5D0\uC11C \uBCF5\uC0AC (" + rtMasterKey + "-\uB9C8\uC2A4\uD130)");
                    } else if (totalRtFilled > 0) {
                        log("  [\uB9AC\uBDF0] " + rtTypeLabel + " \uB9AC\uBDF0\uD14C\uC2A4\uD2B8 " + totalRtFilled + "/" + passages.length + "\uAC1C \uC0BD\uC785 (" + rtMasterKey + "-\uB9C8\uC2A4\uD130)");
                    } else {
                        log("  [\uB9AC\uBDF0] " + rtTypeLabel + " \uBE48 \uB9AC\uBDF0\uD14C\uC2A4\uD2B8 " + passages.length + "\uAC1C \uC0BD\uC785 (" + rtMasterKey + "-\uB9C8\uC2A4\uD130)");
                    }
                }

                try { analDoc.close(SaveOptions.NO); } catch(e) {}
            }
            closePnoLookupDocs();
            var resultMsg = "[결과] 신규 " + newCount + "개, 스킵 " + skipCount + "개";
            if (pnoCopyCount > 0) resultMsg += ", pno복사 " + pnoCopyCount + "개";
            log(resultMsg);
            if (illustCount > 0) log("[삽화] " + illustCount + "개 배치");
            if (iconSrc && csYellow) log("[아이콘] 서술형아이콘 삽입 완료");
            saveLog();
        }

        // (개별복제 제거됨)

        if (copyCount === 0 && newCount === 0 && pnoCopyCount === 0) {
            log("[경고] 처리된 지문이 없습니다");
        }

        // -- 1-1. 카테고리(레슨) 텍스트프레임 정리: 과/강별 첫 페이지만 남기고 삭제 --
        if (csLesson) {
            var seenCats = {}; // { 정규화된카테고리: true }
            var catDelCount = 0;
            for (var ci = 0; ci < doc.spreads.length; ci++) {
                try {
                    var cSpread = doc.spreads[ci];
                    var cPages = cSpread.pages.everyItem().getElements();
                    for (var cpi = 0; cpi < cPages.length; cpi++) {
                        var cTFs = cPages[cpi].textFrames.everyItem().getElements();
                        for (var cti = cTFs.length - 1; cti >= 0; cti--) {
                            var ctf = cTFs[cti];
                            var cgb = ctf.geometricBounds;
                            // 카테고리 프레임: 페이지 위쪽 (top < 5, 작은 높이)
                            if (cgb[0] >= 5 || (cgb[2] - cgb[0]) > 15) continue;
                            // "레슨" 문자스타일이 적용된 텍스트가 있는지 확인
                            var hasLesson = false;
                            try {
                                var chars = ctf.characters.everyItem().getElements();
                                for (var chi = 0; chi < chars.length && chi < 5; chi++) {
                                    if (chars[chi].appliedCharacterStyle === csLesson) {
                                        hasLesson = true; break;
                                    }
                                }
                            } catch(e) {}
                            if (!hasLesson) continue;
                            // 카테고리 텍스트 추출 및 정규화
                            var catText = ctf.contents.replace(/[\r\n]/g, "").replace(/^\s+|\s+$/g, "");
                            if (!catText) continue;
                            // 모의고사: 연/월 구분 없이 "모의고사"로 통합
                            var catKey = catText;
                            // 모의고사 패턴: "XX년 X월" 또는 연월 정보 포함
                            if (/\d+\uB144|\uBAA8\uC758\uACE0\uC0AC/.test(catText)) {
                                catKey = "\uBAA8\uC758\uACE0\uC0AC";
                                ctf.contents = "\uBAA8\uC758\uACE0\uC0AC";
                            }
                            if (seenCats[catKey]) {
                                // 이미 나온 카테고리 — 프레임 삭제
                                try { ctf.remove(); catDelCount++; } catch(e) {}
                            } else {
                                seenCats[catKey] = true;
                            }
                        }
                    }
                } catch(e) {}
            }
            if (catDelCount > 0) log("[\uB808\uC2A8] " + catDelCount + "\uAC1C \uC911\uBCF5 \uCE74\uD14C\uACE0\uB9AC \uD504\uB808\uC784 \uC0AD\uC81C");
            saveLog();
        }

        // -- 2-1. 2차 오버플로우 해소 (전체 페이지 재검사) --
        var fixCount = 0;
        for (var pi = 0; pi < doc.pages.length; pi++) {
            var pg = doc.pages[pi];
            var tfs = pg.textFrames.everyItem().getElements();
            for (var ti = 0; ti < tfs.length; ti++) {
                if (!tfs[ti].overflows) continue;
                if (tfs[ti].label === "topic" || tfs[ti].label === "passageNo") continue;
                var ovTF = tfs[ti];
                // 행간 0.5pt씩 추가 축소 (하한: 6pt)
                for (var rs = 0; rs < 8 && ovTF.overflows; rs++) {
                    try {
                        var ovParas = ovTF.paragraphs.everyItem().getElements();
                        if (ovParas[0].leading <= 6) break;
                        for (var rp = 0; rp < ovParas.length; rp++) {
                            ovParas[rp].leading = ovParas[rp].leading - 0.5;
                        }
                    } catch(e) { break; }
                }
                // 글자 크기 0.25pt씩 추가 축소 (하한: 5pt)
                for (var rs = 0; rs < 4 && ovTF.overflows; rs++) {
                    try {
                        var ovParas = ovTF.paragraphs.everyItem().getElements();
                        if (ovParas[0].pointSize <= 5) break;
                        for (var rp = 0; rp < ovParas.length; rp++) {
                            ovParas[rp].pointSize = ovParas[rp].pointSize - 0.25;
                        }
                    } catch(e) { break; }
                }
                // 프레임 하단 확장 (최대 15mm)
                if (ovTF.overflows) {
                    var ovGb = ovTF.geometricBounds;
                    ovTF.geometricBounds = [ovGb[0], ovGb[1], ovGb[2] + 15, ovGb[3]];
                }
                if (!ovTF.overflows) fixCount++;
            }
        }
        if (fixCount > 0) log("[2차] " + fixCount + "개 오버플로우 해소");
        saveLog();

        // -- 3. 암기테스트 배치 (docx 업로드 시에만 -- 완성본 재사용 시 이미 포함됨) --
        var memtest = S.memtest || [];
        if (memtest.length > 0) {
            // 교과서만 있으면 F-마스터, 모의고사 포함이면 D-마스터
            var ftArr = S.file_types || [];
            var hasNonTextbook = false;
            for (var fi = 0; fi < ftArr.length; fi++) {
                if (ftArr[fi] !== "textbook") { hasNonTextbook = true; break; }
            }
            var mtMaster = hasNonTextbook ? "D" : "F";
            log("[암기] " + memtest.length + "개 배치 시작 (" + mtMaster + "-마스터)");
            for (var t = 0; t < memtest.length; t++) {
                var mt = memtest[t];
                createMemtestSpread(doc, refDoc, templateSpreads, mt, masters, stMemtest, stMemCopy, mtMaster);
            }
            log("[암기] " + memtest.length + "개 완료");
        }

        // -- 4. 마지막 페이지(포켓북_마지막P.ai)는 듣기 등 AT_END 콘텐츠가 모두
        //    들어간 뒤라야 진짜 문서 맨 끝에 오므로, 4.5 듣기 배치 직후(4.6)로 옮김. --

        // -- 4-1. 삽화 링크 재연결 (깨진 링크 + passageNo 불일치) --
        if (illustBase && grade) {
            var relinkCount = 0;
            var relinkFail = 0;
            for (var li = doc.links.length - 1; li >= 0; li--) {
                try {
                    var lnk = doc.links[li];
                    // 삽화 링크만 대상 (숫자.jpg, 숫자-숫자.jpg, 복사본 등)
                    var lnkName = lnk.name;
                    var isIllust = /^\d+/.test(lnkName) || lnkName.indexOf("\uBCF5\uC0AC\uBCF8") >= 0;
                    if (!isIllust) continue;
                    // MISSING이거나, passageNo와 폴더 불일치이면 재연결
                    var needsRelink = (lnk.status == LinkStatus.LINK_MISSING);
                    if (!needsRelink) {
                        // passageNo에서 기대 연/월 추출 후 실제 경로와 비교
                        try {
                            var pf = lnk.parent;
                            var lkPage = null;
                            try { lkPage = pf.parentPage; } catch(e) {}
                            if (!lkPage) try { lkPage = pf.parent.parentPage; } catch(e) {}
                            if (lkPage) {
                                var lkSpread = lkPage.parent;
                                for (var lsi = 0; lsi < lkSpread.pages.length; lsi++) {
                                    var lsTFs = lkSpread.pages[lsi].textFrames.everyItem().getElements();
                                    for (var lti = 0; lti < lsTFs.length; lti++) {
                                        var lgb = lsTFs[lti].geometricBounds;
                                        if (lgb[0] >= 13 && lgb[0] <= 17 && lgb[2] <= 22) {
                                            var lpno = lsTFs[lti].contents.replace(/[\r\n\s]/g, "");
                                            if (lpno && lpno.length >= 4) {
                                                var ey = lpno.substring(0, 2);
                                                var em = String(parseInt(lpno.substring(2, 4), 10));
                                                var fp = "";
                                                try { fp = decodeURI(lnk.filePath); } catch(e2) {}
                                                if (fp && fp.indexOf(ey + "\uB144") < 0) needsRelink = true;
                                                else if (fp && fp.indexOf(em + "\uC6D4") < 0) needsRelink = true;
                                            }
                                            break;
                                        }
                                    }
                                    if (needsRelink) break;
                                }
                            }
                        } catch(e) {}
                    }
                    if (!needsRelink) continue;
                    // 파일명에서 지문번호 추출 시도
                    var lnkName = lnk.name;
                    var lnkBase = lnkName.replace(/\.(jpg|png|jpeg|tif|tiff|psd|ai|eps|pdf)$/i, "");
                    // 숫자만 추출 -> 문번호일 수 있음
                    var lnkDigits = lnkBase.replace(/[^\d]/g, "");

                    // 삽화 폴더 전체에서 같은 파일명으로 탐색
                    var found = null;

                    // 방법 1: 지문번호 6자리로 찾기 (파일명이 문번호인 경우: "34.jpg" -> 삽화정리 폴더에서)
                    // 링크가 있던 스프레드에서 passageNo 프레임을 읽어서 정확한 경로 특정
                    var parentFrame = null;
                    try { parentFrame = lnk.parent; } catch(e) {}
                    if (parentFrame) {
                        var linkPage = null;
                        try { linkPage = parentFrame.parentPage; } catch(e) {}
                        if (!linkPage) {
                            try { linkPage = parentFrame.parent.parentPage; } catch(e) {}
                        }
                        if (linkPage) {
                            // 같은 스프레드의 모든 페이지에서 passageNo 프레임 찾기
                            var linkSpread = linkPage.parent;
                            for (var lsi = 0; lsi < linkSpread.pages.length && !found; lsi++) {
                                try {
                                    var lsTFs = linkSpread.pages[lsi].textFrames.everyItem().getElements();
                                    for (var lti = 0; lti < lsTFs.length; lti++) {
                                        var lgb = lsTFs[lti].geometricBounds;
                                        if (lgb[0] >= 13 && lgb[0] <= 17 && lgb[2] <= 22 && lgb[1] >= 13 && lgb[1] <= 17) {
                                            var lpno = lsTFs[lti].contents.replace(/[\r\n\s]/g, "");
                                            if (lpno && lpno.length === 6) {
                                                found = findIllustFile(illustBase, grade, lpno);
                                                break;
                                            }
                                            // 확장: ~, - 범위의 첫 번째 번호 사용
                                            if (lpno) {
                                                var lpnoKeys = expandPassageNo(lpno);
                                                for (var lk = 0; lk < lpnoKeys.length && !found; lk++) {
                                                    if (lpnoKeys[lk].length === 6) {
                                                        found = findIllustFile(illustBase, grade, lpnoKeys[lk]);
                                                    }
                                                }
                                                if (found) break;
                                            }
                                        }
                                    }
                                } catch(e) {}
                            }
                        }
                    }

                    // 방법 2: 파일명 자체로 삽화 폴더 전체 탐색
                    if (!found) {
                        try {
                            var gradeFolder = new Folder(illustBase + "/" + grade);
                            if (gradeFolder.exists) {
                                var gSubs = gradeFolder.getFiles(function(f) { return f instanceof Folder; });
                                for (var gs = 0; gs < gSubs.length && !found; gs++) {
                                    var tryF = new File(gSubs[gs].fsName + "/" + lnkName);
                                    if (tryF.exists) { found = tryF; break; }
                                    // NFC/NFD 대응: 파일 목록에서 숫자 매칭
                                    if (lnkDigits) {
                                        var gFiles = gSubs[gs].getFiles(function(f) {
                                            var n = f.name.toLowerCase();
                                            return n.indexOf(".jpg") >= 0 || n.indexOf(".png") >= 0;
                                        });
                                        for (var gf = 0; gf < gFiles.length; gf++) {
                                            var gfBase = decodeURI(gFiles[gf].name).replace(/\.(jpg|png)$/i, "");
                                            if (gfBase === lnkDigits || gfBase === lnkBase) {
                                                found = gFiles[gf];
                                                break;
                                            }
                                        }
                                    }
                                }
                            }
                        } catch(e) {}
                    }

                    if (found) {
                        lnk.relink(found);
                        lnk.update();
                        relinkCount++;
                    } else {
                        relinkFail++;
                    }
                } catch(e) {}
            }
            if (relinkCount > 0) log("[링크] " + relinkCount + "개 삽화 재연결");
            if (relinkFail > 0) log("[링크] " + relinkFail + "개 삽화 찾지 못함 (무시)");
        }

        // -- 4-2. 삽화-지문번호 일치 검증 --
        if (illustBase && grade) {
            var verifyOk = 0;
            var verifyFail = 0;
            for (var vi = 0; vi < doc.links.length; vi++) {
                try {
                    var vLnk = doc.links[vi];
                    var vName = vLnk.name;
                    // 삽화 링크만 대상 (숫자로 시작하는 jpg/png)
                    if (!/^\d+/.test(vName)) continue;
                    if (!/\.(jpg|png|jpeg)$/i.test(vName)) continue;
                    if (vLnk.status == LinkStatus.LINK_MISSING) continue;

                    // 링크의 실제 파일 경로에서 연/월/문번호 추출
                    var vPath = "";
                    try { vPath = decodeURI(vLnk.filePath); } catch(e) { continue; }
                    // 파일명에서 문번호 추출
                    var vFileBase = vName.replace(/\.(jpg|png|jpeg)$/i, "");
                    var vFileQ = parseInt(vFileBase.replace(/[^\d]/g, ""), 10);
                    // 경로에서 "YY년 M월" 폴더 추출
                    var vYmMatch = vPath.match(/(\d{2})\uB144\s*(\d{1,2})\uC6D4/);
                    if (!vYmMatch) {
                        // NFD: 년(\u1102\u1167\u11AB) 월(\u110B\u116F\u11AF)
                        vYmMatch = vPath.match(/(\d{2})\u1102\u1167\u11AB\s*(\d{1,2})\u110B\u116F\u11AF/);
                    }

                    // 같은 스프레드에서 passageNo 프레임 찾기
                    var vFrame = vLnk.parent;
                    var vPage = null;
                    try { vPage = vFrame.parentPage; } catch(e) {}
                    if (!vPage) try { vPage = vFrame.parent.parentPage; } catch(e) {}
                    if (!vPage) continue;

                    var vSpread = vPage.parent;
                    var vPno = "";
                    for (var vsi = 0; vsi < vSpread.pages.length; vsi++) {
                        var vTFs = vSpread.pages[vsi].textFrames.everyItem().getElements();
                        for (var vti = 0; vti < vTFs.length; vti++) {
                            var vgb = vTFs[vti].geometricBounds;
                            // passageNo 프레임: 높이 < 10, 너비 < 25, top 13~22
                            if ((vgb[2] - vgb[0]) < 10 && (vgb[3] - vgb[1]) < 25 && vgb[0] >= 13 && vgb[0] <= 22) {
                                vPno = vTFs[vti].contents.replace(/[\r\n\s]/g, "");
                                break;
                            }
                        }
                        if (vPno) break;
                    }

                    if (!vPno || vPno.length < 6) continue;

                    // 지문번호에서 기대하는 연/월/문번호
                    var expY = vPno.substring(0, 2);
                    var expM = String(parseInt(vPno.substring(2, 4), 10));
                    var expQ = parseInt(vPno.substring(4, 6), 10);

                    // 검증 1: 연/월 폴더 일치
                    var ymOk = true;
                    if (vYmMatch) {
                        if (vYmMatch[1] !== expY || String(parseInt(vYmMatch[2], 10)) !== expM) {
                            ymOk = false;
                        }
                    }

                    // 검증 2: 문번호 일치 (단일 파일 또는 범위 파일)
                    var qOk = false;
                    if (!isNaN(vFileQ)) {
                        if (vFileQ === expQ) {
                            qOk = true;
                        } else {
                            // 범위 파일 (예: 30-35.jpg, 41~42.jpg, 41~2.jpg)
                            var vRangeParts = vFileBase.split(/[~\-]/);
                            if (vRangeParts.length === 2) {
                                var vRs = parseInt(vRangeParts[0], 10);
                                var vRe = parseInt(vRangeParts[1], 10);
                                // 짧은 suffix 보정: "41~2" -> 42
                                if (!isNaN(vRs) && !isNaN(vRe) && vRe < vRs) {
                                    var sE = String(vRe), sS = String(vRs);
                                    if (sE.length < sS.length) {
                                        vRe = parseInt(sS.substring(0, sS.length - sE.length) + sE, 10);
                                    }
                                }
                                if (!isNaN(vRs) && !isNaN(vRe) && expQ >= vRs && expQ <= vRe) {
                                    qOk = true;
                                }
                            }
                        }
                    }

                    if (ymOk && qOk) {
                        verifyOk++;
                    } else {
                        verifyFail++;
                        var mismatchMsg = "[검증 실패] 지문 " + vPno + " <-> 삽화 " + vName;
                        if (!ymOk && vYmMatch) mismatchMsg += " (폴더: " + vYmMatch[1] + "년 " + vYmMatch[2] + "월, 기대: " + expY + "년 " + expM + "월)";
                        if (!qOk) mismatchMsg += " (문번호: " + vFileQ + ", 기대: " + expQ + ")";
                        log(mismatchMsg);

                        // 불일치 시 올바른 파일로 재연결 시도
                        var correctFile = findIllustFile(illustBase, grade, vPno);
                        if (correctFile) {
                            vLnk.relink(correctFile);
                            vLnk.update();
                            log("  -> 수정: " + decodeURI(correctFile.name) + " 로 재연결");
                            verifyFail--;
                            verifyOk++;
                        }
                    }
                } catch(e) {}
            }
            if (verifyOk > 0) log("[검증] 삽화 " + verifyOk + "개 지문번호 일치 확인");
            if (verifyFail > 0) log("[검증] 삽화 " + verifyFail + "개 지문번호 불일치 (수정 불가)");
        }

        // -- 4-3. 색상견본 교체: C26 M30 Y47 K10 → C66 M52 Y0 K19 --
        // 완성본 복제 후 실행해야 복제된 스프레드의 색상도 교체됨
        try {
            var swatches = doc.colors.everyItem().getElements();
            for (var swi = 0; swi < swatches.length; swi++) {
                var sw = swatches[swi];
                if (sw.model == ColorModel.PROCESS && sw.space == ColorSpace.CMYK) {
                    var cv = sw.colorValue;
                    if (Math.abs(cv[0] - 26) < 2 && Math.abs(cv[1] - 30) < 2 &&
                        Math.abs(cv[2] - 47) < 2 && Math.abs(cv[3] - 10) < 2) {
                        sw.colorValue = [66, 52, 0, 19];
                        log("[\uC0C9\uC0C1] C26M30Y47K10 \u2192 C66M52Y0K19 \uAD50\uCCB4");
                    }
                }
            }
        } catch(e) {}
        saveLog();

        // -- 4.5 듣기 배치 (listening_text_file이 있을 때만) --
        if (S.listening_text_file && S.listening_text_file !== "") {
            var ltf = new File(S.listening_text_file);
            if (ltf.exists) {
                log("[듣기] 듣기 배치 시작: " + ltf.name);
                ltf.open("r"); ltf.encoding = "UTF-8";
                var rawListen = ltf.read(); ltf.close();
                var lLines = rawListen.split(/\r\n|\r|\n/);

                // 텍스트 파싱
                var lSections = [];
                var lCurSec = null, lCurPsg = null, lMode = "";
                for (var li = 0; li < lLines.length; li++) {
                    var ln = lLines[li];
                    if (ln.indexOf("===SECTION===") === 0) {
                        if (lCurPsg && lCurSec) lCurSec.passages.push(lCurPsg);
                        if (lCurSec) lSections.push(lCurSec);
                        lCurSec = {name: ln.substring(13), passages: []};
                        lCurPsg = null; lMode = "";
                        continue;
                    }
                    if (ln.indexOf("===PASSAGE===") === 0) {
                        if (lCurPsg && lCurSec) lCurSec.passages.push(lCurPsg);
                        lCurPsg = {name: ln.substring(13), script: [], korean: []};
                        lMode = "";
                        continue;
                    }
                    if (ln === "===SCRIPT===") { lMode = "script"; continue; }
                    if (ln === "===KOREAN===") { lMode = "korean"; continue; }
                    if (!lCurPsg || !lCurSec) continue;
                    if (lMode === "script" && ln !== "") lCurPsg.script.push(ln);
                    if (lMode === "korean" && ln !== "") lCurPsg.korean.push(ln);
                }
                if (lCurPsg && lCurSec) lCurSec.passages.push(lCurPsg);
                if (lCurSec) lSections.push(lCurSec);

                // K마스터 찾기
                var kM = null;
                for (var mi = 0; mi < doc.masterSpreads.length; mi++) {
                    if (doc.masterSpreads[mi].name.indexOf("K-") === 0) { kM = doc.masterSpreads[mi]; break; }
                }

                if (!kM) {
                    log("[듣기] K마스터를 찾을 수 없습니다");
                } else {
                    // 스타일 찾기/생성
                    var psDugi = null, psScr = null;
                    var dugiGroup = null;
                    try { dugiGroup = doc.paragraphStyleGroups.itemByName("\uB4E3\uAE30_"); dugiGroup.name; } catch(e) { dugiGroup = null; }
                    if (!dugiGroup) {
                        try { dugiGroup = doc.paragraphStyleGroups.add({name: "\uB4E3\uAE30_"}); } catch(e) {}
                    }
                    for (var si = 0; si < doc.allParagraphStyles.length; si++) {
                        var sn = doc.allParagraphStyles[si].name;
                        if (sn === "\uB4E3\uAE30") psDugi = doc.allParagraphStyles[si];
                        if (sn === "\uC2A4\uD06C\uB9BD\uD2B8") psScr = doc.allParagraphStyles[si];
                    }
                    if (!psDugi) {
                        var notoFont = null;
                        try { notoFont = app.fonts.itemByName("Noto Sans CJK KR\tRegular"); } catch(e) {}
                        var dProps = {name: "\uB4E3\uAE30", pointSize: 7, leading: 10, tracking: -20};
                        if (notoFont && notoFont.isValid) dProps.appliedFont = notoFont;
                        psDugi = dugiGroup ? dugiGroup.paragraphStyles.add(dProps) : doc.paragraphStyles.add(dProps);
                    }
                    if (!psScr) {
                        var scrP = {name: "\uC2A4\uD06C\uB9BD\uD2B8", basedOn: psDugi};
                        psScr = dugiGroup ? dugiGroup.paragraphStyles.add(scrP) : doc.paragraphStyles.add(scrP);
                    }

                    // 프레임 헬퍼
                    function getLFrames(pg) {
                        var mi2 = pg.masterPageItems;
                        for (var j = mi2.length - 1; j >= 0; j--) {
                            try {
                                if (mi2[j] instanceof TextFrame) {
                                    var mgb = mi2[j].geometricBounds;
                                    if ((mgb[2] - mgb[0]) > 50 && (mgb[3] - mgb[1]) > 40) mi2[j].override(pg);
                                }
                            } catch(e) {}
                        }
                        var frames = [];
                        for (var fi = 0; fi < pg.textFrames.length; fi++) {
                            try {
                                var tf2 = pg.textFrames[fi];
                                if (!tf2.isValid) continue;
                                var gb2 = tf2.geometricBounds;
                                if ((gb2[2] - gb2[0]) > 50 && (gb2[3] - gb2[1]) > 40) frames.push(tf2);
                            } catch(e) { continue; }
                        }
                        if (frames.length < 4) {
                            var side2 = (pg.side === PageSideOptions.LEFT_HAND) ? "L" : "R";
                            var pos2 = side2 === "L" ?
                                [[15,15,103,72.5],[15,72.5,103,130],[107,15,195,72.5],[107,72.5,195,130]] :
                                [[15,18,103,75.5],[15,75.5,103,133],[107,18,195,75.5],[107,75.5,195,133]];
                            while (frames.length < 4) {
                                var ntf2 = pg.textFrames.add();
                                ntf2.geometricBounds = pos2[frames.length];
                                frames.push(ntf2);
                            }
                        }
                        frames.sort(function(a, b) {
                            var ag2 = a.geometricBounds, bg2 = b.geometricBounds;
                            if (Math.abs(ag2[0] - bg2[0]) > 20) return ag2[0] - bg2[0];
                            return ag2[1] - bg2[1];
                        });
                        return frames;
                    }

                    // 전체 passages 합치기
                    var allPsg = [];
                    var secPages = [];
                    for (var ss = 0; ss < lSections.length; ss++) {
                        for (var pp = 0; pp < lSections[ss].passages.length; pp++) {
                            var psg = lSections[ss].passages[pp];
                            if (pp === 0) { psg.sectionStart = true; psg.sectionName = lSections[ss].name; }
                            allPsg.push(psg);
                        }
                    }
                    log("[듣기] " + allPsg.length + "개 passage 배치 시작");

                    var pIdx = 0;
                    while (pIdx < allPsg.length) {
                        var spr = doc.spreads.add(LocationOptions.AT_END);
                        spr.appliedMaster = kM;
                        if (spr.pages.length < 2) {
                            try { spr.pages.add(LocationOptions.AT_END); } catch(e) {}
                            spr.appliedMaster = kM;
                        }
                        for (var pi2 = 0; pi2 < spr.pages.length && pIdx < allPsg.length; pi2++) {
                            var pg2 = spr.pages[pi2];
                            if (allPsg[pIdx].sectionStart) {
                                secPages.push({page: pg2, name: allPsg[pIdx].sectionName});
                            }
                            var fr = getLFrames(pg2);
                            if (fr.length < 4) continue;
                            fr[0].nextTextFrame = fr[1];
                            fr[1].nextTextFrame = fr[2];
                            fr[2].nextTextFrame = fr[3];

                            var tp = [];
                            var fbPos = [];

                            var p1 = allPsg[pIdx];
                            tp.push(p1.name);
                            if (p1.script.length > 0) {
                                tp.push("[Script]");
                                for (var x1 = 0; x1 < p1.script.length; x1++) tp.push(p1.script[x1]);
                            }
                            fbPos.push(tp.length);
                            if (p1.korean.length > 0) {
                                tp.push("[\uD574\uC11D]");
                                for (var x2 = 0; x2 < p1.korean.length; x2++) tp.push(p1.korean[x2]);
                            } else { tp.push(""); }
                            pIdx++;

                            if (pIdx < allPsg.length) {
                                var p2 = allPsg[pIdx];
                                if (p2.sectionStart) secPages.push({page: pg2, name: p2.sectionName});
                                fbPos.push(tp.length);
                                tp.push(p2.name);
                                if (p2.script.length > 0) {
                                    tp.push("[Script]");
                                    for (var x3 = 0; x3 < p2.script.length; x3++) tp.push(p2.script[x3]);
                                }
                                fbPos.push(tp.length);
                                if (p2.korean.length > 0) {
                                    tp.push("[\uD574\uC11D]");
                                    for (var x4 = 0; x4 < p2.korean.length; x4++) tp.push(p2.korean[x4]);
                                } else { tp.push(""); }
                                pIdx++;
                            } else {
                                fbPos.push(tp.length); tp.push("");
                                fbPos.push(tp.length); tp.push("");
                            }

                            fr[0].contents = tp.join("\r");
                            var st = fr[0].parentStory;
                            var pc = st.paragraphs.length;
                            for (var fb = fbPos.length - 1; fb >= 0; fb--) {
                                var pidx2 = fbPos[fb];
                                if (pidx2 > 0 && pidx2 < pc) {
                                    try {
                                        var ci2 = st.paragraphs[pidx2].characters[0].index;
                                        st.characters[ci2 - 1].contents = SpecialCharacters.FRAME_BREAK;
                                    } catch(e) {}
                                }
                            }
                            for (var q = 0; q < st.paragraphs.length; q++) {
                                var para2 = st.paragraphs[q];
                                var t2 = para2.contents.replace(/[\r\n\u0003]/g, "");
                                if (t2 === "[Script]") {
                                    para2.applyParagraphStyle(psScr, true);
                                } else {
                                    para2.applyParagraphStyle(psDugi, true);
                                }
                                para2.clearOverrides();
                            }
                        }
                    }

                    // 섹션 마커 추가
                    for (var sp2 = 0; sp2 < secPages.length; sp2++) {
                        try {
                            var ns = doc.sections.add(secPages[sp2].page);
                            ns.continueNumbering = true;
                            ns.name = secPages[sp2].name.replace(/\s+/g, "").substring(0, 5);
                            ns.marker = secPages[sp2].name;
                        } catch(e) {}
                    }

                    log("[듣기] " + allPsg.length + "개 passage 배치 완료");
                }
            } else {
                log("[듣기] 텍스트 파일 없음: " + S.listening_text_file);
            }
        }

        // -- 4.6 마지막 페이지 (포켓북_마지막P.ai) — 왼쪽(짝수) 페이지에 배치 --
        //    (듣기 등 모든 AT_END 콘텐츠 뒤에 추가해야 진짜 문서 맨 끝에 온다)
        var lastPageImg = S.last_page_image || "";
        if (lastPageImg) {
            var imgFile = new File(lastPageImg);
            if (imgFile.exists) {
                var lastSpread = doc.spreads.add(LocationOptions.AT_END);
                // 마스터 없음
                try {
                    for (var lpi = 0; lpi < lastSpread.pages.length; lpi++) {
                        lastSpread.pages[lpi].appliedMaster = NothingEnum.NOTHING;
                    }
                } catch(e) {}
                // 왼쪽(짝수) 페이지 찾기
                var leftPage = null;
                for (var lpi2 = 0; lpi2 < lastSpread.pages.length; lpi2++) {
                    if (lastSpread.pages[lpi2].side == 1818653800) {
                        leftPage = lastSpread.pages[lpi2]; break;
                    }
                }
                if (!leftPage) leftPage = lastSpread.pages[0];
                // 오른쪽 페이지 제거
                for (var rpi = lastSpread.pages.length - 1; rpi >= 0; rpi--) {
                    if (lastSpread.pages[rpi].side != 1818653800) {
                        try { lastSpread.pages[rpi].remove(); } catch(e) {}
                    }
                }
                var pgBounds = leftPage.bounds;
                var rect = leftPage.rectangles.add({
                    geometricBounds: [pgBounds[0] - 3, pgBounds[1] - 3, pgBounds[2] + 3, pgBounds[3] + 3]
                });
                rect.place(imgFile);
                try { rect.fit(FitOptions.PROPORTIONALLY); } catch(e) {}
                log("[마지막] 포켓북 마지막 페이지 추가 (왼쪽)");
            }
        }

        saveLog();

        // -- 5. 저장 + PDF 내보내기 --
        app.scriptPreferences.enableRedraw = true;
        doc.save();
        var pdfPath = S.output_path.replace(/\.indd$/i, ".pdf");
        var pdfFile = new File(pdfPath);
        try {
            var preset = app.pdfExportPresets.itemByName("[\uACE0\uD488\uC9C8 \uC778\uC1C4]");
            doc.exportFile(ExportFormat.PDF_TYPE, pdfFile, false, preset);
            log("PDF: 성공 -- " + pdfFile.name);
        } catch(e) {
            try {
                doc.exportFile(ExportFormat.PDF_TYPE, pdfFile);
                log("PDF: 성공 (기본) -- " + pdfFile.name);
            } catch(e2) { log("PDF: 실패 -- " + e2.message); }
        }

        // 오버플로우 확인
        var overflow = 0;
        for (var pi = 0; pi < doc.pages.length; pi++) {
            var ptfs = doc.pages[pi].textFrames;
            for (var ti = 0; ti < ptfs.length; ti++) {
                if (ptfs[ti].overflows) overflow++;
            }
        }
        log("오버플로우: " + overflow + "개");
        log("총 페이지: " + doc.pages.length);
        // 참조 템플릿 닫기
        try { refDoc.close(SaveOptions.NO); } catch(e) {}

        log("=== 포켓북 조판 완료 ===");
    }

    // ════════════════════════════════════════════════════════════════════
    // BreakUp 정리 유틸 (PocketbookBreakUp.jsx 로직 적용)
    // ════════════════════════════════════════════════════════════════════
    function resetFC() {
        try { app.findGrepPreferences = app.changeGrepPreferences = NothingEnum.NOTHING; } catch(e) {}
    }

    // 스토리에서 영어/한글 줄만 남기기
    function cleanupStory(story, keep) {
        try {
            var paras = story.paragraphs.everyItem().getElements();
            for (var i = paras.length - 1; i >= 0; i--) {
                var t = paras[i].contents.replace(/[\r\n]+$/, "").replace(/^\s+|\s+$/g, "");
                if (t.length < 2) { try { paras[i].remove(); } catch(e) {} continue; }
                var hasKor = /[\uAC00-\uD7AF\u1100-\u11FF]/.test(t);
                if (keep === "english" && hasKor) { try { paras[i].remove(); } catch(e) {} }
                else if (keep === "korean" && !hasKor) { try { paras[i].remove(); } catch(e) {} }
            }
        } catch(e) {}
    }

    // 문자스타일 "지문 번호"로 적용된 숫자 삭제 (모의고사 단락 앞 번호)
    // + 문자스타일 없이 텍스트 앞에 붙은 번호(1 2 3... 등)도 삭제
    function deletePassageNumberDigits(story) {
        try {
            // 1) 문자스타일 "지문 번호" 기반 삭제
            resetFC();
            var csPN = findCharStyle(story.parent, "\uC9C0\uBB38 \uBC88\uD638"); // 지문 번호
            if (csPN) {
                app.findGrepPreferences.appliedCharacterStyle = csPN;
                app.findGrepPreferences.findWhat = "[0-9\\x{FF10}-\\x{FF19}]+";
                app.changeGrepPreferences.changeTo = "";
                story.changeGrep();
            }
            resetFC();

            // 2) 원문자/괄호숫자 삭제 (①~㊿ 등 Enclosed Alphanumerics 전체)
            app.findGrepPreferences.findWhat = "[\\x{2460}-\\x{24FF}\\x{2776}-\\x{277F}\\x{3251}-\\x{325F}] ?";
            app.changeGrepPreferences.changeTo = "";
            story.changeGrep();
            resetFC();

            // 3) 텍스트 맨 앞 숫자+공백 패턴 삭제 ("1 Text..." -> "Text...", "10 The..." -> "The...")
            //    joinParagraphs 전이라 각 단락 앞에 번호가 붙어 있음
            app.findGrepPreferences.findWhat = "^\\d{1,3}[ \\x{00A0}\\x{2002}-\\x{200B}\\x{3000}\\t]+";
            app.changeGrepPreferences.changeTo = "";
            story.changeGrep();
            resetFC();

            // 3-1) 10번 이상: 제어문자(0x1A 등)로 변환된 두 자릿수 번호 삭제
            app.findGrepPreferences.findWhat = "^[\\x{001A}-\\x{001F}] ?";
            app.changeGrepPreferences.changeTo = "";
            story.changeGrep();
            resetFC();

            // 3) "~+" + 공백 제거
            app.findGrepPreferences.findWhat = "~\\+ ?";
            app.changeGrepPreferences.changeTo = "";
            story.changeGrep();
            resetFC();
        } catch(e) { resetFC(); }
    }

    // ════════════════════════════════════════════════════════════════════
    // 리뷰테스트 스프레드 생성 -- 원본 D-마스터 스프레드 복제, 내용만 교체
    // ════════════════════════════════════════════════════════════════════
    function createMemtestSpread(doc, refDoc, templateSpreads, mtData, masters, stMemtest, stMemCopy, mtMasterKey) {
        if (!mtMasterKey) mtMasterKey = "D";
        var dKey = mtMasterKey + "-\uB9C8\uC2A4\uD130";
        var stampIdx = templateSpreads[dKey];

        if (stampIdx !== undefined && refDoc && refDoc.isValid) {
            refDoc.spreads[stampIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
            var mtSpread = doc.spreads[-1];

            // 왼쪽 페이지: 기존 콘텐츠 프레임 찾아서 내용 교체
            for (var sp = 0; sp < mtSpread.pages.length; sp++) {
                var pg = mtSpread.pages[sp];
                var tfs = pg.textFrames.everyItem().getElements();
                for (var ti = 0; ti < tfs.length; ti++) {
                    var tgb = tfs[ti].geometricBounds;
                    var th = tgb[2] - tgb[0];
                    // 마스터 아이템 건드리지 않음
                    var isLocal = true;
                    try { var pp = tfs[ti].parentPage; if (pp && pp.parent && pp.parent.constructor.name === "MasterSpread") isLocal = false; } catch(e) {}
                    if (!isLocal) continue;
                    // 큰 콘텐츠 프레임 (높이 > 80mm)
                    if (th > 80) {
                        if (pg.side == 1818653800 && mtData && mtData.blank_text) {
                            tfs[ti].contents = mtData.blank_text;
                            try { tfs[ti].characters.everyItem().appliedCharacterStyle = doc.characterStyles[0]; } catch(e) {}
                            joinParagraphs(tfs[ti].parentStory);
                            // 대괄호 내 글자색을 Paper로 변경 (빈칸 효과)
                            try {
                                var paperColor = doc.swatches.itemByName("Paper");
                                resetFC();
                                app.findGrepPreferences.findWhat = "\\d+\\[[^\\]]+\\]";
                                var blankHits = tfs[ti].parentStory.findGrep();
                                resetFC();
                                for (var bh = 0; bh < blankHits.length; bh++) {
                                    try {
                                        var hitChars = blankHits[bh].characters.everyItem().getElements();
                                        var inBracket = false;
                                        for (var hc = 0; hc < hitChars.length; hc++) {
                                            var ch = hitChars[hc].contents;
                                            if (ch === "[") { inBracket = true; continue; }
                                            if (ch === "]") { inBracket = false; continue; }
                                            if (inBracket) {
                                                hitChars[hc].fillColor = paperColor;
                                            }
                                        }
                                    } catch(e) {}
                                }
                            } catch(e) { resetFC(); }
                            if (stMemCopy) {
                                try {
                                    tfs[ti].paragraphs.everyItem().appliedParagraphStyle = stMemCopy;
                                    tfs[ti].paragraphs.everyItem().pointSize = stMemCopy.pointSize;
                                    tfs[ti].paragraphs.everyItem().leading = stMemCopy.leading;
                                } catch(e) {}
                            }
                        } else if (pg.side != 1818653800 && mtData && mtData.answer_text) {
                            tfs[ti].contents = mtData.answer_text;
                            try { tfs[ti].characters.everyItem().appliedCharacterStyle = doc.characterStyles[0]; } catch(e) {}
                            joinParagraphs(tfs[ti].parentStory);
                            if (stMemtest) {
                                try {
                                    tfs[ti].paragraphs.everyItem().appliedParagraphStyle = stMemtest;
                                    tfs[ti].paragraphs.everyItem().pointSize = stMemtest.pointSize;
                                    tfs[ti].paragraphs.everyItem().leading = stMemtest.leading;
                                } catch(e) {}
                            }
                        } else {
                            tfs[ti].contents = "";
                        }
                    }
                }
            }
        } else {
            // 폴백: 템플릿 없으면 마스터만 적용 (override 없음)
            var mtSpread = doc.spreads.add(LocationOptions.AT_END);
            var mtFallbackMaster = masters[dKey];
            if (mtFallbackMaster) {
                for (var sp = 0; sp < mtSpread.pages.length; sp++) {
                    try { mtSpread.pages[sp].appliedMaster = mtFallbackMaster; } catch(e) {}
                }
            }
        }
    }

    // 빈 리뷰테스트 스프레드 -- 원본 스프레드 복제, 내용 비움
    function createEmptyMemtestSpread(doc, refDoc, templateSpreads, masters, mtMasterKey) {
        if (!mtMasterKey) mtMasterKey = "D";
        var dKey = mtMasterKey + "-\uB9C8\uC2A4\uD130";
        var stampIdx = templateSpreads[dKey];

        if (stampIdx !== undefined && refDoc && refDoc.isValid) {
            refDoc.spreads[stampIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
            var mtSpread = doc.spreads[-1];
            // 로컬 콘텐츠 프레임 내용만 비우기
            for (var sp = 0; sp < mtSpread.pages.length; sp++) {
                var tfs = mtSpread.pages[sp].textFrames.everyItem().getElements();
                for (var ti = 0; ti < tfs.length; ti++) {
                    var isLocal = true;
                    try { var pp = tfs[ti].parentPage; if (pp && pp.parent && pp.parent.constructor.name === "MasterSpread") isLocal = false; } catch(e) {}
                    if (isLocal && (tfs[ti].geometricBounds[2] - tfs[ti].geometricBounds[0]) > 80) {
                        tfs[ti].contents = "";
                    }
                }
            }
        } else {
            var mtSpread = doc.spreads.add(LocationOptions.AT_END);
            var mtFallbackMaster2 = masters[dKey];
            if (mtFallbackMaster2) {
                for (var sp = 0; sp < mtSpread.pages.length; sp++) {
                    try { mtSpread.pages[sp].appliedMaster = mtFallbackMaster2; } catch(e) {}
                }
            }
        }
    }

    // passageNo로 리뷰테스트 passage 매칭
    function findReviewTestPassage(rtPassages, pno) {
        if (!rtPassages || !pno || pno.length < 4) return null;

        // 1차: header에 passageNo(6자리) 자체가 포함된 경우 (마더텅 등)
        if (pno.length >= 6) {
            for (var ri = 0; ri < rtPassages.length; ri++) {
                var h = rtPassages[ri].header || "";
                if (h.indexOf(pno) >= 0) return rtPassages[ri];
            }
        }

        // 2차: header의 "no.XX" 또는 "no.XX~YY" 패턴에서 문번호 매칭
        if (pno.length >= 6) {
            var qNum = parseInt(pno.substring(4, 6), 10);
            for (var ri = 0; ri < rtPassages.length; ri++) {
                var h = rtPassages[ri].header || "";
                var noMatch = h.match(/no\.(\d+)/);
                if (noMatch) {
                    var noNum = parseInt(noMatch[1], 10);
                    if (noNum === qNum) return rtPassages[ri];
                    var rangeMatch = h.match(/no\.(\d+)[~\-](\d+)/);
                    if (rangeMatch) {
                        var rStart = parseInt(rangeMatch[1], 10);
                        var rEnd = parseInt(rangeMatch[2], 10);
                        if (qNum >= rStart && qNum <= rEnd) return rtPassages[ri];
                    }
                }
            }
        }
        return null;
    }

    // \r -> 공백, \t -> 공백, 연속 공백 축소 (엔터 없이 이어지게)
    function joinParagraphs(story) {
        try {
            resetFC();
            app.findGrepPreferences.findWhat = "\\r";
            app.changeGrepPreferences.changeTo = " ";
            story.changeGrep();
            resetFC();
            app.findGrepPreferences.findWhat = "\\t";
            app.changeGrepPreferences.changeTo = " ";
            story.changeGrep();
            resetFC();
            app.findGrepPreferences.findWhat = "[ \\x{00A0}\\x{2000}-\\x{200B}\\x{3000}]{2,}";
            app.changeGrepPreferences.changeTo = " ";
            story.changeGrep();
            resetFC();
        } catch(e) { resetFC(); }
    }

    // ════════════════════════════════════════════════════════════════════
    // 서술형아이콘 삽입 — 형광펜_노랑 문자스타일 위치에 앵커 아이콘 배치
    // PocketbookIcon.jsx 로직 간소화 통합
    // ════════════════════════════════════════════════════════════════════
    function insertIconsForStory(story, iconSrc, csYellow, xOff, yOff) {
        if (!story || !story.isValid || !iconSrc || !csYellow) return 0;

        // 1. GREP으로 형광펜_노랑 적용 텍스트 찾기
        resetFC();
        app.findGrepPreferences.appliedCharacterStyle = csYellow;
        var hits;
        try { hits = story.findGrep(); } catch(e) { resetFC(); return 0; }
        resetFC();
        if (!hits || hits.length === 0) return 0;

        // 스토리 전체 텍스트 미리 추출 (문장 경계 계산용)
        var fullText = "";
        try { fullText = story.contents; } catch(e) {}

        // 2. 문장 단위 dedup — 마침표/느낌표/물음표 기준으로 문장 구간 판별
        var targets = [];
        var seen = {};
        for (var i = 0; i < hits.length; i++) {
            var t = hits[i];
            if (!t.isValid) continue;
            try {
                // 형광펜 시작점의 단어 첫 insertionPoint
                var ipWord = null;
                try {
                    var w = t.words[0];
                    if (w && w.isValid) ipWord = w.insertionPoints[0];
                } catch(e) {}
                if (!ipWord) try { ipWord = t.insertionPoints[0]; } catch(e) {}
                if (!ipWord || !ipWord.isValid) continue;

                // 문장 경계 계산: hit 위치까지의 텍스트에서 마지막 마침표/느낌표 찾기
                var hitIdx = 0;
                try { hitIdx = t.insertionPoints[0].index - story.insertionPoints[0].index; } catch(e) {}
                var sentenceStart = 0;
                if (fullText && hitIdx > 0) {
                    var before = fullText.substring(0, hitIdx);
                    for (var ci = before.length - 1; ci >= 0; ci--) {
                        var ch = before.charAt(ci);
                        if (ch === "." || ch === "!" || ch === "?") {
                            sentenceStart = ci + 1;
                            break;
                        }
                    }
                }

                var key = String(sentenceStart);
                var wordIdx = ipWord.index;
                if (!seen[key] || seen[key].wordIdx > wordIdx) {
                    seen[key] = { wordIdx: wordIdx, ip: ipWord, hit: t };
                }
            } catch(e) { continue; }
        }

        // 3. targets 수집 + 역순 정렬 (인덱스 밀림 방지)
        for (var k in seen) {
            if (seen.hasOwnProperty(k)) targets.push(seen[k]);
        }
        targets.sort(function(a, b) { return b.wordIdx - a.wordIdx; });

        // 4. 아이콘 삽입
        var count = 0;
        for (var ti = 0; ti < targets.length; ti++) {
            try {
                var ip = targets[ti].ip;
                var dup = iconSrc.duplicate();
                dup.label = "서술형아이콘_placed";
                try { dup.anchoredObjectSettings.releaseAnchoredObject(); } catch(e) {}

                dup.anchoredObjectSettings.insertAnchoredObject(ip, AnchorPosition.ANCHORED);
                dup.anchoredObjectSettings.anchoredPosition = AnchorPosition.ANCHORED;
                dup.anchoredObjectSettings.spineRelative = false;
                dup.anchoredObjectSettings.anchorPoint = AnchorPoint.BOTTOM_CENTER_ANCHOR;
                try { dup.anchoredObjectSettings.horizontalReferencePoint = AnchoredRelativeTo.ANCHOR_LOCATION; } catch(e) {}
                try { dup.anchoredObjectSettings.verticalReferencePoint = AnchoredRelativeTo.ANCHOR_LOCATION; } catch(e) {}
                try { dup.anchoredObjectSettings.lockPosition = false; } catch(e) {}

                // 형광펜 시작 문자 위에 배치
                var finalX = xOff;
                try {
                    var hit = targets[ti].hit;
                    if (hit && hit.isValid && hit.characters.length > 0) {
                        var hitStartX = hit.characters[0].horizontalOffset;
                        var ipX = ip.horizontalOffset;
                        finalX = hitStartX - ipX;
                    }
                } catch(e) {}
                try { dup.anchoredObjectSettings.anchorXoffset = finalX; } catch(e) {}
                try { dup.anchoredObjectSettings.anchorYoffset = yOff; } catch(e) {}

                count++;
            } catch(e) { continue; }
        }
        return count;
    }

    // ════════════════════════════════════════════════════════════════════
    // passageNo(6자리)로 삽화 파일 찾기 (NFD/NFC + 범위파일 대응)
    // 41~42, 41-42, 4142, 41, 42 모두 동일 번호로 취급
    // ════════════════════════════════════════════════════════════════════
    function findIllustFile(illustBase, grade, pno) {
        if (!illustBase || !pno) return null;
        // range passageNo -> 첫 번째 6자리 키 사용
        var keys = expandPassageNo(pno);
        var key6 = null;
        for (var ki = 0; ki < keys.length; ki++) {
            if (keys[ki].length === 6) { key6 = keys[ki]; break; }
        }
        if (!key6) return null;
        var iy = key6.substring(0, 2);
        var im = key6.substring(2, 4);
        var iq = key6.substring(4, 6);
        var imNum = parseInt(im, 10);
        var iqNum = parseInt(iq, 10);

        // 매칭할 문번호 목록 (41~42 -> [41, 42])
        var iqNums = [];
        for (var ki2 = 0; ki2 < keys.length; ki2++) {
            if (keys[ki2].length === 6 && keys[ki2].substring(0, 4) === key6.substring(0, 4)) {
                var q = parseInt(keys[ki2].substring(4, 6), 10);
                if (!isNaN(q)) iqNums.push(q);
            }
        }
        if (iqNums.length === 0) iqNums.push(iqNum);

        // 1) 정확 경로 (단일 번호)
        var illustDir = illustBase + "/" + grade + "/" + iy + "\uB144 " + imNum + "\uC6D4";
        for (var ei = 0; ei < iqNums.length; ei++) {
            var testFile = new File(illustDir + "/" + iqNums[ei] + ".jpg");
            if (testFile.exists) return testFile;
        }

        // 2) NFD/NFC 폴더명 차이 대응 + 범위 파일 탐색
        try {
            var illustFolder = new Folder(illustBase + "/" + grade);
            if (!illustFolder.exists) return null;
            var subFolders = illustFolder.getFiles(function(f) { return f instanceof Folder; });
            for (var sfi = 0; sfi < subFolders.length; sfi++) {
                var fn = decodeURI(subFolders[sfi].name);
                if (fn.indexOf(iy) >= 0 && fn.indexOf(String(imNum)) >= 0) {
                    // 단일 번호 시도 (jpg, png)
                    for (var ei2 = 0; ei2 < iqNums.length; ei2++) {
                        var tryFile = new File(subFolders[sfi].fsName + "/" + iqNums[ei2] + ".jpg");
                        if (tryFile.exists) return tryFile;
                        var tryPng = new File(subFolders[sfi].fsName + "/" + iqNums[ei2] + ".png");
                        if (tryPng.exists) return tryPng;
                    }
                    // 범위 파일 탐색 (41-42.jpg, 41~42.jpg, 41~2.jpg 등)
                    var dirFiles = subFolders[sfi].getFiles(function(f) {
                        var n = f.name.toLowerCase();
                        return n.indexOf(".jpg") >= 0 || n.indexOf(".png") >= 0;
                    });
                    for (var df = 0; df < dirFiles.length; df++) {
                        var dfn = decodeURI(dirFiles[df].name).replace(/\.(jpg|png)$/i, "");
                        // ~, -, 모두 범위 구분자로 처리
                        var rangeParts = dfn.split(/[~\-]/);
                        if (rangeParts.length === 2) {
                            var rStart = parseInt(rangeParts[0], 10);
                            var rEnd = parseInt(rangeParts[1], 10);
                            // 짧은 suffix: "41~2" -> rEnd=2 -> 보정: 42
                            if (!isNaN(rStart) && !isNaN(rEnd) && rEnd < rStart) {
                                var sEnd = String(rEnd);
                                var sStart = String(rStart);
                                if (sEnd.length < sStart.length) {
                                    rEnd = parseInt(sStart.substring(0, sStart.length - sEnd.length) + sEnd, 10);
                                }
                            }
                            if (!isNaN(rStart) && !isNaN(rEnd)) {
                                for (var qi = 0; qi < iqNums.length; qi++) {
                                    if (iqNums[qi] >= rStart && iqNums[qi] <= rEnd) {
                                        return dirFiles[df];
                                    }
                                }
                            }
                        }
                    }
                }
            }
        } catch(e) {}
        return null;
    }

    // ════════════════════════════════════════════════════════════════════
    // 짤지문 양면 스프레드 생성 (G-마스터)
    // 왼쪽 페이지: passage 본문, 오른쪽 페이지: passage.rightPassage 본문
    // ════════════════════════════════════════════════════════════════════
    function createPairSpread(doc, refDoc, templateSpreads, passage, sourceType, fileCategory, masters, styleMap, stBody, stMemtest, basicPara, iconSrc, csYellow) {
        var result = {};
        var pairMap = { ebs: "H-\uB9C8\uC2A4\uD130", mockexam: "G-\uB9C8\uC2A4\uD130", textbook: "G-\uB9C8\uC2A4\uD130" };
        var masterName = pairMap[sourceType] || "G-\uB9C8\uC2A4\uD130";

        // G-마스터 템플릿 스프레드 복제
        var tsIdx = templateSpreads[masterName];
        if (tsIdx === undefined || tsIdx === null) {
            log("  [경고] G-마스터 템플릿 스프레드 없음");
            return result;
        }
        try {
            refDoc.spreads[tsIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
        } catch(e) {
            log("  [경고] G-마스터 스프레드 복제 실패: " + e.message);
            return result;
        }
        var newSpread = doc.spreads[-1];

        // 양쪽 페이지에 각각 조판
        var sides = [
            { passage: passage, side: 1818653800 },
            { passage: passage.rightPassage, side: 1919382632 }
        ];

        for (var si = 0; si < sides.length; si++) {
            var curPassage = sides[si].passage;
            var targetSide = sides[si].side;
            if (!curPassage) continue;

            // 해당 side의 페이지 찾기
            var thePage = null;
            for (var sp = 0; sp < newSpread.pages.length; sp++) {
                if (newSpread.pages[sp].side == targetSide) { thePage = newSpread.pages[sp]; break; }
            }
            if (!thePage) thePage = newSpread.pages[si];

            // 프레임 찾기: passageNo, 영어, 한글, 카테고리
            var tfs = thePage.textFrames.everyItem().getElements();
            var noTF = null, engTF = null, korTF = null, catTF = null;
            for (var fi = 0; fi < tfs.length; fi++) {
                var fgb = tfs[fi].geometricBounds;
                var fh = fgb[2] - fgb[0];
                var fw = fgb[3] - fgb[1];
                // passageNo: 작은 프레임 상단
                if (fh < 10 && fw < 25 && fgb[0] < 22) { noTF = tfs[fi]; continue; }
                // 영어: top ~24, 큰 프레임
                if (fgb[0] >= 20 && fgb[0] <= 30 && fh > 50) { engTF = tfs[fi]; continue; }
                // 한글: top > 100
                if (fgb[0] > 100 && fh > 20) { korTF = tfs[fi]; continue; }
                // 카테고리: top < 0, 작은 프레임
                if (fgb[0] < 0 && fh < 15) { catTF = tfs[fi]; continue; }
            }

            var passageNo = curPassage.passageNo || "";
            var displayCat = fileCategory || "";
            var sm = styleMap[sourceType] || styleMap.textbook;

            if (catTF && displayCat) catTF.contents = displayCat;
            if (noTF) {
                noTF.textFramePreferences.autoSizingType = AutoSizingTypeEnum.OFF;
                noTF.contents = passageNo;
                noTF.textFramePreferences.autoSizingType = AutoSizingTypeEnum.WIDTH_ONLY;
                noTF.textFramePreferences.autoSizingReferencePoint = AutoSizingReferenceEnum.LEFT_CENTER_POINT;
                noTF.textFramePreferences.useMinimumWidthForAutoSizing = true;
                noTF.textFramePreferences.minimumWidthForAutoSizing = 18;
                noTF.geometricBounds = [15, 15, 20.5, 33];
            }

            // 영어 본문
            if (engTF) {
                engTF.contents = "";
                if (curPassage.engStory) {
                    try { curPassage.engStory.texts[0].duplicate(LocationOptions.AT_BEGINNING, engTF.insertionPoints[0]); } catch(e) {}
                }
                if (curPassage.extraEngStories) {
                    for (var exi = 0; exi < curPassage.extraEngStories.length; exi++) {
                        try { curPassage.extraEngStories[exi].texts[0].duplicate(LocationOptions.AT_END, engTF.insertionPoints[-1]); } catch(e) {}
                    }
                }
                cleanupStory(engTF.parentStory, "english");
                deletePassageNumberDigits(engTF.parentStory);
                joinParagraphs(engTF.parentStory);
                applyStyleWithSize(engTF, stBody, sm.engSize, sm.engLead);
                if (iconSrc) {
                    if (!csYellow) {
                        csYellow = findCharStyle(doc, "\uD615\uAD11\uD39C_\uB178\uB791");
                    }
                    if (csYellow) {
                        try {
                            var ic = insertIconsForStory(engTF.parentStory, iconSrc, csYellow, 12, -3);
                            if (ic > 0) result.iconCount = (result.iconCount || 0) + ic;
                        } catch(e) {}
                    }
                }
            }

            // 한글 해석
            if (korTF) {
                korTF.contents = "";
                if (curPassage.korStory) {
                    try { curPassage.korStory.texts[0].duplicate(LocationOptions.AT_BEGINNING, korTF.insertionPoints[0]); } catch(e) {}
                }
                if (curPassage.extraKorStories) {
                    for (var exi = 0; exi < curPassage.extraKorStories.length; exi++) {
                        try { curPassage.extraKorStories[exi].texts[0].duplicate(LocationOptions.AT_END, korTF.insertionPoints[-1]); } catch(e) {}
                    }
                }
                cleanupStory(korTF.parentStory, "korean");
                joinParagraphs(korTF.parentStory);
                applyStyleWithSize(korTF, stBody, sm.korSize, sm.korLead);
            }

            // 분석본 페이지 이미지 배치 (짤지문 — 그래프/차트 등)
            var imgs = curPassage.pageImages || [];
            if (imgs.length > 0 && engTF && korTF) {
                for (var imi = 0; imi < imgs.length; imi++) {
                    try {
                        var imgFile = new File(imgs[imi].filePath);
                        if (!imgFile.exists) continue;
                        // 영어 프레임을 줄이고 그 아래에 이미지 배치
                        var egb = engTF.geometricBounds;
                        var kgb = korTF.geometricBounds;
                        var imgH = 35; // 이미지 높이 (pt)
                        // 영어 프레임 bottom을 imgH만큼 올리기
                        engTF.geometricBounds = [egb[0], egb[1], egb[2] - imgH - 2, egb[3]];
                        var newEngBottom = egb[2] - imgH - 2;
                        // 이미지 프레임: 영어 프레임 바로 아래
                        var imgRect = thePage.rectangles.add({
                            geometricBounds: [newEngBottom + 1, egb[1], newEngBottom + 1 + imgH, egb[3]]
                        });
                        imgRect.place(imgFile);
                        try { imgRect.fit(FitOptions.PROPORTIONALLY); } catch(e) {}
                        try { imgRect.fit(FitOptions.CENTER_CONTENT); } catch(e) {}
                        result.illustPlaced = true;
                        log("  [\uC774\uBBF8\uC9C0] " + decodeURI(imgFile.name));
                    } catch(e) {}
                }
            }

            // 오버플로우 해소
            if (engTF && korTF) {
                resolveOverflow(engTF, korTF, 195);
            }

            log("  [짤지문] " + (targetSide == 1818653800 ? "L" : "R") + " pno=" + passageNo);
        }

        return result;
    }

    // ════════════════════════════════════════════════════════════════════
    // 새 스프레드 생성 -- 원본 템플릿 스프레드를 복제하고 내용만 교체
    // ════════════════════════════════════════════════════════════════════
    function createNewSpread(doc, refDoc, templateSpreads, passage, sourceType, fileCategory, baseMasterName, masters, styleMap, stBody, stKorean, stMemtest, stTopic, basicPara, csLesson, csPassNo, illustBase, grade, iconSrc, csYellow) {
        var result = { illustPlaced: false };
        var masterName = baseMasterName;

        // 삽화 파일 확인 (모의고사만)
        var illustFile = null;
        if (sourceType === "mockexam" && passage.passageNo && illustBase) {
            illustFile = findIllustFile(illustBase, grade, passage.passageNo);
        }
        // 삽화 없는 모의고사: C-마스터 템플릿 유지, 생성 후 왼쪽만 G-마스터 적용
        var noIllustMockexam = (sourceType === "mockexam" && !illustFile);

        var sm = styleMap[sourceType] || styleMap.textbook;

        // 카테고리명
        var displayCat = fileCategory;
        // EBS \uB2E8\uC6D0\uBA85: \uBD84\uC11D\uBCF8 \uCE74\uD14C\uACE0\uB9AC\uB85C \uCC45 \uAD6C\uBD84(\uB9AC\uB529\uD30C\uC6CC vs \uC62C\uB9BC\uD3EC\uC2A4).
        // \uACFC\uAC70\uC5D4 EBS\uBA74 \uBB34\uC870\uAC74 \uC62C\uB9BC\uD3EC\uC2A4\uB85C \uD558\uB4DC\uCF54\uB529\uD574 \uB9AC\uB529\uD30C\uC6CC\uB3C4 \uC62C\uB9BC\uD3EC\uC2A4\uB85C \uCC0D\uD614\uB2E4.
        if (sourceType === "ebs") {
            if (fileCategory && (fileCategory.indexOf("\uB9AC\uB529\uD30C\uC6CC") >= 0 || fileCategory.indexOf("\uB9AC\uD30C") >= 0))
                displayCat = "\uB9AC\uB529\uD30C\uC6CC";   // \uB9AC\uB529\uD30C\uC6CC
            else
                displayCat = "\uC62C\uB9BC\uD3EC\uC2A4";   // \uC62C\uB9BC\uD3EC\uC2A4(\uAE30\uBCF8)
        }
        else if (sourceType === "mockexam") displayCat = "\uBAA8\uC758\uACE0\uC0AC";
        else if (fileCategory) {
            displayCat = fileCategory.replace(/([^\d\s])(\d)/, "$1 $2");
        }

        var passageNo = passage.passageNo || "";
        log("  [pno] " + passageNo);

        // ── 템플릿 스프레드 복제 방식 ──
        var stampIdx = templateSpreads[masterName];
        if (stampIdx !== undefined && refDoc && refDoc.isValid) {
            // 원본 템플릿에서 스프레드 통째 복제
            refDoc.spreads[stampIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
            var newSpread = doc.spreads[-1];

            // 왼쪽 페이지 찾기
            var leftPage = null;
            for (var sp = 0; sp < newSpread.pages.length; sp++) {
                if (newSpread.pages[sp].side == 1818653800) { leftPage = newSpread.pages[sp]; break; }
            }
            if (!leftPage) leftPage = newSpread.pages[0];

            // 왼쪽 페이지: 기존 프레임 찾아서 내용만 교체
            var tfs = leftPage.textFrames.everyItem().getElements();
            var engTF = null, korTF = null, noTF = null, catTF = null;
            for (var fi = 0; fi < tfs.length; fi++) {
                var fgb = tfs[fi].geometricBounds;
                var fh = fgb[2] - fgb[0];
                var fw = fgb[3] - fgb[1];
                // 카테고리: 페이지 위쪽 (top < 0)
                if (fgb[0] < 0) { catTF = tfs[fi]; continue; }
                // 지문번호: 작은 프레임 (높이 < 10, 너비 < 25, top < 22)
                if (fh < 10 && fw < 25 && fgb[0] < 22) { noTF = tfs[fi]; continue; }
                // 영어: top ~24, left < 20, 큰 프레임
                if (fgb[0] >= 20 && fgb[0] <= 30 && fgb[1] < 20 && fh > 50) { engTF = tfs[fi]; continue; }
                // 한글: 나머지 큰 프레임 (top > 100)
                if (fgb[0] > 100 && fh > 20) { korTF = tfs[fi]; continue; }
            }

            // 삽화 프레임 찾기 (C-마스터 왼쪽 페이지 하단 — 템플릿에서 복제된 기존 프레임)
            var illustRect = null;
            if (masterName.indexOf("C") === 0) {
                var rects = leftPage.rectangles.everyItem().getElements();
                for (var ri = 0; ri < rects.length; ri++) {
                    var rgb = rects[ri].geometricBounds;
                    // 삽화 프레임: top ~149, left ~13 (블리드 사각형 제외)
                    if (rgb[0] > 100 && rgb[0] < 200 && rgb[1] > 5 && rgb[1] < 80) {
                        illustRect = rects[ri]; break;
                    }
                }
            }

            // 카테고리 내용 교체
            if (catTF && displayCat) {
                catTF.contents = displayCat;
            }

            // 지문번호 내용 교체
            if (noTF) {
                noTF.textFramePreferences.autoSizingType = AutoSizingTypeEnum.OFF;
                noTF.contents = passageNo;
                noTF.textFramePreferences.autoSizingType = AutoSizingTypeEnum.WIDTH_ONLY;
                noTF.textFramePreferences.autoSizingReferencePoint = AutoSizingReferenceEnum.LEFT_CENTER_POINT;
                noTF.textFramePreferences.useMinimumWidthForAutoSizing = true;
                noTF.textFramePreferences.minimumWidthForAutoSizing = 18;
                noTF.geometricBounds = [15, 15, 20.5, 33];
            }

            // 영어 본문: 기존 내용 지우고 새 내용 복제
            if (engTF) {
                engTF.contents = "";
                if (passage.engStory) {
                    try {
                        passage.engStory.texts[0].duplicate(
                            LocationOptions.AT_BEGINNING, engTF.insertionPoints[0]
                        );
                    } catch(e) { log("  [경고] 영어 복제 실패 p" + passage.page); }
                }
                // 추가 영어 스토리 (장문이 여러 페이지에 걸친 경우)
                if (passage.extraEngStories) {
                    for (var exi = 0; exi < passage.extraEngStories.length; exi++) {
                        try {
                            passage.extraEngStories[exi].texts[0].duplicate(
                                LocationOptions.AT_END, engTF.insertionPoints[-1]
                            );
                        } catch(e) {}
                    }
                }
                cleanupStory(engTF.parentStory, "english");
                deletePassageNumberDigits(engTF.parentStory);
                joinParagraphs(engTF.parentStory);
                applyStyleWithSize(engTF, stBody, sm.engSize, sm.engLead);
                // 서술형아이콘 삽입 (형광펜_노랑 위치)
                if (iconSrc) {
                    if (!csYellow) {
                        csYellow = findCharStyle(doc, "\uD615\uAD11\uD39C_\uB178\uB791");
                    }
                    if (csYellow) {
                        try {
                            var ic = insertIconsForStory(engTF.parentStory, iconSrc, csYellow, 12, -3);
                            if (ic > 0) result.iconCount = (result.iconCount || 0) + ic;
                        } catch(e) {}
                    }
                }
            }

            // 한글 해석: 기존 내용 지우고 새 내용 복제
            if (korTF) {
                korTF.contents = "";
                if (passage.korStory) {
                    try {
                        passage.korStory.texts[0].duplicate(
                            LocationOptions.AT_BEGINNING, korTF.insertionPoints[0]
                        );
                    } catch(e) { log("  [경고] 한글 복제 실패 p" + passage.page); }
                }
                // 추가 한글 스토리 (장문이 여러 페이지에 걸친 경우)
                if (passage.extraKorStories) {
                    for (var exi = 0; exi < passage.extraKorStories.length; exi++) {
                        try {
                            passage.extraKorStories[exi].texts[0].duplicate(
                                LocationOptions.AT_END, korTF.insertionPoints[-1]
                            );
                        } catch(e) {}
                    }
                }
                cleanupStory(korTF.parentStory, "korean");
                joinParagraphs(korTF.parentStory);
                applyStyleWithSize(korTF, stBody, sm.korSize, sm.korLead);
            }

            // 삽화 재연결: 기존 프레임의 링크를 새 파일로 relink
            if (illustRect && illustFile) {
                try {
                    var lnk = illustRect.allGraphics[0].itemLink;
                    lnk.relink(illustFile);
                    lnk.update();
                    result.illustPlaced = true;
                } catch(e) {}
            }

            // 삽화 없는 모의고사: 왼쪽만 G-마스터, 오른쪽은 C-마스터 유지
            if (noIllustMockexam && leftPage) {
                var gMaster = masters["G-\uB9C8\uC2A4\uD130"];
                if (gMaster) {
                    try { leftPage.appliedMaster = gMaster; } catch(e) {}
                }
                // 오른쪽 페이지 C-마스터 복원 (스프레드 마스터 적용 시 양쪽 변경되므로)
                var rpNoIll = null;
                for (var rni = 0; rni < newSpread.pages.length; rni++) {
                    if (newSpread.pages[rni].side != 1818653800) { rpNoIll = newSpread.pages[rni]; break; }
                }
                if (rpNoIll) {
                    var cMaster = masters["C-\uB9C8\uC2A4\uD130"];
                    if (cMaster) {
                        try { rpNoIll.appliedMaster = cMaster; } catch(e) {}
                    }
                }
                // 삽화 프레임 제거
                if (illustRect) {
                    try { illustRect.remove(); } catch(e) {}
                }
                // 짤지문과 동일한 프레임 크기로 조정 (왼쪽만)
                if (engTF) engTF.geometricBounds = [24, 15, 155, 130];
                if (korTF) korTF.geometricBounds = [162.5, 15, 195, 130];
            }

            // 오버플로우 해소
            if (engTF && korTF && (engTF.overflows || korTF.overflows)) {
                var korGb = korTF.geometricBounds;
                resolveOverflow(engTF, korTF, korGb[2]);
            }

            // 오른쪽 페이지: 로컬 프레임 내용만 비우고, topic은 로컬 프레임에 삽입
            var rightPage = null;
            for (var rp = 0; rp < newSpread.pages.length; rp++) {
                if (newSpread.pages[rp].side != 1818653800) { rightPage = newSpread.pages[rp]; break; }
            }
            if (rightPage) {
                var rtfs = rightPage.textFrames.everyItem().getElements();
                var topicFrame = null;
                for (var rti = 0; rti < rtfs.length; rti++) {
                    // 마스터 아이템은 건드리지 않음
                    var isLocalItem = true;
                    try {
                        var rpp = rtfs[rti].parentPage;
                        if (rpp && rpp.parent && rpp.parent.constructor.name === "MasterSpread") isLocalItem = false;
                    } catch(e) {}
                    if (!isLocalItem) continue;

                    // topic 프레임 식별: 로컬 프레임 중 top ~59-60, left ~27-28 (페이지 좌표 기준)
                    var rtgb = rtfs[rti].geometricBounds;
                    if (rtgb[0] > 55 && rtgb[0] < 70 && rtgb[1] > 20 && rtgb[1] < 40) {
                        topicFrame = rtfs[rti];
                    }
                    // 모든 로컬 프레임 내용 비우기
                    rtfs[rti].contents = "";
                }

                // topic 텍스트 삽입 (원본 로컬 프레임 사용, 마스터 override 없음)
                if (topicFrame && passage.topic) {
                    // 탭 제거, 주제/요약문 사이 엔터 삽입
                    var topicText = passage.topic;
                    topicText = topicText.replace(/\t/g, "");
                    // 연속 공백 4개 이상 -> 엔터로 분리 (주제와 요약문 구분)
                    topicText = topicText.replace(/ {4,}/g, "\r");
                    // 앞뒤 공백/엔터 정리
                    topicText = topicText.replace(/^\s+/, "").replace(/\s+$/, "");
                    topicFrame.contents = topicText;
                    // 단락스타일: 주제/요약문
                    var stTopicSummary = findPStyle(doc, "\uC8FC\uC81C/\uC694\uC57D\uBB38");
                    if (stTopicSummary) {
                        try { topicFrame.paragraphs.everyItem().appliedParagraphStyle = stTopicSummary; } catch(e) {}
                    }
                    if (topicFrame.overflows) {
                        var tc = topicFrame.contents;
                        while (topicFrame.overflows && tc.length > 20) {
                            tc = tc.substring(0, tc.length - 5);
                            topicFrame.contents = tc;
                        }
                    }
                }
            }

            return result;
        }

        // ── 폴백: A/E-마스터 -- G-마스터 스프레드 복제 후 마스터 변경 + 프레임 리사이즈 ──
        var gKey = "G-\uB9C8\uC2A4\uD130";
        var gStampIdx = templateSpreads[gKey];
        if (gStampIdx !== undefined && refDoc && refDoc.isValid) {
            // G-마스터 스프레드 복제
            refDoc.spreads[gStampIdx].duplicate(LocationOptions.AFTER, doc.spreads[-1]);
            var newSpread = doc.spreads[-1];

            // 마스터를 A/E로 변경
            var master = masters[masterName];
            if (master) {
                try {
                    for (var sp = 0; sp < newSpread.pages.length; sp++) {
                        newSpread.pages[sp].appliedMaster = master;
                    }
                } catch(e) {}
            }

            var leftPage = null;
            for (var sp = 0; sp < newSpread.pages.length; sp++) {
                if (newSpread.pages[sp].side == 1818653800) { leftPage = newSpread.pages[sp]; break; }
            }
            if (!leftPage) leftPage = newSpread.pages[0];

            // 프레임 찾기 (G-마스터 복제본의 로컬 프레임)
            var tfs = leftPage.textFrames.everyItem().getElements();
            var engTF = null, korTF = null, noTF = null, catTF = null;
            for (var fi = 0; fi < tfs.length; fi++) {
                var fgb = tfs[fi].geometricBounds;
                var fh = fgb[2] - fgb[0];
                var fw = fgb[3] - fgb[1];
                if (fgb[0] < 0) { catTF = tfs[fi]; continue; }
                if (fh < 10 && fw < 25 && fgb[0] < 22) { noTF = tfs[fi]; continue; }
                if (fgb[0] >= 20 && fgb[0] <= 30 && fgb[1] < 20 && fh > 50) { engTF = tfs[fi]; continue; }
                if (fgb[0] > 100 && fh > 20) { korTF = tfs[fi]; continue; }
            }

            // eng/kor 프레임을 A/E-마스터 크기로 리사이즈
            var engBounds, korBounds;
            if (masterName.indexOf("E") === 0) {
                engBounds = [24, 15, 155, 130];
                korBounds = [162, 15, 195, 130];
            } else {
                engBounds = [24, 15, 151, 130];
                korBounds = [159, 15, 202, 130];
            }
            if (engTF) { engTF.geometricBounds = engBounds; }
            if (korTF) { korTF.geometricBounds = korBounds; }

            // 카테고리 내용 교체
            if (catTF && displayCat) { catTF.contents = displayCat; }

            // 지문번호 내용 교체
            if (noTF) {
                noTF.textFramePreferences.autoSizingType = AutoSizingTypeEnum.OFF;
                noTF.contents = passageNo;
                noTF.textFramePreferences.autoSizingType = AutoSizingTypeEnum.WIDTH_ONLY;
                noTF.textFramePreferences.autoSizingReferencePoint = AutoSizingReferenceEnum.LEFT_CENTER_POINT;
                noTF.textFramePreferences.useMinimumWidthForAutoSizing = true;
                noTF.textFramePreferences.minimumWidthForAutoSizing = 18;
                noTF.geometricBounds = [15, 15, 20.5, 33];
            }

            // 영어 본문
            if (engTF) {
                engTF.contents = "";
                if (passage.engStory) {
                    try { passage.engStory.texts[0].duplicate(LocationOptions.AT_BEGINNING, engTF.insertionPoints[0]); } catch(e) { log("  [경고] 영어 복제 실패 p" + passage.page); }
                }
                if (passage.extraEngStories) {
                    for (var exi = 0; exi < passage.extraEngStories.length; exi++) {
                        try { passage.extraEngStories[exi].texts[0].duplicate(LocationOptions.AT_END, engTF.insertionPoints[-1]); } catch(e) {}
                    }
                }
                cleanupStory(engTF.parentStory, "english");
                deletePassageNumberDigits(engTF.parentStory);
                joinParagraphs(engTF.parentStory);
                applyStyleWithSize(engTF, stBody, sm.engSize, sm.engLead);
                if (iconSrc && csYellow) {
                    try {
                        var ic2 = insertIconsForStory(engTF.parentStory, iconSrc, csYellow, 12, -3);
                        if (ic2 > 0) result.iconCount = (result.iconCount || 0) + ic2;
                    } catch(e) {}
                }
            }

            // 한글 해석
            if (korTF) {
                korTF.contents = "";
                if (passage.korStory) {
                    try { passage.korStory.texts[0].duplicate(LocationOptions.AT_BEGINNING, korTF.insertionPoints[0]); } catch(e) { log("  [경고] 한글 복제 실패 p" + passage.page); }
                }
                if (passage.extraKorStories) {
                    for (var exi = 0; exi < passage.extraKorStories.length; exi++) {
                        try { passage.extraKorStories[exi].texts[0].duplicate(LocationOptions.AT_END, korTF.insertionPoints[-1]); } catch(e) {}
                    }
                }
                cleanupStory(korTF.parentStory, "korean");
                joinParagraphs(korTF.parentStory);
                applyStyleWithSize(korTF, stBody, sm.korSize, sm.korLead);
            }

            if (engTF && korTF && (engTF.overflows || korTF.overflows)) {
                resolveOverflow(engTF, korTF, korBounds[2]);
            }

            // 오른쪽 페이지: 로컬 프레임 내용 비우기 + topic 삽입
            var rightPage = null;
            for (var rp = 0; rp < newSpread.pages.length; rp++) {
                if (newSpread.pages[rp].side != 1818653800) { rightPage = newSpread.pages[rp]; break; }
            }
            if (rightPage) {
                var rtfs = rightPage.textFrames.everyItem().getElements();
                var topicFrame = null;
                for (var rti = 0; rti < rtfs.length; rti++) {
                    var isLocal = true;
                    try { var rpp = rtfs[rti].parentPage; if (rpp && rpp.parent && rpp.parent.constructor.name === "MasterSpread") isLocal = false; } catch(e) {}
                    if (!isLocal) continue;
                    var rtgb = rtfs[rti].geometricBounds;
                    if (rtgb[0] > 55 && rtgb[0] < 70 && rtgb[1] > 20 && rtgb[1] < 40) {
                        topicFrame = rtfs[rti];
                    }
                    rtfs[rti].contents = "";
                }
                if (topicFrame && passage.topic) {
                    var topicText2 = passage.topic;
                    topicText2 = topicText2.replace(/\t/g, "").replace(/ {4,}/g, "\r").replace(/^\s+/, "").replace(/\s+$/, "");
                    topicFrame.contents = topicText2;
                    var stTS2 = findPStyle(doc, "\uC8FC\uC81C/\uC694\uC57D\uBB38");
                    if (stTS2) { try { topicFrame.paragraphs.everyItem().appliedParagraphStyle = stTS2; } catch(e) {} }
                }
            }

            return result;
        }

        // 최종 폴백: refDoc도 없는 경우 (실행 불가 상황)
        log("  [경고] 템플릿 스프레드 복제 불가: " + masterName);
        return result;
    }

    // ════════════════════════════════════════════════════════════════════
    // 분석본에서 지문 추출 -- 영어/한글 스토리 쌍 (서식 유지)
    // ════════════════════════════════════════════════════════════════════
    function extractPassages(analDoc, sourceType, fileCategory) {
        function isMasterPage(pg) {
            try { return pg.parent.constructor.name === "MasterSpread"; } catch(e) { return false; }
        }
        function countKorean(text) {
            var cnt = 0;
            var len = Math.min(text.length, 500);
            for (var i = 0; i < len; i++) {
                var c = text.charCodeAt(i);
                if ((c >= 0xAC00 && c <= 0xD7AF) || (c >= 0x1100 && c <= 0x11FF)) cnt++;
            }
            return cnt;
        }

        // 페이지별 본문 스토리 수집
        var pageMap = {};
        var stories = analDoc.stories.everyItem().getElements();
        for (var s = 0; s < stories.length; s++) {
            var st = stories[s];
            try {
                if (!st || !st.isValid || st.characters.length < 30) continue;
                var tc = st.textContainers[0];
                if (!tc || !tc.parentPage || isMasterPage(tc.parentPage)) continue;

                var pg = tc.parentPage;
                var gb = tc.geometricBounds;
                // 어법해설 프레임 제외 (left > 100)
                // 오른쪽 페이지: gb는 페이지 내부 좌표일 수 있으므로 page.bounds 보정
                var frameLeft = gb[1];
                var pgLeft = pg.bounds[1]; // 스프레드 좌표계에서 페이지 시작
                if (pgLeft > 0 && frameLeft > pgLeft) {
                    // gb가 스프레드 좌표인 경우: 페이지 기준으로 보정
                    frameLeft = frameLeft - pgLeft;
                }
                if (frameLeft > 100) continue;

                // 단락스타일 중 "본문" 포함 여부 확인
                var hasBodyStyle = false;
                try {
                    var paras = st.paragraphs.everyItem().getElements();
                    for (var pi = 0; pi < paras.length && !hasBodyStyle; pi++) {
                        var psName = "";
                        try { psName = paras[pi].appliedParagraphStyle.name; } catch(e2) {}
                        if (psName.indexOf("\uBCF8\uBB38") >= 0 || psName.indexOf("\u1107\u1169\u11AB\u1106\u116E\u11AB") >= 0) {
                            hasBodyStyle = true;
                        }
                    }
                } catch(e) {}

                var pgName = pg.name;
                if (!pageMap[pgName]) pageMap[pgName] = { items: [], side: pg.side, hasBodyStyle: false };
                if (hasBodyStyle) pageMap[pgName].hasBodyStyle = true;
                pageMap[pgName].items.push({
                    story: st,
                    top: gb[0],
                    korCount: countKorean(st.contents.substring(0, 500)),
                    chars: st.characters.length
                });
            } catch(e) { continue; }
        }

        var passages = [];
        for (var pgName in pageMap) {
            var entry = pageMap[pgName];
            var items = entry.items;
            var pgSide = entry.side;

            // 오른쪽 페이지: 본문 단락스타일이 없으면 주제/요약문 전용 → 스킵
            if (pgSide != 1818653800 && !entry.hasBodyStyle) continue;

            // 페이지 내 이미지(링크된 그래픽) 수집 — 짤지문 조판 시 사용
            // filePath를 문자열로 저장 (analDoc 닫힌 후에도 유효)
            var pageImages = [];
            try {
                var thePg = analDoc.pages.itemByName(pgName);
                if (thePg.isValid) {
                    var allPgItems = thePg.allPageItems;
                    for (var aii = 0; aii < allPgItems.length; aii++) {
                        try {
                            var pi = allPgItems[aii];
                            if (pi.allGraphics && pi.allGraphics.length > 0) {
                                var gr = pi.allGraphics[0];
                                if (gr.itemLink && gr.itemLink.status == LinkStatus.NORMAL) {
                                    pageImages.push({
                                        filePath: gr.itemLink.filePath,
                                        bounds: pi.geometricBounds.slice(0)
                                    });
                                }
                            }
                        } catch(e) {}
                    }
                }
            } catch(e) {}

            if (items.length >= 2) {
                items.sort(function(a, b) { return a.top - b.top; });
                var engItem = items[0];
                var korItem = items[1];
                if (engItem.korCount > korItem.korCount) {
                    var tmp = engItem; engItem = korItem; korItem = tmp;
                }
                passages.push({
                    page: pgName,
                    engStory: engItem.story,
                    korStory: korItem.story,
                    passageNo: "",
                    type: "separate",
                    isRightPage: pgSide != 1818653800,
                    pageImages: pageImages
                });

            } else if (items.length === 1) {
                // 혼합 스토리: 분리하지 않고 그대로 전달 (성능)
                // createNewSpread에서 cleanupStory("english"/"korean")로 분리
                var mixedStory = items[0].story;
                passages.push({
                    page: pgName,
                    engStory: mixedStory,
                    korStory: mixedStory,
                    passageNo: "",
                    type: "mixed",
                    isRightPage: pgSide != 1818653800,
                    pageImages: pageImages
                });
            }
        }

        passages.sort(function(a, b) { return parseInt(a.page) - parseInt(b.page); });

        // EBS: 커버 페이지에서 지문 라벨 추출
        var coverLabels = [];
        if (sourceType === "ebs") {
            try {
                var coverPage = analDoc.pages[0];
                var coverTFs = coverPage.textFrames.everyItem().getElements();
                var labelTexts = [];
                for (var cli = 0; cli < coverTFs.length; cli++) {
                    var ctf = coverTFs[cli];
                    var cgb = ctf.geometricBounds;
                    var ctxt = ctf.contents.replace(/[\r\n]/g, "").replace(/^\s+|\s+$/g, "");
                    if (ctxt.length > 3 && ctxt.length < 50 && cgb[0] > 5 && cgb[1] > 30) {
                        var hasLecture = ctxt.match(/(\d+)\uAC15/) || ctxt.match(/(\d+)\u1100\u1161\u11BC/);
                        if (hasLecture) {
                            labelTexts.push(ctxt);
                        }
                    }
                }
                labelTexts.reverse();
                for (var li = 0; li < labelTexts.length; li++) {
                    var lt = labelTexts[li];
                    var lecMatch = lt.match(/(\d+)\uAC15/) || lt.match(/(\d+)\u1100\u1161\u11BC/);
                    var lecNum = lecMatch ? lecMatch[1] : "";
                    var label = lecNum + "\uAC15 ";
                    if (lt.indexOf("\uBD84\uC11D") >= 0 || lt.indexOf("\u1107\u116E\u11AB\u1109\u1165\u11A8") >= 0) {
                        label += "\uBD84\uC11D";
                    } else if (lt.indexOf("\uC11C\uC220") >= 0) {
                        label += "\uC11C\uC220\uD615";
                    } else if (lt.indexOf("\uB17C\uC220") >= 0) {
                        label += "\uB17C\uC220\uD615";
                    } else {
                        var numMatch = lt.match(/(\d+)\uBC88/) || lt.match(/(\d+)\u1107\u1165\u11AB/);
                        if (numMatch) {
                            var n = parseInt(numMatch[1]);
                            label += (n < 10 ? "0" + n : String(n));
                        }
                    }
                    coverLabels.push(label);
                }
            } catch(e) {}
        }

        // 문자스타일에서 텍스트 추출 (로컬 프레임 우선, 마스터 프레임 폴백)
        function extractCharStyleText(theDoc, pageTFList, styleName, styleNFD) {
            var cs = findCharStyle(theDoc, styleName);
            if (!cs) cs = findCharStyle(theDoc, styleNFD);
            if (!cs) return "";
            var localResult = "";
            var masterResult = "";
            for (var cti2 = 0; cti2 < pageTFList.length; cti2++) {
                var isMaster = pageTFList[cti2].geometricBounds[0] < 0;
                try {
                    var chars2 = pageTFList[cti2].characters.everyItem().getElements();
                    for (var chi2 = 0; chi2 < chars2.length; chi2++) {
                        if (chars2[chi2].appliedCharacterStyle === cs) {
                            var buf2 = "";
                            for (var chj2 = chi2; chj2 < chars2.length; chj2++) {
                                if (chars2[chj2].appliedCharacterStyle === cs) {
                                    buf2 += chars2[chj2].contents;
                                } else { break; }
                            }
                            var cleaned = buf2.replace(/[\r\n]/g, "").replace(/^\s+|\s+$/g, "");
                            // 실제 챕터 라벨은 한글/영문을 포함한다("18강 장문Ⅱ", "L1 본문", "고2 9월").
                            // 앵커 객체(￼)만 든 로컬 프레임은 객체 ID(예 1397781622)가 잡혀
                            // 마스터의 진짜 라벨을 덮어쓰므로, 글자 없는 값은 무시한다.
                            if (cleaned && /[A-Za-z가-힣]/.test(cleaned)) {
                                if (!isMaster) { localResult = cleaned; break; }
                                else if (!masterResult) masterResult = cleaned;
                            }
                            chi2 = chj2;
                        }
                    }
                } catch(e) {}
                if (localResult) break;
            }
            return localResult || masterResult;
        }

        // 지문번호 추출 + 주제 추출
        var _origLen = passages.length; // 루프 중 push 방지: 원본 길이만 순회
        for (var i = 0; i < _origLen; i++) {
            var pgName = passages[i].page;

            try {
                var thePage = analDoc.pages.itemByName(pgName);
                if (thePage.isValid) {
                    var pageTFs = thePage.textFrames.everyItem().getElements();
                    var shortLabel = "";
                    var longLabel = "";
                    var subLabel = "";  // 짤지문 보조 라벨
                    for (var pti = 0; pti < pageTFs.length; pti++) {
                        var ptf = pageTFs[pti];
                        var ptgb = ptf.geometricBounds;
                        if (ptgb[0] < 5 && ptf.characters.length >= 2 && ptf.characters.length <= 30) {
                            var txt = ptf.contents.replace(/[\r\n]/g, "").replace(/^\s+|\s+$/g, "");
                            if (ptgb[1] < 50 && ptgb[3] < 50) {
                                shortLabel = txt;
                            } else if (ptgb[1] > 30) {
                                longLabel = txt;
                            }
                        }
                        // 짤지문 보조 라벨: top 10~20, left > 30, "년"/"월" 포함
                        if (ptgb[0] >= 5 && ptgb[0] < 25 && ptgb[1] > 30 && ptf.characters.length >= 5 && ptf.characters.length <= 30) {
                            var stxt = ptf.contents.replace(/[\r\n]/g, "").replace(/^\s+|\s+$/g, "");
                            if (stxt.indexOf("\uB144") >= 0 || stxt.indexOf("\u1102\u1167\u11AB") >= 0) {
                                subLabel = stxt;
                            }
                        }
                    }

                    // [혼합] 분석본에 교과서·모의고사가 섞여 있으면 지문별 챕터 라벨로 판정.
                    // 라벨에 "년"+"월"이 함께 있으면 모의고사, 없으면 교과서.
                    var effType = sourceType;
                    if (sourceType === "mixed") {
                        var probeLbl = extractCharStyleText(analDoc, pageTFs,
                            "\uCC55\uD130", "\u110E\u1162\u11B8\u1110\u1165");
                        var probe = probeLbl || subLabel || longLabel || shortLabel || "";
                        var eHasYear = (probe.indexOf("\uB144") >= 0) || (probe.indexOf("\u1102\u1167\u11AB") >= 0);
                        var eHasMonth = (probe.indexOf("\uC6D4") >= 0) || (probe.indexOf("\u110B\u116F\u11AF") >= 0);
                        effType = (eHasYear && eHasMonth) ? "mockexam" : "textbook";
                    }
                    passages[i].sourceType = effType;

                    if (effType === "mockexam") {
                        // 챕터 스타일에서 추출 우선 시도 (예: "고2 21년 9월 43~45번")
                        var chapMock = extractCharStyleText(analDoc, pageTFs,
                            "\uCC55\uD130", "\u110E\u1162\u11B8\u1110\u1165");

                        var primaryLabel = "";
                        var fallbackLabel = "";

                        // 챕터 스타일 텍스트에서 YYMM+QQ 추출
                        var mockSrc = chapMock || subLabel || longLabel || shortLabel || "";
                        if (mockSrc) {
                            var sym = mockSrc.match(/(\d+)\uB144\s*(\d+)\uC6D4/);
                            if (!sym) sym = mockSrc.match(/(\d+)\u1102\u1167\u11AB\s*(\d+)\u110B\u116F\u11AF/);
                            // "43~45번" → 첫 번호 43 추출, "18번" → 18
                            var sqn = mockSrc.match(/(\d+)[~\-]?\d*\uBC88/);
                            if (!sqn) sqn = mockSrc.match(/(\d+)[~\-]?\d*\u1107\u1165\u11AB/);
                            if (sym && sqn) {
                                var syy = sym[1].length === 4 ? sym[1].substring(2) : sym[1];
                                var smm = sym[2].length === 1 ? "0" + sym[2] : sym[2];
                                var sqq = sqn[1].length === 1 ? "0" + sqn[1] : sqn[1];
                                primaryLabel = syy + smm + sqq;
                            }
                        }

                        // 폴백: subLabel 별도 / longLabel/shortLabel 별도
                        if (!primaryLabel && subLabel) {
                            var sym2 = subLabel.match(/(\d+)\uB144\s*(\d+)\uC6D4/);
                            if (!sym2) sym2 = subLabel.match(/(\d+)\u1102\u1167\u11AB\s*(\d+)\u110B\u116F\u11AF/);
                            var sqn2 = subLabel.match(/(\d+)[~\-]?\d*\uBC88/);
                            if (!sqn2) sqn2 = subLabel.match(/(\d+)[~\-]?\d*\u1107\u1165\u11AB/);
                            if (sym2 && sqn2) {
                                var syy2 = sym2[1].length === 4 ? sym2[1].substring(2) : sym2[1];
                                var smm2 = sym2[2].length === 1 ? "0" + sym2[2] : sym2[2];
                                var sqq2 = sqn2[1].length === 1 ? "0" + sqn2[1] : sqn2[1];
                                primaryLabel = syy2 + smm2 + sqq2;
                            }
                        }
                        if (!primaryLabel) {
                            var mockLabel = longLabel || shortLabel || "";
                            if (mockLabel) {
                                var ym = mockLabel.match(/(\d+)\uB144\s*(\d+)\uC6D4/);
                                if (!ym) ym = mockLabel.match(/(\d+)\u1102\u1167\u11AB\s*(\d+)\u110B\u116F\u11AF/);
                                var qn = mockLabel.match(/(\d+)[~\-]?\d*\uBC88/);
                                if (!qn) qn = mockLabel.match(/(\d+)[~\-]?\d*\u1107\u1165\u11AB/);
                                if (ym && qn) {
                                    var yy = ym[1].length === 4 ? ym[1].substring(2) : ym[1];
                                    var mm = ym[2].length === 1 ? "0" + ym[2] : ym[2];
                                    var qq = qn[1].length === 1 ? "0" + qn[1] : qn[1];
                                    fallbackLabel = yy + mm + qq;
                                } else {
                                    var digits = mockLabel.replace(/[^\d]/g, "");
                                    if (digits.length >= 6) fallbackLabel = digits.substring(0, 6);
                                    else if (digits.length >= 4) fallbackLabel = digits;
                                }
                            }
                        }

                        passages[i].passageNo = primaryLabel || fallbackLabel;

                        // 짤지문: subLabel과 longLabel 모두 유효하고 다르면 별도 passage
                        if (primaryLabel && fallbackLabel && primaryLabel !== fallbackLabel) {
                            passages.push({
                                page: pgName,
                                engStory: passages[i].engStory,
                                korStory: passages[i].korStory,
                                passageNo: fallbackLabel,
                                topic: "",
                                type: passages[i].type,
                                sourceType: effType,
                                isSubPassage: true
                            });
                        }
                    } else if (effType === "textbook" || effType === "ebs") {
                        // 교과서/EBS/리딩파워/올림포스 모두: 챕터 스타일에서 추출
                        var chapLabel = extractCharStyleText(analDoc, pageTFs,
                            "\uCC55\uD130", "\u110E\u1162\u11B8\u1110\u1165", false);

                        // [리딩파워] 지문 라벨은 "챕터"(유형 헤더: 어법/어휘/장문)가 아니라
                        // "챕터_숫자"(Unit N XX)에 있다. 유형 헤더가 "어법 (1)"처럼 숫자를 포함하면
                        // 아래 숫자 검증을 통과해 잘못 라벨이 된다. 올림포스는 canon 매칭 위해 미관여.
                        if (fileCategory && (fileCategory.indexOf("\uB9AC\uB529\uD30C\uC6CC") >= 0 || fileCategory.indexOf("\uB9AC\uD30C") >= 0)) {
                            var numLabel = extractCharStyleText(analDoc, pageTFs,
                                "\uCC55\uD130\u005F\uC22B\uC790", "\u110E\u1162\u11B8\u1110\u1165\u005F\u1109\u116E\u11BA\u110C\u1161", false);
                            if (numLabel && numLabel.length <= 50 && /\d/.test(numLabel)) chapLabel = numLabel;
                        }

                        // 챕터 라벨 유효성 검증: 50자 이하이고 숫자 포함
                        // 미래엔 DL(딥러닝 장문): 페이지에 "N과 DL" 마커가 있으면 그것을
                        // 지문번호로 사용. 분석본 챕터 라벨이 본문과 다른 엉뚱한 값일 수
                        // 있어, DL 마커를 우선해야 미래엔 완성본 "N과 DL"과 매칭/복사된다.
                        var dlNum = "";
                        for (var dti = 0; dti < pageTFs.length; dti++) {
                            try {
                                var dtxt = String(pageTFs[dti].contents).replace(/\s/g, "");
                                var dlm = dtxt.match(/(\d+)과DL/); // "3과DL"
                                if (dlm) { dlNum = dlm[1]; break; }
                            } catch(e) {}
                        }
                        if (dlNum) {
                            passages[i].passageNo = dlNum + "과 DL";
                            passages[i].isDL = true;
                        } else if (chapLabel && chapLabel.length <= 50 && /\d/.test(chapLabel)) {
                            passages[i].passageNo = chapLabel;
                        } else if (shortLabel) {
                            // 폴백: 기존 위치 기반 shortLabel
                            var nfcBonmun = "\uBCF8\uBB38";
                            var nfdBonmun = "\u1107\u1169\u11AB\u1106\u116E\u11AB";
                            var bmIdx = shortLabel.indexOf(nfcBonmun);
                            if (bmIdx < 0) bmIdx = shortLabel.indexOf(nfdBonmun);
                            if (bmIdx >= 0) {
                                var afterBm = shortLabel.substring(bmIdx).replace(/[^\d]/g, "");
                                var prefix = shortLabel.substring(0, bmIdx);
                                if (afterBm.length > 0) {
                                    var num = parseInt(afterBm);
                                    shortLabel = prefix + (num < 10 ? "0" + num : String(num));
                                }
                            }
                            passages[i].passageNo = shortLabel;
                        }
                    }
                }
            } catch(e) {}

            // EBS: 커버 라벨에서 지문번호
            if (!passages[i].passageNo && coverLabels.length > 0 && i < coverLabels.length) {
                passages[i].passageNo = coverLabels[i];
            }
            if (!passages[i].passageNo) {
                var seqNo = i + 1;
                passages[i].passageNo = (seqNo < 10 ? "0" : "") + seqNo;
            }

            // 오른쪽 페이지에서 주제 요약문 추출 (왼쪽 페이지 지문만)
            if (passages[i].isRightPage) continue;
            var nextPg = String(parseInt(pgName) + 1);
            try {
                var nextPage = analDoc.pages.itemByName(nextPg);
                if (nextPage.isValid) {
                    var nextTFs = nextPage.textFrames.everyItem().getElements();
                    for (var nti = 0; nti < nextTFs.length; nti++) {
                        var ntf = nextTFs[nti];
                        var ntgb = ntf.geometricBounds;
                        if (ntgb[0] < 45 && ntgb[2] < 50 && ntf.characters.length >= 20 && ntf.characters.length < 500) {
                            // 첫 번째 \r은 유지 (주제/요약문 구분), 나머지 \r\n은 공백으로
                            var topicText = ntf.contents;
                            topicText = topicText.replace(/\uFFFC/g, "");
                            var firstCR = topicText.indexOf("\r");
                            if (firstCR >= 0) {
                                var topicPart = topicText.substring(0, firstCR).replace(/^\s+|\s+$/g, "");
                                var summaryPart = topicText.substring(firstCR + 1).replace(/[\r\n]/g, " ").replace(/^\s+|\s+$/g, "");
                                topicText = topicPart + "\r" + summaryPart;
                            }
                            topicText = topicText.replace(/^\s+|\s+$/g, "");
                            if (topicText.length > 10) {
                                passages[i].topic = topicText;
                            }
                            break;
                        }
                    }
                }
            } catch(e) {}
        }

        // 인접한 LEFT+RIGHT passage → 짤지문 쌍 (G-마스터로 양면 조판)
        for (var mi = passages.length - 1; mi > 0; mi--) {
            if (!passages[mi].isRightPage) continue;
            if (passages[mi - 1].isRightPage) continue;
            passages[mi - 1].rightPassage = passages[mi];
            passages[mi - 1].isPair = true;
            passages.splice(mi, 1);
        }

        return passages;
    }

    // ════════════════════════════════════════════════════════════════════
    // 교과서 혼합 프레임 분리 -- 영어/한글 줄을 별도 스토리로 복제
    // ════════════════════════════════════════════════════════════════════
    function splitMixedStory(analDoc, mixedStory) {
        function countKorean(text) {
            var cnt = 0;
            for (var i = 0; i < text.length; i++) {
                var c = text.charCodeAt(i);
                if ((c >= 0xAC00 && c <= 0xD7AF) || (c >= 0x1100 && c <= 0x11FF)) cnt++;
            }
            return cnt;
        }
        function isKoreanPara(para) {
            var t = para.contents;
            if (t.length < 2) return false;
            return countKorean(t) > t.length * 0.3;
        }

        var paras = mixedStory.paragraphs.everyItem().getElements();
        if (paras.length < 2) return null;

        var engTmp = analDoc.textFrames.add({ geometricBounds: [400, 0, 600, 100] });
        var korTmp = analDoc.textFrames.add({ geometricBounds: [400, 110, 600, 200] });

        for (var i = 0; i < paras.length; i++) {
            var para = paras[i];
            var t = para.contents.replace(/[\r\n]/g, "");
            if (t.replace(/\s/g, "").length < 2) continue;

            var targetTF;
            if (isKoreanPara(para)) {
                targetTF = korTmp;
            } else {
                targetTF = engTmp;
            }

            try {
                para.duplicate(LocationOptions.AT_END, targetTF.insertionPoints[-1]);
            } catch(e) { continue; }
        }

        var engStory = engTmp.parentStory;
        var korStory = korTmp.parentStory;

        if (engStory.characters.length < 10 || korStory.characters.length < 10) {
            try { engTmp.remove(); } catch(e) {}
            try { korTmp.remove(); } catch(e) {}
            return null;
        }

        return {
            engStory: engStory,
            korStory: korStory,
            engTmpFrame: engTmp,
            korTmpFrame: korTmp
        };
    }

})();
