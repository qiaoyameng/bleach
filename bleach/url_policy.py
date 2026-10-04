"""URL policy entry point for URI-bearing attributes.

A URL policy decides, for a given tag/namespace/attribute/value and a fixed
base URL, whether a URI value is allowed and what value gets adopted. It's
used in two places:

* :py:class:`bleach.sanitizer.Cleaner` runs every URI attribute value through
  the policy when one is configured.
* :py:class:`bleach.linkifier.Linker` runs the hrefs of links it generates
  through the same entry point.

A policy is any callable with the signature::

    url_policy(tag, namespace, attribute, value, base_url)

returning either a :py:class:`URLPolicyResult`, the adopted value as a str,
or ``None`` to reject the value.

:py:class:`OriginURLPolicy` is a ready-made policy that allows origins to be
configured per resource category (for example, links may point anywhere but
images only load from this site and an image CDN) and supports rewriting
values--for example to a CDN--where the rewritten value is validated again
before being adopted.

Everything here is pure string and URL parsing: no network requests are made
and no DNS resolution is performed to decide whether an origin is trusted.

"""

from collections import namedtuple

from bleach.parse_shim import urljoin, urlparse
from bleach.sanitizer import (
    ALLOWED_PROTOCOLS,
    normalize_uri_value,
    sanitize_uri_value,
)


#: Default ports per scheme--used to treat explicit default ports as equal
#: to omitted ones
DEFAULT_PORTS = {
    "ftp": 21,
    "http": 80,
    "https": 443,
    "ws": 80,
    "wss": 443,
}

#: Resource category used for tag/attribute pairs not explicitly categorized
DEFAULT_CATEGORY = "uri"

#: Map of (tag, attribute) to resource category
DEFAULT_RESOURCE_CATEGORIES = {
    ("a", "href"): "link",
    ("area", "href"): "link",
    ("blockquote", "cite"): "link",
    ("del", "cite"): "link",
    ("ins", "cite"): "link",
    ("q", "cite"): "link",
    ("img", "src"): "image",
    ("img", "longdesc"): "image",
    ("input", "src"): "image",
    ("script", "src"): "script",
    ("embed", "src"): "embed",
    ("frame", "src"): "embed",
    ("iframe", "src"): "embed",
    ("audio", "src"): "media",
    ("source", "src"): "media",
    ("track", "src"): "media",
    ("video", "src"): "media",
    ("video", "poster"): "media",
    ("form", "action"): "form",
}


class URLPolicyResult(namedtuple("URLPolicyResult", ["value", "reason"])):
    """Result of a URL policy decision

    ``value`` is the adopted value--the original or a rewritten one--and
    ``reason`` is None. If the value is rejected, ``value`` is None and
    ``reason`` is a human-readable string explaining why.

    """

    __slots__ = ()

    @property
    def allowed(self):
        """Whether the value was allowed"""
        return self.reason is None

    def __bool__(self):
        return self.allowed

    @classmethod
    def allow(cls, value):
        """Builds a result adopting ``value``"""
        return cls(value=value, reason=None)

    @classmethod
    def reject(cls, reason):
        """Builds a result rejecting the value with ``reason``"""
        return cls(value=None, reason=reason)


class Origin(namedtuple("Origin", ["scheme", "host", "port"])):
    """A normalized URL origin

    ``scheme`` is lowercased, ``host`` is lowercased and IDNA-encoded, and
    ``port`` is an int with the default port for the scheme filled in when
    omitted (None for schemes without a known default port).

    """

    __slots__ = ()

    def __str__(self):
        if not self.host:
            return ""
        if self.scheme:
            formatted = f"{self.scheme}://{self.host}"
        else:
            formatted = f"//{self.host}"
        if self.port is not None and DEFAULT_PORTS.get(self.scheme) != self.port:
            formatted = f"{formatted}:{self.port}"
        return formatted


def normalize_host(host):
    """Normalizes a hostname for origin comparison

    Lowercases the host and IDNA-encodes non-ASCII (internationalized) host
    names so a unicode host and its punycode form compare equal.

    :arg host: the hostname to normalize

    :returns: normalized hostname

    :raises ValueError: if the host is empty or not a valid IDNA name

    """
    if not host:
        raise ValueError("empty host")

    host = host.lower()
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError(f"invalid internationalized host {host!r}")
    return host


def parse_origin(origin):
    """Parses an origin string into an :py:class:`Origin`

    :arg origin: origin string like ``"https://cdn.example.com:8443"``; any
        userinfo part is ignored and default ports are normalized away

    :returns: Origin

    :raises ValueError: if the origin is malformed or has no host

    """
    parsed = urlparse(origin)
    try:
        host = normalize_host(parsed.hostname or "")
        port = parsed.port
    except ValueError:
        raise ValueError(f"invalid origin {origin!r}")
    if port is None:
        port = DEFAULT_PORTS.get(parsed.scheme.lower())
    return Origin(scheme=parsed.scheme.lower(), host=host, port=port)


