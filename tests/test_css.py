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


ALLOWED_TEST_VARIABLES = {
    "--accent": "color",
    "--spacing": "length",
    "--gap": "length",
    "--light": "percentage",
    "--a": "color",
    "--b": "color",
}


@pytest.mark.parametrize(
    "data, expected",
    [
        # Basic substitution; the variable definition is not emitted
        (
            '<p style="--accent: red; color: var(--accent);">bar</p>',
            '<p style="color: red;">bar</p>',
        ),
        (
            '<p style="--spacing: 10px; width: var(--spacing);">bar</p>',
            '<p style="width: 10px;">bar</p>',
        ),
        # A bare zero is a valid length
        (
            '<p style="--spacing: 0; width: var(--spacing);">bar</p>',
            '<p style="width: 0;">bar</p>',
        ),
        # !important on the referencing declaration is preserved
        (
            '<p style="--accent: red; color: var(--accent) !important;">bar</p>',
            '<p style="color: red !important;">bar</p>',
        ),
        # Last definition wins within the same block
        (
            '<p style="--accent: red; --accent: blue; color: var(--accent);">bar</p>',
            '<p style="color: blue;">bar</p>',
        ),
        # !important definitions beat normal ones regardless of order
        (
            '<p style="--accent: blue !important; --accent: green; color: var(--accent);">bar</p>',
            '<p style="color: blue;">bar</p>',
        ),
        (
            '<p style="--accent: green; --accent: blue !important; --accent: red; color: var(--accent);">bar</p>',
            '<p style="color: blue;">bar</p>',
        ),
        # Variables can reference other variables
        (
            '<p style="--spacing: 5px; --gap: var(--spacing); width: var(--gap);">bar</p>',
            '<p style="width: 5px;">bar</p>',
        ),
        # Nested fallbacks
        (
            '<p style="color: var(--missing, var(--also-missing, green));">bar</p>',
            '<p style="color: green;">bar</p>',
        ),
        # Fallbacks can contain functions
        (
            '<p style="color: var(--missing, hsl(30,100%,50%));">bar</p>',
            '<p style="color: hsl(30,100%,50%);">bar</p>',
        ),
        # var() inside function arguments
        (
            '<p style="--light: 50%; color: hsl(30, 100%, var(--light));">bar</p>',
            '<p style="color: hsl(30, 100%, 50%);">bar</p>',
        ),
        # Escaped names resolve to the same variable
        (
            '<p style="--\\61 ccent: red; color: var(--accent);">bar</p>',
            '<p style="color: red;">bar</p>',
        ),
        (
            '<p style="--accent: red; color: var(--\\61 ccent);">bar</p>',
            '<p style="color: red;">bar</p>',
        ),
        # Cyclic dependencies are invalid: the fallback is used, or the
        # declaration is dropped when there is no fallback
        (
            '<p style="--a: var(--b); --b: var(--a); color: var(--a, red);">bar</p>',
            '<p style="color: red;">bar</p>',
        ),
        (
            '<p style="--a: var(--b); --b: var(--a); color: var(--a);">bar</p>',
            '<p style="">bar</p>',
        ),
        # Values that don't match the declared value type are dropped
        (
            '<p style="--accent: 10px; color: var(--accent);">bar</p>',
            '<p style="">bar</p>',
        ),
        (
            '<p style="--spacing: 10deg; width: var(--spacing);">bar</p>',
            '<p style="">bar</p>',
        ),
        # Variables not declared in this block (external stylesheets and
        # ancestor inheritance are not resolved) use the fallback or drop
        (
            '<p style="color: var(--external);">bar</p>',
            '<p style="">bar</p>',
        ),
        (
            '<p style="color: var(--external, blue);">bar</p>',
            '<p style="color: blue;">bar</p>',
        ),
        # Variables not in allowed_css_variables are never resolved
        (
            '<p style="--evil: red; color: var(--evil);">bar</p>',
            '<p style="">bar</p>',
        ),
        # Variables cannot smuggle dangerous functions or urls
        (
            "<p style=\"cursor: var(--missing, url('javascript:alert(1)'));\">bar</p>",
            '<p style="">bar</p>',
        ),
        (
            '<p style="color: var(--missing, expression(alert(1)));">bar</p>',
            '<p style="">bar</p>',
        ),
        (
            "<p style=\"--accent: url('javascript:alert(1)'); color: var(--accent, red);\">bar</p>",
            '<p style="color: red;">bar</p>',
        ),
        (
            "<p style=\"cursor: var(--missing, url('data:text/html,x'));\">bar</p>",
            '<p style="">bar</p>',
        ),
        # Safe urls in fallbacks are fine
        (
            "<p style=\"cursor: var(--missing, url('https://example.com/a.png')), auto;\">bar</p>",
            '<p style=\'cursor: url("https://example.com/a.png"), auto;\'>bar</p>',
        ),
    ],
)
def test_allowed_css_variables(data, expected):
    css_sanitizer = CSSSanitizer(
        allowed_css_properties=["color", "width", "cursor"],
        allowed_css_variables=ALLOWED_TEST_VARIABLES,
    )
    assert clean(data, css_sanitizer=css_sanitizer) == expected


def test_css_variables_default_behavior_unchanged():
    """Without allowed_css_variables, var() passes through untouched"""
    css_sanitizer = CSSSanitizer(allowed_css_properties=["color"])
    assert (
        clean('<p style="color: var(--accent);">bar</p>', css_sanitizer=css_sanitizer)
        == '<p style="color: var(--accent);">bar</p>'
    )


@pytest.mark.parametrize(
    "allowed_css_variables",
    [
        {"accent": "color"},
        {"--accent": "bogus"},
    ],
)
def test_css_variables_invalid_configuration(allowed_css_variables):
    with pytest.raises(ValueError):
        CSSSanitizer(allowed_css_variables=allowed_css_variables)
