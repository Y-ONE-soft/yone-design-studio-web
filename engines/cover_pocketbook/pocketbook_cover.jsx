#target illustrator

/*
 * Pocket Book Cover Generator
 * settings.json에서 학교 데이터를 읽어 포켓북 표지 생성
 */

var SETTINGS_PATH = "%%SETTINGS_PATH%%";

// ---- settings.json 로드 ------------------------------------------------

function readJSON(path) {
    var f = new File(path);
    f.open("r");
    var text = f.read();
    f.close();
    return eval("(" + text + ")");
}

var cfg = readJSON(SETTINGS_PATH);

// ---- 유틸 함수 ----------------------------------------------------------

function makeCMYK(arr) {
    var c = new CMYKColor();
    c.cyan = arr[0];
    c.magenta = arr[1];
    c.yellow = arr[2];
    c.black = arr[3];
    return c;
}

function cmykMatch(color, ref) {
    if (color.typename !== "CMYKColor") return false;
    return Math.abs(color.cyan - ref[0]) < 0.5 &&
           Math.abs(color.magenta - ref[1]) < 0.5 &&
           Math.abs(color.yellow - ref[2]) < 0.5 &&
           Math.abs(color.black - ref[3]) < 0.5;
}

function replaceColorsInGroup(group, tc, sc, bc, refT, refS, refB) {
    for (var i = 0; i < group.pageItems.length; i++) {
        var item = group.pageItems[i];
        if (item.typename === "PathItem") {
            if (item.filled && item.fillColor.typename === "CMYKColor") {
                if (cmykMatch(item.fillColor, refT)) item.fillColor = tc;
                else if (cmykMatch(item.fillColor, refS)) item.fillColor = sc;
                else if (cmykMatch(item.fillColor, refB)) item.fillColor = bc;
            }
            if (item.stroked && item.strokeColor.typename === "CMYKColor") {
                if (cmykMatch(item.strokeColor, refT)) item.strokeColor = tc;
                else if (cmykMatch(item.strokeColor, refS)) item.strokeColor = sc;
            }
        } else if (item.typename === "TextFrame") {
            for (var j = 0; j < item.textRange.characters.length; j++) {
                var ch = item.textRange.characters[j];
                var fc = ch.characterAttributes.fillColor;
                if (fc.typename === "CMYKColor") {
                    if (cmykMatch(fc, refT)) ch.characterAttributes.fillColor = tc;
                    else if (cmykMatch(fc, refS)) ch.characterAttributes.fillColor = sc;
                }
            }
        } else if (item.typename === "GroupItem") {
            replaceColorsInGroup(item, tc, sc, bc, refT, refS, refB);
        } else if (item.typename === "CompoundPathItem") {
            try {
                for (var k = 0; k < item.pathItems.length; k++) {
                    var cp = item.pathItems[k];
                    if (cp.filled && cp.fillColor.typename === "CMYKColor") {
                        if (cmykMatch(cp.fillColor, refT)) cp.fillColor = tc;
                        else if (cmykMatch(cp.fillColor, refS)) cp.fillColor = sc;
                    }
                }
            } catch (e) {}
        }
    }
}

function replaceSchoolName(group, newName) {
    for (var i = 0; i < group.pageItems.length; i++) {
        var item = group.pageItems[i];
        if (item.typename === "TextFrame") {
            // 강동고 + 숫자 패턴 교체
            if (item.contents.indexOf("\uAC15\uB3D9\uACE0") >= 0) {
                var oldCenter = item.left + item.width / 2;
                item.contents = item.contents.replace(/\uAC15\uB3D9\uACE0\s*\d/, newName);
                // 텍스트 교체 후 중앙 정렬 유지
                item.paragraphs[0].justification = Justification.CENTER;
                var newCenter = item.left + item.width / 2;
                item.left += oldCenter - newCenter;
            }
        } else if (item.typename === "GroupItem") {
            replaceSchoolName(item, newName);
        }
    }
}

// ---- 메인 ---------------------------------------------------------------

