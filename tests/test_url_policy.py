"""Tests for the URL policy entry point shared by Cleaner and linkify."""

import pytest

from bleach import linkify
from bleach.linkifier import Linker
from bleach.sanitizer import Cleaner
from bleach.url_policy import (
    REASON_DISALLOWED_PROTOCOL,
    REASON_INVALID_URL,
    REASON_ORIGIN_NOT_ALLOWED,
    REASON_REWRITE_INVALID,
    CATEGORY_IMAGE,
    CATEGORY_LINK,
    Origin,
    URLPolicy,
)


BASE_URL = "https://www.example.com/app/"


def make_cleaner(policy):
    return Cleaner(
        tags={"a", "img", "svg", "pattern"},
        attributes={
            "a": ["href"],
            "img": ["src"],
            "pattern": ["id", "href"],
        },
        url_policy=policy,
    )


def locked_policy(**kwargs):
    options = dict(
        base_url=BASE_URL,
        origins={
            # Rich text links may point at any external site
            CATEGORY_LINK: ["*"],
            # Images must be same-site or served by the image CDN
            CATEGORY_IMAGE: ["self", "https://img-cdn.example.com"],
            # Everything else (e.g. action/cite) stays on-site
            "default": ["self"],
        },
    )
    options.update(kwargs)
    return URLPolicy(**options)


#
# Direct URLPolicy.check tests
#


def test_check_returns_adopted_value_or_reason():
    policy = locked_policy()

    result = policy.check("a", "href", "https://other.com/x")
    assert result.allowed is True
    assert result.value == "https://other.com/x"
    assert result.reason is None

    result = policy.check("img", "src", "https://other.com/x")
    assert result.allowed is False
    assert result.value is None
    assert result.reason == REASON_ORIGIN_NOT_ALLOWED
    assert bool(result) is False


def test_same_url_different_result_by_attribute():
    """The same URL is allowed in href but rejected in src."""
    policy = locked_policy()

    assert policy.check("a", "href", "https://other.com/x").allowed
    assert not policy.check("img", "src", "https://other.com/x").allowed


def test_relative_and_protocol_relative_resolve_against_base():
    policy = locked_policy()

    # Relative path resolves to the base origin ("self")
    assert policy.check("img", "src", "/assets/a.png").value == "/assets/a.png"
    assert policy.check("img", "src", "assets/a.png").allowed

    # Protocol-relative inherits the base scheme
    assert policy.check("img", "src", "//img-cdn.example.com/a.png").allowed
    assert not policy.check("img", "src", "//evil.example/a.png").allowed

    # Relative URL with no base configured cannot be resolved
    policy_without_base = URLPolicy(
        origins={"default": ["self"]},
    )
    result = policy_without_base.check("img", "src", "/assets/a.png")
    assert not result.allowed
    assert result.reason == REASON_INVALID_URL


def test_default_port_normalized():
    policy = locked_policy()

    # Explicit default port is the same origin
    assert policy.check("img", "src", "https://www.example.com:443/a.png").allowed

    # Non-default port does not match the CDN origin
    assert not policy.check(
        "img", "src", "https://img-cdn.example.com:8443/a.png"
    ).allowed

    policy_with_port = URLPolicy(
        base_url=BASE_URL,
        origins={CATEGORY_IMAGE: ["https://img-cdn.example.com:8443"]},
    )
    assert policy_with_port.check(
        "img", "src", "https://img-cdn.example.com:8443/a.png"
    ).allowed


def test_idna_hosts_match_in_either_form():
    # Origin configured with a Unicode hostname
    policy = URLPolicy(
        base_url=BASE_URL,
        origins={"default": ["https://k\u00f6ln.example"]},
    )
    assert policy.check("a", "href", "https://xn--kln-sna.example/p").allowed
    assert policy.check("a", "href", "https://k\u00f6ln.example/p").allowed

    # Origin configured with an A-label
    policy = URLPolicy(
        base_url=BASE_URL,
        origins={"default": ["https://xn--bcher-kva.example"]},
    )
    assert policy.check("a", "href", "https://xn--bcher-kva.example/x").allowed
    # Hosts are case-insensitive
    assert policy.check("a", "href", "https://XN--BCHER-KVA.example/x").allowed


