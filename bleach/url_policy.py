"""URL policy for deciding which URI attribute values Cleaner and linkify adopt.

This module is the single place where Bleach decides whether the value of a
URI-valued attribute (``href``, ``src`` and friends) is safe to keep.  It does
two things that the old protocol-only check did not:

1. checks that the protocol is allowed using the exact same entity and control
   character normalization the sanitizer has always used;
2. resolves the value against a fixed base URL and checks that its *origin* is
   allowed for the resource category the attribute belongs to.

Everything is done with string parsing only--there are no network requests and
no DNS lookups.  Origins are compared structurally, so hostnames are compared
using IDNA encoding and default ports are normalized before comparison.
"""

import re
import unicodedata

from bleach import html5lib_shim
from bleach.parse_shim import urljoin, urlparse


#
# Rejection reasons
#

#: The value uses a protocol that is not allowed.
REASON_DISALLOWED_PROTOCOL = "disallowed-protocol"

#: The protocol is allowed, but the resolved origin is not in the allowlist
#: for the resource category.
REASON_ORIGIN_NOT_ALLOWED = "origin-not-allowed"

#: The value cannot be parsed as a URL or cannot be resolved (for example a
#: relative URL without a configured base URL).
REASON_INVALID_URL = "invalid-url"

#: A configured rewrite function returned something other than a string.
REASON_REWRITE_INVALID = "rewrite-invalid-url"


#: Built-in resource categories.  Businesses may define additional category
#: names; unknown categories fall back to the ``default`` category.
CATEGORY_LINK = "link"
CATEGORY_IMAGE = "image"
CATEGORY_FRAME = "frame"
CATEGORY_OBJECT = "object"
CATEGORY_DEFAULT = "default"


#: Default mapping of attribute names to resource categories.  The mapping
#: is keyed by attribute name because the attributes that carry URI values
#: (see ``html5lib_shim.attr_val_is_uri``) keep the same meaning across tags;
#: pass ``resource_classes`` to override a specific (tag, attribute) pair.
DEFAULT_ATTRIBUTE_CATEGORIES = {
    "href": CATEGORY_LINK,
    "cite": CATEGORY_LINK,
    "src": CATEGORY_IMAGE,
    "poster": CATEGORY_IMAGE,
    "background": CATEGORY_IMAGE,
    "datasrc": CATEGORY_IMAGE,
    "dynsrc": CATEGORY_IMAGE,
    "lowsrc": CATEGORY_IMAGE,
    "ping": CATEGORY_IMAGE,
    "action": CATEGORY_FRAME,
    "formaction": CATEGORY_FRAME,
    "longdesc": CATEGORY_FRAME,
    "data": CATEGORY_OBJECT,
    "classid": CATEGORY_OBJECT,
    "codebase": CATEGORY_OBJECT,
}


#: Default ports per scheme so that ``https://example.com:443`` and
#: ``https://example.com`` compare as the same origin.
_DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
    "ws": 80,
    "wss": 443,
    "ftp": 21,
}


#: Strips backtick, whitespace and control characters (including the C1 range
#: and Unicode whitespace), matching the normalization the protocol check has
#: historically used after entity conversion.
_CONTROL_CHARS_RE = re.compile(r"[`\000-\040\177-\240\s]+")

#: ASCII-only filtering used by the protocol check so that invisible Unicode
#: characters cannot smuggle a scheme past the parser.
_NON_ASCII_RE = re.compile(r"[^\x00-\x7f]")


def normalize_uri_for_protocol(value):
    """Normalizes a URI value the way the protocol check needs.

    Character entities are converted, then backtick, whitespace and control
    characters are stripped, then non-ASCII characters are stripped and the
    result is lowercased.

    The normalized value is only used for matching and must never be emitted
    in cleaned output.
    """
    normalized = html5lib_shim.convert_entities(value)
    normalized = _CONTROL_CHARS_RE.sub("", normalized)
    normalized = _NON_ASCII_RE.sub("", normalized)
    return normalized.lower()


def normalize_uri_for_origin(value):
    """Normalizes a URI value the way origin resolution needs.

    This performs the same entity conversion and control/whitespace stripping
    as :func:`normalize_uri_for_protocol`, but keeps non-ASCII characters so
    that internationalized hostnames can be IDNA encoded.
    """
    normalized = html5lib_shim.convert_entities(value)
    return _CONTROL_CHARS_RE.sub("", normalized)


def validate_protocol(value, allowed_protocols):
    """Checks the protocol of a URI value against an allowlist.

    This contains the exact logic historically used by
    ``BleachSanitizerFilter.sanitize_uri_value`` (including anchor handling
    and the fallback for protocols ``urlparse`` does not recognize) so that
    the URL policy is never more permissive than the old check.

    :arg str value: the raw URI value
    :arg set allowed_protocols: lowercased allowed protocols

    :returns: ``True`` if the value may be kept, ``False`` otherwise
    """
    normalized = normalize_uri_for_protocol(value)

    try:
        parsed = urlparse(normalized)
    except ValueError:
        return False

    if parsed.scheme:
        return parsed.scheme in allowed_protocols

    # Allow uris that are just an anchor
    if normalized.startswith("#"):
        return True

    # Handle protocols that urlparse doesn't recognize like "myprotocol"
    if ":" in normalized and normalized.split(":")[0] in allowed_protocols:
        return True

    # No protocol/scheme specified: assume http/https when those are allowed
    return "http" in allowed_protocols or "https" in allowed_protocols


