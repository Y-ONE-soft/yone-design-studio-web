#target illustrator

/*
 * 파이널 직전보충 표지 — yone-design-web 엔진용
 *
 * settings.json: {
 *   template_path, exam, school, grade,
 *   outputs: [ { vol, path, name }, ... ],
 *   log_path
 * }
 *
 * 각 output(vol)마다: 템플릿 열기 -> 정보줄/세종큰글씨/Vol 교체 ->
 *   앞표지+빈2P+뒤표지 4페이지 -> CMYK A4(도련없음) 고품질 PDF 출력.
 * 원본 템플릿은 저장하지 않음(PDF만). 완료 시 로그에 "DONE" 기록.
 */

var SETTINGS_PATH = "%%SETTINGS_PATH%%";

function readJSON(path){
    var f = new File(path);
    f.encoding = "UTF-8";
    f.open("r");
    var t = f.read();
    f.close();
    return eval("(" + t + ")");
}
var cfg = readJSON(SETTINGS_PATH);

var LOG = [];
function logln(s){ LOG.push(s); }
function flushLog(){
    var f = new File(cfg.log_path);
    f.encoding = "UTF-8";
    f.open("w");
    f.write(LOG.join("\n"));
    f.close();
}

// ── 문자열 유틸 ─────────────────────────────────────────────
function trim(s){ return String(s).replace(/^\s+/, "").replace(/\s+$/, ""); }
function noSpace(s){ return String(s).replace(/\s+/g, ""); }

// 한글 NFC 음절을 NFD 자모로 분해 (ExtendScript엔 normalize 없음 → NFC/NFD 혼용 비교 해소)
function toNFD(str){
    str = String(str);
    var out = "";
    for (var i=0;i<str.length;i++){
        var code = str.charCodeAt(i);
        if (code >= 0xAC00 && code <= 0xD7A3){
            var s = code - 0xAC00;
            out += String.fromCharCode(0x1100 + Math.floor(s/588));
            out += String.fromCharCode(0x1161 + Math.floor((s%588)/28));
            var t = s % 28;
            if (t > 0) out += String.fromCharCode(0x11A7 + t);
        } else {
            out += str.charAt(i);
        }
    }
    return out;
}
// "학기"(학기) / "고사"(고사) — NFD 정규화하여 부분일치에 사용
var NFD_HAKGI = toNFD("학기");
var NFD_GOSA  = toNFD("고사");

// ── 텍스트 프레임 찾기 ──────────────────────────────────────
function findInfoLine(doc){
    for (var i=0;i<doc.textFrames.length;i++){
        if (String(doc.textFrames[i].contents).indexOf("|") >= 0) return doc.textFrames[i];
    }
    return null;
}
function findVolFrame(doc){
    for (var i=0;i<doc.textFrames.length;i++){
        var c = trim(doc.textFrames[i].contents).toLowerCase();
        if (c.indexOf("vol") === 0) return doc.textFrames[i];
    }
    return null;
}
// 세종 전용 뒤표지 큰 글씨(시험기간). "|" 없고 NFD상 "학기"+"고사" 포함.
function findExamBigFrames(doc){
    var arr = [];
    for (var i=0;i<doc.textFrames.length;i++){
        var c = String(doc.textFrames[i].contents);
        if (c.indexOf("|") >= 0) continue;
        var n = toNFD(c);
        if (n.indexOf(NFD_HAKGI) >= 0 && n.indexOf(NFD_GOSA) >= 0) arr.push(doc.textFrames[i]);
    }
    return arr;
}

// 텍스트 교체 후 원래 중심(가로/세로) 유지. forceCenter면 중앙정렬 강제.
function setKeepCenter(tf, newText, forceCenter){
    var b0 = tf.geometricBounds;                       // [l,t,r,b]
    var cx = (b0[0]+b0[2])/2, cy = (b0[1]+b0[3])/2;
    if (forceCenter){ try { tf.textRange.justification = Justification.CENTER; } catch(e){} }
    tf.contents = newText;
    if (forceCenter){ try { tf.textRange.justification = Justification.CENTER; } catch(e){} }
    var b1 = tf.geometricBounds;
    var ncx = (b1[0]+b1[2])/2, ncy = (b1[1]+b1[3])/2;
    tf.translate(cx-ncx, cy-ncy);
}

