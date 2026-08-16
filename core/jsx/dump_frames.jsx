// 프레임 단위 덤프 — 세로 변환(convert_to_vertical) S1 슬롯↔지문 매핑용.
// core/jsx/dump_stories.jsx 는 스토리 단위라 "이 프레임이 몇 번째 지문인가"를
// 알 수 없다. 이 스크립트는 텍스트 프레임 1개 = 레코드 1개로 덤프한다.
// ES3 — let/const/화살표/JSON 내장 금지.
var settingsPath = "__LOG_PATH__";  // core.indesign.runner 호환용 (러너가 존재만 검사 — 미사용)
var INDD_PATH = "__INDD_PATH__";
var OUT_PATH  = "__OUT_PATH__";
var LOG_PATH  = "__LOG_PATH__";

var LOG = new File(LOG_PATH);
LOG.encoding = "UTF-8"; LOG.lineFeed = "Unix"; LOG.open("w");
function L(m) { LOG.writeln(m); }

function esc(s) {
    if (s === null || s === undefined) { return '""'; }
    s = String(s);
    var out = '"';
    for (var i = 0; i < s.length; i++) {
        var c = s.charCodeAt(i);
        if (c === 0x22) { out += '\\"'; }
        else if (c === 0x5C) { out += "\\\\"; }
        else if (c === 0x0A) { out += "\\n"; }
        else if (c === 0x0D) { out += "\\n"; }
        else if (c === 0x09) { out += "\\t"; }
        else if (c < 0x20) { out += " "; }
        else { out += s.charAt(i); }
    }
    return out + '"';
}
function num(n) { return String(Math.round(n * 10) / 10); }

var d = null;
try {
    L("프레임 덤프 시작: " + INDD_PATH);
    d = app.open(new File(INDD_PATH), false);
    d.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
    L("페이지 " + d.pages.length + "개");

    var recs = [];
    for (var pi = 0; pi < d.pages.length; pi++) {
        if (pi % 25 === 0) { L("진행: 페이지 " + pi + "/" + d.pages.length); }
        var pg = d.pages[pi];
        var master = "";
        try { master = pg.appliedMaster ? pg.appliedMaster.name : ""; } catch (eM) {}
        var side = "";
        try {
            side = (pg.side === PageSideOptions.LEFT_HAND) ? "L"
                 : ((pg.side === PageSideOptions.RIGHT_HAND) ? "R" : "S");
        } catch (eS) {}
        var frs = pg.textFrames.everyItem().getElements();
        for (var fi = 0; fi < frs.length; fi++) {
            var f = frs[fi];
            var gb = [0, 0, 0, 0];
            try { gb = f.geometricBounds; } catch (eB) {}
            var nch = 0;
            try { nch = f.characters.length; } catch (eC) { nch = 0; }
            var head = "", tail = "";
            if (nch > 0) {
                try { head = f.texts[0].contents.substr(0, 160); } catch (eH) {}
                try {
                    var all = f.texts[0].contents;
                    tail = all.substr(Math.max(0, all.length - 80));
                } catch (eT) {}
            }
            var sid = "", prev = "", next = "";
            try { sid = f.parentStory.id; } catch (eI) {}
            try { prev = f.previousTextFrame ? f.previousTextFrame.id : ""; } catch (eP) {}
            try { next = f.nextTextFrame ? f.nextTextFrame.id : ""; } catch (eN) {}
            var ovf = false;
            try { ovf = f.overflows; } catch (eO) {}

            recs.push("{" +
                '"page":' + esc(pg.name) +
                ',"pidx":' + pi +
                ',"master":' + esc(master) +
                ',"side":' + esc(side) +
                ',"fid":' + esc(String(f.id)) +
                ',"sid":' + esc(String(sid)) +
                ',"prev":' + esc(String(prev)) +
                ',"next":' + esc(String(next)) +
                ',"chars":' + nch +
                ',"overflow":' + (ovf ? "true" : "false") +
                ',"gb":[' + num(gb[0]) + "," + num(gb[1]) + "," + num(gb[2]) + "," + num(gb[3]) + "]" +
                ',"head":' + esc(head) +
                ',"tail":' + esc(tail) +
                "}");
        }
    }

    var out = new File(OUT_PATH);
    out.encoding = "UTF-8"; out.lineFeed = "Unix";
    out.open("w");
    out.write('{"indd":' + esc(INDD_PATH) +
              ',"page_count":' + d.pages.length +
              ',"frames":[' + recs.join(",") + "]}");
    out.close();
    L("쓰기 완료: 프레임 " + recs.length + "개");

    d.close(SaveOptions.NO);
    d = null;
    L("덤프 완료");
} catch (e) {
    L("[오류] " + e);
    try { if (d) { d.close(SaveOptions.NO); } } catch (e2) {}
}
LOG.close();
