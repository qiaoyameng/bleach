"""Tests for the post-cleaning node constraint phase."""

import pytest

from bleach import clean
from bleach import callbacks
from bleach.constraints import (
    ClampTableCellSpan,
    NodeAction,
    RequireImageAlt,
    RequireRelForBlankTarget,
)
from bleach.css_sanitizer import CSSSanitizer
from bleach.linkifier import LinkifyFilter
from bleach.sanitizer import Cleaner


TAGS = {
    "a",
    "b",
    "div",
    "i",
    "img",
    "p",
    "span",
    "svg",
    "image",
    "table",
    "tbody",
    "td",
    "th",
    "tr",
}

ATTRS = {
    "a": ["href", "rel", "style", "target"],
    "img": ["alt", "src"],
    "image": ["height", "width"],
    "span": ["class"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}

TABLE_TAGS = {"table", "tbody", "tr", "td", "th"}
TABLE_ATTRS = {"td": ["colspan", "rowspan"], "th": ["colspan", "rowspan"]}

RULES = [
    RequireRelForBlankTarget(),
    ClampTableCellSpan(),
    RequireImageAlt(),
]


def make_cleaner(**overrides):
    kwargs = {"tags": TAGS, "attributes": ATTRS, "constraints": RULES}
    kwargs.update(overrides)
    return Cleaner(**kwargs)


def table_cell(cell_html):
    """Wraps a cell fragment in a valid table so HTML5 keeps it.

    Returns just the serialized cell (and its contents).
    """
    cleaner = Cleaner(
        tags=TABLE_TAGS,
        attributes=TABLE_ATTRS,
        constraints=[ClampTableCellSpan()],
    )
    html = f"<table><tr>{cell_html}x</tr></table>"
    out = cleaner.clean(html)
    # pull out everything between <tr> and the trailing "x"
    start = out.index("<tr>") + 4
    end = out.rindex("x")
    return out[start:end]


# ---------------------------------------------------------------------------
# RequireRelForBlankTarget
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            '<a href="https://example.com" target="_blank">x</a>',
            '<a href="https://example.com" target="_blank" '
            'rel="noopener noreferrer">x</a>',
        ),
        (
            '<a href="https://example.com" target=" _BlAnK ">x</a>',
            '<a href="https://example.com" target=" _BlAnK " '
            'rel="noopener noreferrer">x</a>',
        ),
        (
            '<a href="https://example.com" target="_blank" '
            'rel="external nofollow">x</a>',
            '<a href="https://example.com" target="_blank" '
            'rel="external nofollow noopener noreferrer">x</a>',
        ),
        # tokens outside the allow-list are stripped
        (
            '<a href="https://example.com" target="_blank" '
            'rel="stylesheet tag">x</a>',
            '<a href="https://example.com" target="_blank" '
            'rel="tag noopener noreferrer">x</a>',
        ),
        # duplicate tokens collapse and case is normalized; required tokens
        # are still added once
        (
            '<a href="https://example.com" target="_blank" '
            'rel="NOOPENER noopener NoOpEnEr">x</a>',
            '<a href="https://example.com" target="_blank" '
            'rel="noopener noreferrer">x</a>',
        ),
        # non-blank targets are left completely alone
        (
            '<a href="https://example.com" target="_self" '
            'rel="stylesheet">x</a>',
            '<a href="https://example.com" target="_self" '
            'rel="stylesheet">x</a>',
        ),
        (
            '<a href="https://example.com">x</a>',
            '<a href="https://example.com">x</a>',
        ),
    ],
)
def test_require_rel_for_blank_target(text, expected):
    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["href", "rel", "target"]},
        constraints=[RequireRelForBlankTarget()],
    )
    assert cleaner.clean(text) == expected


def test_require_rel_custom_tokens():
    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["href", "rel", "target"]},
        constraints=[
            RequireRelForBlankTarget(
                required_tokens=("nofollow",),
                allowed_tokens=("nofollow", "ugc"),
            )
        ],
    )
    text = '<a href="https://example.com" target="_blank" rel="ugc tag">x</a>'
    expected = (
        '<a href="https://example.com" target="_blank" '
        'rel="ugc nofollow">x</a>'
    )
    assert cleaner.clean(text) == expected


def test_require_rel_does_not_touch_svg_anchor():
    # SVG content uses a non-HTML namespace; the HTML-namespace rule must
    # not match and namespaces must round-trip.
    cleaner = Cleaner(
        tags={"a", "svg"},
        attributes={"a": ["href", "target"]},
        constraints=[RequireRelForBlankTarget()],
    )
    text = '<svg><a target="_blank">x</a></svg>'
    assert cleaner.clean(text) == text


