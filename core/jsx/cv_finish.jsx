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

    // ── 마스터 확보 — **이름이 아니라 내용으로 판정한다.** ────────────────
    // 전체(C) 원본에도 A~D 라는 이름의 마스터가 있지만 그건 전체버전용이다
    // (2026-08-27 실측: 전체(C)의 A·C 는 개체 33/텍스트프레임 15, 세로 템플릿은
    // 46/18). 이름만 보고 "있다"고 넘기면 전체버전 마스터가 세로본에 그대로
    // 남는다. 세로본의 마스터 공급원은 언제나
    // `[원본]워크북(세로)_내지.indd` 다.
    var need = ["A-마스터", "B-마스터", "C-마스터", "D-마스터", "E-마스터",
                "O-마스터", "M-마스터"];
    function itemCount(ms) {
        var n = -1;
        try { n = ms.allPageItems.length; } catch (e) {}
        return n;
    }
    if (!cfg.master_src) { throw "마스터 원본(master_src) 경로 미지정"; }
    srcDoc = app.open(new File(cfg.master_src), false);
    var stale = [];      // 이름은 같은데 내용이 다른 것 — 교체 대상
    var missing = [];
    for (var i = 0; i < need.length; i++) {
        var sm0 = srcDoc.masterSpreads.itemByName(need[i]);
        if (!sm0.isValid) { L("[경고] 템플릿에 없음: " + need[i]); continue; }
        var dm0 = d.masterSpreads.itemByName(need[i]);
        if (!dm0.isValid) { missing.push(need[i]); continue; }
        var cS = itemCount(sm0), cD = itemCount(dm0);
        if (cS !== cD) {
            stale.push(need[i]);
            L("   내용 불일치: " + need[i] + " (문서 " + cD + "개체 / 템플릿 " +
              cS + "개체) — 템플릿 것으로 교체");
        }
    }
    L("마스터 — 부족 " + (missing.length ? missing.join(",") : "없음") +
      " / 교체 " + (stale.length ? stale.join(",") : "없음"));

    // 교체 대상은 먼저 이름을 비켜 준다(복제본이 원래 이름을 갖도록).
    // MasterSpread.name 은 **읽기 전용**이다 — namePrefix/baseName 으로 바꾼다
    // (2026-08-27 실측: name 대입은 "'name'은(는) 읽기 전용 속성입니다" 로 실패,
    // 그 결과 낡은 전체버전 마스터가 그대로 적용됐다).
    var retired = [];
    for (var r0 = 0; r0 < stale.length; r0++) {
        var dmR = d.masterSpreads.itemByName(stale[r0]);
        if (!dmR.isValid) { continue; }
        // InDesign 마스터 접두어는 **4자 제한**이다 ("_oldA" 5자는 거부됨 —
        // 2026-08-28 실측). 한 글자만 덧붙인다.
        // itemByName 이 준 것은 **이름 기반 지정자**다. 이름을 바꾸면 그 참조가
        // 나중에 같은 이름으로 들어온 새 마스터를 가리킨다 — 그대로 remove 하면
        // 방금 가져온 템플릿 마스터를 지운다(2026-08-28 실측: A0 C0).
        // 그래서 참조가 아니라 **바뀐 이름 문자열**을 기억한다.
        try {
            dmR.namePrefix = "o" + dmR.namePrefix;
            retired.push(dmR.name);
            L("   낡은 마스터 비켜둠: " + dmR.name);
        } catch (eR) {
            throw "낡은 마스터 이름 변경 실패(" + stale[r0] + "): " + eR +
                  " — 교체를 진행하면 전체버전 마스터가 그대로 남는다";
        }
    }
    var bring = missing.concat(stale);
    for (var m2 = 0; m2 < bring.length; m2++) {
        var sm = srcDoc.masterSpreads.itemByName(bring[m2]);
        if (!sm.isValid) { L("[경고] 템플릿에 없음: " + bring[m2]); continue; }
        var wantPrefix = sm.namePrefix, wantBase = sm.baseName;
        var nm = null;
        try { nm = sm.duplicate(LocationOptions.AT_END, d); }
        catch (eD) { L("[경고] 마스터 복제 실패: " + bring[m2] + " — " + eD); continue; }
        // 복제본은 prefix 가 자동 배정될 수 있다 — 원본과 같게 맞춘다
        try {
            if (nm.namePrefix !== wantPrefix) { nm.namePrefix = wantPrefix; }
            if (nm.baseName !== wantBase) { nm.baseName = wantBase; }
        } catch (eP) {
            throw "복제본 이름 설정 실패(" + bring[m2] + " → " + nm.name + "): " +
                  eP + " — 이대로 두면 엉뚱한 이름의 마스터만 늘어난다";
        }
        L("   마스터 가져옴: " + bring[m2] + " → " + nm.name);
    }
    srcDoc.close(SaveOptions.NO);
    srcDoc = null;
    for (var f0 = 0; f0 < bring.length; f0++) {
        if (!d.masterSpreads.itemByName(bring[f0]).isValid) {
            throw "마스터 확보 실패: " + bring[f0] + " — 이름이 맞지 않는다";
        }
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
    // 낡은 마스터 제거 — 이 시점엔 슬롯 적용이 끝나 참조가 없어야 한다.
    // 참조가 남아 있으면 제거 후 그 페이지가 [none] 이 되어 머리말·꼬리말이
    // 통째로 사라진다. 남은 페이지를 먼저 세어 보고, 있으면 멈춘다.
    var stillUsing = [];
    for (var pu = 0; pu < d.pages.length; pu++) {
        var mName = "";
        try { mName = d.pages[pu].appliedMaster ? d.pages[pu].appliedMaster.name : ""; }
        catch (ePU) {}
        for (var rn = 0; rn < retired.length; rn++) {
            if (mName === retired[rn]) { stillUsing.push(d.pages[pu].name); break; }
        }
    }
    if (stillUsing.length) {
        throw "낡은 전체버전 마스터를 아직 쓰는 페이지 " + stillUsing.length +
              "개 (p" + stillUsing.slice(0, 8).join(",") + ") — 제거하면 머리말이 " +
              "사라진다. 슬롯 적용 범위를 확인할 것";
    }
    var removed = 0;
    for (var rm = 0; rm < retired.length; rm++) {
        try {
            var msOld = d.masterSpreads.itemByName(retired[rm]);
            if (msOld.isValid) { msOld.remove(); removed++; L("   제거: " + retired[rm]); }
        } catch (eRM) { L("[경고] 낡은 마스터 제거 실패: " + retired[rm] + " — " + eRM); }
    }
    if (removed) { L("   낡은 전체버전 마스터 " + removed + "개 제거"); }

    L("마스터 적용 " + applied + "p, 메모 패딩 " + padded + "p, 최종 " + d.pages.length + "p");

    var ovf = 0;
    for (var s = 0; s < d.stories.length; s++) { if (d.stories[s].overflows) { ovf++; } }
    if (ovf > 0) { throw "오버셋 " + ovf + "건 — 저장하지 않음"; }
    L("오버셋 0 확인");

    d.save(new File(DOC_PATH));
    L("저장 완료");

    // PDF 는 반드시 여기서 — body 가 뽑은 PDF 는 마스터/패딩 이전 상태다.
    if (cfg.out_pdf) {
        try {
            var pf = new File(cfg.out_pdf);
            var preset = app.pdfExportPresets.itemByName("[고품질 인쇄]");
            if (!preset.isValid) { preset = app.pdfExportPresets.itemByName("[High Quality Print]"); }
            if (preset.isValid) { d.exportFile(ExportFormat.PDF_TYPE, pf, false, preset); }
            else { d.exportFile(ExportFormat.PDF_TYPE, pf, false); }
            L("PDF 내보내기 완료: " + cfg.out_pdf);
        } catch (ePdf) { L("[경고] PDF 내보내기 실패: " + ePdf); }
    }

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
