/**
 * MergeMockExamSero.jsx
 * Merge selected vertical-version mock exam .indd files by question codes
 * into a single InDesign file. (No PDF export.)
 *
 * Usage:
 *   1. Pick grade (G1 / G2)
 *   2. Folder is auto-mapped (editable)
 *   3. Enter question codes (one per line, 6-digit YYMMQQ)
 *      e.g. 260320 = 26-Mar Q20, 250921 = 25-Sep Q21, 211138 = 21-Nov Q38
 *   4. Set result filename + output folder
 *   5. Run
 *
 * Group identification:
 *   The vertical version uses A/B/C/D/E/O (and sometimes M) masters per
 *   passage. A page with master "A*" starts a new group. The 6-digit
 *   code on that A-page identifies the group.
 *
 * File mapping:
 *   YYMMQQ -> grade + YY-year + MM-month -> auto-find vertical file.
 *   Filename pattern: G{N}_{YY}YR_{M|MM}MO_VERT*.indd  (Korean strings,
 *   tolerant of zero-padding and underscore/space separators).
 *
 * Merge strategy:
 *   - saveACopy of first code's source -> base copy
 *   - delete pages outside first code's range
 *   - duplicate(AT_END) pages of remaining codes
 *   - save copy. Source files are not modified.
 *
 * Note: Korean strings are written as \uXXXX escapes throughout because
 * macOS APFS/HFS+ returns NFD filenames while editors save source as
 * NFC; explicit escapes guarantee match-time correctness in ES3.
 */

#target indesign

