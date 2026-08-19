"""2패스 면 지정 — "1패스로 조판해 면 번호를 알아낸 뒤, 그 면에만 규칙을 건다".

계약(이게 핵심이다): **마진 박스의 '내용'과 `@page` 배경만 바꾸면 페이지 나눔은
1패스와 동일하다.** 그래서 2패스는 재조판이 아니라 덧칠이고, 수렴을 걱정하지
않아도 된다. 흐름을 반복 조판으로 수렴시키려 하면 발산한다(블랙북 해설 10→8→7).

⚠ `@page :nth(N)` 은 `@page p-head` 같은 **이름 규칙에 명시도로 밀린다**.
그래서 `nth_rule()` 은 페이지 이름들과 **함께** 셀렉터를 만든다. 빠뜨리면
"규칙을 넣었는데 안 먹는다"(헤더 밴드 둥근 모서리로 배경이 비쳐 보임).
"""
from core.render_vivlio import probe

HEADER = "/* 자동 생성 — 2패스 빌드. 직접 고치지 말 것 */"


def find_open_pages(pdf_or_texts, marker="DAYOPEN"):
    """보이지 않는 마커가 심긴 '시작 면' 쪽번호(1-based) 목록."""
    return probe.pages_with_marker(pdf_or_texts, marker)


def right_start_indices(opens):
    """시작 면들 중 **오른쪽(홀수) 면에서 시작한 것**의 일련번호(1-based).

    렌더러에 돌려주면 그 면만 헤더를 좌우 반전한다(태그·제목이 바깥쪽으로).
    """
    return [i + 1 for i, p in enumerate(opens) if p % 2 == 1]


def nth_rule(page_names, n, body):
    """이름 있는 페이지들 + `:nth(n)` 셀렉터 한 줄.

    page_names 가 비면 이름 없는 `@page :nth(n)` 을 쓴다(이름 규칙과 겹치는
    속성이 없을 때만 안전).
    """
    if page_names:
        sel = ", ".join(f"{nm}:nth({n})" for nm in page_names)
    else:
        sel = f":nth({n})"
    return f"@page {sel} {{ {body} }}"


class PageRules(object):
    """2패스에서 만들어질 `@page` 규칙 모음 → CSS 텍스트."""

    def __init__(self, page_names=()):
        self.page_names = tuple(page_names)
        self.lines = [HEADER]

    def nth(self, n, body, names=None):
        self.lines.append(nth_rule(
            self.page_names if names is None else names, n, body))
        return self

    def raw(self, line):
        self.lines.append(line)
        return self

    def text(self):
        return "\n".join(self.lines) + "\n"

    def write(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.text())
        return path


def last_page_footer_css(pages, element="pageFooterLast", slot="bottom-center"):
    """마지막 면에만 '끝.' 러닝 푸터를 켠다(면수를 알아야 하므로 2패스)."""
    if not pages:
        return ""
    return (f"@page :nth({pages}) {{\n"
            f"  @{slot} {{ content: element({element}); }}\n"
            f"}}\n")