def test_userinfo_is_ignored_for_origin_comparison():
    """user@host must never downgrade the origin check to userinfo host."""
    policy = locked_policy()

    # The actual host is evil.example, regardless of the userinfo
    result = policy.check("img", "src", "https://img-cdn.example.com@evil.example/x")
    assert not result.allowed
    assert result.reason == REASON_ORIGIN_NOT_ALLOWED


def test_invisible_characters_cannot_smuggle_origin_or_protocol():
    policy = locked_policy()

    # Unicode invisible characters in the scheme are stripped by the
    # protocol normalization, exactly like the historical protocol check
    for payload in [
        "javascript\u200b:alert(1)",
        "java\u00adscript:alert(1)",
        "\ufeffjavascript:alert(1)",
        "javas&#x09;cript:alert(1)",
        "&#14;javascript:alert(1)",
    ]:
        result = policy.check("img", "src", payload)
        assert not result.allowed
        assert result.reason == REASON_DISALLOWED_PROTOCOL

    # Invisible characters in the host cannot trick IDNA into matching
    # "self" or the CDN origin
    for payload in [
        "https://www.exa\u200bmple.com/x",
        "https://www.exa\u00admple.com/x",
        "https://www.\ufeffexample.com/x",
    ]:
        result = policy.check("img", "src", payload)
        assert not result.allowed
        assert result.reason in (REASON_INVALID_URL, REASON_ORIGIN_NOT_ALLOWED)


def test_anchors_are_same_document_references():
    policy = URLPolicy(
        base_url=BASE_URL,
        origins={CATEGORY_LINK: ["self"], "default": ["self"]},
        protocols=set(),
    )
    # Even with no allowed protocols, bare anchors are accepted as before
    assert policy.check("a", "href", "#section").value == "#section"


def test_unparseable_urls_rejected():
    policy = locked_policy()
    assert not policy.check("a", "href", "http://[::1/x").allowed
    assert policy.check("a", "href", "http://host:99999/x").reason == REASON_INVALID_URL

    # A value that parses for protocol purposes but fails origin resolution
    # is also rejected
    assert (
        policy.check("img", "src", "https://host:99999/x").reason
        == REASON_INVALID_URL
    )


def test_origin_parsing_rejects_bad_specs():
    with pytest.raises(ValueError):
        Origin.parse("img-cdn.example.com")
    origin = Origin.parse("https://img-cdn.example.com:443/path#frag")
    assert origin == Origin("https", "img-cdn.example.com", None)


def test_classify_uses_attribute_and_overrides():
    policy = locked_policy()
    assert policy.classify("a", None, "href") == CATEGORY_LINK
    assert policy.classify("img", None, "src") == CATEGORY_IMAGE
    assert policy.classify("img", None, "data") == "object"
    assert policy.classify("x", None, "bogus") == "default"

    policy = locked_policy(
        resource_classes={("video", "src"): "media", "poster": "media"}
    )
    assert policy.classify("video", None, "src") == "media"
    assert policy.classify("any", None, "poster") == "media"

    policy = locked_policy(
        resource_classes=lambda tag, namespace, attr: "custom"
    )
    assert policy.classify("a", None, "href") == "custom"


#
# CDN rewrite tests
#


def test_rewrite_relative_to_cdn_is_accepted():
    def to_cdn(tag, namespace, attr, value):
        if value.startswith("/"):
            return "https://img-cdn.example.com" + value
        return value

    policy = locked_policy(rewrite={CATEGORY_IMAGE: to_cdn})
    result = policy.check("img", "src", "/assets/a.png")
    assert result.allowed
    assert result.value == "https://img-cdn.example.com/assets/a.png"
    assert result.stage == "rewritten"


def test_rewrite_introducing_forbidden_protocol_is_rejected():
    def evil_rewrite(tag, namespace, attr, value):
        return "javascript:alert(1)"

    policy = locked_policy(rewrite={CATEGORY_IMAGE: evil_rewrite})
    result = policy.check("img", "src", "/assets/a.png")
    assert not result.allowed
    assert result.reason == REASON_DISALLOWED_PROTOCOL
    assert result.stage == "rewritten"