(function () {

    // ═══════════════════════════════════════════════════════════
    // Korean literals (NFC + NFD)
    //   N = NFC, D = NFD form for filesystem-returned names
    // ═══════════════════════════════════════════════════════════

    var GO_N    = '고';                          // 고
    var GO_D    = '고';                    // 고 (NFD)
    var YEAR_N  = '년';                          // 년
    var YEAR_D  = '년';              // 년 (NFD)
    var MON_N   = '월';                          // 월
    var MON_D   = '월';              // 월 (NFD)
    var SERO_N  = '세로';                    // 세로
    var SERO_D  = '세로';        // 세로 (NFD)

    // ═══════════════════════════════════════════════════════════
    // Default base folder (Google Drive Stream)
    //   Path string is whatever encoding Folder() resolves; we don't
    //   compare it against filesystem-returned strings, so this is OK.
    // ═══════════════════════════════════════════════════════════

    var DEFAULT_BASE = '/Users/nhj/Library/CloudStorage/' +
        'GoogleDrive-etyrano11@gmail.com/내 드라이브/' +     // 내 드라이브
        '콘텐츠 관리/' +                                       // 콘텐츠 관리
        '내신대비/' +                                              // 내신대비
        '인디자인 파일/' +                                 // 인디자인 파일
        '워크북/모의고사';                             // 워크북/모의고사

    // ═══════════════════════════════════════════════════════════
    // Helpers - parse / encoding-tolerant string ops
    // ═══════════════════════════════════════════════════════════

    function parseCode(raw) {
        var code = String(raw).replace(/\s/g, '');
        if (!/^\d{6}$/.test(code)) return null;
        return {
            raw:   code,
            year:  code.substring(0, 2),
            month: code.substring(2, 4),
            qNum:  code.substring(4, 6)
        };
    }

    function nameHas(name, nfc, nfd) {
        return (name.indexOf(nfc) !== -1) || (name.indexOf(nfd) !== -1);
    }
    function nameStarts(name, nfc, nfd) {
        return (name.indexOf(nfc) === 0) || (name.indexOf(nfd) === 0);
    }

    // ═══════════════════════════════════════════════════════════
    // Find vertical .indd for a given grade / year / month
    //   Filename example: G1_22YR_03MO_VERT(C).indd / G1_22YR_6MO_VERT(C).indd
    // ═══════════════════════════════════════════════════════════

    function findVerticalFile(folder, grade, year, month) {
        if (!folder || !folder.exists) return null;

        var monthInt = parseInt(month, 10);
        var monthVariants = [String(monthInt)];                 // "3"
        if (monthInt < 10) monthVariants.push('0' + monthInt);  // "03"

        var files = folder.getFiles();
        var candidates = [];

        for (var i = 0; i < files.length; i++) {
            var f = files[i];
            if (!(f instanceof File)) continue;
            // File.name은 URL-encoded ('%E1%84%80...'). displayName은 디코딩된 실제 이름.
            var name = f.displayName;
            if (!/\.indd$/i.test(name)) continue;

            // contains 세로
            if (!nameHas(name, SERO_N, SERO_D)) continue;

            // starts with 고{N}
            if (!nameStarts(name, GO_N + grade, GO_D + grade)) continue;

            // contains {YY}년
            if (!nameHas(name, year + YEAR_N, year + YEAR_D)) continue;

            // contains {M|MM}월
            var monMatched = false;
            for (var mi = 0; mi < monthVariants.length; mi++) {
                if (nameHas(name, monthVariants[mi] + MON_N,
                                  monthVariants[mi] + MON_D)) {
                    monMatched = true;
                    break;
                }
            }
            if (!monMatched) continue;

            candidates.push(f);
        }

        if (candidates.length === 0) return null;

        // Multiple matches: shortest name wins (fewest extra annotations
        // like "[in-progress]", " cleanup-needed").
        candidates.sort(function (a, b) { return a.displayName.length - b.displayName.length; });
        return candidates[0];
    }

    // ═══════════════════════════════════════════════════════════
    // Document / marker helpers
    // ═══════════════════════════════════════════════════════════

    function getDoc(file, cache) {
        var key = file.absoluteURI;
        if (cache[key]) return { doc: cache[key], opened: false };
        for (var d = 0; d < app.documents.length; d++) {
            try {
                if (app.documents[d].fullName.toString() === file.toString()) {
                    cache[key] = app.documents[d];
                    return { doc: cache[key], opened: false };
                }
            } catch (e) {}
        }
        var doc = app.open(file, false);
        cache[key] = doc;
        return { doc: doc, opened: true };
    }

    // ═══════════════════════════════════════════════════════════
    // Story threading 보존 (STEP3 같은 지문 내 자동 번호 유지)
    //   - prepass: 원본 파일의 모든 textFrame.label 에 storyId 표기
    //     (메모리상 변경 / close(NO)로 디스크 미반영)
    //   - 결합 후: 같은 그룹 페이지 범위 내 같은 storyId 프레임을
    //     페이지+좌표 순으로 nextTextFrame 으로 다시 연결
    //   - 마무리: newDoc 의 임시 라벨 청소
    // ═══════════════════════════════════════════════════════════

    var SID_PFX = '__sero_sid:';
    var SID_SEP = '|';

    function tagStoryLabels(doc) {
        for (var p = 0; p < doc.pages.length; p++) {
            var frames = doc.pages[p].textFrames;
            for (var f = 0; f < frames.length; f++) {
                var tf = frames[f];
                try {
                    var existing = tf.label || '';
                    if (existing.indexOf(SID_PFX) === 0) continue; // 이미 라벨링됨
                    var sid;
                    try { sid = String(tf.parentStory.id); } catch (eS) { sid = 'X'; }
                    tf.label = SID_PFX + sid + (existing ? SID_SEP + existing : '');
                } catch (e) {}
            }
        }
    }

    function getSidFromLabel(tf) {
        var lab = '';
        try { lab = tf.label || ''; } catch (e) { return null; }
        if (lab.indexOf(SID_PFX) !== 0) return null;
        var rest = lab.substring(SID_PFX.length);
        var sepIdx = rest.indexOf(SID_SEP);
        return (sepIdx >= 0) ? rest.substring(0, sepIdx) : rest;
    }

    function rethreadGroup(doc, startIdx, endIdx) {
        var byStory = {};
        for (var p = startIdx; p <= endIdx && p < doc.pages.length; p++) {
            var frames = doc.pages[p].textFrames;
            for (var f = 0; f < frames.length; f++) {
                var tf = frames[f];
                var sid = getSidFromLabel(tf);
                if (!sid) continue;
                var gb;
                try { gb = tf.geometricBounds; } catch (eGb) { gb = [0, 0, 0, 0]; }
                if (!byStory[sid]) byStory[sid] = [];
                byStory[sid].push({ pageIdx: p, tf: tf, y: gb[0], x: gb[1] });
            }
        }
        for (var sid in byStory) {
            var arr = byStory[sid];
            if (arr.length < 2) continue;
            arr.sort(function (a, b) {
                if (a.pageIdx !== b.pageIdx) return a.pageIdx - b.pageIdx;
                if (a.y !== b.y) return a.y - b.y;
                return a.x - b.x;
            });
            for (var i = 0; i < arr.length - 1; i++) {
                try { arr[i].tf.nextTextFrame = arr[i + 1].tf; } catch (eTh) {}
            }
        }
    }

    // LastP.ai 링크가 포함된 페이지 → 문서 마지막으로 이동
    function moveLastPagesToEnd(doc) {
        var hits = [];
        for (var p = 0; p < doc.pages.length; p++) {
            var items;
            try { items = doc.pages[p].allPageItems; } catch (eAp) { continue; }
            var isLast = false;
            for (var i = 0; i < items.length; i++) {
                try {
                    var link = items[i].itemLink;
                    if (link && link.isValid) {
                        var nm = link.name || '';
                        if (nm.indexOf('LastP') !== -1) { isLast = true; break; }
                    }
                } catch (eL) {}
            }
            if (isLast) hits.push(p);
        }
        // 뒤에서부터 이동해야 앞 인덱스 변동을 피할 수 있음
        hits.sort(function (a, b) { return b - a; });
        for (var h = 0; h < hits.length; h++) {
            var idx = hits[h];
            if (idx >= doc.pages.length - 1) continue; // 이미 끝
            try { doc.pages[idx].move(LocationOptions.AT_END); } catch (eMv) {}
        }
        return hits.length;
    }

    function cleanLabels(doc) {
        for (var p = 0; p < doc.pages.length; p++) {
            var frames = doc.pages[p].textFrames;
            for (var f = 0; f < frames.length; f++) {
                var tf = frames[f];
                var lab = '';
                try { lab = tf.label || ''; } catch (e) { continue; }
                if (lab.indexOf(SID_PFX) !== 0) continue;
                var rest = lab.substring(SID_PFX.length);
                var sepIdx = rest.indexOf(SID_SEP);
                try {
                    tf.label = (sepIdx >= 0) ? rest.substring(sepIdx + 1) : '';
                } catch (eC) {}
            }
        }
    }

    // Markers = group starts. A page with master starting with 'A'.
    // Each marker tries to capture both a 6-digit code (구파일) and a
    // [QQ] question number (신파일) from the page's items.
    function findAllMarkers(doc) {
        var markers = [];
        var code6Pat = /\b(\d{6})\b/;
        // [20] / [41~42] / [41-42] 모두 매칭. group1=시작, group2=끝(없으면 단일)
        var qNumPat  = /\[\s*(\d{1,2})(?:\s*[~\-]\s*(\d{1,2}))?\s*\]/;

        for (var i = 0; i < doc.pages.length; i++) {
            var page = doc.pages[i];
            try {
                var masterName = page.appliedMaster.name;
                if (!masterName || masterName.charAt(0).toUpperCase() !== 'A') continue;
            } catch (e) { continue; }

            var foundCode = null;
            var foundQ    = null;
            var foundQEnd = null;
            try {
                var items = page.allPageItems;
                for (var f = 0; f < items.length; f++) {
                    try {
                        var txt = items[f].contents;
                        if (typeof txt !== 'string') continue;
                        if (!foundCode) {
                            var m6 = code6Pat.exec(txt);
                            if (m6) foundCode = m6[1];
                        }
                        if (!foundQ) {
                            var mq = qNumPat.exec(txt);
                            if (mq) {
                                foundQ    = mq[1];
                                foundQEnd = mq[2] || null; // [41~42]의 42
                            }
                        }
                        if (foundCode && foundQ) break;
                    } catch (ef) {}
                }
            } catch (ep) {}

            if (foundCode || foundQ) {
                // 직전 마커와 같은 식별자면 같은 그룹의 연속 페이지로 보고 추가하지 않음.
                // (26년 파일은 한 그룹 내 여러 페이지에 A-마스터가 적용되어 있음)
                var lastM = markers.length > 0 ? markers[markers.length - 1] : null;
                var sameAsLast = false;
                if (lastM) {
                    if (foundCode && foundCode === lastM.code) sameAsLast = true;
                    else if (!foundCode && foundQ &&
                             foundQ === lastM.qNum &&
                             (foundQEnd || '') === (lastM.qNumEnd || '')) sameAsLast = true;
                }
                if (!sameAsLast) {
                    markers.push({
                        code: foundCode, qNum: foundQ, qNumEnd: foundQEnd, pageIndex: i
                    });
                }
            }
        }

        markers.sort(function (a, b) { return a.pageIndex - b.pageIndex; });
        return markers;
    }

    // 매칭: 6자리 코드 정확 매칭 우선, 실패 시 마지막 2자리(QQ).
    // 묶음 [41~42]는 41과 42 둘 다에 매칭됨.
    function findMarkerIndex(markers, code) {
        for (var i = 0; i < markers.length; i++) {
            if (markers[i].code === code) return i;
        }
        var qqInt = parseInt(code.substring(4, 6), 10);
        for (var j = 0; j < markers.length; j++) {
            var m = markers[j];
            if (!m.qNum) continue;
            var s = parseInt(m.qNum, 10);
            var e = m.qNumEnd ? parseInt(m.qNumEnd, 10) : s;
            if (qqInt >= s && qqInt <= e) return j;
        }
        return -1;
    }

    function getCodeRange(markers, code, doc) {
        var idx = findMarkerIndex(markers, code);
        if (idx === -1) return null;
        var startIdx = markers[idx].pageIndex;
        var endIdx   = (idx < markers.length - 1)
                         ? markers[idx + 1].pageIndex - 1
                         : doc.pages.length - 1;
        return { startIdx: startIdx, endIdx: endIdx };
    }

    // ═══════════════════════════════════════════════════════════
    // Dialog
    // ═══════════════════════════════════════════════════════════

    var dlg = new Window('dialog',
        '모의고사 세로 결합 → InDesign');
    // 모의고사 세로 결합 → InDesign

    dlg.orientation = 'column';
    dlg.alignChildren = 'fill';
    dlg.margins = [16, 16, 16, 16];
    dlg.spacing = 10;

    // Grade
    var grpGrade = dlg.add('group');
    grpGrade.add('statictext', undefined, '학년:'); // 학년:
    var rb1 = grpGrade.add('radiobutton', undefined, '고1'); // 고1
    var rb2 = grpGrade.add('radiobutton', undefined, '고2'); // 고2
    rb1.value = true;

    // Input folder
    dlg.add('statictext', undefined,
        '세로 파일 폴더:'); // 세로 파일 폴더:
    var grpIn = dlg.add('group');
    var txtIn = grpIn.add('edittext', [0, 0, 380, 22], DEFAULT_BASE + '/고1'); // /고1
    var btnIn = grpIn.add('button', undefined, '...');
    btnIn.onClick = function () {
        var f = Folder.selectDialog(
            '세로 파일 폴더 선택'); // 세로 파일 폴더 선택
        if (f) txtIn.text = f.fsName;
    };
    // 라디오 학년 변경 시 폴더를 무조건 해당 학년 default로 변경
    // (사용자가 폴더를 직접 골랐으면 ... 버튼으로 다시 변경 가능)
    rb1.onClick = function () { txtIn.text = DEFAULT_BASE + '/고1'; };
    rb2.onClick = function () { txtIn.text = DEFAULT_BASE + '/고2'; };

    // Codes
    dlg.add('statictext', undefined,
        '문제 코드 (한 줄에 하나, 6자리 YYMMQQ):');
    // 문제 코드 (한 줄에 하나, 6자리 YYMMQQ):
    var txtCodes = dlg.add('edittext', [0, 0, 0, 130], '', { multiline: true, scrollable: true });
    txtCodes.helpTip = '260320 = 26년 3월 20번'; // 260320 = 26년 3월 20번

    // Result name
    var grpName = dlg.add('group');
    grpName.add('statictext', [0, 0, 80, 18],
        '결과 파일명:'); // 결과 파일명:
    var txtName = grpName.add('edittext', [0, 0, 320, 22], '');
    txtName.helpTip = '확장자 제외. 예: 명일1_워크북02_내지';
    // 확장자 제외. 예: 명일1_워크북02_내지

    // Output folder
    var grpOut = dlg.add('group');
    grpOut.add('statictext', [0, 0, 80, 18], '출력 폴더:'); // 출력 폴더:
    var txtOut = grpOut.add('edittext', [0, 0, 280, 22], '');
    txtOut.enabled = false;
    var btnOut = grpOut.add('button', undefined, '선택...'); // 선택...
    var outFolder = null;
    btnOut.onClick = function () {
        var f = Folder.selectDialog(
            '결과 .indd 저장 폴더'); // 결과 .indd 저장 폴더
        if (f) { outFolder = f; txtOut.text = f.fsName; }
    };

    // Buttons
    var grpBtn = dlg.add('group');
    grpBtn.alignment = 'right';
    grpBtn.add('button', undefined, '취소', { name: 'cancel' }); // 취소
    grpBtn.add('button', undefined, '실행', { name: 'ok' });     // 실행

    if (dlg.show() !== 1) return;

    // ═══════════════════════════════════════════════════════════
    // Validate input
    // ═══════════════════════════════════════════════════════════

    var grade = rb1.value ? '1' : '2';
    var inFolder = new Folder(txtIn.text);
    if (!inFolder.exists) {
        alert('입력 폴더가 없습니다:\n' + txtIn.text);
        // 입력 폴더가 없습니다:
        return;
    }

    var rawLines = txtCodes.text.split(/[\r\n]+/);
    var codes = [];
    for (var li = 0; li < rawLines.length; li++) {
        var line = rawLines[li].replace(/\s/g, '');
        if (!line) continue;
        var p = parseCode(line);
        if (!p) {
            alert('잘못된 코드: "' + rawLines[li] +
                  '"\n6자리 숫자여야 합니다 (예: 260320)');
            // 잘못된 코드: "..."\n6자리 숫자여야 합니다 (예: 260320)
            return;
        }
        codes.push(p);
    }
    if (codes.length === 0) {
        alert('문제 코드를 입력해 주세요.');
        // 문제 코드를 입력해 주세요.
        return;
    }

    var resultName = txtName.text.replace(/^\s+|\s+$/g, '');
    if (!resultName) {
        alert('결과 파일명을 입력해 주세요.');
        // 결과 파일명을 입력해 주세요.
        return;
    }
    if (!outFolder) {
        alert('출력 폴더를 선택해 주세요.');
        // 출력 폴더를 선택해 주세요.
        return;
    }

    // ═══════════════════════════════════════════════════════════
    // 1) Code -> File mapping
    // ═══════════════════════════════════════════════════════════

    var codeToFile = {};
    var notFound   = [];

    for (var ci = 0; ci < codes.length; ci++) {
        var c = codes[ci];
        var f = findVerticalFile(inFolder, grade, c.year, c.month);
        if (!f) {
            notFound.push(c.raw + '  (' + c.year + '년 ' +     // 년
                          parseInt(c.month, 10) + '월 ' +       // 월
                          '파일 없음)');           // 파일 없음
            continue;
        }
        codeToFile[c.raw] = f;
    }
    if (notFound.length > 0) {
        // 진단 정보: 검색 폴더 + 폴더 내 .indd 파일 목록 + 첫 파일명의 charCode
        var dbg = '파일을 찾지 못한 코드:\n\n' + notFound.join('\n');
        // 파일을 찾지 못한 코드:
        dbg += '\n\n[진단]';                               // [진단]
        dbg += '\n검색 폴더: ' + inFolder.fsName;          // 검색 폴더:
        dbg += '\n폴더 존재: ' + (inFolder.exists ? 'YES' : 'NO');
        // 폴더 존재:
        if (inFolder.exists) {
            var allFiles2 = inFolder.getFiles();
            var inddNames = [];
            for (var dfi = 0; dfi < allFiles2.length; dfi++) {
                if (!(allFiles2[dfi] instanceof File)) continue;
                var dnm = allFiles2[dfi].displayName;
                if (/\.indd$/i.test(dnm)) inddNames.push(dnm);
            }
            dbg += '\n.indd 파일 수: ' + inddNames.length;  // .indd 파일 수:
            // 첫 5개 파일명만 (charCode는 사람이 읽기 어려우므로 displayName만)
            var maxShow = Math.min(5, inddNames.length);
            for (var ni = 0; ni < maxShow; ni++) {
                dbg += '\n[' + ni + '] ' + inddNames[ni];
            }
        }
        alert(dbg);
        return;
    }

    // ═══════════════════════════════════════════════════════════
    // 2) Open files + collect markers (each file once)
    // ═══════════════════════════════════════════════════════════

    var docCache    = {};
    var openedByUs  = {};
    var fileMarkers = {};

    function closeOurDocs() {
        for (var u in openedByUs) {
            try { docCache[u].close(SaveOptions.NO); } catch (e) {}
        }
    }

    for (var ci2 = 0; ci2 < codes.length; ci2++) {
        var fc  = codeToFile[codes[ci2].raw];
        var uri = fc.absoluteURI;
        if (docCache[uri]) continue;

        var got;
        try {
            got = getDoc(fc, docCache);
        } catch (eOpen) {
            closeOurDocs();
            alert('파일 열기 실패:\n' + fc.fsName + '\n' + eOpen.message);
            // 파일 열기 실패:
            return;
        }
        if (got.opened) openedByUs[uri] = true;
        fileMarkers[uri] = findAllMarkers(got.doc);
        // prepass: 모든 텍스트프레임에 storyId 라벨 부여 (메모리상; close NO로 디스크 미반영)
        try { tagStoryLabels(got.doc); } catch (eTag) {}
    }

    // ═══════════════════════════════════════════════════════════
    // 3) Verify all codes have markers
    // ═══════════════════════════════════════════════════════════

    var missingCodes = [];
    for (var ci3 = 0; ci3 < codes.length; ci3++) {
        var cd  = codes[ci3];
        var ufm = codeToFile[cd.raw].absoluteURI;
        var mks = fileMarkers[ufm];
        if (findMarkerIndex(mks, cd.raw) === -1) {
            missingCodes.push(cd.raw + '  (파일: ' + codeToFile[cd.raw].displayName + ')');
            // 파일:
        }
    }
    if (missingCodes.length > 0) {
        // 진단: 첫 번째 missing 코드의 파일에서
        //   - 마스터 이름 분포 (페이지별)
        //   - 발견된 모든 마커 코드 (6자리)
        //   - 첫 A 마스터 페이지의 아이템 contents 샘플
        var dbg = '그룹을 찾지 못한 코드:\n\n' + missingCodes.join('\n');
        // 그룹을 찾지 못한 코드:

        var firstMissUri = codeToFile[codes[0].raw].absoluteURI;
        var dDoc = docCache[firstMissUri];
        var dMks = fileMarkers[firstMissUri];

        dbg += '\n\n[진단] ' + codeToFile[codes[0].raw].displayName;
        dbg += '\n총 페이지: ' + dDoc.pages.length;

        // 마스터 분포 (처음 20페이지)
        var mDist = {};
        var mList = [];
        var lim = Math.min(dDoc.pages.length, 20);
        for (var dpi = 0; dpi < lim; dpi++) {
            var mnm = '?';
            try { mnm = dDoc.pages[dpi].appliedMaster.name; } catch (eMm) {}
            mDist[mnm] = (mDist[mnm] || 0) + 1;
            if (dpi < 8) mList.push('p' + (dpi + 1) + ':' + mnm);
        }
        dbg += '\n마스터 (첫 8p): ' + mList.join(', ');
        dbg += '\n마스터 분포 (첫 20p): ';
        var mKeys = [];
        for (var mk in mDist) mKeys.push(mk + '=' + mDist[mk]);
        dbg += mKeys.join(', ');

        // 발견된 마커 코드 (전체) - code/qNum 둘 다 표시
        dbg += '\n\n발견된 마커 (' + dMks.length + '개): ';
        // 발견된 마커:
        if (dMks.length > 0) {
            var mkCodes = [];
            for (var mki = 0; mki < Math.min(dMks.length, 30); mki++) {
                var lab = dMks[mki].code ||
                          ('[' + dMks[mki].qNum +
                           (dMks[mki].qNumEnd ? '~' + dMks[mki].qNumEnd : '') + ']');
                mkCodes.push(lab + '(p' + (dMks[mki].pageIndex + 1) + ')');
            }
            dbg += mkCodes.join(', ');
        } else {
            dbg += '없음';
        }

        // 첫 A 마스터 페이지의 아이템 contents 샘플
        for (var sdi = 0; sdi < dDoc.pages.length; sdi++) {
            var smn = '';
            try { smn = dDoc.pages[sdi].appliedMaster.name; } catch (eSm) { continue; }
            if (!smn || smn.charAt(0).toUpperCase() !== 'A') continue;
            var sIts;
            try { sIts = dDoc.pages[sdi].allPageItems; } catch (eIt) { break; }
            dbg += '\n\n첫 A마스터 페이지 (p' + (sdi + 1) + ') 아이템: ' + sIts.length;
            // 첫 A마스터 페이지 (...) 아이템:
            for (var si = 0; si < Math.min(sIts.length, 8); si++) {
                try {
                    var sct = sIts[si].contents;
                    if (typeof sct === 'string') {
                        dbg += '\n  [' + si + '] "' + sct.substring(0, 40) + '"';
                    } else {
                        dbg += '\n  [' + si + '] (no text)';
                    }
                } catch (eCt) {
                    dbg += '\n  [' + si + '] (err)';
                }
            }
            break;
        }

        closeOurDocs();
        alert(dbg);
        return;
    }

    // ═══════════════════════════════════════════════════════════
    // 4) Create base copy + merge pages
    // ═══════════════════════════════════════════════════════════

    // 같은 이름 파일이 있으면 _2, _3, ... 으로 번호 자동 부여
    var inddOut = new File(outFolder.absoluteURI + '/' + resultName + '.indd');
    if (inddOut.exists) {
        var dupN = 2;
        while (dupN < 1000) {
            var trial = new File(outFolder.absoluteURI + '/' + resultName + '_' + dupN + '.indd');
            if (!trial.exists) { inddOut = trial; break; }
            dupN++;
        }
    }

    // 베이스는 고정 템플릿 파일 (첫 번째 코드 파일이 아님).
    // 템플릿을 출력 위치로 복사한 뒤 그 사본을 결합 베이스로 사용.
    var TEMPLATE_PATH = '/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/' +
        '내 드라이브/콘텐츠 관리/내신대비/인디자인 파일/Y.ONE WEB/' +
        '인디자인 원본/[원본]워크북_C세로(모의고사)_내지.indd';
    // [원본]워크북_C세로(모의고사)_내지.indd
    var templateFile = new File(TEMPLATE_PATH);
    if (!templateFile.exists) {
        closeOurDocs();
        alert('템플릿 파일을 찾을 수 없습니다:\n' + TEMPLATE_PATH);
        // 템플릿 파일을 찾을 수 없습니다:
        return;
    }
    if (!templateFile.copy(inddOut)) {
        closeOurDocs();
        alert('템플릿 사본 생성 실패:\n' + inddOut.fsName);
        // 템플릿 사본 생성 실패:
        return;
    }

    var newDoc;
    try {
        newDoc = app.open(inddOut, false);
    } catch (eOpen2) {
        closeOurDocs();
        alert('사본 열기 실패:\n' + inddOut.fsName + '\n' + eOpen2.message);
        // 사본 열기 실패:
        return;
    }

    var totalPages = 0;
    var dupErrors  = [];

    try {
        // 템플릿 베이스: 앞 KEEP_HEAD 페이지(간지)와 마지막 1페이지(꼬리)는 보존.
        // 그 사이 페이지는 모두 삭제. 마지막 페이지는 모든 코드 추가가 끝난 뒤
        // 다시 결과 문서의 마지막 위치로 이동시킨다.
        var KEEP_HEAD = 3;
        var tailPageRef = null;
        if (newDoc.pages.length > KEEP_HEAD) {
            tailPageRef = newDoc.pages[newDoc.pages.length - 1];
            // 인덱스 KEEP_HEAD ~ length-2 페이지 삭제 (back-to-front)
            for (var p = newDoc.pages.length - 2; p >= KEEP_HEAD; p--) {
                try { newDoc.pages[p].remove(); } catch (er) {}
            }
        }
        totalPages = newDoc.pages.length;

        // 그룹별 페이지 인덱스 추적 (rethread 용)
        var codeRanges = [];

        // 모든 코드의 markers 범위 페이지를 AT_END 로 추가
        // (이제 첫 번째 코드도 다른 코드와 동일하게 처리)
        for (var ci4 = 0; ci4 < codes.length; ci4++) {
            var c4 = codes[ci4];
            var u4 = codeToFile[c4.raw].absoluteURI;
            var sd = docCache[u4];
            var rg = getCodeRange(fileMarkers[u4], c4.raw, sd);
            if (!rg) {
                dupErrors.push(c4.raw + ' range missing');
                continue;
            }
            var grpStart = newDoc.pages.length;
            for (var p2 = rg.startIdx; p2 <= rg.endIdx; p2++) {
                try {
                    sd.pages[p2].duplicate(LocationOptions.AT_END, newDoc.pages.lastItem());
                    totalPages++;
                } catch (eDup) {
                    dupErrors.push(c4.raw + ' p' + p2 + ': ' + eDup.message);
                }
            }
            var grpEnd = newDoc.pages.length - 1;
            if (grpEnd >= grpStart) {
                codeRanges.push({ code: c4.raw, startIdx: grpStart, endIdx: grpEnd });
            }
        }

        // 템플릿 마지막 페이지를 다시 끝으로 이동 (코드 페이지 추가 후)
        if (tailPageRef) {
            try { tailPageRef.move(LocationOptions.AT_END); } catch (eMv) {}
        }

        // 그룹별 텍스트프레임 다시 threading (STEP3 자동 번호 보존)
        for (var rgi = 0; rgi < codeRanges.length; rgi++) {
            try {
                rethreadGroup(newDoc, codeRanges[rgi].startIdx, codeRanges[rgi].endIdx);
            } catch (eRt) {
                dupErrors.push('rethread ' + codeRanges[rgi].code + ': ' + eRt.message);
            }
        }

        // LastP.ai 링크가 들어있는 페이지를 끝으로 이동한 뒤
        // 템플릿 마지막 페이지를 한번 더 끝으로 보낸다 (항상 가장 마지막에 위치).
        try { moveLastPagesToEnd(newDoc); } catch (eLp) {}
        if (tailPageRef) {
            try { tailPageRef.move(LocationOptions.AT_END); } catch (eMv2) {}
        }

        // 임시 라벨 청소 (newDoc 만; 원본은 close NO 로 어차피 미반영)
        try { cleanLabels(newDoc); } catch (eCl) {}

        newDoc.save();
    } catch (eMain) {
        try { newDoc.close(SaveOptions.NO); } catch (e) {}
        closeOurDocs();
        alert('결합 작업 중 오류:\n' + eMain.message);
        // 결합 작업 중 오류:
        return;
    }

    var savedPath = inddOut.fsName;

    // Add a window so user can review the result
    try { newDoc.windows.add(); } catch (eWin) {}

    closeOurDocs();

    var msg = '완료\n\n' +              // 완료
              codes.length + '개 코드 / ' + // 개 코드 /
              totalPages + ' 페이지 결합\n\n' + // 페이지 결합
              '저장: ' + savedPath;       // 저장:
    if (dupErrors.length > 0) {
        msg += '\n\n[경고] 일부 페이지 복제 실패:\n' +
               // [경고] 일부 페이지 복제 실패:
               dupErrors.join('\n');
    }
    alert(msg);

}());
