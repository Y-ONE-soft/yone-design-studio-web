/**
 * RelinkKoreanToEnglish.jsx  v2
 * ─────────────────────────────────────────────────────────────────────
 * 문제: macOS HFS+/APFS 는 한글을 NFD(자모 분리) 형태로 저장하므로
 *       소스 파일의 NFC 한글 리터럴 정규식이 link.name 과 매칭되지 않음.
 * 해결: 정규식 한글 리터럴 없이 charCodeAt() 스캐닝으로 NFC/NFD 모두 처리.
 *
 * 변환 규칙
 *   간지(…)_STEP1.ai  →  STEP1.ai    (접두 '한글(…)_' 제거)
 *   1P간지(…).ai      →  1P.ai       (접미 '한글(…)' 제거)
 *   마지막P간지(…).ai →  LastP.ai    (한글→영문 치환 후 접미 제거)
 * ─────────────────────────────────────────────────────────────────────
 */

#target indesign

(function () {

    if (!app.documents.length) {
        alert('열려 있는 문서가 없습니다.\n문서를 먼저 열어 주세요.');
        return;
    }
    var doc = app.activeDocument;


    // ═══════════════════════════════════════════════════════════════════
    // 1. 한글 감지 — charCode 직접 비교 (NFC 완성형 + NFD 자모 모두 커버)
    // ═══════════════════════════════════════════════════════════════════
    function isKoreanCode(code) {
        return (code >= 0xAC00 && code <= 0xD7AF) ||   // 완성형 음절 (NFC)
               (code >= 0x1100 && code <= 0x11FF) ||   // 한글 자모   (NFD)
               (code >= 0x3130 && code <= 0x318F) ||   // 호환 자모
               (code >= 0xA960 && code <= 0xA97F) ||   // 자모 확장 A
               (code >= 0xD7B0 && code <= 0xD7FF);     // 자모 확장 B
    }

    function hasKorean(str) {
        for (var i = 0; i < str.length; i++) {
            if (isKoreanCode(str.charCodeAt(i))) return true;
        }
        return false;
    }

    // 앞에서 연속된 한글 문자 개수
    function countLeadingKorean(str) {
        var i = 0;
        while (i < str.length && isKoreanCode(str.charCodeAt(i))) i++;
        return i;
    }

    // 뒤에서 연속된 한글 문자 개수
    function countTrailingKorean(str) {
        var i = str.length - 1;
        while (i >= 0 && isKoreanCode(str.charCodeAt(i))) i--;
        return str.length - 1 - i;
    }


    // ═══════════════════════════════════════════════════════════════════
    // 2. 한글→영문 단어 사전  (NFC 음절형 + NFD 자모형 양쪽 등록)
    //
    //  마지막 NFC : U+B9C8 U+C9C0 U+B9C9
    //  마지막 NFD : U+1106 U+1161  U+110C U+1175  U+1106 U+1161 U+11A8
    //              (ㅁㅏ)         (ㅈㅣ)          (ㅁㅏㄱ)
    //
    //  세로   NFC : U+C138 U+B85C
    //  세로   NFD : U+1109 U+1166  U+1105 U+1169
    //              (ㅅㅔ)         (ㄹㅗ)
    // ═══════════════════════════════════════════════════════════════════
    var WORD_MAP = [
        {
            nfc: '\uB9C8\uC9C0\uB9C9P',                          // 마지막P
            nfd: '\u1106\u1161\u110C\u1175\u1106\u1161\u11A8P',
            english: 'LastP'
        },
        {
            nfc: '\uC138\uB85C',                                  // 세로
            nfd: '\u1109\u1166\u1105\u1169',
            english: 'STEP123'
        }
        // 필요 시 추가:
        // { nfc: '...', nfd: '...', english: '...' }
    ];

    function lookupWord(str) {
        for (var i = 0; i < WORD_MAP.length; i++) {
            if (str === WORD_MAP[i].nfc || str === WORD_MAP[i].nfd) {
                return WORD_MAP[i].english;
            }
        }
        return null;
    }


    // ═══════════════════════════════════════════════════════════════════
    // 3. basename 변환 (확장자 제외)
    // ═══════════════════════════════════════════════════════════════════
    function transformBase(base) {

        // ── 패턴 A: 접두 제거 ──────────────────────────────────────────
        // 한글+(괄호선택)_XXX  →  XXX
        // 예) 간지_STEP1 / 간지(B)_STEP1
        var leadLen = countLeadingKorean(base);
        if (leadLen > 0) {
            var tail = base.slice(leadLen);

            // 선택적 (…) 건너뛰기
            if (tail.length > 0 && tail.charAt(0) === '(') {
                var closeIdx = tail.indexOf(')');
                if (closeIdx >= 0) tail = tail.slice(closeIdx + 1);
            }

            // 다음이 _ 이면 접두 패턴 확정
            if (tail.length > 0 && tail.charAt(0) === '_') {
                var afterUnderscore = tail.slice(1);
                // 접두 제거 후에도 한글이 남으면 단어 사전 조회
                // 예) 간지_세로 → 세로 → STEP123
                if (hasKorean(afterUnderscore)) {
                    return lookupWord(afterUnderscore); // null 이면 미지원으로 처리
                }
                return afterUnderscore;
            }
        }

        // ── 패턴 B: 접미 제거 ──────────────────────────────────────────
        // PREFIX + 한글+(괄호선택)  →  PREFIX
        // 예) 1P간지(B) → 1P  /  마지막P간지(B) → LastP

        // 끝의 (…) 임시 제거
        var stripped = base;
        if (base.charAt(base.length - 1) === ')') {
            var pIdx = base.lastIndexOf('(');
            if (pIdx > 0) stripped = base.slice(0, pIdx);
        }

        var trailLen = countTrailingKorean(stripped);
        if (trailLen > 0) {
            var prefix = stripped.slice(0, stripped.length - trailLen);

            if (prefix.length === 0) return null; // 전체가 한글

            if (!hasKorean(prefix)) {
                // 단순 ASCII 접두사: "1P", "2P" 등
                return prefix;
            } else {
                // 한글 포함 접두사: "마지막P" 등 → 사전 참조
                return lookupWord(prefix);
            }
        }

        return null; // 해당 패턴 없음
    }


    // ═══════════════════════════════════════════════════════════════════
    // 4. 파일명(확장자 포함) 변환
    // ═══════════════════════════════════════════════════════════════════
    function transformFilename(filename) {
        if (!hasKorean(filename)) return null;

        var dot  = filename.lastIndexOf('.');
        var base = (dot !== -1) ? filename.slice(0, dot) : filename;
        var ext  = (dot !== -1) ? filename.slice(dot)    : '';

        var newBase = transformBase(base);
        if (!newBase || newBase === base) return null;

        return newBase + ext;
    }


    // ═══════════════════════════════════════════════════════════════════
    // 5. 파일 탐색 (대소문자 무관)
    // ═══════════════════════════════════════════════════════════════════
    function findFile(folders, name) {
        var nameLower = name.toLowerCase();
        for (var i = 0; i < folders.length; i++) {
            var folder = folders[i];
            if (!folder || !folder.exists) continue;

            var direct = new File(folder.absoluteURI + '/' + name);
            if (direct.exists) return direct;

            var items = folder.getFiles();
            for (var j = 0; j < items.length; j++) {
                if (items[j] instanceof File &&
                    items[j].name.toLowerCase() === nameLower) {
                    return items[j];
                }
            }
        }
        return null;
    }


    // ═══════════════════════════════════════════════════════════════════
    // 6. 메인 루프
    // ═══════════════════════════════════════════════════════════════════
    var successCount = 0, skipCount = 0, unknownCount = 0, failCount = 0;
    var log = [];
    var links = doc.links;

    // ── 탐색 폴더 사전 수집 ──────────────────────────────────────────────────
    // 끊긴 링크는 filePath 가 없는 경우가 많으므로,
    // 정상 링크(LINK_NORMAL / LINK_OUT_OF_DATE)의 폴더 + 문서 폴더를 기본값으로 사용.
    var globalFolders = [];

    function addFolderUniq(folder) {
        if (!folder || !folder.exists) return;
        for (var k = 0; k < globalFolders.length; k++) {
            if (globalFolders[k].absoluteURI === folder.absoluteURI) return;
        }
        globalFolders.push(folder);
    }

    // 1) 문서 폴더
    if (doc.saved) addFolderUniq(doc.filePath);

    // 2) 정상 링크들의 폴더 (가장 확실한 경로 소스)
    for (var li = 0; li < links.length; li++) {
        if (links[li].status !== LinkStatus.LINK_MISSING) {
            try {
                addFolderUniq(new File(links[li].filePath).parent);
            } catch (e) {}
        }
    }

    // 3) 끊긴 링크라도 filePath 가 있으면 수집
    for (var li2 = 0; li2 < links.length; li2++) {
        if (links[li2].status === LinkStatus.LINK_MISSING) {
            try {
                addFolderUniq(new File(links[li2].filePath).parent);
            } catch (e) {}
        }
    }

    // 4) 그래도 없으면 사용자에게 폴더 직접 선택 요청
    if (globalFolders.length === 0) {
        alert('링크 파일의 폴더를 자동으로 찾지 못했습니다.\n다음 화면에서 새 파일명(.ai)이 있는 폴더를 선택해 주세요.');
        var chosen = Folder.selectDialog('새 .ai 파일이 있는 폴더를 선택하세요');
        if (!chosen) { alert('폴더 선택이 취소되었습니다. 스크립트를 종료합니다.'); return; }
        globalFolders.push(chosen);
    }

    var globalFolderNames = [];
    for (var gf = 0; gf < globalFolders.length; gf++) {
        globalFolderNames.push(globalFolders[gf].fsName);
    }
    log.push('[정보] 탐색 폴더:\n       ' + globalFolderNames.join('\n       ') + '\n');

    for (var i = links.length - 1; i >= 0; i--) {
        var link = links[i];
        if (link.status !== LinkStatus.LINK_MISSING) continue;

        var origName = link.name;

        // 한글 없음 → 스킵
        if (!hasKorean(origName)) {
            log.push('[스킵  ] ' + origName);
            skipCount++;
            continue;
        }

        var newName = transformFilename(origName);

        // 변환 규칙 미해당
        if (!newName) {
            log.push('[미지원] ' + origName + '  (알 수 없는 패턴 — 수동 처리 필요)');
            unknownCount++;
            continue;
        }

        // 개별 링크 폴더 우선, 없으면 globalFolders 사용
        var searchFolders = globalFolders.slice(); // 복사
        try {
            var origFile = new File(link.filePath);
            if (origFile.parent && origFile.parent.exists) {
                searchFolders.unshift(origFile.parent); // 최우선
            }
        } catch (e) {}

        var found = findFile(searchFolders, newName);

        if (found) {
            try {
                link.relink(found);
                log.push('[성공  ] ' + origName + '  →  ' + newName);
                successCount++;
            } catch (e) {
                log.push('[오류  ] ' + origName + '  →  ' + newName +
                         '\n         (' + e.message + ')');
                failCount++;
            }
        } else {
            log.push('[미발견] ' + origName + '  →  ' + newName);
            failCount++;
        }
    }


    // ═══════════════════════════════════════════════════════════════════
    // 7. 결과 보고
    // ═══════════════════════════════════════════════════════════════════
    var msg  = '==============================\n';
    msg     += '   링크 재연결 완료\n';
    msg     += '==============================\n\n';
    msg     += ' 성공:    ' + successCount  + '개\n';
    msg     += ' 스킵:    ' + skipCount     + '개  (한글 없음)\n';
    msg     += ' 미지원:  ' + unknownCount  + '개  (알 수 없는 패턴)\n';
    msg     += ' 실패:    ' + failCount     + '개\n';

    if (unknownCount > 0) {
        msg += '\n※ [미지원] 항목은 스크립트에 정의되지 않은\n';
        msg += '  한글 패턴입니다. 팀장에게 규칙 추가 요청하세요.\n';
    }
    if (failCount > 0) {
        msg += '\n※ [미발견] 항목은 변환된 파일명의 파일이\n';
        msg += '  원본 폴더에 존재하지 않습니다.\n';
    }

    if (log.length > 0) {
        msg += '\n------------------------------\n';
        msg += '상세 로그\n';
        msg += '------------------------------\n';
        msg += log.join('\n');
    } else {
        msg += '\n처리할 끊어진 링크가 없습니다.';
    }

    alert(msg);

}());
