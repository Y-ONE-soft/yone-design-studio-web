var doc = app.activeDocument;
var frames = doc.textFrames;

var fixedCount = 0;

for (var i = 0; i < frames.length; i++) {
    var tf = frames[i];
    var inlines = tf.allPageItems;

    for (var j = 0; j < inlines.length; j++) {
        var item = inlines[j];

        if (
            item instanceof TextFrame &&
            item.parent instanceof Character // 즉, Anchored Object
        ) {
            var anchor = item.anchoredObjectSettings;

            // 위치를 살짝 변경 후 복원해서 리플로우 유도
            var origY = anchor.anchorYoffset;
            anchor.anchorYoffset += 0.1;
            anchor.anchorYoffset = origY;

            fixedCount++;
        }
    }
}

alert("정렬된 Anchored Object 수: " + fixedCount);