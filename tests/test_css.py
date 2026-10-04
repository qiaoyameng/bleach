from functools import partial

import pytest

tinycss2 = pytest.importorskip("tinycss2")

from bleach import clean  # noqa
from bleach.css_sanitizer import CSSSanitizer  # noqa


clean = partial(clean, tags={"p"}, attributes=["style"])


@pytest.mark.parametrize(
    "data, styles, expected",
    [
        (
            '<p style="font-family: Arial; color: red; float: left; background-color: red;">bar</p>',
            ["color"],
            '<p style="color: red;">bar</p>',
        ),
        (
            '<p style="border: 1px solid blue; color: red; float: left;">bar</p>',
            ["color"],
            '<p style="color: red;">bar</p>',
        ),
        (
            '<p style="border: 1px solid blue; color: red; float: left;">bar</p>',
            ["color", "float"],
            '<p style="color: red; float: left;">bar</p>',
        ),
        (
            '<p style="color: red; float: left; padding: 1em;">bar</p>',
            ["color", "float"],
            '<p style="color: red; float: left;">bar</p>',
        ),
        (
            '<p style="color: red; float: left; padding: 1em;">bar</p>',
            ["color"],
            '<p style="color: red;">bar</p>',
        ),
        # Handle leading - in attributes
        pytest.param(
            '<p style="cursor: -moz-grab;">bar</p>',
            ["cursor"],
            '<p style="cursor: -moz-grab;">bar</p>',
        ),
        # Handle () in attributes
        (
            '<p style="color: hsl(30,100%,50%);">bar</p>',
            ["color"],
            '<p style="color: hsl(30,100%,50%);">bar</p>',
        ),
        (
            '<p style="color: rgba(255,0,0,0.4);">bar</p>',
            ["color"],
            '<p style="color: rgba(255,0,0,0.4);">bar</p>',
        ),
        # Handle ' in attributes
        pytest.param(
            "<p style=\"text-overflow: ',' ellipsis;\">bar</p>",
            ["text-overflow"],
            "<p style='text-overflow: \",\" ellipsis;'>bar</p>",
        ),
        # Handle " in attributes
        pytest.param(
            "<p style='text-overflow: \",\" ellipsis;'>bar</p>",
            ["text-overflow"],
            "<p style='text-overflow: \",\" ellipsis;'>bar</p>",
        ),
        (
            "<p style='font-family: \"Arial\";'>bar</p>",
            ["font-family"],
            "<p style='font-family: \"Arial\";'>bar</p>",
        ),
        # Handle non-ascii characters in attributes
        (
            '<p style="font-family: \u30e1\u30a4\u30ea\u30aa; color: blue;">bar</p>',
            ["color"],
            '<p style="color: blue;">bar</p>',
        ),
    ],
)
def test_allowed_css(data, styles, expected):
    css_sanitizer = CSSSanitizer(allowed_css_properties=styles)
    assert clean(data, css_sanitizer=css_sanitizer) == expected


def test_valid_css():
    """The sanitizer should fix missing CSS values."""
    css_sanitizer = CSSSanitizer(allowed_css_properties=["color", "float"])
    assert (
        clean('<p style="float: left; color: ">foo</p>', css_sanitizer=css_sanitizer)
        == '<p style="float: left; color: ;">foo</p>'
    )
    assert (
        clean('<p style="color: float: left;">foo</p>', css_sanitizer=css_sanitizer)
        == '<p style="color: float: left;">foo</p>'
    )


