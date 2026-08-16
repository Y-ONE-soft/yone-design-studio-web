// 세로 변환 후처리 — 슬롯별 세로 마스터(A~E) 적용 + 홀수 사이클 M 메모 패딩.
//
// 원본 전체(C)는 A/C/O 세 마스터만 쓴다. 세로본은 슬롯마다 전용 마스터를 쓴다
// (정본 실측: 사이클 = A2 B2 C2 D2 E2 + O + M). 재배치까지 끝난 산출물에
// 슬롯 순번대로 마스터를 얹고, 사이클 길이가 홀수면 M 메모 페이지를 넣어
// 좌우 파리티를 맞춘다.
//
// 마스터가 문서에 없으면 세로 마스터 원본에서 복제해 온다.
// ES3. 페이지 add 후 참조 무효화를 피하려 사이클을 **뒤에서 앞으로** 처리한다.
var settingsPath = "__LOG_PATH__";
var DOC_PATH = "__DOC_PATH__";
var CFG_PATH = "__CFG_PATH__";
var LOG_PATH = "__LOG_PATH__";

var LOG = new File(LOG_PATH);
LOG.encoding = "UTF-8"; LOG.lineFeed = "Unix"; LOG.open("w");
function L(m) { LOG.writeln(m); }
function readJSON(p) {
    var f = new File(p); f.encoding = "UTF-8";
    if (!f.open("r")) { throw "설정 open 실패: " + p; }
    var s = f.read(); f.close();
    return eval("(" + s + ")");
}

var d = null, srcDoc = null;
try {
    var cfg = readJSON(CFG_PATH);
    L("후처리 시작: " + DOC_PATH);
    d = app.open(new File(DOC_PATH), false);
    try { d.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e) {}
    L("페이지 " + d.pages.length + ", 사이클 " + cfg.cycles.length);

    // ── 필요한 마스터 확보 (없으면 세로 마스터 원본에서 복제) ────────────
    var need = ["A-마스터", "B-마스터", "C-마스터", "D-마스터", "E-마스터",
                "O-마스터", "M-마스터"];
    var missing = [];
    for (var i = 0; i < need.length; i++) {
        if (!d.masterSpreads.itemByName(need[i]).isValid) { missing.push(need[i]); }
    }
    L("문서 내 마스터 부족: " + (missing.length ? missing.join(",") : "없음"));
    if (missing.length) {
        if (!cfg.master_src) { throw "마스터 원본 경로 미지정인데 " + missing.join(",") + " 부족"; }
        srcDoc = app.open(new File(cfg.master_src), false);
        for (var m2 = 0; m2 < missing.length; m2++) {
            var sm = srcDoc.masterSpreads.itemByName(missing[m2]);
            if (!sm.isValid) { L("[경고] 원본에도 없음: " + missing[m2]); continue; }
            sm.duplicate(LocationOptions.AT_END, d);
            L("   마스터 복제: " + missing[m2]);
        }
        srcDoc.close(SaveOptions.NO);
        srcDoc = null;
    }

    // ── 사이클 뒤 → 앞 (페이지 삽입이 앞 사이클 번호를 밀지 않도록) ──────
    var cycles = cfg.cycles.slice(0);
    cycles.sort(function (a, b) { return b.start - a.start; });
    var applied = 0, padded = 0;
    for (var c = 0; c < cycles.length; c++) {
        var cy = cycles[c];
        // 슬롯 마스터 적용
        for (var k = 0; k < cy.slot_masters.length; k++) {
            var pgNo = cy.start + k;
            if (pgNo > cy.end) { break; }
            var pg = d.pages[pgNo - 1];
            var want = d.masterSpreads.itemByName(cy.slot_masters[k]);
            if (!want.isValid) { L("[경고] 마스터 없음: " + cy.slot_masters[k]); continue; }
            var curName = pg.appliedMaster ? pg.appliedMaster.name : "";
            if (curName !== cy.slot_masters[k]) {
                pg.appliedMaster = want;
                applied++;
            }
        }
        // 홀수 사이클 → M 메모 1p
        if (cy.pad) {
            var ref = d.pages[cy.end - 1];
            var np = d.pages.add(LocationOptions.AFTER, ref);
            var mm = d.masterSpreads.itemByName("M-마스터");
            if (mm.isValid) { np.appliedMaster = mm; }
            padded++;
            L("   [" + cy.code + "] 메모 페이지 삽입 (사이클 " + (cy.end - cy.start + 1) + "p → 짝수)");
        }
    }
    L("마스터 적용 " + applied + "p, 메모 패딩 " + padded + "p, 최종 " + d.pages.length + "p");

    var ovf = 0;
    for (var s = 0; s < d.stories.length; s++) { if (d.stories[s].overflows) { ovf++; } }
    if (ovf > 0) { throw "오버셋 " + ovf + "건 — 저장하지 않음"; }
    L("오버셋 0 확인");

    d.save(new File(DOC_PATH));
    L("저장 완료");
    d.close(SaveOptions.NO);
    d = null;
    L("후처리 완료");
} catch (e) {
    L("[오류] " + e);
    try { if (srcDoc) { srcDoc.close(SaveOptions.NO); } } catch (e3) {}
    try { if (d) { d.close(SaveOptions.NO); } } catch (e2) {}
    L("중단");
}
LOG.close();