# ---------------------------------------------------------------------------
# ClampTableCellSpan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cell_html,expected",
    [
        ("<td colspan='1000'>", '<td colspan="1000">'),
        ("<td colspan='1001'>", '<td colspan="1000">'),
        ("<td colspan='999999'>", '<td colspan="1000">'),
        ("<td rowspan='65534'>", '<td rowspan="65534">'),
        ("<td rowspan='65535'>", '<td rowspan="65534">'),
        ("<td colspan='2' rowspan='3'>", '<td colspan="2" rowspan="3">'),
        # non-numeric / negative / zero are invalid -> attribute deleted
        ("<td colspan='abc'>", "<td>"),
        ("<td colspan='-1'>", "<td>"),
        ("<td colspan='0'>", "<td>"),
        ("<td rowspan='  3 '>", '<td rowspan="3">'),
        ("<th colspan='42'>", '<th colspan="42">'),
    ],
)
def test_clamp_table_cell_span(cell_html, expected):
    assert table_cell(cell_html) == expected


def test_clamp_table_cell_span_custom_limits():
    rule = ClampTableCellSpan(tags=("td",), max_colspan=4, max_rowspan=4)
    cleaner = Cleaner(
        tags=TABLE_TAGS,
        attributes=TABLE_ATTRS,
        constraints=[rule],
    )
    out = cleaner.clean("<table><tr><td colspan='9'>x</td></tr></table>")
    assert '<td colspan="4">' in out


# ---------------------------------------------------------------------------
# RequireImageAlt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ('<img src="x" alt="a cat">', '<img src="x" alt="a cat">'),
        ('<img src="x" alt="">', ""),
        ('<img src="x" alt="   ">', ""),
        ('<img src="x">', ""),
        # trailing content survives when the image is dropped
        ('<img src="x" alt="">keep', "keep"),
    ],
)
def test_require_image_alt(text, expected):
    cleaner = Cleaner(
        tags={"img"}, attributes={"img": ["src", "alt"]},
        constraints=[RequireImageAlt()],
    )
    assert cleaner.clean(text) == expected


def test_require_image_alt_skips_foreign_namespace():
    # A top-level <image> is mapped to <img> by the HTML parser; inside
    # <svg> it keeps the SVG namespace, which the rule must not touch, and
    # namespace information must survive the constraint phase.
    cleaner = Cleaner(
        tags=TAGS,
        attributes=ATTRS,
        constraints=[RequireImageAlt()],
    )
    text = "<svg><image width='10' height='10'></image></svg>"
    assert cleaner.clean(text) == (
        '<svg><image width="10" height="10"></image></svg>'
    )


# ---------------------------------------------------------------------------
# Structural actions
# ---------------------------------------------------------------------------


def unwrap(tag):
    def _rule(ctx):
        if ctx.tag == tag:
            return NodeAction.UNWRAP
        return NodeAction.KEEP

    return _rule


def test_unwrap_keeps_children():
    cleaner = Cleaner(
        tags={"div", "span", "b"},
        attributes={},
        constraints=[unwrap("span")],
    )
    text = "<div>x<span>y<b>z</b></span>w</div>"
    assert cleaner.clean(text) == "<div>xy<b>z</b>w</div>"


def test_unwrap_handles_implicit_close_repair():
    cleaner = Cleaner(
        tags={"div", "span"}, attributes={}, constraints=[unwrap("span")]
    )
    # the missing </span> is repaired by HTML5 to close before </div>
    assert cleaner.clean("<div>x<span>y</div>tail") == "<div>xy</div>tail"


def test_drop_removes_subtree():
    def drop_div(ctx):
        return NodeAction.DROP if ctx.tag == "div" else NodeAction.KEEP

    cleaner = Cleaner(
        tags={"div", "b", "span"}, attributes={}, constraints=[drop_div]
    )
    assert cleaner.clean("a<div><span><b>x</b></span></div>b") == "ab"


def test_ancestor_context_is_navigable():
    def rule(ctx):
        if ctx.tag == "a" and ctx.has_ancestor("b"):
            return NodeAction.DROP
        return NodeAction.KEEP

    cleaner = Cleaner(
        tags={"a", "b"}, attributes={"a": ["href"]}, constraints=[rule]
    )
    text = '<b><a href="x">in</a></b><a href="y">out</a>'
    assert cleaner.clean(text) == '<b></b><a href="y">out</a>'


# ---------------------------------------------------------------------------
# Declaration order and idempotency
# ---------------------------------------------------------------------------


def test_rules_run_in_declaration_order_last_structural_action_wins():
    def keep_with_attr(ctx):
        if ctx.tag == "a":
            ctx.set_attr("class", "x")
        return NodeAction.KEEP

    def drop_anchors(ctx):
        return NodeAction.DROP if ctx.tag == "a" else NodeAction.KEEP

    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["class"]},
        constraints=[keep_with_attr, drop_anchors],
    )
    assert cleaner.clean("p<a>q</a>r") == "pr"


def test_rules_run_in_declaration_order_later_unwrap_wins():
    def drop_span(ctx):
        return NodeAction.DROP if ctx.tag == "span" else NodeAction.KEEP

    def unwrap_span(ctx):
        return NodeAction.UNWRAP if ctx.tag == "span" else NodeAction.KEEP

    # Last structural decision (unwrap) overrides the earlier drop.
    cleaner = Cleaner(
        tags={"span", "b"},
        attributes={},
        constraints=[drop_span, unwrap_span],
    )
    assert cleaner.clean("<span><b>x</b></span>") == "<b>x</b>"

    # Reversed order: drop wins.
    cleaner = Cleaner(
        tags={"span", "b"},
        attributes={},
        constraints=[unwrap_span, drop_span],
    )
    assert cleaner.clean("<span><b>x</b></span>") == ""


