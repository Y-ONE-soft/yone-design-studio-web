/**
 * MergeMockExam.jsx
 * 모의고사 세로버전 파일에서 문제 코드별 페이지를 추출해 PDF로 내보냅니다.
 *
 * 사용법:
 *   1. 필요한 세로버전 .indd 파일들을 선택
 *   2. 추출할 문제 코드 입력 (한 줄에 하나, 예: 210320)
 *   3. PDF 파일명 + 출력 폴더 선택 후 실행
 *
 * 코드 형식: YYMMQQ  (예: 210320 = 21년 3월 20번)
 * 섹션 감지: A마스터가 적용된 페이지 중 6자리 문제 코드가 포함된 페이지를 구간 시작점으로 인식
 *
 * 방식: page.move() 대신 InDesign 페이지 범위 PDF 내보내기 + Python CoreGraphics 결합
 *       → 페이지 순서/마스터 문제 없음, 원본 파일 수정 없음
 */

#target indesign

(function () {

    // ═══════════════════════════════════════════════════════════
    // 유틸
    // ═══════════════════════════════════════════════════════════

    function parseCode(raw) {
        var code = raw.replace(/\s/g, '');
        if (code.length !== 6 || isNaN(Number(code))) return null;
        return { raw: code };
    }

    // 문서 캐시 (동일 파일 중복 열기 방지)
    function getDoc(file, cache) {
        var key = file.absoluteURI;
        if (cache[key]) return cache[key];
        // 이미 열려 있으면 재사용, 없으면 열기
        for (var d = 0; d < app.documents.length; d++) {
            try {
                if (app.documents[d].fullName.toString() === file.toString()) {
                    cache[key] = app.documents[d];
                    return cache[key];
                }
            } catch (e) {}
        }
        var doc = app.open(file, false);
        cache[key] = doc;
        return doc;
    }

    // 문서에서 A마스터가 적용된 페이지 중 6자리 코드가 포함된 페이지를 구간 시작점으로 반환
    function findAllMarkers(doc) {
        var markers = [];
        var codePattern = /\b(\d{6})\b/;

        for (var i = 0; i < doc.pages.length; i++) {
            var page = doc.pages[i];

            // A마스터 적용 여부 확인
            try {
                var masterName = page.appliedMaster.name;
                if (!masterName || masterName.charAt(0).toUpperCase() !== 'A') continue;
            } catch (e) {
                continue;
            }

            // 페이지의 모든 아이템(그룹 포함)에서 6자리 코드 탐색
            try {
                var items = page.allPageItems;
                for (var f = 0; f < items.length; f++) {
                    try {
                        var txt = items[f].contents;
                        if (typeof txt !== 'string' || txt.length < 6) continue;
                        var match = codePattern.exec(txt);
                        if (match) {
                            markers.push({
                                code:      match[1],
                                pageIndex: i,
                                pageName:  page.name   // InDesign 표시 번호 (range 문자열용)
                            });
                            break;
                        }
                    } catch (ef) {}
                }
            } catch (e) {}
        }

        markers.sort(function (a, b) { return a.pageIndex - b.pageIndex; });
        return markers;
    }

    // 특정 코드의 페이지 범위 반환 (InDesign 표시 번호 기준 range 문자열 포함)
    function getCodeRange(markers, code, srcDoc) {
        for (var i = 0; i < markers.length; i++) {
            if (markers[i].code !== code) continue;
            var startIdx = markers[i].pageIndex;
            var endIdx   = (i < markers.length - 1)
                             ? markers[i + 1].pageIndex - 1
                             : srcDoc.pages.length - 1;
            // 끝 페이지의 표시 번호
            var endPageName = '';
            try { endPageName = srcDoc.pages[endIdx].name; } catch(e) {}
            return {
                startIdx:  startIdx,
                endIdx:    endIdx,
                rangeStr:  markers[i].pageName + '-' + endPageName
            };
        }
        return null;
    }

    // 페이지 범위를 순차 번호로 임시 재설정해서 내보낸 뒤 원복
    // ─ 전략: 원본 섹션 전체를 50000번대로 이동(음수 방지) →
    //         내보낼 구간에만 순차 번호 섹션 추가 → 내보내기 → 전부 복원
    function exportRangeWithNumber(srcDoc, range, startNum, tempPdf, preset) {
        var startIdx  = range.startIdx;
        var endIdx    = range.endIdx;
        var pageCount = endIdx - startIdx + 1;
        var BIG       = 50000;   // 원본 번호 대피용 오프셋 (실제 페이지 수보다 충분히 큼)

        // ── Phase 1: 원본 섹션 전체 저장 ─────────────────────────
        var saved = [];
        for (var s = 0; s < srcDoc.sections.length; s++) {
            try {
                saved.push({
                    sec:    srcDoc.sections[s],
                    num:    srcDoc.sections[s].pageNumberStart,
                    isCont: srcDoc.sections[s].continueNumbering,
                    pfx:    srcDoc.sections[s].sectionPrefix
                });
            } catch(e) {}
        }

        // ── Phase 2: continueNumbering=false 섹션을 BIG번대로 대피 ─
        for (var s2 = 0; s2 < saved.length; s2++) {
            if (!saved[s2].isCont) {
                try {
                    saved[s2].sec.pageNumberStart = saved[s2].num + BIG;
                    saved[s2].sec.sectionPrefix   = '';
                } catch(e) {}
            }
        }

        // ── Phase 3: 내보낼 구간에 순차 번호 섹션 삽입 ───────────
        var secStart = null, secAfter = null;
        try {
            secStart = srcDoc.sections.add(srcDoc.pages[startIdx]);
            secStart.continueNumbering = false;
            secStart.pageNumberStart   = startNum;
            secStart.sectionPrefix     = '';
        } catch(eAdd) {}

        // 구간 직후 페이지에 원래 번호(BIG 대피 상태) 고정 섹션 추가
        // → 구간 이후 페이지들이 순차 번호를 이어받지 않도록 차단
        var afterIdx = endIdx + 1;
        if (afterIdx < srcDoc.pages.length) {
            // afterIdx 에 원래 있던 번호 = 저장된 섹션 중 afterIdx 를 담당하는 섹션의 원래 번호
            var afterOrigDisplay = parseInt(srcDoc.pages[afterIdx].name, 10);
            // 현재는 BIG 대피 상태이므로 원래 번호 = 현재 name - BIG (대략)
            // 더 정확하게: 원래 저장해둔 섹션에서 afterIdx가 속한 섹션의 origNum 참조
            var afterBigNum = afterOrigDisplay; // 이미 BIG 대피된 번호 그대로 사용
            try {
                secAfter = srcDoc.sections.add(srcDoc.pages[afterIdx]);
                secAfter.continueNumbering = false;
                secAfter.pageNumberStart   = afterBigNum;
                secAfter.sectionPrefix     = '';
            } catch(eAdd2) {}
        }

        // ── Phase 4: 내보내기 ─────────────────────────────────────
        var newRange = startNum + '-' + (startNum + pageCount - 1);
        app.pdfExportPreferences.pageRange = newRange;

        try {
            if (preset && preset.isValid) {
                srcDoc.exportFile(ExportFormat.PDF_TYPE, tempPdf, false, preset);
            } else {
                srcDoc.exportFile(ExportFormat.PDF_TYPE, tempPdf, false);
            }
            return tempPdf.exists;
        } catch (eExp) {
            throw eExp;
        } finally {
            // ── Phase 5: 임시 섹션 제거 & 원본 복원 ──────────────
            if (secAfter) { try { secAfter.remove(); } catch(er) {} }
            if (secStart) { try { secStart.remove(); } catch(er) {} }
            for (var s3 = 0; s3 < saved.length; s3++) {
                try {
                    saved[s3].sec.pageNumberStart = saved[s3].num;
                    saved[s3].sec.sectionPrefix   = saved[s3].pfx;
                } catch(er) {}
            }
        }
    }

    // 코드별 페이지를 결합한 .indd 파일 저장
    // ─ 전략: 첫 코드 srcDoc을 saveACopy로 베이스 사본 생성
    //         → 사본에서 첫 코드 범위 외 페이지 삭제
    //         → 나머지 코드들의 페이지를 page.duplicate로 끝에 추가
    function saveAsIndd(codes, codeFileMap, markersCache, outFolder, pdfName) {
        var validCodes = [];
        for (var ci = 0; ci < codes.length; ci++) {
            if (codeFileMap[codes[ci].raw]) validCodes.push(codes[ci].raw);
        }
        if (validCodes.length === 0) return { ok: false, error: '유효한 코드 없음' };

        var inddFile  = new File(outFolder.absoluteURI + '/' + pdfName + '.indd');
        var firstCode = validCodes[0];
        var firstSrc  = codeFileMap[firstCode].doc;
        var firstUri  = codeFileMap[firstCode].uri;
        var firstRng  = getCodeRange(markersCache[firstUri], firstCode, firstSrc);
        if (!firstRng) return { ok: false, error: '첫 코드 페이지 범위 계산 실패' };

        // saveACopy로 사본 .indd 생성 (firstSrc 본체는 변경 없음)
        firstSrc.saveACopy(inddFile);

        // 사본 열기 (UI 창 표시 안 함)
        var newDoc = app.open(inddFile, false);

        try {
            // 첫 코드 범위 외 페이지 삭제 (끝에서부터, 인덱스 변동 방지)
            for (var p = newDoc.pages.length - 1; p >= 0; p--) {
                if (p < firstRng.startIdx || p > firstRng.endIdx) {
                    try { newDoc.pages[p].remove(); } catch (er) {}
                }
            }

            // 나머지 코드들의 페이지를 newDoc 끝에 복제
            for (var ci2 = 1; ci2 < validCodes.length; ci2++) {
                var c    = validCodes[ci2];
                var sd   = codeFileMap[c].doc;
                var sUri = codeFileMap[c].uri;
                var rg   = getCodeRange(markersCache[sUri], c, sd);
                if (!rg) continue;

                for (var p2 = rg.startIdx; p2 <= rg.endIdx; p2++) {
                    try {
                        sd.pages[p2].duplicate(
                            LocationOptions.AT_END,
                            newDoc.pages.lastItem()
                        );
                    } catch (eDup) {}
                }
            }

            newDoc.save();
            return { ok: true, path: inddFile.fsName };
        } finally {
            try { newDoc.close(SaveOptions.NO); } catch (eClose) {}
        }
    }

    // ═══════════════════════════════════════════════════════════
    // 다이얼로그
    // ═══════════════════════════════════════════════════════════

    var dlg = new Window('dialog', '모의고사 세로버전 추출  ›  PDF 내보내기');
    dlg.orientation = 'column';
    dlg.alignChildren = 'fill';
    dlg.margins = [16, 16, 16, 16];
    dlg.spacing = 10;

    // 파일 목록
    dlg.add('statictext', undefined, '세로버전 .indd 파일 선택 (여러 개 가능):');

    var grpFiles = dlg.add('group');
    grpFiles.orientation = 'row';
    grpFiles.alignChildren = ['left', 'top'];
    grpFiles.spacing = 8;

    var fileList = grpFiles.add('listbox', [0, 0, 310, 120]);
    var files = [];

    var grpCtrl = grpFiles.add('group');
    grpCtrl.orientation = 'column';
    grpCtrl.alignChildren = 'fill';
    grpCtrl.spacing = 5;

    var btnAdd    = grpCtrl.add('button', undefined, '추가');
    var btnRemove = grpCtrl.add('button', undefined, '제거');

    btnAdd.onClick = function () {
        // macOS 호환: filter는 함수로 (문자열 필터는 macOS에서 multiSelect 무시될 수 있음)
        var inddFilter = function (f) {
            return (f instanceof Folder) || /\.indd$/i.test(f.name);
        };
        var sel = File.openDialog(
            '세로버전 파일 선택 (Cmd/Shift 클릭으로 여러 개)',
            inddFilter,
            true
        );
        if (!sel) return;

        // 단일/복수 선택을 배열로 통일
        var picked = (sel instanceof Array) ? sel : [sel];

        for (var k = 0; k < picked.length; k++) {
            var f = picked[k];
            var dup = false;
            for (var i = 0; i < files.length; i++) {
                if (files[i].absoluteURI === f.absoluteURI) { dup = true; break; }
            }
            if (dup) continue;
            files.push(f);
            fileList.add('item', f.displayName);
        }
    };

    btnRemove.onClick = function () {
        var sel = fileList.selection;
        if (!sel) return;
        files.splice(sel.index, 1);
        fileList.remove(sel.index);
    };

    // 문제 코드 입력
    dlg.add('statictext', undefined, '문제 코드 (한 줄에 하나, 예: 210320):');
    var txtCodes = dlg.add('edittext', [0, 0, 0, 120], '', { multiline: true, scrollable: true });

    // PDF 파일명
    var grpName = dlg.add('group');
    grpName.orientation = 'row';
    grpName.spacing = 6;
    grpName.add('statictext', [0, 0, 72, 18], 'PDF 파일명:');
    var txtName = grpName.add('edittext', [0, 0, 274, 22], '');
    txtName.helpTip = '예: 명일1_워크북02(21년3월20번외)_내지';

    // 출력 폴더
    var grpOut = dlg.add('group');
    grpOut.orientation = 'row';
    grpOut.spacing = 6;
    grpOut.add('statictext', [0, 0, 72, 18], '출력 폴더:');
    var txtOut = grpOut.add('edittext', [0, 0, 228, 22], '');
    txtOut.enabled = false;
    var btnOut = grpOut.add('button', undefined, '선택...');
    var outFolder = null;

    btnOut.onClick = function () {
        var f = Folder.selectDialog('PDF 저장 폴더 선택 (학교 폴더)');
        if (f) { outFolder = f; txtOut.text = f.fsName; }
    };

    // PDF 프리셋
    var grpPreset = dlg.add('group');
    grpPreset.orientation = 'row';
    grpPreset.spacing = 6;
    grpPreset.add('statictext', [0, 0, 72, 18], 'PDF 프리셋:');
    var presetItems = [];
    var presets = app.pdfExportPresets.everyItem().getElements();
    for (var pi = 0; pi < presets.length; pi++) presetItems.push(presets[pi].name);
    var ddPreset = grpPreset.add('dropdownlist', [0, 0, 274, 22], presetItems);
    if (presetItems.length > 0) ddPreset.selection = 0;

    // InDesign 파일 저장 옵션
    var chkSaveIndd = dlg.add('checkbox', undefined, 'InDesign 파일(.indd)도 함께 저장');
    chkSaveIndd.value = true;

    // 실행 / 취소
    var grpBtns = dlg.add('group');
    grpBtns.alignment = 'right';
    grpBtns.add('button', undefined, '취소', { name: 'cancel' });
    grpBtns.add('button', undefined, '실행', { name: 'ok' });

    if (dlg.show() !== 1) return;

    var saveIndd = chkSaveIndd.value;

    // 유효성 검사
    if (files.length === 0)  { alert('파일을 하나 이상 추가해 주세요.'); return; }
    if (!txtCodes.text.replace(/\s/g, '')) { alert('문제 코드를 입력해 주세요.'); return; }
    if (!txtName.text.replace(/\s/g, ''))  { alert('PDF 파일명을 입력해 주세요.'); return; }
    if (!outFolder) { alert('출력 폴더를 선택해 주세요.'); return; }

    // 코드 파싱
    var rawLines = txtCodes.text.split(/[\r\n]+/);
    var codes = [];
    for (var li = 0; li < rawLines.length; li++) {
        var line = rawLines[li].replace(/\s/g, '');
        if (!line) continue;
        var parsed = parseCode(line);
        if (!parsed) {
            alert('잘못된 코드 형식: "' + rawLines[li] + '"\n6자리 숫자여야 합니다. (예: 210320)');
            return;
        }
        codes.push(parsed);
    }
    if (codes.length === 0) { alert('유효한 코드가 없습니다.'); return; }

    var pdfName    = txtName.text;
    var presetName = (ddPreset.selection) ? ddPreset.selection.text : '';

    // ═══════════════════════════════════════════════════════════
    // 파일 열기 & 마커 수집
    // ═══════════════════════════════════════════════════════════

    var docCache     = {};
    var codeFileMap  = {};   // code → { doc, uri }
    var markersCache = {};   // uri  → markers[]

    for (var fi = 0; fi < files.length; fi++) {
        var uri = files[fi].absoluteURI;
        var doc;
        try {
            doc = getDoc(files[fi], docCache);
        } catch (e) {
            alert('파일 열기 실패:\n' + files[fi].displayName + '\n' + e.message);
            continue;
        }
        var mks = findAllMarkers(doc);
        markersCache[uri] = mks;

        // ── 진단 출력 (코드를 못 찾은 경우) ──────────────────────
        if (mks.length === 0) {
            var dbg = '파일: ' + files[fi].displayName + '\n총 페이지: ' + doc.pages.length + '\n\n';
            var aCnt = 0, firstMasters = [];
            for (var di = 0; di < Math.min(doc.pages.length, 20); di++) {
                try {
                    var mn = doc.pages[di].appliedMaster.name;
                    if (firstMasters.length < 5) firstMasters.push('p' + di + ':' + mn);
                    if (mn && mn.charAt(0).toUpperCase() === 'A') aCnt++;
                } catch (edi) {
                    if (firstMasters.length < 5) firstMasters.push('p' + di + ':오류');
                }
            }
            dbg += 'A마스터 페이지(처음 20p 기준): ' + aCnt + '개\n';
            dbg += '마스터 이름 샘플:\n' + firstMasters.join('\n') + '\n\n';
            // 첫 A마스터 페이지 아이템 내용 확인
            for (var di2 = 0; di2 < doc.pages.length; di2++) {
                try {
                    var mn2 = doc.pages[di2].appliedMaster.name;
                    if (!mn2 || mn2.charAt(0).toUpperCase() !== 'A') continue;
                    var its = doc.pages[di2].allPageItems;
                    dbg += '첫 A마스터 페이지(p' + di2 + ') 아이템 수: ' + its.length + '\n';
                    for (var fi2 = 0; fi2 < Math.min(its.length, 5); fi2++) {
                        try {
                            var tc = its[fi2].contents;
                            if (typeof tc === 'string') dbg += '  [' + fi2 + '] "' + tc.substring(0, 30) + '"\n';
                        } catch(ei) { dbg += '  [' + fi2 + '] (contents 오류)\n'; }
                    }
                    break;
                } catch(edi2) {}
            }
            alert(dbg);
        }
        // ─────────────────────────────────────────────────────────

        for (var mi = 0; mi < mks.length; mi++) {
            if (!codeFileMap[mks[mi].code]) {
                codeFileMap[mks[mi].code] = { doc: doc, uri: uri };
            }
        }
    }

    // ═══════════════════════════════════════════════════════════
    // 코드별 페이지 범위 PDF 내보내기 (page.move() 없음 → 순서/마스터 문제 없음)
    // ═══════════════════════════════════════════════════════════

    var preset = null;
    if (presetName) {
        try { preset = app.pdfExportPresets.itemByName(presetName); } catch (e) {}
    }

    // PDF export preferences 백업
    var savedRange   = app.pdfExportPreferences.pageRange;
    var savedSpreads = app.pdfExportPreferences.exportReaderSpreads;

    // 페이지 순서 보장: 스프레드 묶음 내보내기 OFF
    app.pdfExportPreferences.exportReaderSpreads = false;

    var tempPdfPaths = [];  // 임시 PDF 경로 목록
    var errors       = [];
    var pageCounter  = 1;   // 출력 PDF 순차 페이지 번호

    for (var ci = 0; ci < codes.length; ci++) {
        var code = codes[ci].raw;

        if (!codeFileMap[code]) {
            errors.push(code + ' : A마스터 페이지에서 코드를 찾을 수 없음');
            continue;
        }

        var srcDoc  = codeFileMap[code].doc;
        var srcUri  = codeFileMap[code].uri;
        var markers = markersCache[srcUri];
        var range   = getCodeRange(markers, code, srcDoc);

        if (!range) {
            errors.push(code + ' : 페이지 범위 계산 실패');
            continue;
        }

        // 임시 PDF 파일
        var tempPdf = new File(
            Folder.temp.absoluteURI + '/MrgMock_' + ci + '_' + code + '.pdf'
        );

        try {
            // 섹션 번호를 순차로 임시 재설정해서 내보내기 (원본 복원됨)
            var exported = exportRangeWithNumber(srcDoc, range, pageCounter, tempPdf, preset);
            if (exported) {
                pageCounter += (range.endIdx - range.startIdx + 1);
                tempPdfPaths.push(tempPdf.fsName);
            } else {
                errors.push(code + ' : 임시 PDF 생성 실패');
            }
        } catch (eExp) {
            errors.push(code + ' : 내보내기 오류 - ' + eExp.message);
        }
    }

    // PDF export preferences 복원
    try { app.pdfExportPreferences.pageRange           = savedRange;   } catch (e) {}
    try { app.pdfExportPreferences.exportReaderSpreads = savedSpreads; } catch (e) {}

    if (tempPdfPaths.length === 0) {
        alert('처리된 코드가 없습니다.\n\n오류:\n' + errors.join('\n'));
        return;
    }

    // ═══════════════════════════════════════════════════════════
    // Python CoreGraphics로 임시 PDF 결합
    // ═══════════════════════════════════════════════════════════

    var pdfFile = new File(outFolder.absoluteURI + '/' + pdfName + '.pdf');

    // paths.txt: 첫 줄 = 출력 경로, 이후 = 입력 경로들
    var pathsTxt = new File('/tmp/MrgMock_paths.txt');
    pathsTxt.encoding = 'UTF-8';
    pathsTxt.open('w');
    pathsTxt.writeln(pdfFile.fsName);
    for (var ti = 0; ti < tempPdfPaths.length; ti++) {
        pathsTxt.writeln(tempPdfPaths[ti]);
    }
    pathsTxt.close();

    // Python 결합 스크립트
    var pyCode = [
        'import sys, ctypes, ctypes.util',
        'CF = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))',
        'CG = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))',
        'class CGPoint(ctypes.Structure):',
        '    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]',
        'class CGSize(ctypes.Structure):',
        '    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]',
        'class CGRect(ctypes.Structure):',
        '    _fields_ = [("origin", CGPoint), ("size", CGSize)]',
        'CF.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p',
        'CF.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]',
        'CF.CFRelease.argtypes = [ctypes.c_void_p]',
        'CG.CGPDFDocumentCreateWithURL.restype = ctypes.c_void_p',
        'CG.CGPDFDocumentCreateWithURL.argtypes = [ctypes.c_void_p]',
        'CG.CGPDFDocumentGetNumberOfPages.restype = ctypes.c_size_t',
        'CG.CGPDFDocumentGetNumberOfPages.argtypes = [ctypes.c_void_p]',
        'CG.CGPDFDocumentGetPage.restype = ctypes.c_void_p',
        'CG.CGPDFDocumentGetPage.argtypes = [ctypes.c_void_p, ctypes.c_size_t]',
        'CG.CGPDFPageGetBoxRect.restype = CGRect',
        'CG.CGPDFPageGetBoxRect.argtypes = [ctypes.c_void_p, ctypes.c_int]',
        'CG.CGPDFDocumentRelease.argtypes = [ctypes.c_void_p]',
        'CG.CGPDFContextCreateWithURL.restype = ctypes.c_void_p',
        'CG.CGPDFContextCreateWithURL.argtypes = [ctypes.c_void_p, ctypes.POINTER(CGRect), ctypes.c_void_p]',
        'CG.CGContextBeginPage.argtypes = [ctypes.c_void_p, ctypes.POINTER(CGRect)]',
        'CG.CGContextEndPage.argtypes = [ctypes.c_void_p]',
        'CG.CGContextRelease.argtypes = [ctypes.c_void_p]',
        'CG.CGContextDrawPDFPage.argtypes = [ctypes.c_void_p, ctypes.c_void_p]',
        'def url(p):',
        '    b = p.encode("utf-8")',
        '    return CF.CFURLCreateFromFileSystemRepresentation(None, b, len(b), False)',
        'with open("/tmp/MrgMock_paths.txt", encoding="utf-8") as f:',
        '    lines = [l.strip() for l in f if l.strip()]',
        'out_path = lines[0]; in_paths = lines[1:]',
        'docs = []',
        'for p in in_paths:',
        '    u = url(p); d = CG.CGPDFDocumentCreateWithURL(u); CF.CFRelease(u)',
        '    if d: docs.append((d, CG.CGPDFDocumentGetNumberOfPages(d)))',
        'if not docs: sys.exit("no docs")',
        'fp = CG.CGPDFDocumentGetPage(docs[0][0], 1)',
        'ir = CG.CGPDFPageGetBoxRect(fp, 0)',
        'ou = url(out_path)',
        'ctx = CG.CGPDFContextCreateWithURL(ou, ctypes.byref(ir), None)',
        'CF.CFRelease(ou)',
        'if not ctx: sys.exit("no ctx")',
        'for d, n in docs:',
        '    for i in range(1, n+1):',
        '        pg = CG.CGPDFDocumentGetPage(d, i)',
        '        if not pg: continue',
        '        r = CG.CGPDFPageGetBoxRect(pg, 0)',
        '        CG.CGContextBeginPage(ctx, ctypes.byref(r))',
        '        CG.CGContextDrawPDFPage(ctx, pg)',
        '        CG.CGContextEndPage(ctx)',
        'CG.CGContextRelease(ctx)',
        'for d, n in docs: CG.CGPDFDocumentRelease(d)',
        'print("OK")'
    ].join('\n');

    var pyFile = new File('/tmp/MrgMock_combine.py');
    pyFile.encoding = 'UTF-8';
    pyFile.open('w');
    pyFile.write(pyCode);
    pyFile.close();

    var errBlock = (errors.length > 0) ? '\n\n처리 안 된 코드:\n' + errors.join('\n') : '';

    try {
        var result = app.doScript(
            'do shell script "python3 /tmp/MrgMock_combine.py"',
            ScriptLanguage.APPLESCRIPT_LANGUAGE
        );
        // 임시 파일 정리
        try { pathsTxt.remove(); } catch (e) {}
        try { pyFile.remove(); }   catch (e) {}
        for (var ti2 = 0; ti2 < tempPdfPaths.length; ti2++) {
            try { new File(tempPdfPaths[ti2]).remove(); } catch (e) {}
        }
    } catch (eCombine) {
        alert('PDF 결합 실패:\n' + eCombine.message + errBlock +
              '\n\n임시 PDF 위치: ' + Folder.temp.fsName);
        return;
    }

    // ═══════════════════════════════════════════════════════════
    // INDD 결합 (옵션)
    // ═══════════════════════════════════════════════════════════

    var inddMsg = '';
    if (saveIndd) {
        try {
            var inddRes = saveAsIndd(codes, codeFileMap, markersCache, outFolder, pdfName);
            if (inddRes.ok) {
                inddMsg = '\n' + inddRes.path;
            } else {
                inddMsg = '\n\n[INDD 저장 실패] ' + inddRes.error;
            }
        } catch (eIndd) {
            inddMsg = '\n\n[INDD 저장 실패] ' + eIndd.message;
        }
    }

    alert('완료!' + errBlock + '\n\n저장 위치:\n' + pdfFile.fsName + inddMsg);

}());
