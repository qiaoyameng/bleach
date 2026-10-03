import pytest

from bleach import clean
from bleach.css_sanitizer import CSSSanitizer
from bleach.sanitizer import Cleaner


ID_ATTRS = {"*": ["id"], "a": ["href"]}
ID_TAGS = {"a", "p", "h1", "label", "input", "span"}


def test_namespace_rewrites_id_and_local_href():
    assert (
        clean(
            '<h1 id="title">x</h1><a href="#title">go</a>',
            tags=ID_TAGS,
            attributes=ID_ATTRS,
            namespace="frag",
        )
        == '<h1 id="frag-title">x</h1><a href="#frag-title">go</a>'
    )


def test_namespace_disabled_by_default():
    assert (
        clean(
            '<h1 id="title">x</h1><a href="#title">go</a>',
            tags=ID_TAGS,
            attributes=ID_ATTRS,
        )
        == '<h1 id="title">x</h1><a href="#title">go</a>'
    )


def test_namespace_only_rewrites_allowed_attributes():
    # "id" is not an allowed attribute, so the sanitizer drops it and the
    # namespace filter never sees it
    assert (
        clean(
            '<h1 id="title">x</h1>',
            tags=ID_TAGS,
            attributes={},
            namespace="frag",
        )
        == "<h1>x</h1>"
    )


def test_namespace_ignores_fragment_in_external_url():
    assert (
        clean(
            '<a href="https://example.com/page#title">go</a>',
            tags=ID_TAGS,
            attributes=ID_ATTRS,
            namespace="frag",
        )
        == '<a href="https://example.com/page#title">go</a>'
    )


def test_namespace_rewrites_for_attribute():
    assert (
        clean(
            '<label for="in1">x</label><input id="in1">',
            tags=ID_TAGS,
            attributes={"*": ["id", "for"]},
            namespace="frag",
        )
        == '<label for="frag-in1">x</label><input id="frag-in1">'
    )


def test_namespace_rewrites_multi_value_idrefs_per_token():
    assert (
        clean(
            '<p id="a">x</p><p id="b">y</p>'
            '<p headers="a b" aria-labelledby="b a" aria-describedby="a">z</p>',
            tags=ID_TAGS,
            attributes={
                "*": ["id", "headers", "aria-labelledby", "aria-describedby"]
            },
            namespace="frag",
        )
        == '<p id="frag-a">x</p><p id="frag-b">y</p>'
        '<p headers="frag-a frag-b" aria-labelledby="frag-b frag-a" '
        'aria-describedby="frag-a">z</p>'
    )


def test_namespace_resolves_forward_references():
    assert (
        clean(
            '<a href="#later">go</a><p id="later">y</p>',
            tags=ID_TAGS,
            attributes=ID_ATTRS,
            namespace="frag",
        )
        == '<a href="#frag-later">go</a><p id="frag-later">y</p>'
    )


def test_namespace_unresolved_refs_kept_by_default():
    cleaner = Cleaner(tags=ID_TAGS, attributes=ID_ATTRS, namespace="frag")
    assert cleaner.clean('<a href="#missing">go</a>') == '<a href="#missing">go</a>'
    assert cleaner.namespace_report["unresolved_refs"] == [("href", "missing")]
    assert cleaner.namespace_report["dropped_refs"] == []


def test_namespace_unresolved_refs_dropped_and_reported():
    cleaner = Cleaner(
        tags=ID_TAGS,
        attributes={"*": ["id", "aria-labelledby"], "a": ["href"]},
        namespace="frag",
        drop_unresolved_refs=True,
    )
    assert (
        cleaner.clean('<a href="#missing">go</a><p aria-labelledby="a missing b">x</p>')
        == "<a>go</a><p>x</p>"
    )
    assert cleaner.namespace_report["unresolved_refs"] == [
        ("href", "missing"),
        ("aria-labelledby", "a"),
        ("aria-labelledby", "missing"),
        ("aria-labelledby", "b"),
    ]
    assert cleaner.namespace_report["dropped_refs"] == [
        ("href", "missing"),
        ("aria-labelledby", "a"),
        ("aria-labelledby", "missing"),
        ("aria-labelledby", "b"),
    ]


def test_namespace_unresolved_tokens_dropped_individually():
    cleaner = Cleaner(
        tags=ID_TAGS,
        attributes={"*": ["id", "aria-labelledby"]},
        namespace="frag",
        drop_unresolved_refs=True,
    )
    assert (
        cleaner.clean('<p id="a">x</p><p aria-labelledby="a missing">y</p>')
        == '<p id="frag-a">x</p><p aria-labelledby="frag-a">y</p>'
    )
    assert cleaner.namespace_report["dropped_refs"] == [
        ("aria-labelledby", "missing")
    ]


def test_namespace_duplicate_ids_first_occurrence_wins():
    cleaner = Cleaner(tags=ID_TAGS, attributes=ID_ATTRS, namespace="frag")
    assert (
        cleaner.clean('<p id="t">1</p><p id="t">2</p><a href="#t">go</a>')
        == '<p id="frag-t">1</p><p>2</p><a href="#frag-t">go</a>'
    )
    # The duplicate id attribute is dropped deterministically and reported
    assert cleaner.namespace_report["dropped_ids"] == ["t"]
    assert cleaner.namespace_report["id_map"] == {"t": "frag-t"}


