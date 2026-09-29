"""필드 타입별 견본 값 — 콘텐츠 없이 디자인만 볼 때 칸을 채운다. 지어낸 글이라는 것이 보이게 둔다."""

_EN = ("The boy ", {"t": "who", "u": True}, " I met at the station yesterday turned out to be my cousin, "
       "and we spent the whole afternoon talking about the years we had missed.")
_ONE = ("The boy ", {"t": "who", "u": True}, " I met at the station was my cousin.")   # 한 줄짜리 — 문장 자리는 책에서도 한 줄이라, 견본이 길면 판이 실제와 다르게 보인다

SAMPLE = {
    "text": "다음 글의 밑줄 친 부분 중, 어법상 틀린 것은?",
    "rich": list(_EN),
    "number": 1,
    "choices": ["turned out", "spent", "talking", "had missed", "whole"],
    "answer": "③",
    "image": None,
    "bool": True,
}

# 블록 필드 이름으로 더 맞는 견본이 있으면 그것을 — 이름은 관행일 뿐 규칙이 아니다
BY_NAME = {
    "no": 1, "pnum": "20", "title": "어법 O/X", "tag": "BUILD UP", "logo": "B1",
    "sentence": list(_ONE), "passage": list(_EN) * 3,
    "prompt": "다음 글의 밑줄 친 부분 중, 어법상 틀린 것은?",
    "answer": "③", "kr": "내가 어제 역에서 만난 그 소년은 내 사촌으로 밝혀졌다.",
}


def value(name, ftype):
    if name in BY_NAME:
        return BY_NAME[name]
    return SAMPLE.get(ftype, "")


def fill(block, given):
    """블록 필드 전부에 값을 — 준 것이 있으면 그것, 없으면 견본."""
    out = {}
    for name, f in (block.get("fields") or {}).items():
        if name in (given or {}):
            out[name] = given[name]
        else:
            out[name] = value(name, (f or {}).get("type", "text"))
    for k, v in (given or {}).items():
        out.setdefault(k, v)
    return out