function applyInfoLine(doc, exam, school, grade){
    var tf = findInfoLine(doc);
    if (!tf) return false;
    var parts = String(tf.contents).split("|");
    var year = (parts.length>0) ? trim(parts[0]) : "2026";
    tf.contents = year + "   |   " + exam + "   |   " + school + grade;
    return true;
}
function applyExamBig(doc, exam){
    var arr = findExamBigFrames(doc);
    for (var i=0;i<arr.length;i++){
        var hasBreak = /[\r\n]/.test(String(arr[i].contents));   // 원본이 2줄이면 줄바꿈 유지
        setKeepCenter(arr[i], hasBreak ? exam.replace(/ /, "\r") : exam, false);
    }
    return arr.length;
}
function applyVol(doc, volDisplay){
    var tf = findVolFrame(doc);
    if (!tf) return false;
    setKeepCenter(tf, volDisplay, true);
    return true;
}

// ── 4페이지(앞/빈/빈/뒤) 아트보드 재구성 ────────────────────
function build4Pages(doc){
    var abs = doc.artboards;
    var rf = abs[0].artboardRect;                       // 앞표지(대지1)
    var W = rf[2]-rf[0], H = rf[1]-rf[3];
    var rb = abs[1].artboardRect;                       // 뒤표지(대지2)
    var rectBack = [rb[0], rb[1], rb[2], rb[3]];
    abs.remove(1);                                       // 뒤표지 아트보드 제거(아트워크는 캔버스에 남음)
    var y1 = -1000;                                      // 빈 캔버스 영역(아트워크 y: 0~-844)
    var y2 = y1 - H - 100;
    abs.add([0, y1, W, y1 - H]);                         // 빈 1 -> index1
    abs.add([0, y2, W, y2 - H]);                         // 빈 2 -> index2
    abs.add(rectBack);                                   // 뒤표지 -> index3
    return abs.length;                                   // 4
}

// ── PDF ─────────────────────────────────────────────────────
function pickPreset(){
    var list = app.PDFPresetsList;
    var prefs = ["고품질", "High Quality", "프레스", "Press", "PDF/X-1a"];
    for (var p=0;p<prefs.length;p++){
        for (var i=0;i<list.length;i++){
            if (String(list[i]).indexOf(prefs[p]) >= 0) return list[i];
        }
    }
    return (list.length) ? list[0] : "[High Quality Print]";
}
function exportPDF(doc, outPath, preset){
    if (doc.documentColorSpace != DocumentColorSpace.CMYK){
        try { doc.documentColorSpace = DocumentColorSpace.CMYK; } catch(e){}
    }
    var opts = new PDFSaveOptions();
    try { opts.pDFPreset = preset; } catch(e){}
    opts.preserveEditability = false;
    opts.viewAfterSaving = false;
    opts.generateThumbnails = true;
    opts.saveMultipleArtboards = true;
    opts.artboardRange = "1-" + doc.artboards.length;    // 1-4
    opts.bleedOffsetRect = [0,0,0,0];                    // 도련 없음(A4 정사이즈)
    doc.saveAs(new File(outPath), opts);
}

// ── 메인 ────────────────────────────────────────────────────
function main(){
    var prevAlerts;
    try { prevAlerts = app.userInteractionLevel; app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch(e){}

    var preset = pickPreset();
    logln("프리셋: " + preset);

    var outputs = cfg.outputs;
    for (var v=0; v<outputs.length; v++){
        var o = outputs[v];
        var doc = app.open(new File(cfg.template_path));
        $.sleep(300);
        doc = app.activeDocument;
        try {
            var cmyk = (doc.documentColorSpace == DocumentColorSpace.CMYK);
            applyInfoLine(doc, cfg.exam, cfg.school, cfg.grade);
            var nBig = applyExamBig(doc, cfg.exam);
            applyVol(doc, o.vol);
            var nAb = build4Pages(doc);
            exportPDF(doc, o.path, preset);
            logln("저장: " + o.name + "  (" + nAb + "P, " + (cmyk?"CMYK":"RGB!") +
                  (nBig>0 ? (", 세종큰글씨 "+nBig+"개") : "") + ")");
        } catch(e){
            logln("[오류] " + o.vol + ": " + e);
        }
        doc.close(SaveOptions.DONOTSAVECHANGES);
        flushLog();   // 진행상황 실시간 반영
    }

    try { app.userInteractionLevel = prevAlerts; } catch(e){}

    logln("DONE");
    flushLog();
}

main();
