"""Tests for the optional fragment id namespacing feature."""

import pytest

import bleach
from bleach import clean
from bleach.sanitizer import Cleaner


TAGS = {
    "a",
    "div",
    "h1",
    "input",
    "label",
    "span",
    "table",
    "td",
    "th",
    "tr",
    "svg",
    "pattern",
    "rect",
}

ATTRS = {
    "*": ["id"],
    "a": ["id", "href", "ping"],
    "div": [
        "aria-controls",
        "aria-describedby",
        "aria-labelledby",
        "aria-owns",
    ],
    "input": ["id", "form", "aria-labelledby"],
    "label": ["for"],
    "td": ["headers", "aria-labelledby", "aria-describedby"],
    "th": ["id", "headers"],
    "rect": ["fill", "clip-path"],
    "pattern": ["id", "href"],
}


def clean_ns(text, **kwargs):
    kwargs.setdefault("tags", TAGS)
    kwargs.setdefault("attributes", ATTRS)
    kwargs.setdefault("id_namespace", "ns")
    return clean(text, **kwargs)


def test_disabled_by_default_leaves_ids_alone():
    text = '<h1 id="title">Hi</h1><a href="#title">top</a>'
    assert clean(text, tags=TAGS, attributes=ATTRS) == text


def test_id_and_local_href_are_rewritten():
    assert clean_ns('<h1 id="title">Hi</h1><a href="#title">top</a>') == (
        '<h1 id="ns-title">Hi</h1><a href="#ns-title">top</a>'
    )


def test_forward_reference_resolves():
    text = '<a href="#later">go</a><span id="later">L</span>'
    assert clean_ns(text) == '<a href="#ns-later">go</a><span id="ns-later">L</span>'


@pytest.mark.parametrize(
    "attribute, value, expected",
    [
        ("for", "x", 'ns-x'),
        ("form", "x", 'ns-x'),
        ("aria-activedescendant", "x", "ns-x"),
        ("aria-details", "x", "ns-x"),
        ("aria-errormessage", "x", "ns-x"),
        ("usemap", "#x", "#ns-x"),
    ],
)
def test_single_idref_attributes(attribute, value, expected):
    tags = TAGS | {"img", "map"}
    attrs = {
        "*": ["id"],
        "label": ["for"],
        "input": ["form", "aria-activedescendant", "aria-details", "aria-errormessage"],
        "img": ["usemap"],
    }
    if attribute == "usemap":
        text = f'<img usemap="{value}"><span id="x">X</span>'
    else:
        text = (
            f'<input {attribute}="{value}">'
            '<label for="x">L</label><span id="x">X</span>'
        )
    out = clean(text, tags=tags, attributes=attrs, id_namespace="ns")
    assert f'{attribute}="{expected}"' in out
    if attribute != "usemap":
        assert 'for="ns-x"' in out


def test_for_label_example():
    text = '<label for="email">E</label><input id="email">'
    assert clean_ns(text) == '<label for="ns-email">E</label><input id="ns-email">'


@pytest.mark.parametrize(
    "attribute",
    ["headers", "aria-labelledby", "aria-describedby", "aria-controls", "aria-owns"],
)
def test_multi_value_idref_tokenized(attribute):
    attrs = dict(ATTRS)
    attrs["*"] = ["id", attribute]
    text = (
        f'<div {attribute}="a b"></div>'
        '<span id="a">A</span><span id="b">B</span>'
    )
    out = clean_ns(text, attributes=attrs)
    assert f'{attribute}="ns-a ns-b"' in out


def test_headers_table_tokens():
    text = (
        "<table><tr><th id='h1'>H1</th><th id='h2'>H2</th></tr>"
        "<tr><td headers='h1 h2'>cell</td></tr></table>"
    )
    out = clean_ns(text)
    assert 'id="ns-h1"' in out
    assert 'headers="ns-h1 ns-h2"' in out


def test_external_url_fragment_is_not_local():
    text = (
        '<a id="t" href="https://example.com/page.html#t">ext</a>'
        '<a href="http://example.com/?a=b#t">ext2</a>'
        '<a href="/path#t">root</a>'
        '<a href="#t">local</a>'
    )
    out = clean_ns(text)
    assert 'href="https://example.com/page.html#t"' in out
    assert 'href="http://example.com/?a=b#t"' in out
    assert 'href="/path#t"' in out
    assert 'href="#ns-t"' in out
    assert 'id="ns-t"' in out


