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

    // 후처리 착수 전 오버셋 스냅샷 — 마스터 적용·패딩이 새로 만든 오버셋을
    // 구분하려면 "들어올 때" 값을 알아야 한다 (26년 9월 고1: body 산출물은
    // 1건이었는데 후처리 뒤 2건이 됐다).
    function _ovSnapshot(doc2) {
        var map = {};
        var sts2 = doc2.stories.everyItem().getElements();
        for (var i2 = 0; i2 < sts2.length; i2++) {
            var t2 = -1, sh2 = 0;
            try { t2 = sts2[i2].characters.length; } catch (e2) {}
            try {
                var cc2 = sts2[i2].textContainers;
                for (var j2 = 0; j2 < cc2.length; j2++) { sh2 += cc2[j2].characters.length; }
            } catch (e2) {}
            if (t2 !== sh2) { map[sts2[i2].id] = t2 - sh2; }
        }
        return map;
    }
    // 본문 프레임 기하 스냅샷 — 마스터를 갈아 끼우면 **마스터에서 오버라이드된
    // 본문 프레임이 새 마스터의 정의로 리셋**돼 크기가 달라질 수 있다. 그러면
    // 그 프레임의 글이 지면 밖으로 밀린다 (26년 9월 고1 260928: 4,793자가
    // 후처리 뒤에 숨었다 — 진입 스냅샷에서는 멀쩡했다). 적용 후 원래 크기로
    // 되돌린다.
    function _gbSnapshot(doc2) {
        var map = {};
        for (var p2 = 0; p2 < doc2.pages.length; p2++) {
            var fs2 = doc2.pages[p2].textFrames.everyItem().getElements();
            for (var f2 = 0; f2 < fs2.length; f2++) {
                try { map[fs2[f2].id] = fs2[f2].geometricBounds; } catch (e2) {}
            }
        }
        return map;
    }
    var gbBefore = _gbSnapshot(d);

    var ovBefore = _ovSnapshot(d);
    var _ovBn = 0;
    for (var _k in ovBefore) { _ovBn++; }
    L("후처리 진입 시 숨은 글자 있는 스토리 " + _ovBn + "개");

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
    // 마스터 교체가 바꿔 놓은 본문 프레임 크기 복원
    var _fixed = 0, _gone = 0;
    for (var p3 = 0; p3 < d.pages.length; p3++) {
        var fs3 = d.pages[p3].textFrames.everyItem().getElements();
        for (var f3 = 0; f3 < fs3.length; f3++) {
            var id3 = null;
            try { id3 = fs3[f3].id; } catch (e3) { continue; }
            var was = gbBefore[id3];
            if (!was) { continue; }
            var now = null;
            try { now = fs3[f3].geometricBounds; } catch (e3) { continue; }
            var diff = false;
            for (var k3 = 0; k3 < 4; k3++) {
                if (Math.abs(now[k3] - was[k3]) > 0.01) { diff = true; break; }
            }
            if (diff) {
                try { fs3[f3].geometricBounds = was; _fixed++; } catch (e3) { _gone++; }
            }
        }
    }
    if (_fixed || _gone) {
        L("   마스터 교체로 바뀐 본문 프레임 " + _fixed + "개 복원" +
          (_gone ? " (복원 실패 " + _gone + "개)" : ""));
        try { d.recompose(); } catch (e) {}
    }

    var ovAfter = _ovSnapshot(d);
    for (var _k2 in ovAfter) {
        if (ovBefore[_k2] === undefined) {
            L("[경고] 후처리가 새 오버셋을 만들었다: 스토리 " + _k2 + " — 숨은 글자 "
              + ovAfter[_k2] + "자");
        } else if (ovAfter[_k2] > ovBefore[_k2]) {
            L("[경고] 후처리로 오버셋 증가: 스토리 " + _k2 + " — " + ovBefore[_k2]
              + " → " + ovAfter[_k2] + "자");
        }
    }

    // 오버셋 판정 — 플래그만 보면 **무해한 것까지 막는다.**
    // 지문별로 끊긴 스토리는 마지막(메모 페이지) 프레임이 비어 있어도
    // overflows 가 켜지는 경우가 있다(26년 9월 고1 지문 260919 실측: 말미 CR
    // 을 지워도 안 풀림). 글자가 실제로 숨었는지는 **표시 문자 합**으로
    // 판정한다 — 컨테이너들에 보이는 문자 수가 스토리 전체와 같으면 유실이
    // 아니다. 다르면 글자가 프레임 밖에 숨은 것이므로 그대로 막는다.
    var ovf = 0, benign = 0;
    for (var s = 0; s < d.stories.length; s++) {
        var stO = d.stories[s];
        var flagged = false;
        try { flagged = stO.overflows; } catch (eO) { flagged = false; }
        if (!flagged) { continue; }
        var total = -1, shown = 0, okCount = true;
        try { total = stO.characters.length; } catch (eT) { okCount = false; }
        try {
            var csO = stO.textContainers;
            for (var cO = 0; cO < csO.length; cO++) {
                shown += csO[cO].characters.length;
            }
        } catch (eS) { okCount = false; }
        if (okCount && total >= 0 && shown === total) {
            benign++;
            L("   오버셋 플래그(무해): 스토리 " + stO.id + " — 표시 문자 " +
              shown + "/" + total + " 전량 인쇄");
            continue;
        }
        // 숨은 것이 **공백·개행뿐**이면 지면에 인쇄될 글자는 하나도 안 빠졌다.
        // 지문별 재스레드(STEP11)가 조각 경계마다 CR 을 되살리므로 그 CR 이
        // 마지막에 몇 자 밀려 나는 일이 있다(26년 9월 고1 260919: 10자).
        // 글자가 섞여 있으면 그대로 막는다 — 그건 진짜 유실이다.
        if (okCount && total > shown) {
            var hid = total - shown;
            var tailTxt = null;
            try {
                var allTxt = String(stO.texts[0].contents);
                tailTxt = allTxt.substr(allTxt.length - hid);
            } catch (eH) { tailTxt = null; }
            // 숨은 것이 **다음 지문의 코드 마커**뿐이면 인쇄에 영향이 없다.
            // 그 코드는 다음 묶음 첫 면에 온전히 찍히고, 여기 남은 잔여는
            // 어디에도 인쇄되지 않는다 (26년 9월 고1 260919: "{260920}\n다"
            // 10자). 길이를 40자로 묶어 진짜 유실이 섞여 드는 것을 막는다.
            if (tailTxt !== null && hid <= 40 && /^\s*\{\d{6}\}/.test(tailTxt)) {
                benign++;
                L("   오버셋 플래그(무해): 스토리 " + stO.id + " — 숨은 " + hid +
                  "자는 다음 지문 코드 잔여 (인쇄 글자 " + shown + "/" + total + ")");
                continue;
            }
            if (tailTxt !== null && !/[^\s\u00a0]/.test(tailTxt)) {
                benign++;
                L("   오버셋 플래그(무해): 스토리 " + stO.id + " — 숨은 " + hid +
                  "자가 전부 공백/개행 (인쇄 글자 " + shown + "/" + total + ")");
                continue;
            }
        }
        ovf++;
        var pgs = "", hd = "", hidTxt = "";
        try {
            var cs3 = stO.textContainers;
            for (var c3 = 0; c3 < cs3.length && c3 < 12; c3++) {
                if (cs3[c3].parentPage) { pgs += (pgs ? "," : "") + cs3[c3].parentPage.name; }
            }
        } catch (eP3) {}
        try { hd = String(stO.texts[0].contents).substr(0, 40); } catch (eH3) {}
        try {
            var at3 = String(stO.texts[0].contents);
            hidTxt = at3.substr(at3.length - (total - shown)).substr(0, 60);
        } catch (eT3) {}
        L("[오류] 오버셋: 스토리 " + stO.id + " — 표시 " + shown + "/" + total +
          " (글자가 프레임 밖에 숨었다) 면 " + pgs);
        L("        머리: " + hd.replace(/[\r\n]/g, " "));
        L("        숨은 글: " + hidTxt.replace(/[\r\n]/g, "\\n"));
    }
    if (ovf > 0) { throw "오버셋 " + ovf + "건 — 저장하지 않음"; }
    L("오버셋 0 확인" + (benign ? " (무해 플래그 " + benign + "건)" : ""));

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
