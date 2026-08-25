"""자산 PNG 를 팔레트 색으로 다시 굽는다.

계열 자산 중 **글자가 들어간 두 개**만 PNG 다 — 로고의 "2026" 알약(원본 서체
`TTSupersizeBk` 없음)과 MEMO 탭(세로 "MEMO"). 나머지 도형은 전부 배경 SVG 라
팔레트를 바꾸면 자동으로 따라가는데, PNG 만 **옛 색으로 남는다**(연보라 지면을
분홍으로 바꿨을 때 알약만 보라로 남아 실제로 겪음).

그래서 빌드마다 원본 PNG 를 읽어 `build/assets/` 에 **팔레트 색으로 다시 굽는다.**
두 PNG 는 전부 "바탕색 한 가지 + 흰 글자 + 알파" 구조라, 흰색 쪽으로 얼마나
섞였는지(coverage)를 재서 바탕색만 갈아끼우면 글자·안티에일리어싱이 그대로 산다.
"""
import os
import shutil

# (파일명, 원본 바탕색, 새 색을 가져올 팔레트 키, 팔레트에 없을 때 기본색)
TINTED = (
    ("pill2026.png", (0xc7, 0xb9, 0xdb), "pill", None),
    ("memotab.png",  (0xd1, 0xdf, 0xc4), "memo", "#d1dfc4"),
)


def _rgb(hex_str):
    h = (hex_str or "").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def retint(cfg, build_dir, src_dir, log=None):
    """`src_dir` 의 PNG → `build_dir/assets/` (팔레트 색으로). 실패해도 원본은 남긴다."""
    dst_dir = os.path.join(build_dir, "assets")
    os.makedirs(dst_dir, exist_ok=True)
    pal = cfg.section("palette") or {}
    done = []
    for name, base, key, default in TINTED:
        src = os.path.join(src_dir, name)
        if not os.path.exists(src):
            continue
        want = pal.get(key) or default
        if key == "pill" and not want:
            want = pal.get("logo")          # 따로 안 정하면 로고 글자색을 따른다
        dst = os.path.join(dst_dir, name)
        if not want:
            shutil.copy2(src, dst)
            continue
        try:
            _tint(src, dst, base, _rgb(want))
            done.append(f"{name}→{want}")
        except Exception as e:                      # noqa: BLE001 — 조판은 계속
            shutil.copy2(src, dst)
            (log or print)(f"[경고] 자산 재염색 실패({name}): {e} — 원본색으로 진행")
    if log and done:
        log(f"[자산] 팔레트 색으로 재염색 {', '.join(done)}")
    return done


def _tint(src, dst, base, new):
    """바탕색 `base` → `new`. 흰 글자와 알파는 그대로."""
    import numpy as np
    from PIL import Image

    a = np.asarray(Image.open(src).convert("RGBA"), dtype=float)
    rgb, alpha = a[..., :3], a[..., 3:]
    b = np.array(base, dtype=float)
    denom = np.where(255.0 - b == 0, 1.0, 255.0 - b)
    # 흰색 쪽으로 섞인 정도 = 글자(와 그 가장자리) 커버리지
    cov = np.clip(((rgb - b) / denom).mean(axis=-1, keepdims=True), 0.0, 1.0)
    out = np.array(new, dtype=float) + (255.0 - np.array(new, dtype=float)) * cov
    Image.fromarray(np.concatenate([out, alpha], axis=-1)
                    .round().clip(0, 255).astype("uint8")).save(dst)
    return dst