function main() {
    var templatePath = cfg.template_path;
    var outputDir = cfg.output_dir;
    var schools = cfg.schools;
    var refT = cfg.ref_title;
    var refS = cfg.ref_sub;
    var refB = cfg.ref_bg;

    var logLines = [];

    for (var s = 0; s < schools.length; s++) {
        var school = schools[s];
        var schoolKey = school.school_key;
        var schoolName = school.school_name;

        logLines.push("[" + (s + 1) + "/" + schools.length + "] " + schoolKey + " (" + schoolName + ")");

        // 템플릿 열기
        var doc = app.open(new File(templatePath));
        $.sleep(500);
        doc = app.activeDocument;

        // 색상 객체 생성
        var tc = makeCMYK(school.title_cmyk);
        var sc = makeCMYK(school.sub_cmyk);
        var bc = makeCMYK(school.bg_cmyk);

        // 색상 교체
        for (var i = 0; i < doc.layers.length; i++) {
            replaceColorsInGroup(doc.layers[i], tc, sc, bc, refT, refS, refB);
        }

        // 학교명 교체
        for (var i = 0; i < doc.layers.length; i++) {
            replaceSchoolName(doc.layers[i], schoolName);
        }

        // 일러스트 교체 (Layer 0 > Group[0] > Group[0] = illustGroup)
        try {
            var mainGroup = doc.layers[0].groupItems[0];
            var illustGroup = mainGroup.pageItems[0];
            var clipPath = illustGroup.pageItems[0];
            var rasterGroup = illustGroup.pageItems[1];

            var visLeft = clipPath.left;
            var visTop = clipPath.top;
            var visWidth = clipPath.width;
            var visHeight = clipPath.height;

            // 기존 래스터 제거
            while (rasterGroup.pageItems.length > 0) {
                rasterGroup.pageItems[0].remove();
            }

            // 새 일러스트 배치
            var illustFile = new File(school.illustration_path);
            if (illustFile.exists) {
                var placed = rasterGroup.placedItems.add();
                placed.file = illustFile;
                placed.left = visLeft;
                placed.top = visTop;
                placed.width = visWidth;
                placed.height = visHeight;
                placed.embed();
            }
        } catch (e) {
            logLines.push("  [경고] 일러스트 교체 실패: " + e.message);
        }

        // PDF 저장
        // PDF/X-1a:2001 (Japan) \uC778\uC1C4\uC6A9 \u2014 CMYK + 3mm \uB3C4\uB828 + OutputIntent
        if (doc.documentColorSpace !== DocumentColorSpace.CMYK) {
            try { doc.documentColorSpace = DocumentColorSpace.CMYK; } catch (e) {}
        }
        var pdfOpts = new PDFSaveOptions();
        try {
            pdfOpts.pDFPreset = "[PDF/X-1a:2001 (Japan)]";
        } catch (e1) {
            try { pdfOpts.pDFPreset = "[PDF/X-1a:2001]"; } catch (e2) {
                pdfOpts.compatibility = PDFCompatibility.ACROBAT5;
            }
        }
        pdfOpts.preserveEditability = false;
        pdfOpts.generateThumbnails = true;
        pdfOpts.optimization = true;
        // PDF/X-1a 프리셋이 bleedOffsetRect를 정수 pt로 반올림하므로 9pt(3.18mm)로 약간 초과 설정
        pdfOpts.bleedOffsetRect = [9, 9, 9, 9];

        var pdfPath = outputDir + "/" + schoolKey + "_\uD3EC\uCF13\uBD81_\uD45C\uC9C0.pdf";
        var pdfFile = new File(pdfPath);
        doc.saveAs(pdfFile, pdfOpts);
        logLines.push("  PDF: " + pdfPath);

        doc.close(SaveOptions.DONOTSAVECHANGES);
    }

    logLines.push("DONE");

    // 로그 저장
    var logFile = new File(cfg.log_path);
    logFile.open("w");
    logFile.write(logLines.join("\n"));
    logFile.close();
}

main();
