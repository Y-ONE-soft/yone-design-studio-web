#target "InDesign"

var doc = app.activeDocument;
var styles = doc.allParagraphStyles;
var lines = [];

for (var i = 0; i < styles.length; i++) {
    var name = styles[i].name;
    var hex = "";
    for (var c = 0; c < name.length; c++) {
        hex += name.charCodeAt(c).toString(16).toUpperCase() + " ";
    }
    lines.push("[" + name + "]  ==>  " + hex);
}

alert(lines.join("\n"));
