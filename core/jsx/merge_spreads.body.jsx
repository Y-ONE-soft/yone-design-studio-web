// core/jsx/merge_spreads.body.jsx — 다중 강 spread 통합 (suneungteukgang_workbook_v2)
//
// 강별로 조판된 .indd들을 받아 첫 파일을 통합본 경로로 saveAs한 뒤, 나머지
// 파일의 spread를 끝에 duplicate(LocationOptions.AT_END)해 한 파일로 합친다
// (v1 SuneungteukgangWorkbookEngine._build_merge_jsx와 동일 의미론).
//
// sources 항목은 경로 문자열 또는 { path, drop_first, drop_last } 객체.
//   drop_first/drop_last — 그 소스의 첫/마지막 **단독 페이지 스프레드**
//   (표지/뒷표지)를 빼고 합친다. 여러 강을 한 권으로 묶을 때 표지가 강마다
//   반복되는 것을 막는다. 경계 스프레드가 단독 페이지가 아니면 [오류]로
//   멈춘다 (2페이지를 통째로 날리는 침묵 손실 금지).
// cfg.parity_pad — 소스 사이 홀수 파리티 채움 (기본 true = 종전 동작).
//   표지를 떼어 의도적으로 홀수로 만든 합본에서는 false로 끈다.
// 추가로 검수 게이트 입력(stats JSON)을 남긴다:
//   - 소스별 spread/페이지 수 + 전체 단락 텍스트 (강별 단어셋 대조용 —
//     소스 문서를 어차피 여는 김에 수확, 별도 InDesign 세션 불필요)
//   - 통합본 spread/페이지 수, duplicate 실패 건수
// 게이트 판정 자체는 파이썬(_gate_merge)이 통합본을 dump_indd로 재오픈해 수행
// — 저장된 파일 기준 검증이라 saveAs silent fail도 잡는다.
//
// ExtendScript ES3 — let/const/화살표/템플릿 리터럴/JSON 내장 금지.
// 플레이스홀더 __MERGE_SETTINGS_PATH__ 는 build_jsx가 절대경로로 치환.
// 완료 마커: "스프레드 머지 완료" (러너 completion_marker와 일치해야 함)

var MERGE_SETTINGS_PATH = "__MERGE_SETTINGS_PATH__";