def test_ping_tokenized():
    text = (
        '<a href="#x" ping="#x https://example.com/track#x">x</a>'
        '<span id="x"></span>'
    )
    out = clean_ns(text)
    assert 'ping="#ns-x https://example.com/track#x"' in out


def test_only_surviving_attributes_touched():
    # data-id is not an allowed attribute and must never be rewritten.
    text = '<span id="real" data-id="real">x</span>'
    assert clean_ns(text) == '<span id="ns-real">x</span>'


def test_only_surviving_elements_define_targets():
    # The target element is escaped by cleaning, so the href stays dangling.
    text = '<a href="#gone">x</a><script id="gone">alert(1)</script>'
    assert clean_ns(text) == (
        '<a href="#gone">x</a>&lt;script id="gone"&gt;alert(1)&lt;/script&gt;'
    )


def test_dangling_reference_left_alone_by_default():
    reported = []
    text = '<div aria-labelledby="missing real"></div><span id="real">r</span>'
    out = clean_ns(text)
    assert out == (
        '<div aria-labelledby="missing ns-real"></div>'
        '<span id="ns-real">r</span>'
    )
    assert reported == []


def test_dangling_single_reference_removed_and_reported():
    reported = []
    text = '<label for="missing">L</label>'
    out = clean_ns(
        text, dangling_idref_callback=lambda t, a, r: reported.append((t, a, r))
    )
    assert out == "<label>L</label>"
    assert reported == [("label", "for", "missing")]


def test_dangling_tokens_removed_others_kept():
    reported = []
    text = (
        '<div aria-labelledby="keep missing too" aria-describedby="nope"></div>'
        '<span id="keep">k</span>'
    )
    out = clean_ns(
        text, dangling_idref_callback=lambda t, a, r: reported.append((t, a, r))
    )
    assert out == (
        '<div aria-labelledby="ns-keep"></div><span id="ns-keep">k</span>'
    )
    assert ("div", "aria-labelledby", "missing") in reported
    assert ("div", "aria-labelledby", "too") in reported
    assert ("div", "aria-describedby", "nope") in reported


def test_dangling_href_removed_when_callback_set():
    reported = []
    text = '<a href="#missing">x</a>'
    out = clean_ns(
        text, dangling_idref_callback=lambda t, a, r: reported.append((t, a, r))
    )
    assert out == "<a>x</a>"
    assert reported == [("a", "href", "missing")]


def test_duplicate_ids_deterministic_first_wins():
    text = '<div id="dup">one</div><div id="dup">two</div><a href="#dup">x</a>'
    out = clean_ns(text)
    assert out == (
        '<div id="ns-dup">one</div>'
        '<div id="ns-dup-2">two</div>'
        '<a href="#ns-dup">x</a>'
    )


def test_two_fragments_do_not_cross_link():
    frag_a = '<h1 id="title">A</h1><a href="#title">to A title</a>'
    frag_b = '<h1 id="title">B</h1><a href="#title">to B title</a>'

    out_a = clean_ns(frag_a, id_namespace="a")
    out_b = clean_ns(frag_b, id_namespace="b")

    combined = out_a + out_b
    assert 'id="a-title"' in combined
    assert 'id="b-title"' in combined
    assert 'href="#a-title"' in combined
    assert 'href="#b-title"' in combined
    assert 'href="#title"' not in combined
    # A's link must not resolve to B's element (or vice versa).
    assert combined.index('href="#a-title"') < combined.index('id="b-title"')


def test_reference_to_other_fragment_stays_dangling():
    # f1 defines "email"; f2 refers to it. f2's reference must not be
    # rewritten to f1's namespaced id when the fragments are combined.
    f1 = '<input id="email">'
    f2 = '<div aria-controls="email">d</div>'
    out1 = clean_ns(f1, id_namespace="f1")
    out2 = clean_ns(f2, id_namespace="f2")
    combined = out1 + out2
    assert 'id="f1-email"' in combined
    assert 'aria-controls="email"' in combined
    assert "f1-email" not in out2


def test_removed_target_does_not_hide_reference():
    # The script element (and its id) is escaped by cleaning, so the label
    # can't silently bind to anything--it keeps an explicit unresolved ref or
    # (with a callback) loses it entirely.
    text = '<label for="evil">L</label><script id="evil"></script>'
    assert clean_ns(text) == (
        '<label for="evil">L</label>&lt;script id="evil"&gt;&lt;/script&gt;'
    )

    reported = []
    out = clean_ns(
        text, dangling_idref_callback=lambda t, a, r: reported.append((t, a, r))
    )
    assert out == '<label>L</label>&lt;script id="evil"&gt;&lt;/script&gt;'
    assert reported == [("label", "for", "evil")]


