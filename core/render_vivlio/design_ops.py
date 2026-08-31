# -*- coding: utf-8 -*-
"""디자인 편집도 **같은 이력**에 쌓는다 — ⌘Z 하나로 다 되돌리려고.

## 왜 합치는가

글은 `edits.json` 에, 디자인은 `.bak` 에 따로 있었다. 그러면 방금 한 일을
되돌리려고 **어느 되돌리기를 눌러야 하는지** 사람이 알아야 한다. 조판
프로그램에서 그건 말이 안 된다 — 인디자인은 무엇을 했든 ⌘Z 하나다.

그래서 디자인 편집도 연산으로 만든다. 다만 글 편집과 달리 **파일을 직접**
고치므로(config.json · overrides.css), 얹고 걷는 일을 여기서 한다.

    style   config.json 의 `styles` 절 한 선택자
    knob    config.json 의 값 하나(점 경로)
    css     그 책의 overrides.css 전체

각 연산은 **고치기 전 값**(`prev`)을 함께 들고 있다. 되돌리기는 그 값을 도로
쓰는 것이고, 다시 실행은 `v` 를 쓰는 것이다. 순서대로만 오가므로 이걸로 충분하다.

⚠ 글 연산과 달리 이 연산들은 `data` 를 읽을 때 얹으면 **안 된다** —
  이미 파일에 들어가 있기 때문이다. `edits.apply_all()` 이 건너뛴다.
"""
import json
import os
import shutil

KINDS = ("style", "knob", "css")


def _read_cfg_text(cfg):
    return open(cfg.path("config.json"), encoding="utf-8").read()


def _write_cfg(cfg, changes):
    """`config.json` 을 **바뀐 자리만** 갈아 끼운다(손으로 맞춘 모양을 지킨다)."""
    from core.render_vivlio import knobs as kn
    path = cfg.path("config.json")
    raw = _read_cfg_text(cfg)
    try:
        out = kn.patch_text(raw, changes)
    except Exception:
        out = json.dumps(kn.apply(cfg.data, changes),
                         ensure_ascii=False, indent=2) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)


def _styles(cfg):
    return dict(cfg.section("styles") or {})


def current(cfg, op):
    """이 연산이 건드릴 자리의 **지금 값**. `prev` 로 쌓아 둔다."""
    kind = op.get("op")
    if kind == "style":
        return _styles(cfg).get(op.get("sel"))
    if kind == "knob":
        from core.render_vivlio import knobs as kn
        return kn.get(cfg.data, op.get("key"))
    if kind == "css":
        p = cfg.path("overrides.css")
        return open(p, encoding="utf-8").read() if os.path.exists(p) else None
    return None


def put(cfg, op, value):
    """그 자리에 값을 쓴다. `value` 가 None 이면 **없애는 것**이다."""
    kind = op.get("op")
    if kind == "style":
        st = _styles(cfg)
        if value:
            st[op["sel"]] = value
        else:
            st.pop(op["sel"], None)
        # ⚠ 다 지웠으면 **절 자체를 없앤다.** 빈 `"styles": {}` 를 남기면
        #   되돌린 뒤에도 config 가 원래와 달라, 회귀 대조가 시끄러워진다.
        _write_cfg(cfg, {"styles": st if st else None})
    elif kind == "knob":
        _write_cfg(cfg, {op["key"]: value})
        if value is None:
            _drop_empty_parents(cfg, op["key"])
    elif kind == "css":
        p = cfg.path("overrides.css")
        if value is None:
            if os.path.exists(p):
                os.remove(p)
        else:
            with open(p, "w", encoding="utf-8") as f:
                f.write(value)
    # 파일을 고쳤으니 다음에 읽을 때는 새로 읽어야 한다
    try:
        cfg.reload()
    except Exception:
        pass


def _drop_empty_parents(cfg, key):
    """지운 뒤 **빈 껍데기로 남은 부모 절**을 걷어낸다.

    ⚠ 블랙북에는 `palette` 절이 아예 없다(색이 테마 CSS 에 있다). 그런 책에서
      색을 한 번 바꿨다 되돌리면 `"palette": {}` 가 남아, config 가 원래와
      달라진다 — 되돌렸는데 안 돌아온 것처럼 보인다.
    """
    from core.render_vivlio import knobs as kn
    parts = key.split(".")
    while len(parts) > 1:
        parts.pop()
        path = ".".join(parts)
        cfg.reload()
        v = kn.get(cfg.data, path)
        if isinstance(v, dict) and not v:
            _write_cfg(cfg, {path: None})
        else:
            break


def apply(cfg, op):
    put(cfg, op, op.get("v"))


def revert(cfg, op):
    put(cfg, op, op.get("prev"))


def label(op):
    """이력에 사람 말로 적을 이름."""
    k = op.get("op")
    if k == "style":
        return "스타일 " + str(op.get("sel", ""))
    if k == "knob":
        return "값 " + str(op.get("key", ""))
    if k == "css":
        return "직접 손본 CSS"
    return k or ""
