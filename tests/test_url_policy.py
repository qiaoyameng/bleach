import pytest

from bleach.linkifier import Linker
from bleach.sanitizer import Cleaner
from bleach.url_policy import (
    Origin,
    OriginURLPolicy,
    URLPolicyResult,
    parse_origin,
    url_origin,
)


BASE_URL = "https://example.com/"
IMAGE_ORIGINS = ["https://example.com", "https://cdn.example.com"]


def make_cleaner(policy, tags=None, attributes=None, **kwargs):
    return Cleaner(
        tags=tags or {"a", "img"},
        attributes=attributes or {"a": ["href", "title"], "img": ["src"]},
        url_policy=policy,
        base_url=BASE_URL,
        **kwargs,
    )


class TestURLPolicyResult:
    def test_allow(self):
        result = URLPolicyResult.allow("https://example.com/")
        assert result.allowed
        assert bool(result)
        assert result.value == "https://example.com/"
        assert result.reason is None

    def test_reject(self):
        result = URLPolicyResult.reject("nope")
        assert not result.allowed
        assert not bool(result)
        assert result.value is None
        assert result.reason == "nope"


class TestOriginParsing:
    def test_default_port_normalized(self):
        assert parse_origin("https://cdn.example.com:443") == parse_origin(
            "https://cdn.example.com"
        )
        assert parse_origin("http://example.com:80") == Origin("http", "example.com", 80)

    def test_non_default_port_kept(self):
        assert parse_origin("https://cdn.example.com:8443").port == 8443

    def test_idna_host(self):
        assert parse_origin("https://bücher.de") == parse_origin(
            "https://xn--bcher-kva.de"
        )

    def test_userinfo_ignored(self):
        assert parse_origin("https://user:pass@example.com") == parse_origin(
            "https://example.com"
        )

    def test_str(self):
        assert str(parse_origin("https://cdn.example.com")) == "https://cdn.example.com"
        assert (
            str(parse_origin("https://cdn.example.com:8443"))
            == "https://cdn.example.com:8443"
        )


class TestUrlOrigin:
    def test_relative_path(self):
        assert url_origin("/a.png", BASE_URL) == Origin("https", "example.com", 443)
        assert url_origin("a.png", BASE_URL) == Origin("https", "example.com", 443)

    def test_protocol_relative(self):
        assert url_origin("//cdn.example.com/a.png", BASE_URL) == Origin(
            "https", "cdn.example.com", 443
        )

    def test_non_hierarchical_has_no_origin(self):
        # mailto: is non-hierarchical and has no host
        assert url_origin("mailto:jim@example.com", BASE_URL) is None

    def test_userinfo_not_confused_with_host(self):
        assert url_origin("https://cdn.example.com@evil.example.net/a.png").host == (
            "evil.example.net"
        )

    def test_entity_and_control_char_normalization(self):
        # "https" with a tab and an entity-encoded "s"
        assert url_origin("http\t&#115;://example.com/a.png") == Origin(
            "https", "example.com", 443
        )