def test_rewrite_to_disallowed_origin_is_rejected():
    def offsite_rewrite(tag, namespace, attr, value):
        return "https://evil.example/x.png"

    policy = locked_policy(rewrite={CATEGORY_IMAGE: offsite_rewrite})
    result = policy.check("img", "src", "/assets/a.png")
    assert not result.allowed
    assert result.reason == REASON_ORIGIN_NOT_ALLOWED


def test_rewrite_returning_non_string_rejected():
    policy = locked_policy(rewrite={CATEGORY_IMAGE: lambda *a: 123})
    result = policy.check("img", "src", "/assets/a.png")
    assert not result.allowed
    assert result.reason == REASON_REWRITE_INVALID


def test_generic_rewrite_applies_to_all_categories():
    policy = locked_policy(rewrite=lambda tag, ns, attr, value: value + "?cb=1")
    result = policy.check("a", "href", "https://other.com/x")
    assert result.value == "https://other.com/x?cb=1"


def test_protocol_relative_inherits_base_scheme_for_matching():
    # Base is http, the CDN origin entry is https: no match
    policy = URLPolicy(
        base_url="http://www.example.com/",
        origins={CATEGORY_IMAGE: ["https://img-cdn.example.com"]},
    )
    assert not policy.check("img", "src", "//img-cdn.example.com/a.png").allowed

    # Reverse direction mismatch is caught too
    policy = URLPolicy(
        base_url="https://www.example.com/",
        origins={CATEGORY_IMAGE: ["http://img-cdn.example.com"]},
    )
    assert not policy.check("img", "src", "//img-cdn.example.com/a.png").allowed


def test_entity_encoded_protocol_attacks_blocked():
    cleaner = make_cleaner(locked_policy())
    assert cleaner.clean('<img src="javascript&#58;alert(1)">') == "<img>"
    assert cleaner.clean('<img src="java&#10;script:alert(1)">') == "<img>"
    assert cleaner.clean('<a href="javascript&#58;alert(1)">x</a>') == "<a>x</a>"


def test_data_url_blocked_and_custom_protocol_and_mailto():
    cleaner = make_cleaner(locked_policy())
    assert cleaner.clean('<img src="data:text/html,x">') == "<img>"
    assert cleaner.clean('<a href="mailto:user@example.com">m</a>') == (
        '<a href="mailto:user@example.com">m</a>'
    )

    policy = URLPolicy(
        base_url=BASE_URL,
        protocols={"http", "https", "myproto"},
        origins={CATEGORY_LINK: ["*"], "default": ["self"]},
    )
    cleaner = make_cleaner(policy)
    assert cleaner.clean('<a href="myproto://whatever">x</a>') == (
        '<a href="myproto://whatever">x</a>'
    )
    # mailto is no longer in the protocol allowlist
    assert cleaner.clean('<a href="mailto:x@y.com">x</a>') == "<a>x</a>"


def test_empty_protocols_blocks_relative_but_not_anchors():
    policy = URLPolicy(
        base_url=BASE_URL,
        protocols=set(),
        origins={CATEGORY_IMAGE: ["self"]},
    )
    cleaner = make_cleaner(policy)
    assert cleaner.clean('<img src="/a.png">') == "<img>"
    assert cleaner.clean('<img src="#x">') == '<img src="#x">'


def test_origin_host_tricks_rejected():
    policy = locked_policy()
    # userinfo, backslash and percent tricks cannot spoof the CDN origin
    for value in [
        "https://img-cdn.example.com@evil.com/x",
        "https://img-cdn.example.com%2f@evil.com/x",
        "https://img-cdn.example.com%2f%2fevil.com/x",
    ]:
        assert not policy.check("img", "src", value).allowed


def test_host_matching_is_case_and_trailing_dot_insensitive():
    policy = locked_policy()
    assert policy.check("img", "src", "HTTPS://IMG-CDN.EXAMPLE.COM/a").allowed
    assert policy.check("img", "src", "https://img-cdn.example.com./a").allowed


#
# Cleaner integration
#


