import fnmatch
import re
from collections.abc import Callable


def compile_filter(expr: str | None) -> Callable[[str], bool]:
    if not expr:
        return lambda s: True

    if expr.startswith("re:"):
        pat = re.compile(expr[3:])
        return lambda s: bool(pat.search(s))

    return lambda s: fnmatch.fnmatch(s, expr)
