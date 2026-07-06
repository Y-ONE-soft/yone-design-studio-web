#target "InDesign"

var tf = app.selection[0];

if (tf) {
    alert(tf.geometricBounds);
} else {
    alert("프레임을 선택하세요.");
}