@pytest.mark.parametrize(
    "data, expected",
    [
        # No url--unchanged
        (
            '<p style="background: #00D;">foo</p>',
            '<p style="background: #00D;">foo</p>',
        ),
        (
            '<p style="background: url(topbanner.png) #00D;">foo</p>',
            '<p style="background: url(topbanner.png) #00D;">foo</p>',
        ),
        (
            "<p style=\"background: url('topbanner.png') #00D;\">foo</p>",
            "<p style='background: url(\"topbanner.png\") #00D;'>foo</p>",
        ),
        (
            "<p style='background: url(\"topbanner.png\") #00D;'>foo</p>",
            "<p style='background: url(\"topbanner.png\") #00D;'>foo</p>",
        ),
        # Verify urls with spacing
        (
            "<p style=\"background: url(  'topbanner.png') #00D;\">foo</p>",
            "<p style='background: url(  \"topbanner.png\") #00D;'>foo</p>",
        ),
        (
            "<p style=\"background: url('topbanner.png'  ) #00D;\">foo</p>",
            "<p style='background: url(\"topbanner.png\"  ) #00D;'>foo</p>",
        ),
        (
            "<p style=\"background: url(  'topbanner.png'  ) #00D;\">foo</p>",
            "<p style='background: url(  \"topbanner.png\"  ) #00D;'>foo</p>",
        ),
        (
            "<p style=\"background: url (  'topbanner.png'  ) #00D;\">foo</p>",
            "<p style='background: url (  \"topbanner.png\"  ) #00D;'>foo</p>",
        ),
        # Verify urls with character entities
        (
            "<p style=\"background: url&#x09;('topbanner.png') #00D;\">foo</p>",
            '<p style="background: url&#x09;">foo</p>',
        ),
    ],
)
def test_urls(data, expected):
    css_sanitizer = CSSSanitizer(allowed_css_properties=["background"])
    assert clean(data, css_sanitizer=css_sanitizer) == expected


def test_style_hang():
    """The sanitizer should not hang on any inline styles"""
    style = [
        "margin-top: 0px;",
        "margin-right: 0px;",
        "margin-bottom: 1.286em;",
        "margin-left: 0px;",
        "padding-top: 15px;",
        "padding-right: 15px;",
        "padding-bottom: 15px;",
        "padding-left: 15px;",
        "border-top-width: 1px;",
        "border-right-width: 1px;",
        "border-bottom-width: 1px;",
        "border-left-width: 1px;",
        "border-top-style: dotted;",
        "border-right-style: dotted;",
        "border-bottom-style: dotted;",
        "border-left-style: dotted;",
        "border-top-color: rgb(203, 200, 185);",
        "border-right-color: rgb(203, 200, 185);",
        "border-bottom-color: rgb(203, 200, 185);",
        "border-left-color: rgb(203, 200, 185);",
        "background-image: initial;",
        "background-attachment: initial;",
        "background-origin: initial;",
        "background-clip: initial;",
        "background-color: rgb(246, 246, 242);",
        "overflow-x: auto;",
        "overflow-y: auto;",
        "font: italic small-caps bolder condensed 16px/3 cursive;",
        "background-position: initial initial;",
        "background-repeat: initial initial;",
    ]
    html = '<p style="%s">Hello world</p>' % " ".join(style)
    styles = [
        "border",
        "float",
        "overflow",
        "min-height",
        "vertical-align",
        "white-space",
        "margin",
        "margin-left",
        "margin-top",
        "margin-bottom",
        "margin-right",
        "padding",
        "padding-left",
        "padding-top",
        "padding-bottom",
        "padding-right",
        "background",
        "background-color",
        "font",
        "font-size",
        "font-weight",
        "text-align",
        "text-transform",
    ]

    expected = (
        '<p style="'
        "margin-top: 0px; "
        "margin-right: 0px; "
        "margin-bottom: 1.286em; "
        "margin-left: 0px; "
        "padding-top: 15px; "
        "padding-right: 15px; "
        "padding-bottom: 15px; "
        "padding-left: 15px; "
        "background-color: rgb(246, 246, 242); "
        "font: italic small-caps bolder condensed 16px/3 cursive;"
        '">Hello world</p>'
    )

    css_sanitizer = CSSSanitizer(allowed_css_properties=styles)
    assert clean(html, css_sanitizer=css_sanitizer) == expected


@pytest.mark.parametrize(
    "data, styles, expected",
    [
        (
            '<p style="font-family: Droid Sans, serif; white-space: pre-wrap;">text</p>',
            ["font-family", "white-space"],
            '<p style="font-family: Droid Sans, serif; white-space: pre-wrap;">text</p>',
        ),
        (
            "<p style=\"content: '&nbsp;';\">text</p>",
            ["content"],
            # This seems wrong, but it's right. Character entities aren't a
            # thing in CSS, so this is treated as text.
            "<p style='content: \"&amp;nbsp;\";'>text</p>",
        ),
    ],
)
def test_css_parsing_with_entities(data, styles, expected):
    """The sanitizer should be ok with character entities"""
    css_sanitizer = CSSSanitizer(allowed_css_properties=styles)
    assert (
        clean(
            data, tags={"p"}, attributes={"p": ["style"]}, css_sanitizer=css_sanitizer
        )
        == expected
    )


