"""Optional fragment namespacing.

When several untrusted HTML fragments are rendered on the same page, two
fragments can legitimately both use ``id="title"``--and both can refer to
their own ``title`` element. The :class:`FragmentNamespaceFilter` rewrites the
``id`` values of a single cleaned fragment with a fixed prefix and rewrites
every ID reference in the fragment to match, so fragments can't accidentally
(or deliberately) point at each other's elements.

The filter is designed to run *after* :class:`bleach.sanitizer.BleachSanitizerFilter`
in the filter chain, so it only ever sees tags and attributes that survived
sanitizing. It never adds an attribute that cleaning would have dropped.
"""

import re
from urllib.parse import quote, unquote

from bleach import html5lib_shim


#: Attributes whose value is a single ID reference.
SINGLE_IDREF_ATTRIBUTES = frozenset(
    (
        (None, "for"),
        (None, "form"),
        (None, "aria-activedescendant"),
        (None, "aria-details"),
        (None, "aria-errormessage"),
    )
)

#: Attributes whose value is a space-separated list of ID references.
LIST_IDREF_ATTRIBUTES = frozenset(
    (
        (None, "headers"),
        (None, "aria-labelledby"),
        (None, "aria-describedby"),
        (None, "aria-controls"),
        (None, "aria-owns"),
        (None, "aria-flowto"),
    )
)

#: URI-valued attributes whose value may be a same-document reference
#: (a bare ``#fragment``). External URLs are left untouched--only the part
#: after the ``#`` of a value that is *only* a fragment is rewritten.
FRAGMENT_URI_ATTRIBUTES = frozenset(
    (
        (None, "href"),
        (html5lib_shim.namespaces["xlink"], "href"),
        (None, "usemap"),
    )
)

#: Attributes that take a space-separated list of URIs (only ``ping`` today).
URI_LIST_ATTRIBUTES = frozenset(((None, "ping"),))

#: Namespace URI html5lib assigns to SVG elements.
SVG_NAMESPACE = "http://www.w3.org/2000/svg"

#: CSS/SVG presentation attributes that sanitizing leaves local ``url(#id)``
#: references in.
SVG_REF_ATTRIBUTES = html5lib_shim.svg_attr_val_allows_ref

# Matches url(...) regardless of quote style so we can decide whether the
# referenced IRI is a local one. Non-local references are left alone (and the
# sanitizer has already removed them by this point).
_URL_RE = re.compile(
    r"""url\(\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^)'"]*))\s*\)""",
    re.IGNORECASE,
)