@pytest.mark.parametrize(
    "text",
    [
        '<a href="https://example.com" target="_blank" rel="noopener '
        'noreferrer">x</a>',
        '<a href="https://example.com" target="_blank" '
        'rel="external">x</a>',
        "<table><tbody><tr><td colspan='1000' rowspan='65534'>x</td></tr>"
        "</tbody></table>",
        '<img src="x" alt="cat">',
        "<div><span>x</span></div>",
    ],
)
def test_phase_is_idempotent(text):
    cleaner = make_cleaner()
    once = cleaner.clean(text)
    assert cleaner.clean(once) == once


# ---------------------------------------------------------------------------
# Safety re-checks: new values cannot bypass protocol / CSS / allow-list
# ---------------------------------------------------------------------------


def test_constraint_added_attribute_must_be_allowed():
    def add_event_handler(ctx):
        ctx.set_attr("onclick", "alert(1)")
        return NodeAction.KEEP

    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["href"]},
        constraints=[add_event_handler],
    )
    assert cleaner.clean('<a href="https://example.com">x</a>') == (
        '<a href="https://example.com">x</a>'
    )


def test_constraint_changed_uri_rechecks_protocol():
    def switch_href(ctx):
        if ctx.tag == "a":
            ctx.set_attr("href", "javascript:alert(1)")
        return NodeAction.KEEP

    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["href", "target"]},
        constraints=[switch_href],
    )
    assert cleaner.clean('<a href="https://example.com">x</a>') == "<a>x</a>"


def test_constraint_changed_style_rechecks_css():
    def add_style(ctx):
        if ctx.tag == "a":
            ctx.set_attr("style", "color: red; position: absolute")
        return NodeAction.KEEP

    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["href", "style"]},
        css_sanitizer=CSSSanitizer(),
        constraints=[add_style],
    )
    out = cleaner.clean('<a href="https://example.com">x</a>')
    assert "position" not in out
    assert 'style="color: red;"' in out


def test_set_attr_rejects_non_string():
    def bad(ctx):
        ctx.set_attr("href", 123)
        return NodeAction.KEEP

    cleaner = Cleaner(
        tags={"a"}, attributes={"a": ["href"]}, constraints=[bad]
    )
    with pytest.raises(TypeError):
        cleaner.clean('<a href="https://example.com">x</a>')


# ---------------------------------------------------------------------------
# Linkify integration: final constraints cover linkified links too
# ---------------------------------------------------------------------------


def linkify_blank_filter():
    return lambda source: LinkifyFilter(
        source, callbacks=[callbacks.target_blank, callbacks.nofollow]
    )


def test_linkify_created_links_pass_final_constraints():
    cleaner = Cleaner(
        tags=TAGS,
        attributes=ATTRS,
        filters=[linkify_blank_filter()],
        constraints=[RequireRelForBlankTarget()],
    )
    out = cleaner.clean("see https://example.com please")
    assert out == (
        'see <a href="https://example.com" target="_blank" '
        'rel="nofollow noopener noreferrer">https://example.com</a> please'
    )
    assert cleaner.clean(out) == out


def test_linkify_existing_links_are_constrained():
    cleaner = Cleaner(
        tags=TAGS,
        attributes=ATTRS,
        filters=[linkify_blank_filter()],
        constraints=[RequireRelForBlankTarget()],
    )
    out = cleaner.clean('<a href="https://example.com">site</a>')
    assert 'rel="nofollow noopener noreferrer"' in out
    assert 'target="_blank"' in out


def test_constraints_disabled_by_default():
    # without constraints the phase does not run and default behavior holds
    cleaner = Cleaner(tags={"a"}, attributes={"a": ["href", "target", "rel"]})
    text = '<a href="https://example.com" target="_blank">x</a>'
    assert cleaner.clean(text) == text


def test_clean_function_passes_constraints():
    out = clean(
        '<a href="https://example.com" target="_blank">x</a>',
        tags={"a"},
        attributes={"a": ["href", "target", "rel"]},
        constraints=[RequireRelForBlankTarget()],
    )
    assert 'rel="noopener noreferrer"' in out


def test_node_context_helper_mutations():
    seen = {}

    def rule(ctx):
        if ctx.tag == "a":
            seen["target"] = ctx.get_attr("target")
            seen["missing"] = ctx.get_attr("nope", "dflt")
            assert ctx.has_attr("target")
            ctx.del_attr("target")
            ctx.set_attr("rel", "noopener")
        return NodeAction.KEEP

    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["href", "rel", "target"]},
        constraints=[rule],
    )
    out = cleaner.clean('<a href="https://example.com" target="_blank">x</a>')
    assert seen == {"target": "_blank", "missing": "dflt"}
    assert 'target="_blank"' not in out
    assert 'rel="noopener"' in out
