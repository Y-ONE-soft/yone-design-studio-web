// [ENGINE TEMPLATE] 기존 완성 .indd → 보충 데이터(fill) 추출
// 스펙(JSON)이 지정한 (섹션, 코드) 칸을 뽑아 merge_select.load_fill 형식으로
// 저장한다. 소스 문서는 열기만 하고 **저장하지 않는다**.
//
// ⚠ ExtendScript 함정 — `PDF`, `prompt` 는 내장 읽기전용 전역이다.
//    변수명으로 쓰면 대입이 실패하며 스크립트가 조용히 죽는다(로그도 안 남음).
//    아래는 pmt / outPath 처럼 회피한 이름을 쓴다.
// ⚠ 밑줄은 문자스타일로 걸린 경우가 많아 textStyleRanges.underline 로는
//    0개로 잡힌다. 문자 단위로 appliedCharacterStyle 이름까지 본다.
#target indesign
(function () {
    var SPEC_PATH = "__SPEC_PATH__";
    var LOG_PATH = "__LOG_PATH__";

    var _b = [];
    function W(s) {
        _b.push(s);
        var f = new File(LOG_PATH);
        f.encoding = "UTF-8"; f.lineFeed = "Unix";
        f.open("w"); f.write(_b.join("\n") + "\n"); f.close();
    }
    function esc(s) {
        s = String(s);
        var o = "", i, c;
        for (i = 0; i < s.length; i++) {
            c = s.charAt(i);
            if (c === '"') o += '\\"';
            else if (c === "\\") o += "\\\\";
            else if (c < " ") o += " ";
            else o += c;
        }
        return o;
    }

    W("추출 시작");
    try {
        var spf = new File(SPEC_PATH);
        spf.encoding = "UTF-8"; spf.open("r");
        var spec = eval("(" + spf.read() + ")");
        spf.close();

        function openRO(path) {
            var i;
            for (i = 0; i < app.documents.length; i++) {
                try {
                    if (String(app.documents[i].fullName) ==
                            String(new File(path))) {
                        return { doc: app.documents[i], ours: false };
                    }
                } catch (e) {}
            }
            return { doc: app.open(new File(path), false), ours: true };
        }
        function pageOf(d, n) {
            var p = null;
            try { p = d.pages.item(String(n)); } catch (e) {}
            if (!p || !p.isValid) { p = d.pages[n - 1]; }
            return p;
        }
        function ulOf(ch) {
            var u = false;
            try { u = (ch.underline === true); } catch (e1) {}
            if (u) { return true; }
            try {
                var cs = ch.appliedCharacterStyle;
                if (cs && String(cs.name).indexOf("밑줄") >= 0) {
                    return true;
                }
            } catch (e2) {}
            return false;
        }
        function parasOf(tf) {
            var out = [], i, j;
            var ps = tf.paragraphs;
            for (i = 0; i < ps.length; i++) {
                var p = ps[i];
                var txt = String(p.contents).replace(/[\r\n]+$/, "");
                if (txt === "") { continue; }
                var runs = [], buf = "", cur = null;
                var chs = p.characters;
                for (j = 0; j < chs.length; j++) {
                    var c = String(chs[j].contents);
                    if (c === "\r" || c === "\n") { continue; }
                    var u = ulOf(chs[j]);
                    if (cur === null) { cur = u; buf = c; }
                    else if (u === cur) { buf += c; }
                    else { runs.push({ t: buf, ul: cur }); cur = u; buf = c; }
                }
                if (cur !== null && buf !== "") { runs.push({ t: buf, ul: cur }); }
                out.push({ text: txt, runs: runs });
            }
            return out;
        }
        function isKorPrompt(t) {
            return /[가-힣]/.test(t) && /(고르|것은|것을|적절)/.test(t);
        }

        var RESULT = {};
        function put(step, code, paras, pmt) {
            if (!RESULT[step]) { RESULT[step] = {}; }
            RESULT[step][code] = { paras: paras, pmt: pmt || "" };
            W("  " + step + " " + code + ": 단락 " + paras.length
              + (pmt ? " / 발문" : ""));
        }

        var si, ii, pi, fi;
        for (si = 0; si < spec.sources.length; si++) {
            var src = spec.sources[si];
            var A = openRO(src.indd);
            W("소스: " + A.doc.name + " (" + src.mode + ")");
            for (ii = 0; ii < src.items.length; ii++) {
                var it = src.items[ii];
                if (src.mode === "marker") {
                    for (pi = 0; pi < it.pages.length; pi++) {
                        var pg = pageOf(A.doc, it.pages[pi]);
                        var tfs = pg.textFrames;
                        for (fi = 0; fi < tfs.length; fi++) {
                            try {
                                var gb = tfs[fi].geometricBounds;
                                if (gb[0] < 20) { continue; }
                                var pr = parasOf(tfs[fi]);
                                if (pr.length < 2) { continue; }
                                var m = pr[0].text.match(/^\s*\[(\d{1,3})\]\s*$/);
                                if (!m) { continue; }
                                var code = it.marker_map[m[1]];
                                if (!code) { continue; }
                                put(it.step, code, pr.slice(1), "");
                            } catch (e3) {
                                W("  [오류] p" + it.pages[pi] + " frame "
                                  + fi + ": " + (e3.message || e3));
                            }
                        }
                    }
                } else if (src.mode === "style") {
                    // 단락스타일로 칸을 특정한다 — 가로판 완성본은 한 페이지에
                    // 상단(A1_어법 선택)과 하단(A1_어법 선택 하단)이 같이
                    // 있어 y 좌표로는 안전하게 못 가른다.
                    var spg = pageOf(A.doc, it.page);
                    var stfs = spg.textFrames.everyItem().getElements();
                    var sacc = [], spmt = "";
                    for (fi = 0; fi < stfs.length; fi++) {
                        try {
                            var sname = "";
                            var sps = stfs[fi].paragraphs;
                            for (var sk2 = 0; sk2 < sps.length && sk2 < 3;
                                    sk2++) {
                                var nm = String(
                                    sps[sk2].appliedParagraphStyle.name);
                                if (nm === it.style) { sname = nm; break; }
                            }
                            if (!sname) { continue; }
                            var spr = parasOf(stfs[fi]);
                            for (var sk3 = 0; sk3 < spr.length; sk3++) {
                                var st3 = spr[sk3].text
                                    .replace(/\uFFFC/g, "")
                                    .replace(/^\s+/, "");
                                if (st3 === "") { continue; }
                                if (isKorPrompt(st3) && st3.length < 80) {
                                    if (spmt === "") { spmt = st3; }
                                    continue;
                                }
                                spr[sk3].text = st3;
                                if (spr[sk3].runs.length > 0) {
                                    spr[sk3].runs[0].t =
                                        String(spr[sk3].runs[0].t)
                                        .replace(/\uFFFC/g, "")
                                        .replace(/^\s+/, "");
                                    if (spr[sk3].runs[0].t === "") {
                                        spr[sk3].runs.shift();
                                    }
                                }
                                sacc.push(spr[sk3]);
                            }
                        } catch (e5) {
                            W("  [오류] p" + it.page + " frame " + fi + ": "
                              + (e5.message || e5));
                        }
                    }
                    put(it.step, it.code, sacc, spmt);
                } else {
                    var bpg = pageOf(A.doc, it.page);
                    var btfs = bpg.textFrames.everyItem().getElements();
                    var acc = [], pmt = "";
                    for (fi = 0; fi < btfs.length; fi++) {
                        try {
                            var bgb = btfs[fi].geometricBounds;
                            if (bgb[0] < (it.y_min || 150)) { continue; }
                            var bpr = parasOf(btfs[fi]);
                            for (var bk = 0; bk < bpr.length; bk++) {
                                var t = bpr[bk].text
                                    .replace(/￼/g, "").replace(/^\s+/, "");
                                if (t === "") { continue; }
                                if (isKorPrompt(t) && t.length < 80) {
                                    if (pmt === "") { pmt = t; }
                                    continue;
                                }
                                bpr[bk].text = t;
                                if (bpr[bk].runs.length > 0) {
                                    bpr[bk].runs[0].t =
                                        String(bpr[bk].runs[0].t)
                                        .replace(/￼/g, "")
                                        .replace(/^\s+/, "");
                                    if (bpr[bk].runs[0].t === "") {
                                        bpr[bk].runs.shift();
                                    }
                                }
                                acc.push(bpr[bk]);
                            }
                        } catch (e4) {
                            W("  [오류] p" + it.page + " frame " + fi + ": "
                              + (e4.message || e4));
                        }
                    }
                    put(it.step, it.code, acc, pmt);
                }
            }
            if (A.ours) { A.doc.close(SaveOptions.NO); }
        }

        var js = "{", firstStep = true, sk, ck, qi, ri;
        for (sk in RESULT) {
            if (!RESULT.hasOwnProperty(sk)) { continue; }
            if (!firstStep) { js += ","; }
            firstStep = false;
            js += '"' + esc(sk) + '":{';
            var firstCode = true;
            for (ck in RESULT[sk]) {
                if (!RESULT[sk].hasOwnProperty(ck)) { continue; }
                if (!firstCode) { js += ","; }
                firstCode = false;
                var ent = RESULT[sk][ck];
                js += '"' + esc(ck) + '":{"prompt":"' + esc(ent.pmt)
                    + '","paras":[';
                for (qi = 0; qi < ent.paras.length; qi++) {
                    if (qi) { js += ","; }
                    js += '{"text":"' + esc(ent.paras[qi].text) + '","runs":[';
                    for (ri = 0; ri < ent.paras[qi].runs.length; ri++) {
                        if (ri) { js += ","; }
                        js += '{"t":"' + esc(ent.paras[qi].runs[ri].t)
                            + '","ul":'
                            + (ent.paras[qi].runs[ri].ul ? "true" : "false")
                            + "}";
                    }
                    js += "]}";
                }
                js += "]}";
            }
            js += "}";
        }
        js += "}";

        var outPath = new File(spec.out);
        var od = outPath.parent;
        if (!od.exists) { od.create(); }
        outPath.encoding = "UTF-8"; outPath.lineFeed = "Unix";
        outPath.open("w"); outPath.write(js); outPath.close();
        W("저장: " + spec.out + " (" + js.length + "자)");
        W("===== 추출 완료 =====");
    } catch (eMain) {
        W("[오류] " + (eMain.message || eMain));
    }
})();