class FragmentNamespaceFilter(html5lib_shim.Filter):
    """Prefix every ``id`` in a fragment and rewrite its ID references.

    :arg source: html5lib TreeWalker stream to filter

    :arg str prefix: prefix to add to every id; references resolve to
        ``<prefix>-<id>``

    :arg bool svg_references: also rewrite local ``url(#id)`` references in
        SVG presentation attributes (``fill``, ``clip-path``, ...) and local
        ``href``/``xlink:href`` fragments on SVG elements

    :arg dangling_callback: optional callable invoked as
        ``dangling_callback(tag, attribute, reference)`` for every ID
        reference whose target doesn't exist in the fragment. When provided,
        dangling references are removed from the output; when ``None`` they
        are left untouched.

    """

    def __init__(self, source, prefix, svg_references=False, dangling_callback=None):
        super().__init__(source)

        if not isinstance(prefix, str) or not prefix or re.search(r"\s", prefix):
            raise ValueError(
                "id namespace prefix must be a non-empty string without "
                "whitespace"
            )

        self.prefix = prefix
        self.prefix_marker = prefix + "-"
        self.svg_references = svg_references
        self.dangling_callback = dangling_callback

        # Map of original (per-fragment) id -> rewritten id. Every reference,
        # including forward references, resolves through this map.
        self.id_map = {}

    def _base_id(self, value):
        """Returns the per-fragment id, undoing a previously applied prefix.

        Re-cleaning an already namespaced fragment must not stack a second
        prefix on top of the first one, so ``ns-foo`` is treated as ``foo``
        again.
        """
        if value.startswith(self.prefix_marker):
            return value[len(self.prefix_marker) :]
        return value

    def _collect_ids(self, tokens):
        """First pass: assign the rewritten id for every surviving element.

        Duplicate ids are resolved deterministically in document order: the
        first occurrence keeps ``<prefix>-<id>`` and later occurrences get a
        ``-2``, ``-3`` ... suffix. References always bind to the first
        occurrence--the same element a browser resolves ``getElementById``
        to--never to a random duplicate node.

        :returns: tuple of (map of base id -> first occurrence's rewritten
            id, map of token position -> rewritten id)
        """
        id_map = {}
        token_ids = {}
        counts = {}
        used = set()

        for position, token in enumerate(tokens):
            if token["type"] not in ("StartTag", "EmptyTag"):
                continue

            attrs = token.get("data")
            if not attrs or (None, "id") not in attrs:
                continue

            original = attrs[(None, "id")]
            if not original:
                continue

            base = self._base_id(original)
            occurrence = counts.get(base, 0) + 1
            counts[base] = occurrence

            rewritten = self.prefix_marker + base
            if occurrence > 1 or rewritten in used:
                # Either this duplicates an earlier id, or the fragment
                # legitimately contained both "x" and "<prefix>-x". Pick the
                # next free numeric suffix deterministically.
                candidate = occurrence if occurrence > 1 else 2
                while f"{self.prefix_marker}{base}-{candidate}" in used:
                    candidate += 1
                counts[base] = candidate
                rewritten = f"{self.prefix_marker}{base}-{candidate}"

            used.add(rewritten)
            token_ids[position] = rewritten
            if base not in id_map:
                # References bind to the first occurrence.
                id_map[base] = rewritten

        return id_map, token_ids

    def _resolve(self, reference):
        """Resolves a raw reference token to its rewritten id.

        Lookup order handles forward references, re-cleaned (already
        prefixed) values and percent-encoded fragment components.
        """
        if reference in self.id_map:
            return self.id_map[reference]

        unprefixed = self._base_id(reference)
        if unprefixed != reference and unprefixed in self.id_map:
            return self.id_map[unprefixed]

        decoded = unquote(reference)
        if decoded != reference and decoded in self.id_map:
            return quote(self.id_map[decoded], safe="")

        return None

    def _report_dangling(self, tag, attribute, reference):
        if self.dangling_callback is not None:
            self.dangling_callback(tag, attribute, reference)

    def _fragment_reference(self, value):
        """Returns the fragment of a bare same-document reference or None.

        An external URL such as ``http://example.com/#foo`` is not a local
        reference and is returned untouched; only values that are entirely a
        fragment (``#foo``) qualify.
        """
        stripped = value.strip()
        if stripped.startswith("#"):
            return stripped[1:]
        return None

    def _rewrite_fragment_uri(self, tag, attribute, value):
        fragment = self._fragment_reference(value)
        if fragment is None:
            return value

        resolved = self._resolve(fragment)
        if resolved is not None:
            return "#" + resolved

        self._report_dangling(tag, attribute[1], fragment)
        if self.dangling_callback is not None:
            return None
        return value

    def _rewrite_uri_list(self, tag, attribute, value):
        pieces = value.split()
        rewritten = []
        for piece in pieces:
            if piece.startswith("#"):
                fragment = piece[1:]
                resolved = self._resolve(fragment)
                if resolved is not None:
                    rewritten.append("#" + resolved)
                else:
                    self._report_dangling(tag, attribute[1], fragment)
                    if self.dangling_callback is None:
                        rewritten.append(piece)
            else:
                rewritten.append(piece)
        if not rewritten:
            return None
        return " ".join(rewritten)

    def _rewrite_single_idref(self, tag, attribute, value):
        reference = value.strip()
        if not reference:
            return value

        resolved = self._resolve(reference)
        if resolved is not None:
            return resolved

        self._report_dangling(tag, attribute[1], reference)
        if self.dangling_callback is not None:
            return None
        return value

    def _rewrite_idref_list(self, tag, attribute, value):
        references = value.split()
        rewritten = []
        for reference in references:
            resolved = self._resolve(reference)
            if resolved is not None:
                rewritten.append(resolved)
            else:
                self._report_dangling(tag, attribute[1], reference)
                if self.dangling_callback is None:
                    rewritten.append(reference)
        if not rewritten:
            return None
        return " ".join(rewritten)

    def _rewrite_svg_urls(self, tag, attribute, value):
        def replace(match):
            if match.group("double") is not None:
                raw, quote = match.group("double"), '"'
            elif match.group("single") is not None:
                raw, quote = match.group("single"), "'"
            else:
                raw, quote = match.group("bare"), ""

            reference = raw.strip()
            if not reference.startswith("#"):
                return match.group(0)

            fragment = reference[1:]
            resolved = self._resolve(fragment)
            if resolved is not None:
                return f"url({quote}#{resolved}{quote})"

            self._report_dangling(tag, attribute[1], fragment)
            if self.dangling_callback is not None:
                return " "
            return match.group(0)

        return _URL_RE.sub(replace, value)

    def _rewrite_attrs(self, token, rewritten_id=None):
        tag = token["name"]
        on_svg_element = token.get("namespace") == SVG_NAMESPACE
        new_attrs = {}

        for namespaced_name, value in token["data"].items():
            if namespaced_name == (None, "id"):
                # Use the per-occurrence output id assigned in the first
                # pass; only fall back when the id was empty/unknown.
                new_attrs[namespaced_name] = (
                    rewritten_id if rewritten_id is not None else value
                )

            elif namespaced_name in FRAGMENT_URI_ATTRIBUTES:
                if on_svg_element and not self.svg_references:
                    new_attrs[namespaced_name] = value
                else:
                    new_value = self._rewrite_fragment_uri(
                        tag, namespaced_name, value
                    )
                    if new_value is not None:
                        new_attrs[namespaced_name] = new_value

            elif namespaced_name in URI_LIST_ATTRIBUTES:
                new_value = self._rewrite_uri_list(tag, namespaced_name, value)
                if new_value is not None:
                    new_attrs[namespaced_name] = new_value

            elif namespaced_name in LIST_IDREF_ATTRIBUTES:
                new_value = self._rewrite_idref_list(tag, namespaced_name, value)
                if new_value is not None:
                    new_attrs[namespaced_name] = new_value

            elif namespaced_name in SINGLE_IDREF_ATTRIBUTES:
                new_value = self._rewrite_single_idref(tag, namespaced_name, value)
                if new_value is not None:
                    new_attrs[namespaced_name] = new_value

            elif (
                self.svg_references
                and on_svg_element
                and namespaced_name in SVG_REF_ATTRIBUTES
            ):
                new_attrs[namespaced_name] = self._rewrite_svg_urls(
                    tag, namespaced_name, value
                )

            else:
                new_attrs[namespaced_name] = value

        token["data"] = new_attrs
        return token

    def __iter__(self):
        tokens = list(html5lib_shim.Filter.__iter__(self))
        self.id_map, token_ids = self._collect_ids(tokens)

        for position, token in enumerate(tokens):
            if token["type"] in ("StartTag", "EmptyTag") and token.get("data"):
                token = self._rewrite_attrs(token, token_ids.get(position))
            yield token
