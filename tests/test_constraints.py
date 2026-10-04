"""Tests for the post-clean node constraint phase.

The sample rules defined below are an example *configuration* of the three
combination rules (target=_blank rel tokens, table-cell span ranges, img alt).
They are deliberately not global Cleaner defaults: each Cleaner declares and
orders the rules it wants.

"""

import functools

import pytest

from bleach import clean
from bleach.constraints import (
    DROP_NODE,
    UNWRAP_NODE,
    ConstraintError,
    constrain_tokens,
    del_attr,
    ensure_rel_tokens,
    get_attr,
    set_attr,
)
from bleach.css_sanitizer import CSSSanitizer
from bleach.linkifier import LinkifyFilter
from bleach.sanitizer import Cleaner

# ---------------------------------------------------------------------------
# Example rules (these are application-provided configuration, not defaults)
# ---------------------------------------------------------------------------


def require_rel_for_target_blank(required=("noopener", "noreferrer")):
    """Rule 1: links opening in a new window must carry the given rel tokens."""

    def rule(attrs, context):
        if context.name != "a":
            return
        if get_attr(attrs, "target", default="") == "_blank":
            ensure_rel_tokens(attrs, required)
        return

    return rule


def clamp_table_span(attr_name, cells=("td", "th"), minimum=1, maximum=65534):
    """Rule 2: rowspan/colspan must be an int within [minimum, maximum].

    Non-integer and out-of-range values are removed. Values above the maximum
    are clamped to it (a documented, value-modifying choice).

    """

    def rule(attrs, context):
        if context.name not in cells or (None, attr_name) not in attrs:
            return

        raw = get_attr(attrs, attr_name)
        try:
            value = int(raw, 10)
        except (TypeError, ValueError):
            del_attr(attrs, attr_name)
            return

        if value < minimum:
            del_attr(attrs, attr_name)
        elif value > maximum:
            set_attr(attrs, attr_name, str(maximum))
        return

    return rule


def drop_images_without_alt(attrs, context):
    """Rule 3: keep an img only when alt is present and non-empty."""
    if context.name == "img" and not get_attr(attrs, "alt", default="").strip():
        return DROP_NODE
    return None


def standard_cleaner(**overrides):
    kwargs = {
        "tags": {
            "a",
            "b",
            "i",
            "pre",
            "img",
            "table",
            "tbody",
            "tr",
            "td",
            "th",
        },
        "attributes": {
            "a": ["href", "target", "rel", "title"],
            "img": ["src", "alt"],
            "td": ["rowspan", "colspan"],
            "th": ["rowspan", "colspan"],
        },
        "constraints": [
            require_rel_for_target_blank(),
            clamp_table_span("colspan"),
            clamp_table_span("rowspan"),
            drop_images_without_alt,
        ],
    }
    kwargs.update(overrides)
    return Cleaner(**kwargs)


# ---------------------------------------------------------------------------
# Rule 1: target=_blank -> required rel tokens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "html,expected",
    [
        (
            '<a href="https://example.com" target="_blank">x</a>',
            (
                '<a href="https://example.com" target="_blank" '
                'rel="noopener noreferrer">x</a>'
            ),
        ),
        # Existing tokens are preserved; only missing ones appended.
        (
            '<a href="https://example.com" target="_blank" rel="bookmark">x</a>',
            (
                '<a href="https://example.com" target="_blank" '
                'rel="bookmark noopener noreferrer">x</a>'
            ),
        ),
        # Case-insensitive match; existing NOOPENER must not be duplicated.
        (
            '<a href="https://example.com" target="_blank" rel="NOOPENER">x</a>',
            (
                '<a href="https://example.com" target="_blank" '
                'rel="NOOPENER noreferrer">x</a>'
            ),
        ),
        # Other target values are left completely alone.
        (
            '<a href="https://example.com" target="_self">x</a>',
            '<a href="https://example.com" target="_self">x</a>',
        ),
        # No target at all.
        (
            '<a href="https://example.com">x</a>',
            '<a href="https://example.com">x</a>',
        ),
    ],
)
def test_target_blank_rel(html, expected):
    cleaner = standard_cleaner()
    assert cleaner.clean(html) == expected


def test_target_blank_rel_idempotent():
    cleaner = standard_cleaner()
    once = cleaner.clean('<a href="https://e.com" target="_blank">x</a>')
    assert cleaner.clean(once) == once


# ---------------------------------------------------------------------------
# Rule 2: rowspan/colspan range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "attr,value,kept",
    [
        ("colspan", "3", 'colspan="3"'),
        ("rowspan", "1", 'rowspan="1"'),
        ("colspan", "65534", 'colspan="65534"'),
        ("colspan", "65535", 'colspan="65534"'),
        ("colspan", "99999999", 'colspan="65534"'),
        ("colspan", "0", None),
        ("colspan", "-2", None),
        ("rowspan", "abc", None),
        ("rowspan", "2x", None),
        ("colspan", "", None),
    ],
)
def test_table_span_bounds(attr, value, kept):
    cleaner = standard_cleaner()
    html = f'<table><tbody><tr><td {attr}="{value}">x</td></tr></tbody></table>'
    out = cleaner.clean(html)
    if kept is None:
        assert f"{attr}=" not in out
    else:
        assert kept in out


