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

    // 좌표(page/fid/offset)가 아니라 **지문 코드 문자열로 매번 다시 찾는다.**
    // 한 건을 분할하면 그 뒤 텍스트가 프레임을 따라 밀리므로, 덤프 한 번으로
    // 잡은 좌표를 여러 건에 쓰면 뒤 대상이 어긋난다 (2026-08-27 실측:
    // [31] 단건은 새 페이지 왼쪽 단에서 시작 — 정상. [30]+[31] 동시에는
    // [31]이 오른쪽 단으로 밀리고 왼쪽 단이 빈칸).
    //
    // 목표는 하나다: **지문이 페이지 첫 프레임 머리에서 시작할 것.**
    // 브레이크는 한 번에 한 칸만 민다(연속 대입은 두 번째부터 no-op — 같은
    // 실측에서 breaks=2 가 1칸만 밀었다). 그래서 목표에 닿을 때까지 한 칸씩
    // 밀며 확인한다.
    // 스토리 캐시 — 문서 전체 findText 는 288p 에서 수십 초가 걸린다(실측:
    // 8건 × 6회 검색이 15분 타임아웃을 넘겼다). 대상들은 실전/영작 각각 한
    // 스토리에 모여 있으므로, 한 번 찾은 스토리를 재사용해 그 안에서만 찾는다.
    var _storyCache = {};

    function findInStory(st, needle) {
        if (!st || !st.isValid) { return null; }
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
        app.findChangeTextOptions.caseSensitive = false;
        app.findChangeTextOptions.wholeWord = false;
        app.findTextPreferences.findWhat = needle;
        var res = null;
        try { res = st.findText(); } catch (e) { res = null; }
        app.findTextPreferences = NothingEnum.NOTHING;
        return (res && res.length) ? res[0] : null;
    }

    function storyOf(t) {
        try { return t.parentStory; } catch (e) { return null; }
    }

    function findCached(key, needle, lo, hi) {
        var hit = findInStory(_storyCache[key], needle);
        if (hit) { return hit; }
        hit = findMark(needle, lo, hi);
        if (hit) { _storyCache[key] = storyOf(hit); }
        return hit;
    }

    function findMark(needle, lo, hi) {
        // lo/hi = 검색을 한정할 페이지 범위(1-based, 문서 순). 같은 코드
        // 표기가 다른 섹션에도 있어서(어휘·본문에도 [30]) 범위 없이 찾으면
        // 엉뚱한 곳을 자른다.
        app.findTextPreferences = NothingEnum.NOTHING;
        app.changeTextPreferences = NothingEnum.NOTHING;
        app.findChangeTextOptions.caseSensitive = false;
        app.findChangeTextOptions.wholeWord = false;
        app.findTextPreferences.findWhat = needle;
        var res = d.findText();
        app.findTextPreferences = NothingEnum.NOTHING;
        if (!res || !res.length) { return null; }
        if (!lo && !hi) { return res[0]; }
        for (var i = 0; i < res.length; i++) {
            var fr = frameOf(res[i]);
            var off = -1;
            try { off = fr.parentPage ? (fr.parentPage.documentOffset + 1) : -1; }
            catch (e) { off = -1; }
            if (off < 0) { continue; }
            if ((!lo || off >= lo) && (!hi || off <= hi)) { return res[i]; }
        }
        return null;
    }

    function frameOf(t) {
        try {
            var cs = t.parentTextFrames;
            return (cs && cs.length) ? cs[0] : null;
        } catch (e) { return null; }
    }

    function headState(t) {
        // 반환: {pg, idx, n, off} — 지문이 어느 페이지 몇 번째 단의 몇 자째인지
        var fr = frameOf(t);
        if (!fr) { return null; }
        var pg = null;
        try { pg = fr.parentPage; } catch (e) {}
        if (!pg) { return null; }
        var frs = bodyFrames(pg), idx = -1;
        for (var i = 0; i < frs.length; i++) {
            if (String(frs[i].id) === String(fr.id)) { idx = i; }
        }
        var off = 0;
        try { off = t.insertionPoints[0].index - fr.characters[0].index; } catch (e) { off = 0; }
        return { pg: pg, idx: idx, n: frs.length, off: off, frame: fr };
    }

    var HEAD_SLACK = 5;
    var MAX_NUDGE = 4;

    for (var t = 0; t < cfg.targets.length; t++) {
        var T = cfg.targets[t];
        var needle = T.find;
        if (!needle) {
            L("[" + T.code + "] 검색 문자열(find) 없음 — 건너뜀");
            continue;
        }
        var ckey = String(T.page_min) + "_" + String(T.page_max);
        var hit = findCached(ckey, needle, T.page_min, T.page_max);
        if (!hit) { throw "대상 미발견: " + needle; }
        var st0 = headState(hit);
        if (!st0) { throw "대상 프레임 해석 실패: " + needle; }
        L("   (" + (t + 1) + "/" + cfg.targets.length + " 검색 완료)");
        L("[" + T.code + "] 시작 위치 p" + st0.pg.name + " 단 " + (st0.idx + 1) +
          "/" + st0.n + " 오프셋 " + st0.off);

        if (st0.idx === 0 && st0.off <= HEAD_SLACK) {
            L("   이미 페이지 머리 — 분할 불필요");
            continue;
        }

        // 밀어낼 자리를 먼저 만든다 (프레임이 모자라면 오버셋 난다)
        var pgRef = st0.pg;
        var geo = [], props = [], master = pgRef.appliedMaster;
        var refFrames = bodyFrames(pgRef);
        for (var g = 0; g < refFrames.length; g++) {
            geo.push(refFrames[g].geometricBounds.slice(0));
            props.push({ tfp: refFrames[g].textFramePreferences.properties,
                         os: refFrames[g].appliedObjectStyle,
                         lyr: refFrames[g].itemLayer });
        }
        var np = d.pages.add(LocationOptions.AFTER, pgRef);
        if (master) { np.appliedMaster = master; }
        var tailFrames = bodyFrames(d.pages[pgRef.documentOffset]);
        var tail = tailFrames[tailFrames.length - 1];
        var newFrames = [];
        for (var k = 0; k < geo.length; k++) {
            var nf = np.textFrames.add(props[k].lyr);
            nf.geometricBounds = geo[k];
            try { nf.textFramePreferences.properties = props[k].tfp; } catch (eP) {}
            try { nf.appliedObjectStyle = props[k].os; } catch (eO) {}
            newFrames.push(nf);
        }
        for (var n2 = 1; n2 < newFrames.length; n2++) {
            newFrames[n2].previousTextFrame = newFrames[n2 - 1];
        }
        newFrames[0].previousTextFrame = tail;
        L("   새 페이지 p" + np.name + " 프레임 " + newFrames.length + "개 삽입");

        // 한 칸씩 밀며 페이지 머리에 닿을 때까지
        var nudges = 0;
        while (nudges < MAX_NUDGE) {
            var cur = findCached(ckey, needle, T.page_min, T.page_max);
            if (!cur) { throw "밀기 도중 대상 소실: " + needle; }
            var st = headState(cur);
            if (!st) { throw "밀기 도중 프레임 해석 실패: " + needle; }
            if (st.idx === 0 && st.off <= HEAD_SLACK) { break; }
            cur.insertionPoints[0].contents = SpecialCharacters.FRAME_BREAK;
            nudges++;
        }
        var fin = headState(findCached(ckey, needle, T.page_min, T.page_max));
        L("   브레이크 " + nudges + "회 → p" + (fin ? fin.pg.name : "?") +
          " 단 " + (fin ? (fin.idx + 1) : "?") + " 오프셋 " + (fin ? fin.off : "?"));
        if (!fin || fin.idx !== 0 || fin.off > HEAD_SLACK) {
            throw "[" + T.code + "] 페이지 머리로 보내지 못함 (브레이크 " +
                  nudges + "회 후에도)";
        }
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
