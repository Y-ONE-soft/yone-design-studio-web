// 세로 변환 Phase 1 — 실전(O) 스레드를 지문 경계에서 분할한다.
//
// 프레임 중간에서 시작하는 지문(26년 6월: 30·33·26)은 앞 지문과 페이지를
// 공유한다. 그 지문이 자기 페이지에서 시작하도록,
//   1) 공유 페이지 뒤에 새 페이지를 만들고 프레임을 스레드에 끼운 뒤
//   2) 분할 오프셋에 프레임 브레이크를 (그 페이지의 남은 프레임 수 + 1)회 넣어
//      경계 이후 텍스트를 새 페이지로 밀어낸다.
//
// 대상은 **문서 뒤에서 앞으로** 처리한다 — 앞에서 처리하면 뒤 대상의
// 페이지 번호/프레임 내용이 캐스케이드로 밀려 오프셋이 어긋난다.
//
// ES3. 페이지 add 후에는 프레임 참조를 반드시 다시 잡는다(지정자 무효화).
var settingsPath = "__LOG_PATH__";
var DOC_PATH = "__DOC_PATH__";
var CFG_PATH = "__CFG_PATH__";
var LOG_PATH = "__LOG_PATH__";

var LOG = new File(LOG_PATH);
LOG.encoding = "UTF-8"; LOG.lineFeed = "Unix"; LOG.open("w");
function L(m) { LOG.writeln(m); }

function readJSON(p) {
    var f = new File(p); f.encoding = "UTF-8";
    if (!f.open("r")) { throw "설정 파일 open 실패: " + p; }
    var s = f.read(); f.close();
    return eval("(" + s + ")");
}
function bodyFrames(pg) {
    var all = pg.textFrames.everyItem().getElements(), out = [];
    for (var i = 0; i < all.length; i++) {
        if (all[i].geometricBounds[0] > 0) { out.push(all[i]); }
    }
    out.sort(function (a, b) { return a.geometricBounds[1] - b.geometricBounds[1]; });
    return out;
}
function nchars(f) { try { return f.characters.length; } catch (e) { return 0; } }

var d = null;
try {
    L("분할 시작: " + DOC_PATH);
    var cfg = readJSON(CFG_PATH);
    d = app.open(new File(DOC_PATH), false);
    try { d.adjustLayoutPreferences.enableAdjustLayout = false; } catch (e) {}
    d.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
    L("페이지 " + d.pages.length + "개, 대상 " + cfg.targets.length + "건");

    var tg = cfg.targets.slice(0);
    tg.sort(function (a, b) { return b.page - a.page; });   // 뒤 → 앞

    for (var t = 0; t < tg.length; t++) {
        var T = tg[t];
        var pi = T.page - 1;
        var pg = d.pages[pi];
        if (pg.name !== String(T.page)) {
            throw "페이지 불일치: 기대 " + T.page + " 실제 " + pg.name;
        }
        var frs = bodyFrames(pg);
        var idx = -1;
        for (var i = 0; i < frs.length; i++) {
            if (String(frs[i].id) === String(T.fid)) { idx = i; }
        }
        if (idx < 0) { throw "대상 프레임 미발견 (p" + T.page + " fid " + T.fid + ")"; }
        var breaks = frs.length - idx;          // 남은 프레임 수 + 1
        var lastFrame = frs[frs.length - 1];
        var geo = [];
        for (var g = 0; g < frs.length; g++) { geo.push(frs[g].geometricBounds.slice(0)); }
        var props = [];
        for (var g2 = 0; g2 < frs.length; g2++) {
            props.push({ tfp: frs[g2].textFramePreferences.properties,
                         os: frs[g2].appliedObjectStyle,
                         lyr: frs[g2].itemLayer });
        }
        var master = pg.appliedMaster;
        var beforeChars = 0;
        for (var c0 = 0; c0 < frs.length; c0++) { beforeChars += nchars(frs[c0]); }
        L("[" + T.code + "] p" + T.page + " 단 " + (idx + 1) + "/" + frs.length +
          " → 프레임브레이크 " + breaks + "회, 오프셋 " + T.offset);

        // 1) 새 페이지 + 프레임 (페이지 add 후 참조 재해석 필수)
        var np = d.pages.add(LocationOptions.AFTER, pg);
        if (master) { np.appliedMaster = master; }
        var pgR = d.pages[pi];                 // 재해석
        var frsR = bodyFrames(pgR);
        var tail = frsR[frsR.length - 1];      // 공유 페이지 마지막 프레임
        var newFrames = [];
        for (var k = 0; k < geo.length; k++) {
            var nf = np.textFrames.add(props[k].lyr);
            nf.geometricBounds = geo[k];
            try { nf.textFramePreferences.properties = props[k].tfp; } catch (eP) {}
            try { nf.appliedObjectStyle = props[k].os; } catch (eO) {}
            newFrames.push(nf);
        }
        // 새 프레임들을 서로 잇고, 공유 페이지 마지막 프레임 뒤에 끼운다
        for (var n2 = 1; n2 < newFrames.length; n2++) {
            newFrames[n2].previousTextFrame = newFrames[n2 - 1];
        }
        newFrames[0].previousTextFrame = tail;
        L("   새 페이지 p" + np.name + " 프레임 " + newFrames.length + "개 스레드 삽입");

        // 2) 분할 오프셋에 프레임 브레이크 (역순 삽입 — 오프셋 불변)
        var frs2 = bodyFrames(d.pages[pi]);
        var target = null;
        for (var i2 = 0; i2 < frs2.length; i2++) {
            if (String(frs2[i2].id) === String(T.fid)) { target = frs2[i2]; }
        }
        if (!target) { throw "브레이크 대상 프레임 소실 (fid " + T.fid + ")"; }
        var ip = target.characters[T.offset].insertionPoints[0];
        for (var b = 0; b < breaks; b++) {
            ip.contents = SpecialCharacters.FRAME_BREAK;
        }
        L("   프레임 브레이크 " + breaks + "회 삽입 완료");
    }

    var ovf = 0;
    for (var s = 0; s < d.stories.length; s++) { if (d.stories[s].overflows) { ovf++; } }
    L("분할 후: 페이지 " + d.pages.length + ", 오버셋 스토리 " + ovf);
    if (ovf > 0) { throw "오버셋 " + ovf + "건 발생 — 저장하지 않음"; }

    d.save(new File(DOC_PATH));
    L("저장 완료");
    d.close(SaveOptions.NO);
    d = null;
    L("분할 완료");
} catch (e) {
    L("[오류] " + e);
    try { if (d) { d.close(SaveOptions.NO); } } catch (e2) {}
    L("중단");
}
LOG.close();
