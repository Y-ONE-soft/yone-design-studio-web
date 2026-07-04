// core/jsx/merge_spreads.body.jsx — 다중 강 spread 통합 (suneungteukgang_workbook_v2)
//
// 강별로 조판된 .indd들을 받아 첫 파일을 통합본 경로로 saveAs한 뒤, 나머지
// 파일의 spread를 끝에 duplicate(LocationOptions.AT_END)해 한 파일로 합친다
// (v1 SuneungteukgangWorkbookEngine._build_merge_jsx와 동일 의미론).
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

    var dst = null;
    var src = null;
    try {
        var cfg = readJSONFile(MERGE_SETTINGS_PATH);
        var srcs = cfg.sources;        // 절대경로 배열 (첫 항목 = base)
        var mergedPath = cfg.merged;   // 통합본 저장 절대경로
        var statsPath = cfg.stats;     // 게이트 입력 JSON 절대경로
        wlog("머지 시작: " + srcs.length + "개 → " + mergedPath);

        var stats = { sources: [], merged: {}, dup_fail: 0 };

        var firstFile = new File(srcs[0]);
        if (!firstFile.exists) { throw "소스 없음: " + srcs[0]; }
        dst = app.open(firstFile);
        wlog("base 열림: " + dst.name + " (spreads=" + dst.spreads.length + ")");
        stats.sources.push({
            path: srcs[0],
            spreads: dst.spreads.length,
            pages: dst.pages.length,
            paras: docParagraphTexts(dst)
        });
        // saveAs — 원본(첫 강 indd)은 그대로 두고 통합본 경로에 저장
        dst.save(new File(mergedPath));
        wlog("saveAs 완료: " + mergedPath);

        for (var i = 1; i < srcs.length; i++) {
            var srcFile = new File(srcs[i]);
            if (!srcFile.exists) { throw "소스 없음: " + srcs[i]; }
            src = app.open(srcFile);
            stats.sources.push({
                path: srcs[i],
                spreads: src.spreads.length,
                pages: src.pages.length,
                paras: docParagraphTexts(src)
            });
            // 컬렉션 인덱싱 금지 — everyItem().getElements() 캐시 후 순회
            var spreads = src.spreads.everyItem().getElements();
            wlog("append: " + src.name + " (spreads=" + spreads.length + ")");
            for (var s = 0; s < spreads.length; s++) {
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
            src.close(SaveOptions.NO);
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