class TestCleanerURLPolicy:
    def test_same_url_different_result_per_attribute(self):
        """The same external url is fine in a link href, but not in img src"""
        policy = OriginURLPolicy(resource_origins={"image": IMAGE_ORIGINS})
        cleaner = make_cleaner(policy)

        assert (
            cleaner.clean('<a href="https://evil.example.net/x">x</a>')
            == '<a href="https://evil.example.net/x">x</a>'
        )
        assert cleaner.clean('<img src="https://evil.example.net/x">') == "<img>"

    def test_relative_path_uses_base_url(self):
        policy = OriginURLPolicy(resource_origins={"image": IMAGE_ORIGINS})
        cleaner = make_cleaner(policy)

        assert cleaner.clean('<img src="/a.png">') == '<img src="/a.png">'
        assert cleaner.clean('<img src="a.png">') == '<img src="a.png">'

    def test_protocol_relative_url(self):
        policy = OriginURLPolicy(resource_origins={"image": IMAGE_ORIGINS})
        cleaner = make_cleaner(policy)

        assert (
            cleaner.clean('<img src="//cdn.example.com/a.png">')
            == '<img src="//cdn.example.com/a.png">'
        )
        assert cleaner.clean('<img src="//evil.example.net/a.png">') == "<img>"

    def test_default_port_matches(self):
        policy = OriginURLPolicy(resource_origins={"image": IMAGE_ORIGINS})
        cleaner = make_cleaner(policy)

        assert (
            cleaner.clean('<img src="https://cdn.example.com:443/a.png">')
            == '<img src="https://cdn.example.com:443/a.png">'
        )
        assert cleaner.clean('<img src="https://cdn.example.com:8443/a.png">') == (
            "<img>"
        )

    def test_idna_host_matches_punycode_origin(self):
        policy = OriginURLPolicy(
            resource_origins={"image": ["https://xn--bcher-kva.de"]}
        )
        cleaner = make_cleaner(policy)

        assert (
            cleaner.clean('<img src="https://bücher.de/a.png">')
            == '<img src="https://bücher.de/a.png">'
        )

    def test_idna_origin_matches_punycode_host(self):
        policy = OriginURLPolicy(resource_origins={"image": ["https://bücher.de"]})
        cleaner = make_cleaner(policy)

        assert (
            cleaner.clean('<img src="https://xn--bcher-kva.de/a.png">')
            == '<img src="https://xn--bcher-kva.de/a.png">'
        )

    def test_userinfo_does_not_spoof_host(self):
        policy = OriginURLPolicy(resource_origins={"image": IMAGE_ORIGINS})
        cleaner = make_cleaner(policy)

        assert (
            cleaner.clean('<img src="https://cdn.example.com@evil.example.net/a.png">')
            == "<img>"
        )
        assert (
            cleaner.clean('<img src="https://user:pass@cdn.example.com/a.png">')
            == '<img src="https://user:pass@cdn.example.com/a.png">'
        )

    def test_entity_obfuscated_protocol_rejected(self):
        policy = OriginURLPolicy()
        cleaner = make_cleaner(policy)

        assert cleaner.clean('<a href="java&#115;cript:alert(1)">x</a>') == "<a>x</a>"

    def test_control_char_obfuscated_protocol_rejected(self):
        policy = OriginURLPolicy()
        cleaner = make_cleaner(policy)

        assert cleaner.clean('<a href="jav\tascript:alert(1)">x</a>') == "<a>x</a>"

    def test_rejection_reason(self):
        policy = OriginURLPolicy(resource_origins={"image": IMAGE_ORIGINS})

        result = policy("img", None, "src", "https://evil.example.net/x", BASE_URL)
        assert not result.allowed
        assert "https://evil.example.net" in result.reason
        assert "image" in result.reason

        result = policy("a", None, "href", "javascript:alert(1)", BASE_URL)
        assert not result.allowed
        assert result.reason == "protocol not allowed"

    def test_plain_callable_policy(self):
        def policy(tag, namespace, attribute, value, base_url):
            if value.startswith("https://"):
                return URLPolicyResult.allow(value)
            return URLPolicyResult.reject("only https")

        cleaner = make_cleaner(policy)
        assert (
            cleaner.clean('<a href="https://example.com/x">x</a>')
            == '<a href="https://example.com/x">x</a>'
        )
        assert cleaner.clean('<a href="http://example.com/x">x</a>') == "<a>x</a>"

    def test_plain_callable_policy_str_and_none(self):
        def policy(tag, namespace, attribute, value, base_url):
            if "good" in value:
                return value
            return None

        cleaner = make_cleaner(policy)
        assert (
            cleaner.clean('<a href="https://example.com/good">x</a>')
            == '<a href="https://example.com/good">x</a>'
        )
        assert cleaner.clean('<a href="https://example.com/bad">x</a>') == "<a>x</a>"