def _normalize_host(host):
    """Returns a comparable host: IDNA encoded and case-folded.

    IP literals are returned lowercased without IDNA encoding.

    Invisible format characters (Unicode general category ``Cf`` such as
    ZWSP, soft hyphen and BOM) are rejected outright: the IDNA2003 codec in
    the standard library silently strips them, which would otherwise let a
    value smuggle its way into matching an allowed origin.  This keeps the
    origin check consistent with the protocol check, where the same
    characters are stripped before matching.
    """
    if host is None:
        return None

    host = host.strip(".").lower()

    for character in host:
        if unicodedata.category(character) == "Cf":
            raise ValueError(f"invisible character in hostname: {host!r}")

    if ":" in host or all(
        character in "0123456789." for character in host
    ):
        # IPv6 literal or IPv4 literal
        return host

    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("invalid idna hostname: %r" % host)


class Origin:
    """A tuple of ``(scheme, host, port)`` used for origin comparison."""

    __slots__ = ("scheme", "host", "port")

    def __init__(self, scheme, host, port=None):
        self.scheme = scheme.lower()
        self.host = host
        self.port = port

    def __eq__(self, other):
        if not isinstance(other, Origin):
            return NotImplemented
        return (
            self.scheme == other.scheme
            and self.host == other.host
            and self.port == other.port
        )

    def __hash__(self):
        return hash((self.scheme, self.host, self.port))

    def __repr__(self):
        return f"Origin(scheme={self.scheme!r}, host={self.host!r}, port={self.port!r})"

    @classmethod
    def parse(cls, spec):
        """Parses an origin specification such as ``https://cdn.example.com``.

        Default ports are normalized away.  Any userinfo, path, query or
        fragment in ``spec`` is ignored.

        :raises ValueError: if the specification has no scheme or host
        """
        parsed = urlparse(spec)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError(f"origin needs a scheme and host: {spec!r}")

        port = parsed.port
        if port is None or port == _DEFAULT_PORTS.get(parsed.scheme.lower()):
            port = None

        return cls(parsed.scheme.lower(), _normalize_host(parsed.hostname), port)


class URLPolicyResult:
    """Outcome of a :meth:`URLPolicy.check` call."""

    __slots__ = ("allowed", "value", "reason", "stage")

    def __init__(self, allowed, value=None, reason=None, stage=None):
        self.allowed = allowed
        self.value = value
        self.reason = reason
        self.stage = stage

    def __bool__(self):
        return self.allowed

    def __repr__(self):
        if self.allowed:
            return f"URLPolicyResult(allowed=True, value={self.value!r})"
        return (
            "URLPolicyResult(allowed=False, "
            f"reason={self.reason!r}, stage={self.stage!r})"
        )