@pytest.mark.parametrize(
    "style, variables, expected",
    [
        # Basic definition and reference
        (
            "--accent: red; color: var(--accent);",
            {"--accent": "color"},
            "--accent: red; color: red;",
        ),
        # Hex colors and lengths
        (
            "--accent: #0a0; --spacing: 10px; color: var(--accent); "
            "width: var(--spacing);",
            {"--accent": "color", "--spacing": "length"},
            "--accent: #0a0; --spacing: 10px; color: #0a0; width: 10px;",
        ),
        # Names without the "--" prefix are normalized
        (
            "--accent: red; color: var(--accent);",
            {"accent": "color"},
            "--accent: red; color: red;",
        ),
        # Last definition wins within the declaration block
        (
            "--accent: red; --accent: blue; color: var(--accent);",
            {"--accent": "color"},
            "--accent: blue; color: blue;",
        ),
        # !important beats later normal definitions
        (
            "--accent: blue !important; --accent: red; color: var(--accent);",
            {"--accent": "color"},
            "--accent: blue !important; color: blue;",
        ),
        # A variable can reference another variable
        (
            "--accent: red; --theme: var(--accent); color: var(--theme);",
            {"--accent": "color", "--theme": "color"},
            "--accent: red; --theme: red; color: red;",
        ),
        # Dependency cycles are dropped; fallbacks still apply
        (
            "--a: var(--b); --b: var(--a); color: var(--a, green);",
            {"--a": "color", "--b": "color"},
            "color: green;",
        ),
        # Self-referential cycle with no fallback drops the declaration
        (
            "--a: var(--a); color: var(--a);",
            {"--a": "color"},
            "",
        ),
        # A self-referencing variable is cyclic even with a fallback
        (
            "--a: var(--a, red); color: var(--a);",
            {"--a": "color"},
            "",
        ),
        # Variables that aren't defined locally (external stylesheets and
        # ancestor inheritance are not resolved) drop the declaration...
        (
            "color: var(--external);",
            {"--accent": "color"},
            "",
        ),
        # ...unless there's a valid fallback
        (
            "color: var(--external, blue);",
            {"--accent": "color"},
            "color: blue;",
        ),
        # Nested fallbacks
        (
            "--accent: red; color: var(--missing, var(--accent));",
            {"--accent": "color"},
            "--accent: red; color: red;",
        ),
        (
            "color: var(--missing, var(--also-missing, blue));",
            {"--accent": "color"},
            "color: blue;",
        ),
        # Fallbacks containing functions
        (
            "color: var(--missing, hsl(120, 100%, 25%));",
            {"--accent": "color"},
            "color: hsl(120, 100%, 25%);",
        ),
        (
            "--spacing: 10px; width: var(--missing, calc(var(--spacing) * 2));",
            {"--spacing": "length"},
            "--spacing: 10px; width: calc(10px * 2);",
        ),
        # Escaped variable names are decoded before matching
        (
            "--\\61 ccent: red; color: var(--\\61 ccent);",
            {"--accent": "color"},
            "--accent: red; color: red;",
        ),
        # Custom property names are case-sensitive
        (
            "--Accent: red; color: var(--accent);",
            {"--Accent": "color"},
            "--Accent: red;",
        ),
        # Values that fail the declared value type are dropped and
        # references fall back
        (
            "--spacing: red; width: var(--spacing, 1px);",
            {"--spacing": "length"},
            "width: 1px;",
        ),
        # Variables that aren't in the allowed set are not resolved
        (
            "--evil: red; color: var(--evil, blue);",
            {"--accent": "color"},
            "color: blue;",
        ),
        # Variables can't smuggle in dangerous functions
        (
            "--x: expression(alert(1)); color: var(--x);",
            {"--x": "any"},
            "",
        ),
        (
            "--x: url(javascript:alert(1)); background-color: var(--x);",
            {"--x": "any"},
            "",
        ),
        (
            "background-color: var(--missing, url(javascript:alert(1)));",
            {"--accent": "color"},
            "",
        ),
        # Substituted tokens can't merge into new tokens on serialize
        (
            "--x: 1; --y: px; width: var(--x)var(--y);",
            {"--x": "any", "--y": "any"},
            "--x: 1; --y: px; width: 1 px;",
        ),
        # Values in allowed properties are validated in variable mode even
        # without var() references
        (
            "color: red; cursor: url(javascript:alert(1)), pointer;",
            {"--accent": "color"},
            "color: red;",
        ),
        # var() inside calc() and other safe functions
        (
            "--spacing: 2em; width: calc(var(--spacing) * 3);",
            {"--spacing": "length"},
            "--spacing: 2em; width: calc(2em * 3);",
        ),
        # Malformed var() invocations drop the declaration
        (
            "color: var(); width: var(1px);",
            {"--accent": "color"},
            "",
        ),
        # Function names are case-insensitive
        (
            "--accent: red; color: VAR(--accent);",
            {"--accent": "color"},
            "--accent: red; color: red;",
        ),
    ],
)
def test_css_variables(style, variables, expected):
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=["color", "background-color", "width", "cursor"],
        allowed_css_variables=variables,
    )
    assert css_sanitizer.sanitize_css(style) == expected


