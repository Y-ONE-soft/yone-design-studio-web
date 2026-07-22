// 답란 전용 단락스타일 생성 본문 (W45) — lib.jsxinc 뒤에 concat (jsxbuild).
//
// 기존 스타일(보통 지문 스타일)을 duplicate()해 새 이름으로 만들고,
// 들여쓰기(firstLineIndent/leftIndent)를 0으로 내린다. 그 외 속성은 전부
// 승계 — 답란은 "지문과 같은 서식인데 들여쓰기만 없는" 것이 사용자 확정 스펙.
//
// 원칙:
//   - 이미 같은 이름의 스타일이 있으면 **아무것도 하지 않는다**(멱등 skip).
//   - 원본 스타일을 찾지 못하면 생성하지 않고 [오류]로 보고 (침묵 금지).
//   - 저장은 SAVE=1 일 때만. 0이면 dry-run (열고 검사만 후 close NO).
//   - 문서는 창 없이 열고(app.open(f, false)) 끝나면 반드시 닫는다.

var INDD = "__INDD_PATH__";
var OUT = "__OUT_PATH__";
var SRC_STYLE = "__SRC_STYLE__";     // "STEP 03 > 실전 문제 지문 올림포스_"
var DST_STYLE = "__DST_STYLE__";     // "STEP 03 > S_답란"
var DO_SAVE = "__DO_SAVE__";         // "1" | "0"

function _tail(path) {
    var parts = String(path).split(">");
    return parts[parts.length - 1].replace(/^\s+|\s+$/g, "");
}

var doc = null;
var rep = {
    indd: INDD, src: SRC_STYLE, dst: DST_STYLE,
    saved: false, created: false, skipped: false, error: null,
    before: null, after: null
};
try {
    wlog("답란 스타일 작업 시작: " + INDD);
    doc = app.open(File(INDD), false);

    var existing = findParagraphStyleByPath(doc, DST_STYLE);
    if (existing) {
        rep.skipped = true;
        rep.after = {
            firstLineIndent: Number(existing.firstLineIndent),
            leftIndent: Number(existing.leftIndent)
        };
        wlog("이미 존재 — 건너뜀: " + DST_STYLE);
    } else {
        var src = findParagraphStyleByPath(doc, SRC_STYLE);
        if (!src) {
            throw "원본 스타일을 찾을 수 없음: " + SRC_STYLE;
        }
        rep.before = {
            firstLineIndent: Number(src.firstLineIndent),
            leftIndent: Number(src.leftIndent),
            pointSize: Number(src.pointSize),
            leading: String(src.leading)
        };
        var dup = src.duplicate();          // 같은 그룹에 "… 복사" 이름으로 생성
        dup.name = _tail(DST_STYLE);
        dup.firstLineIndent = 0;
        dup.leftIndent = 0;
        rep.created = true;
        rep.after = {
            firstLineIndent: Number(dup.firstLineIndent),
            leftIndent: Number(dup.leftIndent),
            pointSize: Number(dup.pointSize),
            leading: String(dup.leading)
        };
        wlog("생성: " + styleFullPath(dup)
             + " (들여쓰기 " + rep.before.firstLineIndent + "/"
             + rep.before.leftIndent + " → 0/0)");
    }

    // 검증 — 저장 전에 실제 경로로 재해결되는지 확인 (침묵 no-op 방지)
    var check = findParagraphStyleByPath(doc, DST_STYLE);
    if (!check) { throw "생성 후 재해결 실패: " + DST_STYLE; }
    if (Number(check.firstLineIndent) !== 0 || Number(check.leftIndent) !== 0) {
        throw "들여쓰기 0 적용 실패: " + check.firstLineIndent + "/"
              + check.leftIndent;
    }

    if (DO_SAVE === "1" && rep.created) {
        doc.save();
        rep.saved = true;
        wlog("저장 완료: " + INDD);
        doc.close(SaveOptions.YES);
    } else {
        doc.close(SaveOptions.NO);
    }
    doc = null;
    writeJSON(OUT, rep);
    wlog("답란 스타일 작업 완료");
} catch (e) {
    rep.error = String(e);
    wlog("[오류] " + e);
    try { writeJSON(OUT, rep); } catch (e3) {}
    try { if (doc) { doc.close(SaveOptions.NO); } } catch (e2) {}
    wlog("답란 스타일 작업 완료");
}