def test_table_span_idempotent():
    cleaner = standard_cleaner()
    html = (
        '<table><tbody><tr><td colspan="99999" rowspan="0">x</td></tr></tbody></table>'
    )
    once = cleaner.clean(html)
    assert cleaner.clean(once) == once


# ---------------------------------------------------------------------------
# Rule 3: img with non-empty alt only
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "html,expected",
    [
        ('<img src="p.jpg" alt="puppy">', '<img src="p.jpg" alt="puppy">'),
        ('<img src="p.jpg" alt=" x ">', '<img src="p.jpg" alt=" x ">'),
        ('<img src="p.jpg">', ""),
        ('<img src="p.jpg" alt="">', ""),
        ('<img src="p.jpg" alt="   ">', ""),
        # Surrounding text survives; only the node (and its attributes) goes.
        ("before <img src=p.jpg> after", "before  after"),
    ],
)
def test_img_requires_alt(html, expected):
    cleaner = standard_cleaner()
    assert cleaner.clean(html) == expected


def test_img_drop_idempotent():
    cleaner = standard_cleaner()
    assert cleaner.clean("x <img src=p.jpg> y") == cleaner.clean(
        cleaner.clean("x <img src=p.jpg> y")
    )


# ---------------------------------------------------------------------------
# Rule ordering, node actions and ancestor context
# ---------------------------------------------------------------------------


def test_rules_run_in_declaration_order():
    events = []

    def first(attrs, context):
        events.append("first")
        set_attr(attrs, "title", "from-first")

    def second(attrs, context):
        events.append("second")
        assert get_attr(attrs, "title") == "from-first"

    cleaner = Cleaner(
        tags={"span"},
        attributes={"span": ["title"]},
        constraints=[first, second],
    )
    assert cleaner.clean("<span>x</span>") == '<span title="from-first">x</span>'
    assert events == ["first", "second"]


def test_drop_stops_later_rules_for_node():
    calls = []

    def dropping(attrs, context):
        calls.append("drop")
        return DROP_NODE

    def after(attrs, context):
        calls.append("after")

    cleaner = Cleaner(tags={"span"}, constraints=[dropping, after])
    assert cleaner.clean("a<span>gone</span>b") == "ab"
    assert calls == ["drop"]


def test_drop_removes_children():
    cleaner = Cleaner(
        tags={"div", "b"},
        constraints=[lambda attrs, ctx: DROP_NODE if ctx.name == "div" else None],
    )
    assert cleaner.clean("<div>a<b>b</b>c</div>tail") == "tail"


def test_unwrap_keeps_children():
    cleaner = Cleaner(
        tags={"div", "b"},
        constraints=[lambda attrs, ctx: UNWRAP_NODE if ctx.name == "div" else None],
    )
    assert cleaner.clean("<div>a<b>b</b>c</div>tail") == "a<b>b</b>ctail"


def test_unwrap_of_empty_tag_drops_the_tag():
    cleaner = Cleaner(
        tags={"img"},
        attributes={"img": ["src"]},
        constraints=[lambda attrs, ctx: UNWRAP_NODE],
    )
    assert cleaner.clean('x<img src="p.jpg">y') == "xy"


def test_ancestor_context_uses_repaired_tree():
    seen = []

    def record(attrs, context):
        seen.append(context.ancestor_names)

    cleaner = Cleaner(tags={"b", "i"}, constraints=[record])
    # Misnested tags get repaired by the HTML5 parser into two <i> elements.
    cleaner.clean("<b>x<i>y</b>z</i>")
    assert seen == [(), ("b",), ()]


def test_ancestor_context_read_only():
    captured = {}

    def rule(attrs, context):
        captured["ctx"] = context

    cleaner = Cleaner(tags={"div", "b"}, constraints=[rule])
    cleaner.clean("<div><b>x</b></div>")
    with pytest.raises(AttributeError):
        captured["ctx"].name = "hacked"
    with pytest.raises(TypeError):
        captured["ctx"].ancestors[0] = ("x", "y")


def test_ancestor_based_rule():
    # Drop <b> only inside <pre>; the repaired table tree shows real ancestry.
    def drop_b_in_pre(attrs, context):
        if context.name == "b" and context.has_ancestor("pre"):
            return DROP_NODE

    cleaner = Cleaner(tags={"pre", "b"}, constraints=[drop_b_in_pre])
    assert cleaner.clean("<pre><b>gone</b> kept</pre> <b>kept</b>") == (
        "<pre> kept</pre> <b>kept</b>"
    )