def test_css_variables_default_behavior_unchanged():
    """Without allowed_css_variables, custom properties are dropped and
    declaration values are passed through untouched."""
    css_sanitizer = CSSSanitizer(allowed_css_properties=["color"])
    assert (
        css_sanitizer.sanitize_css("--accent: red; color: var(--accent);")
        == "color: var(--accent);"
    )


def test_css_variables_url_policy():
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=["cursor"],
        allowed_css_variables={"--img": "any"},
        allowed_url_protocols=["https"],
    )
    # Allowed protocol passes
    actual = css_sanitizer.sanitize_css(
        "--img: url(https://example.com/a.png); cursor: var(--img), pointer;"
    )
    expected = (
        "--img: url(https://example.com/a.png); "
        "cursor: url(https://example.com/a.png), pointer;"
    )
    assert actual == expected
    # Disallowed protocol is dropped
    assert (
        css_sanitizer.sanitize_css(
            "--img: url(http://example.com/a.png); cursor: var(--img), pointer;"
        )
        == ""
    )


def test_css_variables_custom_value_type_callable():
    def only_red(tokens):
        tokens = [t for t in tokens if t.type != "whitespace"]
        return (
            len(tokens) == 1
            and tokens[0].type == "ident"
            and tokens[0].lower_value == "red"
        )

    css_sanitizer = CSSSanitizer(
        allowed_css_properties=["color"],
        allowed_css_variables={"--accent": only_red},
    )
    assert (
        css_sanitizer.sanitize_css("--accent: red; color: var(--accent);")
        == "--accent: red; color: red;"
    )
    assert (
        css_sanitizer.sanitize_css("--accent: blue; color: var(--accent);") == ""
    )


def test_css_variables_unknown_value_type_raises():
    with pytest.raises(ValueError):
        CSSSanitizer(allowed_css_variables={"--accent": "bogus"})


def test_css_variables_long_reference_chain():
    """Absurdly long reference chains are dropped, not recursed into."""
    variables = {"--v%d" % i: "color" for i in range(501)}
    style = "; ".join("--v%d: var(--v%d)" % (i, i + 1) for i in range(500))
    style += "; --v500: red; color: var(--v0);"
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=["color"], allowed_css_variables=variables
    )
    # Must not raise RecursionError
    css_sanitizer.sanitize_css(style)

    # Reasonable chains still resolve
    variables = {"--v%d" % i: "color" for i in range(11)}
    style = "; ".join("--v%d: var(--v%d)" % (i, i + 1) for i in range(10))
    style += "; --v10: red; color: var(--v0);"
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=["color"], allowed_css_variables=variables
    )
    assert "color: red;" in css_sanitizer.sanitize_css(style)


def test_css_variables_clean():
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=["color"],
        allowed_css_variables={"--accent": "color"},
    )
    assert (
        clean(
            '<p style="--accent: red; color: var(--accent);">bar</p>',
            css_sanitizer=css_sanitizer,
        )
        == '<p style="--accent: red; color: red;">bar</p>'
    )
