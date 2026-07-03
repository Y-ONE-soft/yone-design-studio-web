// template_spec 추출 본문 — lib.jsxinc 뒤에 concat되어 실행됨 (jsxbuild).
// .indd 템플릿의 기계가독 스펙: 마스터/페이지/스타일 인벤토리/프레임 배치.
// 문서는 읽기 전용으로 열고 저장하지 않는다 (SaveOptions.NO).

var INDD = "__INDD_PATH__";
var OUT = "__OUT_PATH__";

var doc = null;
try {
    wlog("스펙 추출 시작: " + INDD);
    doc = app.open(File(INDD), false);

    var spec = {
        source: String(doc.name),
        pages: doc.pages.length,
        masters: [],
        paragraph_styles: [],
        character_styles: [],
        page_map: [],
        labeled_items: []
    };

    // ── 마스터 ───────────────────────────────────────────────────────────
    var masters = doc.masterSpreads.everyItem().getElements();
    for (var mi = 0; mi < masters.length; mi++) {
        var m = masters[mi];
        var mframes = 0;
        try { mframes = m.textFrames.length; } catch (e) {}
        spec.masters.push({
            name: String(m.name),
            prefix: String(m.namePrefix),
            base_name: String(m.baseName),
            text_frames: mframes
        });
    }
    wlog("마스터 " + spec.masters.length + "개");

    // ── 스타일 인벤토리 (그룹 재귀) ──────────────────────────────────────
    function collectParaStyles(container, acc) {
        var sts = container.paragraphStyles.everyItem().getElements();
        for (var i = 0; i < sts.length; i++) {
            var nm = String(sts[i].name);
            if (nm.charAt(0) === "[") { continue; }   // [기본 단락] 등 내장
            acc.push(styleFullPath(sts[i]));
        }
        var grps = container.paragraphStyleGroups.everyItem().getElements();
        for (var g = 0; g < grps.length; g++) { collectParaStyles(grps[g], acc); }
    }
    function collectCharStyles(container, acc) {
        var sts = container.characterStyles.everyItem().getElements();
        for (var i = 0; i < sts.length; i++) {
            var nm = String(sts[i].name);
            if (nm.charAt(0) === "[") { continue; }
            acc.push(styleFullPath(sts[i]));
        }
        var grps = container.characterStyleGroups.everyItem().getElements();
        for (var g = 0; g < grps.length; g++) { collectCharStyles(grps[g], acc); }
    }
    collectParaStyles(doc, spec.paragraph_styles);
    collectCharStyles(doc, spec.character_styles);
    wlog("단락스타일 " + spec.paragraph_styles.length + " / 문자스타일 " + spec.character_styles.length);

    // ── 페이지 맵 (적용 마스터 + 프레임 배치 + 내용 앞부분) ──────────────
    var pages = doc.pages.everyItem().getElements();
    for (var pi = 0; pi < pages.length; pi++) {
        var pg = pages[pi];
        var entry = {
            index: pi,
            name: String(pg.name),
            master: pg.appliedMaster ? String(pg.appliedMaster.name) : null,
            frames: []
        };
        var frames = pg.textFrames;
        for (var fi = 0; fi < frames.length; fi++) {
            var fr = frames[fi];
            var head = "";
            var nparas = 0;
            try {
                head = String(fr.contents).substr(0, 60);
                nparas = fr.paragraphs.length;
            } catch (e) {}
            var gb = [];
            try { gb = fr.geometricBounds; } catch (e) {}
            entry.frames.push({
                label: String(fr.label || ""),
                bounds: [Math.round(gb[0]), Math.round(gb[1]),
                         Math.round(gb[2]), Math.round(gb[3])],
                paragraphs: nparas,
                head: head
            });
        }
        spec.page_map.push(entry);
        if (pi % 20 === 0) { wlog("진행: 페이지 " + (pi + 1) + "/" + pages.length); }
    }

    // ── 라벨 붙은 아이템 (TF 버튼 등 인라인 소스) ────────────────────────
    var items = doc.allPageItems;
    for (var ii = 0; ii < items.length; ii++) {
        try {
            var lb = items[ii].label;
            if (lb && String(lb).length > 0) {
                spec.labeled_items.push({
                    label: String(lb),
                    type: String(items[ii].constructor.name)
                });
            }
        } catch (e) {}
    }

    writeJSON(OUT, spec);
    doc.close(SaveOptions.NO);
    doc = null;
    wlog("스펙 추출 완료: 페이지 " + spec.pages + " / 마스터 " + spec.masters.length +
         " / 단락스타일 " + spec.paragraph_styles.length);
} catch (e) {
    wlog("[오류] " + e);
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
}
