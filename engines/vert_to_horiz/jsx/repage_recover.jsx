#target indesign
// 유실 페이지 복구 — 세로 페이지를 가로에 **페이지째** 다시 넣는다.
//
// 프레임 단위 복제는 짝을 못 찾은 세로 프레임을 버려 내용이 잘린다.
// 여기서는 (1) 세로 각 페이지의 문단이 가로에 다 있는지 확인하고
// (2) 빠진 페이지는 대응 가로 페이지를 찾아 세로 페이지 복제본으로 교체한다.
//
// 토큰: __LOG__ / __VERTI__ / __HORIZ__ / __DRY__ (true 면 진단만)
// 호출: scripts/mt_pipeline.py --repair (기본 꺼짐)
//
// ⚠ 이건 **최후 수단**이다. 세로 페이지를 그대로 넣으므로 그 페이지만
//    세로판 레이아웃이 된다(판형·단 구성이 가로와 다르다). 근본 해결은
//    run.jsx 의 프레임 매칭을 고치는 것이고, 이 도구는 납품 직전 구멍을
//    메우는 용도다. 돌린 뒤에는 교체된 페이지를 반드시 눈으로 확인할 것.
//    실행 전 '_복구전백업.indd' 를 자동으로 남긴다.
(function () {
    var LOG_PATH = "__LOG__";
    var VERTI = "__VERTI__";
    var HORIZ = "__HORIZ__";
    var DRY = __DRY__;
    var _b = [];
    function W(s) {
        _b.push(String(s));
        var f = new File(LOG_PATH);
        f.encoding = "UTF-8"; f.lineFeed = "Unix";
        f.open("w"); f.write(_b.join("\n") + "\n"); f.close();
    }
    function norm(s) { return String(s).replace(/[\s　￼\r\n\t]/g, ""); }
    function openRO(path) {
        var fo = new File(path);
        for (var d = 0; d < app.documents.length; d++) {
            try { if (String(app.documents[d].fullName) === String(fo)) return { doc: app.documents[d], ours: false }; } catch (e) {}
        }
        return { doc: app.open(fo, false), ours: true };
    }
    // 페이지의 본문 문단(길이 12자 이상) 목록
    function paras(page) {
        var out = [], sp = page.parent;
        for (var i = 0; i < sp.textFrames.length; i++) {
            var tf = sp.textFrames[i];
            if (!tf.parentPage || tf.parentPage.id !== page.id) continue;
            var ps;
            try { ps = tf.paragraphs; } catch (e) { continue; }
            for (var j = 0; j < ps.length; j++) {
                var t = "";
                try { t = String(ps[j].contents); } catch (e2) { continue; }
                var n = norm(t);
                if (n.length >= 12) { out.push(n); }
            }
        }
        return out;
    }
    W("페이지 복구 시작" + (DRY ? " (모의 실행)" : ""));
    var V = null, H = null;
    try {
        V = openRO(VERTI); H = openRO(HORIZ);
        // 가로 전체 문단 집합
        var hset = {}, hpages = {};
        for (var p = 0; p < H.doc.pages.length; p++) {
            var pl = paras(H.doc.pages[p]);
            for (var k = 0; k < pl.length; k++) {
                hset[pl[k]] = 1;
                if (!hpages[pl[k]]) { hpages[pl[k]] = []; }
                hpages[pl[k]].push(p + 1);
            }
        }
        var bad = [];
        for (var vp = 0; vp < V.doc.pages.length; vp++) {
            var vl = paras(V.doc.pages[vp]);
            if (vl.length === 0) continue;
            // 같은 지문이 여러 섹션에 반복되므로 첫 등장 페이지를 쓰면
            // 엉뚱한 곳을 가리킨다. 이 세로 페이지의 문단이 **가장 많이
            // 모여 있는** 가로 페이지를 대응으로 본다(다수결).
            var miss = 0, tally = {};
            for (var m = 0; m < vl.length; m++) {
                var cands = hpages[vl[m]];
                if (!cands) { miss++; continue; }
                for (var c = 0; c < cands.length; c++) {
                    tally[cands[c]] = (tally[cands[c]] || 0) + 1;
                }
            }
            if (miss === 0) continue;
            var bestP = 0, bestN = 0;
            for (var kk in tally) {
                if (tally[kk] > bestN) { bestN = tally[kk]; bestP = parseInt(kk, 10); }
            }
            bad.push({ vp: vp + 1, miss: miss, total: vl.length,
                       hp: bestP, score: bestN });
        }
        W("유실 있는 세로 페이지 " + bad.length + "개");
        for (var b = 0; b < bad.length; b++) {
            W("  세로 p" + bad[b].vp + " : 문단 " + bad[b].total +
              "개 중 " + bad[b].miss + "개 없음 / 가로 대응 p" +
              (bad[b].hp || "?") + " (일치 " + bad[b].score + "개)");
        }
        if (!DRY) {
            // 되돌릴 수 있게 사본을 먼저 남긴다
            try {
                var bak = new File(String(H.doc.fullName).replace(
                    /\.indd$/i, "_복구전백업.indd"));
                H.doc.saveACopy(bak);
                W("백업: " + decodeURI(bak.name));
            } catch (eB) { W("[경고] 백업 실패: " + (eB.message || eB)); }
            var fixed = 0, usedHp = {};
            // 뒤에서 앞으로 (페이지 번호 밀림 방지)
            for (var b2 = bad.length - 1; b2 >= 0; b2--) {
                var it = bad[b2];
                if (!it.hp) { W("  [건너뜀] 세로 p" + it.vp + " 대응 가로 페이지 못 찾음"); continue; }
                try {
                    var ref = H.doc.pages[it.hp - 1];
                    V.doc.pages[it.vp - 1].duplicate(LocationOptions.AFTER, ref);
                    // 한 가로 페이지를 여러 세로 페이지가 지목하는 경우가 있다
                    // (빈칸어법: 세로 2페이지 → 가로 1페이지). 그때 교체하면
                    // 나중 것이 앞 것을 덮어써 내용이 계속 진동한다.
                    // 첫 지목만 교체하고, 이후는 **뒤에 삽입**한다.
                    if (usedHp[it.hp]) {
                        fixed++;
                        W("  [삽입] 가로 p" + it.hp + " 뒤 ← 세로 p" + it.vp);
                    } else {
                        usedHp[it.hp] = 1;
                        ref.remove();
                        fixed++;
                        W("  [교체] 가로 p" + it.hp + " ← 세로 p" + it.vp);
                    }
                } catch (eR) {
                    W("  [실패] 세로 p" + it.vp + " : " + (eR.message || eR));
                }
            }
            W("교체 " + fixed + "건");
            if (fixed > 0) { H.doc.save(); W("저장 완료"); }
        }
        if (V.ours) V.doc.close(SaveOptions.NO);
        W("===== 페이지 복구 완료 =====");
    } catch (eM) {
        W("[오류] " + (eM.message || eM));
        W("===== 페이지 복구 완료 =====");
    }
})();
