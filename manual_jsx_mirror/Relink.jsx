#target indesign

relinkAllOpenDocuments();

function relinkAllOpenDocuments() {

    if (app.documents.length === 0) {
        alert("Open a document first.");
        return;
    }

    var workbookFolder = Folder("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/콘텐츠 관리/내신대비/인디자인 파일/이미지/워크북/C버전");
    var analysisFolder = Folder("/Users/nhj/Library/CloudStorage/GoogleDrive-etyrano11@gmail.com/내 드라이브/콘텐츠 관리/내신대비/인디자인 파일/이미지/분석본");

    if (!workbookFolder.exists || !analysisFolder.exists) {
        alert("Image folder(s) not found.");
        return;
    }

    // 폴더별로 파일 수집 (하위폴더 포함) — 한번만
    var workbookFiles = collectFilesRecursively(workbookFolder);
    var analysisFiles = collectFilesRecursively(analysisFolder);

    var totalFixed = 0;
    var totalTried = 0;

    // 🔵 열린 문서 전부 처리 — 링크 이름이 "분석본…"이면 분석본 폴더에서, 아니면 워크북 폴더에서 검색
    for (var d = 0; d < app.documents.length; d++) {
        var doc = app.documents[d];
        var result = relinkDocLinks(doc, workbookFiles, analysisFiles);
        totalFixed += result.fixed;
        totalTried += result.tried;
    }

    alert("Relink finished. Fixed: " + totalFixed + " / Tried: " + totalTried);
}

function collectFilesRecursively(rootFolder) {

    var result = [];
    var stack = [rootFolder];

    while (stack.length > 0) {
        var folder = stack.pop();
        var items = folder.getFiles();

        for (var i = 0; i < items.length; i++) {
            var item = items[i];

            if (item instanceof Folder) {
                stack.push(item);
                continue;
            }

            if (item instanceof File) {
                result.push(item);
            }
        }
    }

    return result;
}

// 링크 이름에 "분석본"(NFC 또는 NFD)이 포함되면 분석본 폴더에서 찾도록 분류
function isAnalysisLink(linkName) {

    // NFC: 분(U+BD84) 석(U+C11D) 본(U+BCF8)
    var BUNSEOKBON_NFC = '분석본';
    // NFD: ㅂ(U+1107)+ㅜ(U+116E)+ㄴ(U+11AB)+ㅅ(U+1109)+ㅓ(U+1165)+ㄱ(U+11A8)+ㅂ(U+1107)+ㅗ(U+1169)+ㄴ(U+11AB)
    var BUNSEOKBON_NFD = '분석본';

    if (linkName.indexOf(BUNSEOKBON_NFC) !== -1) return true;
    if (linkName.indexOf(BUNSEOKBON_NFD) !== -1) return true;
    return false;
}

function relinkDocLinks(doc, workbookFiles, analysisFiles) {

    var links = doc.links;
    var fixed = 0;
    var tried = 0;

    for (var i = 0; i < links.length; i++) {

        var link = links[i];

        // 링크가 깨졌거나(물음표) 수정된 경우에만 시도
        var shouldTry = false;
        try {
            if (link.status === LinkStatus.LINK_MISSING ||
                link.status === LinkStatus.LINK_OUT_OF_DATE ||
                link.status === LinkStatus.LINK_INACCESSIBLE) {
                shouldTry = true;
            }
        } catch (e) {
            shouldTry = true;
        }

        if (!shouldTry) continue;

        tried++;

        var originalName = link.name;
        var normalized = normalizeLinkName(originalName);

        // 링크 이름으로 어느 폴더에서 찾을지 결정
        var targetFiles = isAnalysisLink(originalName) ? analysisFiles : workbookFiles;

        for (var f = 0; f < targetFiles.length; f++) {

            var file = targetFiles[f];
            // ExtendScript returns File.name URI-encoded for non-ASCII names (a Korean
            // target file comes back as "%E1%84%8C..."), while link.name is decoded. Decode
            // here so a Korean-named target (e.g. the "Asset 4@300x.png") actually matches.
            var fileName = File.decode(file.name);

            if (
                fileName === originalName ||
                normalizeLinkName(fileName) === normalized
            ) {
                try {
                    link.relink(file);
                    link.update();

                    if (link.status === LinkStatus.NORMAL) {
                        fixed++;
                    }

                    break;
                } catch (e) {}
            }
        }
    }

    return { fixed: fixed, tried: tried };
}

function normalizeLinkName(name) {

    var n = name;

    // Korean tokens matched in BOTH true NFC and true NFD. macOS stores filenames as NFD,
    // and InDesign link names are often NFD too; a literal '(?:..|..)' saved by an editor
    // that normalizes to NFC silently loses the NFD branch. Build both forms from codepoints.
    var GANJI = '(?:' + String.fromCharCode(0xAC04, 0xC9C0) + '|' +
                        String.fromCharCode(0x1100, 0x1161, 0x11AB, 0x110C, 0x1175) + ')';                   // GANJI
    var MAJIMAK = '(?:' + String.fromCharCode(0xB9C8, 0xC9C0, 0xB9C9) + '|' +
                          String.fromCharCode(0x1106, 0x1161, 0x110C, 0x1175, 0x1106, 0x1161, 0x11A8) + ')'; // MAJIMAK
    var SERO = '(?:' + String.fromCharCode(0xC138, 0xB85C) + '|' +
                       String.fromCharCode(0x1109, 0x1166, 0x1105, 0x1169) + ')';                            // SERO
    var BUNSEOKBON = '(?:' + String.fromCharCode(0xBD84, 0xC11D, 0xBCF8) + '|' +
                             String.fromCharCode(0x1107, 0x116E, 0x11AB, 0x1109, 0x1165, 0x11A8, 0x1107, 0x1169, 0x11AB) + ')'; // BUNSEOKBON

    // Illustrator default export name "Asset" (Korean) -> canonicalize NFC/NFD so the
    // InDesign link name matches the NFD filesystem name. The file keeps its own name;
    // only the comparison is stabilized (relink still targets the real file object).
    var JASAN_NFC = String.fromCharCode(0xC790, 0xC0B0);                          // NFC
    var JASAN_NFD = String.fromCharCode(0x110C, 0x1161, 0x1109, 0x1161, 0x11AB);  // NFD

    n = n.replace("(B)", "");
    n = n.replace(new RegExp('^' + GANJI + '_' + SERO + '(?=\\.[^.]+$)'), 'STEP123'); // 간지_세로.ext -> STEP123.ext
    n = n.replace(new RegExp('^' + BUNSEOKBON + GANJI + '(?=\\.[^.]+$)'), '1P'); // 분석본간지.ext -> 1P.ext
    n = n.replace(new RegExp('^' + GANJI + '_'), '');                       // 간지_STEPx -> STEPx
    n = n.replace(new RegExp(GANJI + '(?=\\.[^.]+$)'), '');                 // xP간지.ext -> xP.ext
    n = n.replace(new RegExp('^' + MAJIMAK + 'P(?=\\.[^.]+$)'), 'LastP');   // 마지막P.ext -> LastP.ext

    n = n.replace(JASAN_NFC, "Asset").replace(JASAN_NFD, "Asset"); // stabilize "Asset 4@300x.png" match across NFC/NFD

    return n;
}