class URLPolicy:
    """Decides which URI attribute values are adopted and what they become.

    The policy is configured once and shared between :class:`~bleach.sanitizer.
    Cleaner` and :class:`~bleach.linkifier.Linker` so that links created by
    linkify go through exactly the same checks as links present in the input.

    Example::

        policy = URLPolicy(
            base_url="https://www.example.com/",
            origins={
                # Rich text links may point anywhere
                "link": ["*"],
                # Images must be same-site or served by the image CDN
                "image": ["self", "https://img-cdn.example.com"],
            },
            rewrite={"image": cdn_rewriter},
        )
        cleaner = Cleaner(url_policy=policy)
    """

    def __init__(
        self,
        base_url=None,
        origins=None,
        protocols=None,
        resource_classes=None,
        rewrite=None,
    ):
        """Initializes a URLPolicy

        :arg str base_url: fixed base URL used to resolve relative and
            protocol-relative URLs

        :arg dict origins: maps a resource category to an allowlist of
            origins.  Origin entries are strings like
            ``"https://cdn.example.com"``; ``"self"`` means the origin of
            ``base_url`` and ``"*"`` allows every origin (the protocol is
            still checked).  Categories without an entry fall back to the
            ``default`` category.  If ``origins`` is None, every origin is
            allowed and only protocols are checked.

        :arg set protocols: allowed protocols; defaults to
            ``{"http", "https", "mailto"}``

        :arg resource_classes: optional callable or dict mapping
            ``(tag, attribute)`` or ``attribute`` keys to resource category
            names; extends the built-in mapping

        :arg rewrite: optional callable ``fn(tag, namespace, attr, value)``
            returning a rewritten URL string, or a dict mapping resource
            category to such callables (for example CDN rewrites).  Rewritten
            values are re-checked for both protocol and origin before they
            are adopted.
        """
        self.base_url = base_url
        self.protocols = frozenset(
            protocols
            if protocols is not None
            else ("http", "https", "mailto")
        )

        self.resource_classes = self._build_resource_classes(resource_classes)

        self.origins = None
        if origins is not None:
            self.origins = {
                category: self._parse_origins(specs)
                for category, specs in origins.items()
            }

        if rewrite is None:
            self.rewrite = {}
        elif callable(rewrite):
            self.rewrite = {CATEGORY_DEFAULT: rewrite}
        else:
            self.rewrite = dict(rewrite)

    @staticmethod
    def _build_resource_classes(extra):
        mapping = dict(DEFAULT_ATTRIBUTE_CATEGORIES)
        if callable(extra):
            return extra
        if extra:
            mapping.update(extra)
        return mapping

    @staticmethod
    def _parse_origins(specs):
        parsed = set()
        for spec in specs:
            if spec in ("*", "self"):
                parsed.add(spec)
            else:
                parsed.add(Origin.parse(spec))
        return parsed

    def classify(self, tag, namespace, attr):
        """Returns the resource category for a tag/attribute pair."""
        mapping = self.resource_classes
        if callable(mapping):
            category = mapping(tag, namespace, attr)
            if category is not None:
                return category
        else:
            category = mapping.get((tag, attr))
            if category is None:
                category = mapping.get(attr)
            if category is not None:
                return category
        return CATEGORY_DEFAULT

    def _allowed_origins(self, category):
        if self.origins is None:
            return {"*"}
        if category in self.origins:
            return self.origins[category]
        return self.origins.get(CATEGORY_DEFAULT, frozenset())

    def _resolve_origin(self, normalized, base_url):
        """Resolves a normalized URL to an Origin, or None for hostless URLs."""
        parsed = urlparse(normalized)

        if not parsed.scheme:
            # Relative or protocol-relative URL--resolve against the fixed
            # base URL so the target origin is known.
            if base_url is None:
                raise ValueError("relative url requires a base url")
            parsed = urlparse(urljoin(base_url, normalized))

        if parsed.hostname is None:
            # Hostless absolute URL such as "mailto:user@example.com".
            return None

        port = parsed.port
        if port is None or port == _DEFAULT_PORTS.get(parsed.scheme.lower()):
            port = None

        return Origin(parsed.scheme.lower(), _normalize_host(parsed.hostname), port)

    @staticmethod
    def _self_origin(base_url):
        """Returns the origin of the configured base URL."""
        if base_url is None:
            raise ValueError("'self' origin requires a base url")
        parsed = urlparse(base_url)
        return Origin.parse(f"{parsed.scheme}://{parsed.netloc}")

    def _origin_allowed(self, category, target, base_url):
        allowed = self._allowed_origins(category)

        if "*" in allowed:
            return True

        if target is None:
            # Hostless URLs (mailto:, ...) can only match the wildcard.
            return False

        self_origin = None
        for candidate in allowed:
            if candidate == "self":
                if self_origin is None:
                    self_origin = self._self_origin(base_url)
                candidate = self_origin

            if candidate == target:
                return True

        return False

    def check(self, tag, attr, value, namespace=None, base_url=None):
        """Checks a URI attribute value and returns the value to adopt.

        :arg str tag: name of the tag carrying the attribute
        :arg str attr: attribute name
        :arg str value: original attribute value
        :arg namespace: attribute namespace (as produced by the html parser)
        :arg str base_url: fixed base URL; defaults to the policy's base_url

        :returns: :class:`URLPolicyResult`; ``result.value`` is the adopted
            attribute value (possibly rewritten) when allowed, otherwise
            ``result.reason`` explains the rejection
        """
        if base_url is None:
            base_url = self.base_url

        category = self.classify(tag, namespace, attr)

        if not validate_protocol(value, self.protocols):
            return URLPolicyResult(
                False,
                reason=REASON_DISALLOWED_PROTOCOL,
                stage="original",
            )

        rewriter = self.rewrite.get(category)
        if rewriter is None:
            rewriter = self.rewrite.get(CATEGORY_DEFAULT)

        if rewriter is not None:
            rewritten = rewriter(tag, namespace, attr, value)
            if not isinstance(rewritten, str):
                return URLPolicyResult(
                    False,
                    reason=REASON_REWRITE_INVALID,
                    stage="rewritten",
                )

            if not validate_protocol(rewritten, self.protocols):
                return URLPolicyResult(
                    False,
                    reason=REASON_DISALLOWED_PROTOCOL,
                    stage="rewritten",
                )

            candidate = rewritten
            stage = "rewritten"
        else:
            candidate = value
            stage = "original"

        # The protocol check already accepts bare anchors; they stay
        # same-document regardless of the configured origins.
        if normalize_uri_for_protocol(candidate).startswith("#"):
            return URLPolicyResult(True, value=candidate, stage=stage)

        try:
            target = self._resolve_origin(
                normalize_uri_for_origin(candidate), base_url
            )
            allowed = self._origin_allowed(category, target, base_url)
        except ValueError:
            return URLPolicyResult(
                False, reason=REASON_INVALID_URL, stage=stage
            )

        if not allowed:
            return URLPolicyResult(
                False, reason=REASON_ORIGIN_NOT_ALLOWED, stage=stage
            )

        return URLPolicyResult(True, value=candidate, stage=stage)