def url_origin(url, base_url=""):
    """Resolves a url against a fixed base URL and returns its origin

    Entity and control character normalization matches the protocol check in
    ``bleach.sanitizer.sanitize_uri_value``. Relative paths and
    protocol-relative urls are resolved against ``base_url``. Any username or
    password part of the authority is ignored when determining the host.

    :arg url: the url to inspect
    :arg base_url: fixed base URL to resolve against

    :returns: Origin, or None if the url has no host (for example a local
        anchor or a non-hierarchical scheme like ``mailto:``)

    :raises ValueError: if the url is malformed

    """
    normalized = normalize_uri_value(url)
    if base_url:
        normalized = urljoin(base_url, normalized)

    try:
        parsed = urlparse(normalized)
    except ValueError:
        raise ValueError(f"unparseable url {url!r}")

    if not parsed.hostname:
        return None

    try:
        host = normalize_host(parsed.hostname)
        port = parsed.port
    except ValueError:
        raise ValueError(f"invalid host or port in url {url!r}")

    scheme = parsed.scheme.lower()
    if port is None:
        port = DEFAULT_PORTS.get(scheme)
    return Origin(scheme=scheme, host=host, port=port)


class OriginURLPolicy:
    """URL policy that allows origins to be configured per resource category

    Example--links may point at external sites, but images only load from
    this site and an image CDN::

        from bleach.sanitizer import Cleaner
        from bleach.url_policy import OriginURLPolicy

        policy = OriginURLPolicy(
            resource_origins={
                "image": ["https://example.com", "https://cdn.example.com"],
            },
        )
        cleaner = Cleaner(
            tags={"a", "img"},
            attributes={"a": ["href"], "img": ["src"]},
            url_policy=policy,
            base_url="https://example.com/",
        )

    """

    def __init__(
        self,
        allowed_protocols=ALLOWED_PROTOCOLS,
        resource_origins=None,
        default_origins=None,
        resource_categories=None,
        rewrite=None,
    ):
        """Initializes an OriginURLPolicy

        :arg set allowed_protocols: set of allowed protocols; defaults to
            ``bleach.sanitizer.ALLOWED_PROTOCOLS``

        :arg dict resource_origins: map of resource category to an iterable of
            allowed origin strings; a value in a category not listed here
            falls back to ``default_origins``

        :arg default_origins: iterable of allowed origin strings for resource
            categories not in ``resource_origins``; None means origins are
            not restricted for those categories

        :arg dict resource_categories: map of ``(tag, attribute)`` to resource
            category, extending or overriding
            ``DEFAULT_RESOURCE_CATEGORIES``

        :arg rewrite: optional callable ``rewrite(category, resolved_url)``
            returning a replacement url (for example a CDN rewrite) or None
            to leave the value alone; rewritten values are resolved against
            the base URL and must pass the protocol and origin checks again
            before being adopted

        """
        self.allowed_protocols = frozenset(allowed_protocols)
        self.resource_origins = {
            category: frozenset(parse_origin(origin) for origin in origins)
            for category, origins in (resource_origins or {}).items()
        }
        if default_origins is None:
            self.default_origins = None
        else:
            self.default_origins = frozenset(
                parse_origin(origin) for origin in default_origins
            )
        self.resource_categories = dict(DEFAULT_RESOURCE_CATEGORIES)
        self.resource_categories.update(resource_categories or {})
        self.rewrite = rewrite

    def categorize(self, tag, attribute):
        """Returns the resource category for a tag/attribute pair"""
        return self.resource_categories.get((tag, attribute), DEFAULT_CATEGORY)

    def resolve(self, value, base_url):
        """Normalizes a value and resolves it against the fixed base URL"""
        resolved = normalize_uri_value(value)
        if base_url:
            resolved = urljoin(base_url, resolved)
        return resolved

    def check_origin(self, resolved_url, category):
        """Checks a resolved url against the origins for a resource category

        :arg resolved_url: url already resolved against the base URL
        :arg category: the resource category

        :returns: None if allowed, else a rejection reason

        """
        allowed = self.resource_origins.get(category, self.default_origins)
        if allowed is None:
            # No origin restriction for this category
            return None

        try:
            origin = url_origin(resolved_url)
        except ValueError as exc:
            return str(exc)

        if origin is None:
            # No host--a local reference that resolves against the embedding
            # page or a non-hierarchical scheme like mailto:
            return None

        if origin in allowed:
            return None

        return f"origin {origin} not allowed for resource category {category!r}"

    def __call__(self, tag, namespace, attribute, value, base_url=""):
        """Applies the policy to a uri value

        :arg tag: the tag name the attribute is on
        :arg namespace: the attribute namespace or None
        :arg attribute: the attribute name
        :arg value: the original attribute value
        :arg base_url: fixed base URL to resolve against

        :returns: URLPolicyResult with the adopted value or a rejection reason

        """
        category = self.categorize(tag, attribute)

        # Protocol check on the original value--this uses the same entity and
        # control character normalization as the built-in check
        if sanitize_uri_value(value, self.allowed_protocols) is None:
            return URLPolicyResult.reject("protocol not allowed")

        resolved = self.resolve(value, base_url)

        candidate = value
        if self.rewrite is not None:
            rewritten = self.rewrite(category, resolved)
            if rewritten is not None:
                # Rewritten values must pass the protocol and target checks
                # again before being adopted
                if sanitize_uri_value(rewritten, self.allowed_protocols) is None:
                    return URLPolicyResult.reject(
                        "rewritten value uses a disallowed protocol"
                    )
                candidate = rewritten
                resolved = self.resolve(rewritten, base_url)

        reason = self.check_origin(resolved, category)
        if reason is not None:
            return URLPolicyResult.reject(reason)

        return URLPolicyResult.allow(candidate)