def test_reclean_does_not_stack_prefixes():
    text = '<h1 id="title">x</h1><a href="#title">y</a>'
    once = clean_ns(text)
    twice = clean_ns(once)
    assert once == twice
    assert "ns-ns-" not in twice


def test_reclean_with_callback_is_stable():
    text = '<div aria-labelledby="real missing"></div><span id="real">r</span>'
    cb = lambda t, a, r: None  # noqa: E731
    once = clean_ns(text, dangling_idref_callback=cb)
    twice = clean_ns(once, dangling_idref_callback=cb)
    assert once == twice
    assert once == '<div aria-labelledby="ns-real"></div><span id="ns-real">r</span>'


def test_svg_url_references_off_by_default():
    text = '<svg><rect fill="url(#b)"></rect><pattern id="b"></pattern></svg>'
    out = clean_ns(text)
    assert 'fill="url(#b)"' in out
    assert 'id="ns-b"' in out


def test_svg_url_references_rewritten_when_enabled():
    text = (
        '<svg><rect fill="url(#b)"></rect>'
        '<rect clip-path="url(#c)"></rect>'
        '<pattern id="b" href="#c"></pattern>'
        '<pattern id="c"></pattern></svg>'
    )
    out = clean_ns(text, svg_references=True)
    assert 'fill="url(#ns-b)"' in out
    assert 'clip-path="url(#ns-c)"' in out
    assert 'href="#ns-c"' in out
    assert 'id="ns-b"' in out


def test_svg_url_reference_quoting_preserved():
    # The sanitizer normalizes quoted local IRIs; the unquoted form shows
    # the rewritten reference round-trips through serialization.
    text = '<svg><rect fill="url(#b)"></rect><pattern id="b"></pattern></svg>'
    out = clean_ns(text, svg_references=True)
    assert 'fill="url(#ns-b)"' in out


def test_non_local_svg_url_untouched():
    text = '<svg><rect fill="red url(#b) right"></rect><pattern id="b"></pattern></svg>'
    out = clean_ns(text, svg_references=True)
    assert "url(#ns-b)" in out

    # CSS strings that aren't local references must never be rewritten.
    text2 = '<svg><rect fill="url(#ns-b)"></rect></svg>'
    out2 = clean_ns(text2, svg_references=True)
    # "ns-b" is not a defined fragment id, so it's left exactly as-is.
    assert 'fill="url(#ns-b)"' in out2


def test_svg_dangling_reported_and_removed():
    reported = []
    text = '<svg><rect fill="url(#missing)"></rect></svg>'
    out = clean_ns(
        text,
        svg_references=True,
        dangling_idref_callback=lambda t, a, r: reported.append((t, a, r)),
    )
    assert reported == [("rect", "fill", "missing")]
    assert "url(" not in out


def test_svg_external_href_fragment_not_touched():
    text = '<svg><pattern id="b" href="https://e/x#b"></pattern></svg>'
    # Non-local hrefs are removed by the sanitizer before namespacing.
    out = clean_ns(text, svg_references=True)
    assert 'href' not in out
    assert 'id="ns-b"' in out


def test_percent_encoded_fragment():
    text = '<a href="#foo%20bar">x</a><span id="foo bar">y</span>'
    out = clean_ns(text)
    assert 'href="#ns-foo%20bar"' in out
    assert 'id="ns-foo bar"' in out


def test_callback_options_require_namespace():
    with pytest.raises(ValueError):
        Cleaner(tags=TAGS, attributes=ATTRS, svg_references=True)
    with pytest.raises(ValueError):
        Cleaner(tags=TAGS, attributes=ATTRS, dangling_idref_callback=lambda *a: None)


def test_invalid_prefix_rejected():
    with pytest.raises(ValueError):
        Cleaner(tags=TAGS, attributes=ATTRS, id_namespace="")
    with pytest.raises(ValueError):
        Cleaner(tags=TAGS, attributes=ATTRS, id_namespace="has space")


def test_cleaner_reusable_for_multiple_fragments():
    cleaner = Cleaner(tags=TAGS, attributes=ATTRS, id_namespace="u")
    first = cleaner.clean('<h1 id="title">1</h1>')
    second = cleaner.clean('<h1 id="title">2</h1>')
    assert first == '<h1 id="u-title">1</h1>'
    assert second == '<h1 id="u-title">2</h1>'