class TestCDNRewrite:
    def test_rewrite_to_cdn_adopted(self):
        def to_cdn(category, url):
            if category == "image":
                return url.replace("https://example.com/", "https://cdn.example.com/")
            return None

        policy = OriginURLPolicy(
            resource_origins={"image": ["https://cdn.example.com"]},
            rewrite=to_cdn,
        )
        cleaner = make_cleaner(policy)

        assert (
            cleaner.clean('<img src="/a.png">')
            == '<img src="https://cdn.example.com/a.png">'
        )
        assert (
            cleaner.clean('<img src="https://example.com/a.png">')
            == '<img src="https://cdn.example.com/a.png">'
        )

    def test_rewrite_introducing_forbidden_protocol_blocked(self):
        def evil_rewrite(category, url):
            return "javascript:alert(1)"

        policy = OriginURLPolicy(
            resource_origins={"image": IMAGE_ORIGINS},
            rewrite=evil_rewrite,
        )
        cleaner = make_cleaner(policy)

        assert cleaner.clean('<img src="/a.png">') == "<img>"
        assert cleaner.clean('<a href="https://example.com/x">x</a>') == "<a>x</a>"

        result = policy("img", None, "src", "/a.png", BASE_URL)
        assert not result.allowed
        assert result.reason == "rewritten value uses a disallowed protocol"

    def test_rewrite_to_disallowed_origin_blocked(self):
        def offsite_rewrite(category, url):
            return "https://evil.example.net/a.png"

        policy = OriginURLPolicy(
            resource_origins={"image": IMAGE_ORIGINS},
            rewrite=offsite_rewrite,
        )
        cleaner = make_cleaner(policy)

        assert cleaner.clean('<img src="/a.png">') == "<img>"


class TestLinkifyURLPolicy:
    def test_generated_links_go_through_policy(self):
        policy = OriginURLPolicy(resource_origins={"link": ["https://example.com"]})
        linker = Linker(url_policy=policy, base_url=BASE_URL)

        assert (
            linker.linkify("go to https://example.com/x now")
            == 'go to <a href="https://example.com/x" rel="nofollow">https://example.com/x</a> now'
        )
        assert (
            linker.linkify("go to https://evil.example.net/x now")
            == "go to https://evil.example.net/x now"
        )

    def test_generated_links_rewritten(self):
        def to_cdn(category, url):
            return url.replace("https://example.com/", "https://cdn.example.com/")

        policy = OriginURLPolicy(
            resource_origins={"link": ["https://cdn.example.com"]},
            rewrite=to_cdn,
        )
        linker = Linker(url_policy=policy, base_url=BASE_URL)

        assert (
            linker.linkify("go to https://example.com/x now")
            == 'go to <a href="https://cdn.example.com/x" rel="nofollow">https://example.com/x</a> now'
        )

    def test_generated_email_links_still_work(self):
        policy = OriginURLPolicy(resource_origins={"link": ["https://example.com"]})
        linker = Linker(parse_email=True, url_policy=policy, base_url=BASE_URL)

        assert (
            linker.linkify("mail jim@example.com")
            == 'mail <a href="mailto:jim@example.com">jim@example.com</a>'
        )


class TestSVGLocalHrefUnchanged:
    @pytest.mark.parametrize(
        "text, expected",
        [
            (
                '<svg><pattern id="patt1" href="#patt2"></pattern></svg>',
                '<svg><pattern id="patt1" href="#patt2"></pattern></svg>',
            ),
            (
                '<svg><pattern id="patt1" href="https://example.com/patt"></pattern></svg>',
                '<svg><pattern id="patt1"></pattern></svg>',
            ),
        ],
    )
    def test_svg_local_href_constraints_not_loosened(self, text, expected):
        """An unrestricted url policy must not loosen svg local href rules"""
        cleaner = Cleaner(
            tags={"svg", "pattern"},
            attributes={"pattern": ["id", "href"]},
            url_policy=OriginURLPolicy(),
            base_url=BASE_URL,
        )
        assert cleaner.clean(text) == expected