def test_cleaner_href_vs_src_different_results():
    cleaner = make_cleaner(locked_policy())

    assert (
        cleaner.clean('<a href="https://other.com/x">ext</a>')
        == '<a href="https://other.com/x">ext</a>'
    )
    assert (
        cleaner.clean('<img src="https://other.com/a.png">')
        == "<img>"
    )
    assert (
        cleaner.clean('<img src="https://img-cdn.example.com/a.png">')
        == '<img src="https://img-cdn.example.com/a.png">'
    )
    assert cleaner.clean('<img src="/assets/a.png">') == '<img src="/assets/a.png">'
    assert cleaner.clean('<img src="//img-cdn.example.com/a.png">') == (
        '<img src="//img-cdn.example.com/a.png">'
    )
    assert cleaner.clean('<img src="//evil.example/a.png">') == "<img>"


def test_cleaner_rewrite_protocol_attack_blocked():
    def cdn(tag, namespace, attr, value):
        if "evil" in value:
            return "javascript:alert(1)"
        return value

    cleaner = make_cleaner(locked_policy(rewrite={CATEGORY_IMAGE: cdn}))
    assert cleaner.clean('<img src="https://evil.example/a.png">') == "<img>"


def test_cleaner_rewrite_to_cdn_succeeds():
    def to_cdn(tag, namespace, attr, value):
        if value.startswith("/"):
            return "https://img-cdn.example.com" + value
        return value

    cleaner = make_cleaner(locked_policy(rewrite={CATEGORY_IMAGE: to_cdn}))
    assert cleaner.clean('<img src="/assets/a.png">') == (
        '<img src="https://img-cdn.example.com/assets/a.png">'
    )


def test_cleaner_without_policy_keeps_legacy_behavior():
    cleaner = Cleaner(
        tags={"a", "img"},
        attributes={"a": ["href"], "img": ["src"]},
    )
    assert cleaner.clean('<img src="https://anywhere.example/a.png">') == (
        '<img src="https://anywhere.example/a.png">'
    )


def test_svg_local_fragment_constraints_unchanged():
    cleaner = make_cleaner(locked_policy())

    # Local references remain allowed
    assert cleaner.clean('<svg><pattern href="#patt2"></pattern></svg>') == (
        '<svg><pattern href="#patt2"></pattern></svg>'
    )
    # Non-local references are still dropped by the SVG rule
    assert cleaner.clean(
        '<svg><pattern href="https://example.com/patt"></pattern></svg>'
    ) == "<svg><pattern></pattern></svg>"
    # xlink local references too (html5lib serializer drops the xlink part)
    assert cleaner.clean(
        '<svg><pattern id="p1" xlink:href="#patt2"></pattern></svg>'
    ) == '<svg><pattern id="p1" href="#patt2"></pattern></svg>'


#
# Linker integration
#


def test_linkify_generated_link_goes_through_policy():
    # Links point anywhere, so the generated link is kept
    linker = Linker(url_policy=locked_policy())
    assert (
        linker.linkify("see https://other.com/x here")
        == 'see <a href="https://other.com/x" rel="nofollow">'
        "https://other.com/x</a> here"
    )

    # A locked-down policy rejects the generated link and emits plain text
    strict = URLPolicy(
        base_url=BASE_URL,
        origins={CATEGORY_LINK: ["self"], "default": ["self"]},
    )
    assert (
        Linker(url_policy=strict).linkify("see https://other.com/x here")
        == "see https://other.com/x here"
    )


def test_linkify_generated_link_cdn_rewrite_attack_blocked():
    def evil_rewrite(tag, namespace, attr, value):
        return "javascript:alert(1)"

    policy = locked_policy(rewrite={CATEGORY_LINK: evil_rewrite})
    # Even a rewrite callback trying to inject javascript is dropped as text
    assert (
        Linker(url_policy=policy).linkify("see https://other.com/x here")
        == "see https://other.com/x here"
    )


def test_linkify_module_function_accepts_policy():
    strict = URLPolicy(
        base_url=BASE_URL,
        origins={CATEGORY_LINK: ["self"], "default": ["self"]},
    )
    assert (
        linkify("see https://other.com/x here", url_policy=strict)
        == "see https://other.com/x here"
    )


def test_linkify_existing_link_validated():
    strict = URLPolicy(
        base_url=BASE_URL,
        origins={CATEGORY_LINK: ["self"], "default": ["self"]},
    )
    # An existing off-site <a> tag gets dropped to text just like generated
    # links
    assert (
        Linker(url_policy=strict).linkify('<a href="https://other.com/x">x</a>')
        == "x"
    )
