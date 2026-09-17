# -*- coding: utf-8 -*-
"""원고 파일 대신 **데이터**로 책을 채우는 출처.

카탈로그의 "원고 넣기"는 docx·hwp 를 올려 `data` 단계(파서)가 data.json 을 만드는 길이다.
이 모듈은 그 단계를 건너뛰는 길 — data.json(또는 워크북의 render_plan.json)이
**이미 만들어져** 들어온다. 어디서 오든 결과는 같은 꼴이라 조판(build)은 구분하지 않는다.

    source = {"type": "data", "data": {...}}            본문에 실어 보냄
    source = {"type": "plan", "plan": {...}}            워크북 v2 렌더 플랜
    source = {"type": "yos",  ...params}                contents 에서 읽어 옴 (yos_contents 어댑터)

`resolve()` 는 `(kind, obj)` 를 돌려준다. kind 는 "data" 또는 "plan".
"""


class SourceError(ValueError):
    pass


def resolve(source, series, log=None):
    if not isinstance(source, dict) or not source.get("type"):
        raise SourceError("source.type 이 없다 (data | plan | yos)")
    t = source["type"]
    if t == "data":
        if not isinstance(source.get("data"), dict):
            raise SourceError("source.data 는 객체여야 한다")
        kind, obj = "data", source["data"]
    elif t == "plan":
        if not isinstance(source.get("plan"), dict):
            raise SourceError("source.plan 은 객체여야 한다")
        kind, obj = "plan", source["plan"]
    elif t == "yos":
        from core.sources import yos_contents
        kind, obj = yos_contents.fetch(series, {k: v for k, v in source.items() if k != "type"}, log)
    else:
        raise SourceError(f"모르는 source.type: {t}")
    return kind, _adapt(obj, kind, series, log)


def _adapt(obj, kind, series, log):
    """contents 가 자기 모양 그대로 보낸 것(`format` 표시)은 여기서 그 틀의 data.json 으로.
    어느 길(data 본문·yos 읽기)로 왔든 한 번만 거친다."""
    from core.sources import yos_workbook
    if kind == "data" and isinstance(obj, dict) and obj.get("format") == yos_workbook.FORMAT:
        if series != "workbook":
            raise SourceError(f"{yos_workbook.FORMAT} 는 workbook 틀에만 쓴다 (이 틀: {series})")
        try:
            return yos_workbook.to_data(obj, log)
        except ValueError as e:
            raise SourceError(str(e))
    return obj