(function () {
    function readJSONFile(path) {
        var f = new File(path);
        if (!f.exists) { throw "머지 설정 파일 없음: " + path; }
        f.encoding = "UTF-8";
        f.open("r");
        var s = f.read();
        f.close();
        return eval("(" + s + ")");
    }

    // 문서 전체 단락 텍스트 수확 — 벌크 게터 (개별 DOM 접근은 대형 문서에서
    // 수 분 소요). everyItem() 일괄 호출은 단락 1개면 스칼라 반환 → 배열화.
    function docParagraphTexts(doc) {
        var out = [];
        var stories = doc.stories.everyItem().getElements();
        for (var si = 0; si < stories.length; si++) {
            var texts = [];
            try {
                texts = stories[si].paragraphs.everyItem().contents;
                if (!(texts instanceof Array)) { texts = [texts]; }
            } catch (e) { texts = []; }
            for (var pi = 0; pi < texts.length; pi++) {
                var t = texts[pi];
                if (typeof t != "string") { t = String(t); }
                out.push(t);
            }
            if (si % 20 === 0) {   // 하트비트 — 러너 행 감지 방지
                wlog("  텍스트 수확: 스토리 " + (si + 1) + "/" + stories.length);
            }
        }
        return out;
    }

    // sources 항목 정규화 — 문자열(구계약) / 객체(신계약) 모두 수용
    function normSource(item) {
        if (typeof item == "string") {
            return { path: item, drop_first: false, drop_last: false };
        }
        return { path: item.path,
                 drop_first: !!item.drop_first,
                 drop_last: !!item.drop_last };
    }

    // 표지/뒷표지 경계 스프레드는 반드시 '단독 페이지'여야 뗀다 —
    // 2페이지 스프레드를 통째로 버리면 본문이 조용히 사라진다.
    function assertSolo(spread, label) {
        var n = spread.pages.length;
        if (n !== 1) {
            throw ("경계 스프레드가 단독 페이지가 아님(" + n + "p): " + label +
                   " — 표지 제외 조건을 확인하세요");
        }
    }

    // 이미 열려 있는 문서인가 — 사용자가 작업 중인 창을 스크립트가 닫지
    // 않도록. (app.open은 열린 문서면 그 문서를 그대로 돌려준다.)
    function alreadyOpen(file) {
        for (var di = 0; di < app.documents.length; di++) {
            try {
                if (app.documents[di].saved &&
                        app.documents[di].fullName &&
                        String(app.documents[di].fullName) === String(file)) {
                    return true;
                }
            } catch (eAO) {}
        }
        return false;
    }

    var dst = null;
    var src = null;
    try {
        var cfg = readJSONFile(MERGE_SETTINGS_PATH);
        var srcs = cfg.sources;        // 절대경로 배열 (첫 항목 = base)
        var parityPad = (cfg.parity_pad === false) ? false : true;
        var srcMeta = [];
        for (var ni = 0; ni < srcs.length; ni++) {
            srcMeta.push(normSource(srcs[ni]));
        }
        var mergedPath = cfg.merged;   // 통합본 저장 절대경로
        var statsPath = cfg.stats;     // 게이트 입력 JSON 절대경로
        wlog("머지 시작: " + srcs.length + "개 → " + mergedPath);

        var stats = { sources: [], merged: {}, dup_fail: 0,
                      parity_pads: 0 };

        var firstFile = new File(srcMeta[0].path);
        if (!firstFile.exists) { throw "소스 없음: " + srcMeta[0].path; }
        dst = app.open(firstFile);
        wlog("base 열림: " + dst.name + " (spreads=" + dst.spreads.length + ")");
        stats.sources.push({
            path: srcMeta[0].path,
            spreads: dst.spreads.length,
            pages: dst.pages.length,
            start_offset: 0,
            paras: docParagraphTexts(dst)
        });
        // saveAs — 원본(첫 강 indd)은 그대로 두고 통합본 경로에 저장
        dst.save(new File(mergedPath));
        wlog("saveAs 완료: " + mergedPath);
        if (srcMeta[0].drop_last) {
            assertSolo(dst.spreads.lastItem(), "base 마지막");
            dst.spreads.lastItem().remove();
            wlog("  base 뒷표지 스프레드 제외 (pages=" + dst.pages.length + ")");
        }
        if (srcMeta[0].drop_first) {
            assertSolo(dst.spreads.firstItem(), "base 첫");
            dst.spreads.firstItem().remove();
            wlog("  base 표지 스프레드 제외 (pages=" + dst.pages.length + ")");
        }

        for (var i = 1; i < srcs.length; i++) {
            // W24 r14 — 홀수 파리티 채움: delete 모드가 홀수 페이지 강
            // 산출물을 만들 수 있어(27강 문제본 9p 실증), 그대로 이어붙이면
            // 뒤 강의 표지/간지가 인쇄 왼쪽으로 뒤집히고 스프레드 재편성이
            // 일어난다 (32≠31 실측). 다음 강을 붙이기 전에 dst가 홀수면
            // 빈 페이지(마스터 없음) 1장을 끝에 추가해 짝수 정렬한다.
            if (parityPad && dst.pages.length % 2 === 1) {
                try {
                    var padPg = dst.pages.add(LocationOptions.AT_END);
                    try { padPg.appliedMaster = NothingEnum.NOTHING; }
                    catch (ePM) {
                        try { padPg.appliedMaster = null; } catch (ePM2) {}
                    }
                    stats.parity_pads++;
                    wlog("  홀수 파리티 채움 페이지 추가 (dst.pages="
                         + dst.pages.length + ")");
                } catch (ePad) {
                    wlog("  [경고] 파리티 채움 페이지 추가 실패: " + ePad);
                }
            }
            var srcFile = new File(srcMeta[i].path);
            if (!srcFile.exists) { throw "소스 없음: " + srcMeta[i].path; }
            var srcWasOpen = alreadyOpen(srcFile);
            src = app.open(srcFile);
            if (srcWasOpen) {
                wlog("  (이미 열려 있던 문서 — 머지 후 닫지 않음)");
            }
            stats.sources.push({
                path: srcMeta[i].path,
                spreads: src.spreads.length,
                pages: src.pages.length,
                start_offset: dst.pages.length,
                paras: docParagraphTexts(src)
            });
            // 컬렉션 인덱싱 금지 — everyItem().getElements() 캐시 후 순회
            var spreads = src.spreads.everyItem().getElements();
            var sFrom = 0, sTo = spreads.length - 1;
            if (srcMeta[i].drop_first) {
                assertSolo(spreads[0], src.name + " 첫");
                sFrom = 1;
            }
            if (srcMeta[i].drop_last) {
                assertSolo(spreads[spreads.length - 1], src.name + " 마지막");
                sTo = spreads.length - 2;
            }
            wlog("append: " + src.name + " (spreads=" + spreads.length +
                 ", 사용 " + (sTo - sFrom + 1) + " [" + (sFrom + 1) + ".." +
                 (sTo + 1) + "])");
            for (var s = sFrom; s <= sTo; s++) {
                try {
                    spreads[s].duplicate(LocationOptions.AT_END, dst);
                } catch (e) {
                    stats.dup_fail++;
                    wlog("  [경고] spread duplicate 실패 #" + s + ": " + e);
                }
                if (s % 5 === 0) {   // 하트비트
                    wlog("  진행: spread " + (s + 1) + "/" + spreads.length +
                         " (dst.pages=" + dst.pages.length + ")");
                }
            }
            if (!srcWasOpen) { src.close(SaveOptions.NO); }
            src = null;
        }

        stats.merged = {
            path: mergedPath,
            spreads: dst.spreads.length,
            pages: dst.pages.length
        };
        wlog("통합본 저장 중... (spreads=" + dst.spreads.length +
             " pages=" + dst.pages.length + " dup_fail=" + stats.dup_fail + ")");
        dst.save();
        dst.close(SaveOptions.YES);
        dst = null;

        writeJSON(statsPath, stats);
        wlog("스프레드 머지 완료: " + srcs.length + "개 강 → " + mergedPath);
    } catch (e) {
        wlog("[오류] 머지 실패: " + e);
        try { if (src) { src.close(SaveOptions.NO); } } catch (e2) {}
        try { if (dst) { dst.close(SaveOptions.NO); } } catch (e3) {}
    }
})();
