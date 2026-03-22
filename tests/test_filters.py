from sepg.download.filters import compile_filter


def test_no_expr_matches_everything():
    want = compile_filter(None)
    assert want("anything/at/all.7z")
    assert want("")


def test_substring_style_uses_fnmatch():
    want = compile_filter("stackexchange/vi.stackexchange.com.7z")
    assert want("stackexchange/vi.stackexchange.com.7z")
    assert not want("stackexchange/en.stackexchange.com.7z")


def test_fnmatch_glob_wildcard():
    want = compile_filter("*stackoverflow.com-Posts*.7z")
    assert want("stackexchange/stackoverflow.com-Posts.7z")
    assert not want("stackexchange/stackoverflow.com-Comments.7z")


def test_regex_style_with_re_prefix():
    want = compile_filter(r"re:(^|/)stackoverflow\.com-[^/]+\.7z$")
    assert want("stackexchange/stackoverflow.com-Posts.7z")
    assert want("stackexchange/stackoverflow.com-Badges.7z")
    assert not want("stackexchange/vi.stackexchange.com.7z")