# ---------------------------------------------------------------------------
# Security: values added by rules cannot bypass protocol/CSS/attribute policy
# ---------------------------------------------------------------------------


def test_rule_cannot_add_disallowed_protocol():
    def rule(attrs, context):
        set_attr(attrs, "href", "javascript:alert(1)")

    cleaner = Cleaner(tags={"a"}, attributes={"a": ["href"]}, constraints=[rule])
    assert cleaner.clean('<a href="https://x.com">x</a>') == "<a>x</a>"


def test_rule_cannot_add_disallowed_attribute():
    def rule(attrs, context):
        set_attr(attrs, "onclick", "alert(1)")

    cleaner = Cleaner(tags={"span"}, attributes={"span": ["title"]}, constraints=[rule])
    assert cleaner.clean("<span>x</span>") == "<span>x</span>"


def test_rule_style_value_goes_through_css_sanitizer():
    def rule(attrs, context):
        set_attr(
            attrs,
            "style",
            "color: red; position: absolute; background: url(javascript:1)",
        )

    cleaner = Cleaner(
        tags={"span"},
        attributes={"span": ["style"]},
        css_sanitizer=CSSSanitizer(),
        constraints=[rule],
    )
    out = cleaner.clean("<span>x</span>")
    assert "position" not in out
    assert "javascript" not in out
    assert "color" in out


def test_rule_can_add_allowed_value():
    def rule(attrs, context):
        set_attr(attrs, "href", "https://other.example/")
        return attrs

    cleaner = Cleaner(tags={"a"}, attributes={"a": ["href"]}, constraints=[rule])
    assert (
        cleaner.clean('<a href="https://x.com">x</a>')
        == '<a href="https://other.example/">x</a>'
    )


def test_rule_cannot_add_rel_token_without_rel_allowed():
    # rel is not in the attribute policy, so even a token-limit rule cannot
    # smuggle it in.
    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["href", "target"]},
        constraints=[require_rel_for_target_blank()],
    )
    out = cleaner.clean('<a href="https://x.com" target="_blank">x</a>')
    assert "rel=" not in out


def test_constrain_tokens_helper():
    attrs = {(None, "rel"): "nofollow tag friend external"}
    constrain_tokens(attrs, "rel", ["nofollow", "external"])
    assert get_attr(attrs, "rel") == "nofollow external"
    constrain_tokens(attrs, "rel", ["tag"])
    assert (None, "rel") not in attrs


# ---------------------------------------------------------------------------
# Namespaces and misc
# ---------------------------------------------------------------------------


def test_namespace_is_preserved_in_context_and_output():
    seen = []

    def spy(attrs, context):
        seen.append((context.namespace, context.name, context.token_type))

    cleaner = Cleaner(
        tags={"svg", "rect"},
        attributes={"rect": ["width"]},
        constraints=[spy],
    )
    out = cleaner.clean('<svg><rect width="1"></rect></svg>')
    assert out == '<svg><rect width="1"></rect></svg>'
    assert seen == [
        ("http://www.w3.org/2000/svg", "svg", "StartTag"),
        ("http://www.w3.org/2000/svg", "rect", "StartTag"),
    ]


def test_invalid_rule_return_raises():
    cleaner = Cleaner(tags={"span"}, constraints=[lambda attrs, ctx: 42])
    with pytest.raises(ConstraintError):
        cleaner.clean("<span>x</span>")


def test_no_constraints_is_unchanged():
    cleaner = Cleaner(tags={"a"}, attributes={"a": ["href"]})
    assert (
        cleaner.clean('<a href="https://x.com">x</a>')
        == '<a href="https://x.com">x</a>'
    )


def test_clean_function_accepts_constraints():
    out = clean(
        '<a href="https://x.com" target="_blank">x</a>',
        tags={"a"},
        attributes={"a": ["href", "target", "rel"]},
        constraints=[require_rel_for_target_blank()],
    )
    assert 'rel="noopener noreferrer"' in out


# ---------------------------------------------------------------------------
# Links created/modified by linkify still go through the final constraints
# ---------------------------------------------------------------------------


def _add_target_blank(attrs, new=False):
    if (None, "href") in attrs:
        attrs[(None, "target")] = "_blank"
    return attrs


def test_linkified_links_pass_final_constraints():
    linkify = functools.partial(LinkifyFilter, callbacks=[_add_target_blank])
    cleaner = Cleaner(
        tags={"a"},
        attributes={"a": ["href", "target", "rel"]},
        filters=[linkify],
        constraints=[require_rel_for_target_blank()],
    )
    out = cleaner.clean("see https://example.com")
    assert out == (
        'see <a href="https://example.com" target="_blank" '
        'rel="noopener noreferrer">https://example.com</a>'
    )
    # Repeated cleaning stays stable.
    assert cleaner.clean(out) == out