def test_namespace_duplicate_after_prefixing():
    # "frag-t" already carries the prefix and "t" maps to the same final id;
    # the first one in document order wins
    cleaner = Cleaner(tags=ID_TAGS, attributes=ID_ATTRS, namespace="frag")
    assert (
        cleaner.clean('<p id="frag-t">1</p><p id="t">2</p>')
        == '<p id="frag-t">1</p><p>2</p>'
    )
    assert cleaner.namespace_report["dropped_ids"] == ["t"]


def test_namespace_idempotent():
    text = (
        '<h1 id="title">x</h1><a href="#title">go</a>'
        '<p aria-labelledby="title missing">y</p>'
    )
    tags = ID_TAGS
    attributes = {"*": ["id", "aria-labelledby"], "a": ["href"]}
    once = clean(text, tags=tags, attributes=attributes, namespace="frag")
    twice = clean(once, tags=tags, attributes=attributes, namespace="frag")
    assert once == twice
    assert "frag-frag" not in twice


def test_namespace_combined_fragments_dont_cross_reference():
    tags = ID_TAGS
    attributes = ID_ATTRS
    frag_one = clean(
        '<p id="title">one</p><a href="#title">1</a>',
        tags=tags,
        attributes=attributes,
        namespace="one",
    )
    frag_two = clean(
        '<p id="title">two</p><a href="#title">2</a>',
        tags=tags,
        attributes=attributes,
        namespace="two",
    )
    combined = frag_one + frag_two
    assert 'id="one-title"' in combined
    assert 'id="two-title"' in combined
    assert 'href="#one-title"' in combined
    assert 'href="#two-title"' in combined
    # No un-namespaced references remain that could bind across fragments
    assert 'href="#title"' not in combined
    assert 'id="title"' not in combined


def test_namespace_stripped_tag_leaves_no_dangling_ref():
    # The span is stripped, so its id never makes it into the id map and the
    # reference to it is dropped instead of dangling
    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["href"]},
        strip=True,
        namespace="frag",
        drop_unresolved_refs=True,
    )
    assert (
        cleaner.clean('<span id="x">hidden</span><a href="#x">go</a>')
        == "hidden<a>go</a>"
    )
    assert cleaner.namespace_report["unresolved_refs"] == [("href", "x")]


def test_namespace_svg_url_reference():
    tags = {"svg", "rect", "pattern"}
    attributes = {"rect": ["fill"], "pattern": ["id"]}
    assert (
        clean(
            '<svg><rect fill="url(#grad)"/><pattern id="grad"></pattern></svg>',
            tags=tags,
            attributes=attributes,
            namespace="frag",
        )
        == '<svg><rect fill="url(#frag-grad)"></rect>'
        '<pattern id="frag-grad"></pattern></svg>'
    )


def test_namespace_svg_hex_color_not_a_reference():
    # "#fff" is a color, not a reference--it must not be rewritten
    tags = {"svg", "rect"}
    attributes = {"rect": ["fill"]}
    assert (
        clean(
            '<svg><rect fill="#fff"/></svg>',
            tags=tags,
            attributes=attributes,
            namespace="frag",
        )
        == '<svg><rect fill="#fff"></rect></svg>'
    )


def test_namespace_svg_local_href():
    tags = {"svg", "pattern"}
    attributes = {"pattern": ["id", "href"]}
    assert (
        clean(
            '<svg><pattern id="patt1" href="#patt2"></pattern>'
            '<pattern id="patt2"></pattern></svg>',
            tags=tags,
            attributes=attributes,
            namespace="frag",
        )
        == '<svg><pattern id="frag-patt1" href="#frag-patt2"></pattern>'
        '<pattern id="frag-patt2"></pattern></svg>'
    )


def test_namespace_style_url_reference():
    assert (
        clean(
            '<p id="grad" style="fill: url(#grad)">x</p>',
            tags={"p"},
            attributes={"p": ["id", "style"]},
            css_sanitizer=CSSSanitizer(),
            namespace="frag",
        )
        == '<p id="frag-grad" style="fill: url(#frag-grad);">x</p>'
    )


def test_namespace_style_url_unresolved_dropped():
    cleaner = Cleaner(
        tags={"p"},
        attributes={"p": ["style"]},
        css_sanitizer=CSSSanitizer(),
        namespace="frag",
        drop_unresolved_refs=True,
    )
    assert cleaner.clean('<p style="fill: url(#gone)">x</p>') == "<p>x</p>"
    assert cleaner.namespace_report["dropped_refs"] == [("style", "gone")]


def test_namespace_report():
    cleaner = Cleaner(tags=ID_TAGS, attributes=ID_ATTRS, namespace="frag")
    cleaner.clean('<p id="a">x</p><a href="#a">go</a>')
    report = cleaner.namespace_report
    assert report["prefix"] == "frag-"
    assert report["id_map"] == {"a": "frag-a"}
    assert report["dropped_ids"] == []
    assert report["unresolved_refs"] == []


def test_namespace_report_none_without_namespace():
    cleaner = Cleaner(tags=ID_TAGS, attributes=ID_ATTRS)
    cleaner.clean('<p id="a">x</p>')
    assert cleaner.namespace_report is None


@pytest.mark.parametrize("namespace", ["", "has space", "has\ttab", 123])
def test_namespace_invalid(namespace):
    with pytest.raises(ValueError):
        Cleaner(namespace=namespace)
