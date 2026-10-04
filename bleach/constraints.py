"""Post-clean node constraint phase.

This module implements a tree-aware phase that runs *after* the regular
attribute sanitization (and after any additional filters such as
:class:`bleach.linkifier.LinkifyFilter`). It lets you express rules that
depend on more than a single attribute value--for example "every ``target``
of ``_blank`` needs a ``rel`` token" or "an ``img`` is kept only when its
``alt`` is non-empty".

Design
------

* Rules are plain callables; the framework is generic and ships no business
  rules. You declare and order the rules when building the :class:`Cleaner`.
* Each rule receives the attributes that survived protocol/CSS/allow-list
  filtering, together with a *read-only* view of the repaired HTML5 tree
  (the element's namespace and its ancestors).
* Rules may delete attributes, restrict token lists, and alter values that
  have already passed type validation. They may also ask for the whole node
  to be removed (:data:`DROP_NODE`) or unwrapped (:data:`UNWRAP_NODE`).
* Any value a rule *adds* is run back through the same security checks
  (attribute allow-list, URI protocol validation, SVG IRI rules and the CSS
  sanitizer). Rules cannot widen the configured policy or bypass protocol or
  CSS restrictions.
* Rules run in declaration order and operate on the already-repaired HTML5
  tree, so repeated cleaning is idempotent for well-behaved rules.

"""

from functools import partial

#: Sentinel returned by a rule to remove the node (and all of its contents).
DROP_NODE = object()

#: Sentinel returned by a rule to unwrap the node: the start/end tags are
#: removed, but the node's children are kept in place.
UNWRAP_NODE = object()


class NodeContext:
    """Read-only context passed to each constraint rule.

    The context describes the node a rule is being applied to. Attributes are
    passed separately (and are mutable); everything on this object is
    read-only. Rules see the tree *after* HTML5 parsing fixes and after all
    earlier phases (sanitizing, filters) have run.

    :ivar str name: element name (without namespace prefix), e.g. ``"a"``
    :ivar namespace: namespace URI of the element, or ``None`` for HTML
    :ivar str token_type: ``"StartTag"`` or ``"EmptyTag"``
    :ivar tuple ancestors: tuple of ``(namespace, name)`` pairs from the
        outermost ancestor down to (and including) the element's parent

    """

    __slots__ = ("ancestors", "name", "namespace", "token_type")

    def __init__(self, name, namespace, token_type, ancestors):
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "token_type", token_type)
        object.__setattr__(self, "ancestors", ancestors)

    def __setattr__(self, name, value):
        raise AttributeError(f"NodeContext is read-only; cannot set {name!r}")

    def __delattr__(self, name):
        raise AttributeError(f"NodeContext is read-only; cannot delete {name!r}")

    @property
    def ancestor_names(self):
        """Tuple of ancestor tag names, outermost first (parent last)."""
        return tuple(name for namespace, name in self.ancestors)

    def has_ancestor(self, name, namespace=None):
        """Whether an ancestor with this name (and optional namespace) exists."""
        return (namespace, name) in self.ancestors


def get_attr(attrs, name, namespace=None, default=None):
    """Reads an attribute value from a namespaced attribute map.

    :arg dict attrs: ``(namespace, name) -> value`` mapping
    :arg str name: attribute name
    :arg namespace: attribute namespace URI (``None`` for HTML attributes)
    :arg default: value returned when the attribute is absent

    """
    return attrs.get((namespace, name), default)


def set_attr(attrs, name, value, namespace=None):
    """Sets an attribute value in a namespaced attribute map.

    The new value is not validated here--validation happens when the rule
    returns, so the framework can re-run the security checks.

    """
    attrs[(namespace, name)] = value
    return attrs


def del_attr(attrs, name, namespace=None):
    """Deletes an attribute from a namespaced attribute map if present."""
    attrs.pop((namespace, name), None)
    return attrs


def get_tokens(attrs, name, namespace=None):
    """Returns a whitespace-split attribute value as a list of tokens."""
    value = attrs.get((namespace, name), "")
    if not value:
        return []
    return value.split()


def set_tokens(attrs, name, tokens, namespace=None):
    """Writes a list of tokens back as a whitespace-separated attribute."""
    attrs[(namespace, name)] = " ".join(tokens)
    return attrs


def constrain_tokens(attrs, name, allowed, namespace=None):
    """Drops every token of ``name`` that is not in ``allowed``.

    Token comparison is case-insensitive; the original casing of kept tokens
    is preserved.

    :arg dict attrs: namespaced attribute map
    :arg str name: attribute name
    :arg allowed: iterable of permitted tokens
    :arg namespace: attribute namespace URI

    :returns: the (possibly updated) attrs dict

    """
    allowed = {token.lower() for token in allowed}
    tokens = [
        token
        for token in get_tokens(attrs, name, namespace)
        if token.lower() in allowed
    ]
    if tokens:
        set_tokens(attrs, name, tokens, namespace)
    else:
        del_attr(attrs, name, namespace)
    return attrs


def ensure_rel_tokens(attrs, required):
    """Adds missing (case-insensitive) tokens to a ``rel`` attribute.

    Existing tokens are preserved and new tokens are appended in the order in
    which they appear in ``required``. This is idempotent: running it on an
    attribute that already contains the tokens changes nothing.

    """
    required = list(required)
    tokens = get_tokens(attrs, "rel")
    present = {token.lower() for token in tokens}
    for token in required:
        if token.lower() not in present:
            tokens.append(token)
            present.add(token.lower())
    if tokens:
        set_tokens(attrs, "rel", tokens)
    else:
        del_attr(attrs, "rel")
    return attrs


class ConstraintError(ValueError):
    """Raised when a rule returns a value the framework cannot apply."""


class NodeConstraintFilter:
    """Applies ordered node constraint rules to a sanitized token stream.

    This is an html5lib-style filter: wrap it around any token iterator and
    iterate it. It is normally added automatically as the *last* stage of
    :meth:`Cleaner.clean`, so it sees the final repaired tree, including links
    produced by :class:`bleach.linkifier.LinkifyFilter`.

    Every StartTag/EmptyTag token is offered to every rule in declaration
    order. A rule may mutate the ``attrs`` mapping (or return a replacement),
    return :data:`DROP_NODE` / :data:`UNWRAP_NODE`, or return ``None`` to
    leave the node untouched. Returned attribute sets are re-validated
    against the configured policy before they are emitted.

    The filter is not thread-safe; use one Cleaner (and therefore one filter
    instance) per thread.

    """

    def __init__(
        self,
        source,
        rules,
        attributes,
        allowed_protocols,
        css_sanitizer=None,
        attr_val_is_uri=None,
        svg_attr_val_allows_ref=None,
        svg_allow_local_href=None,
    ):
        """Creates a NodeConstraintFilter.

        :arg source: html5lib TreeWalker stream
        :arg list rules: ordered list of rule callables
        :arg attributes: the Cleaner's ``attributes`` configuration
            (callable, list or dict); used to re-check added attributes
        :arg set allowed_protocols: allowed URI protocols
        :arg css_sanitizer: :class:`bleach.css_sanitizer.CSSSanitizer` used
            to re-check ``style`` values
        :arg attr_val_is_uri: set of ``(namespace, name)`` pairs whose values
            are URIs; defaults to html5lib's set
        :arg svg_attr_val_allows_ref: set of SVG attributes allowing IRI refs
        :arg svg_allow_local_href: set of SVG elements allowed local hrefs

        """
        # Imported lazily to avoid a circular import with bleach.sanitizer.
        from bleach import html5lib_shim
        from bleach.sanitizer import (
            attribute_filter_factory,
            sanitize_attributes,
            sanitize_uri_value,
        )

        self.source = source
        self.rules = list(rules) if rules else []
        self.attr_filter = attribute_filter_factory(attributes)
        self.allowed_protocols = frozenset(allowed_protocols)
        self.css_sanitizer = css_sanitizer
        self.attr_val_is_uri = (
            attr_val_is_uri
            if attr_val_is_uri is not None
            else html5lib_shim.attr_val_is_uri
        )
        self.svg_attr_val_allows_ref = (
            svg_attr_val_allows_ref
            if svg_attr_val_allows_ref is not None
            else html5lib_shim.svg_attr_val_allows_ref
        )
        self.svg_allow_local_href = (
            svg_allow_local_href
            if svg_allow_local_href is not None
            else html5lib_shim.svg_allow_local_href
        )
        self._sanitize_attributes = sanitize_attributes
        self._sanitize_uri_value_bound = partial(
            sanitize_uri_value, allowed_protocols=self.allowed_protocols
        )

    def _revalidate(self, token, attrs):
        """Re-runs security checks over attributes a rule produced.

        Every attribute the rule keeps must be allowed by the attribute
        policy; every new or modified value goes through the same URI, SVG
        and CSS checks as the initial sanitizing pass. This makes it
        impossible for a rule to bypass the configured protocol/CSS policy.

        """
        return self._sanitize_attributes(
            token_name=token["name"],
            attrs=attrs,
            attr_filter=self.attr_filter,
            allowed_protocols=self.allowed_protocols,
            attr_val_is_uri=self.attr_val_is_uri,
            svg_attr_val_allows_ref=self.svg_attr_val_allows_ref,
            svg_allow_local_href=self.svg_allow_local_href,
            css_sanitizer=self.css_sanitizer,
            sanitize_uri_value=self._sanitize_uri_value_bound,
        )

    def _apply_rules(self, token, ancestors):
        token_type = token["type"]
        context = NodeContext(
            name=token["name"],
            namespace=token.get("namespace"),
            token_type=token_type,
            ancestors=tuple(ancestors),
        )

        attrs = dict(token.get("data") or {})
        for rule in self.rules:
            result = rule(attrs, context)

            if result is None:
                # Rule declined to act; carry on with the current attrs.
                continue

            if result is DROP_NODE or result is UNWRAP_NODE:
                return result

            if isinstance(result, dict):
                attrs = result
                continue

            raise ConstraintError(
                f"{rule!r} returned {result!r}; expected None, an attrs dict, "
                "DROP_NODE or UNWRAP_NODE"
            )

        attrs = self._revalidate(token, attrs)
        token["data"] = attrs
        return token

    def __iter__(self):
        # ``frames`` has one entry per open StartTag so EndTags can be
        # matched against the repaired stream. Each entry is the action for
        # that element: None (kept), DROP_NODE or UNWRAP_NODE.
        #
        # ``ancestors`` tracks only the *kept* open elements--an unwrapped or
        # dropped element is not part of its children's ancestor context,
        # because it is absent from the emitted tree.
        frames = []
        ancestors = []
        frame_pushed = []

        def dropping():
            return bool(frames) and frames[-1] is DROP_NODE

        for token in self.source:
            token_type = token["type"]

            if token_type in ("StartTag", "EmptyTag"):
                if dropping():
                    # Nodes inside a dropped subtree are dropped without
                    # running any rules.
                    result = DROP_NODE
                else:
                    result = self._apply_rules(token, tuple(ancestors))

                if token_type == "EmptyTag":
                    # Empty elements have no children, so unwrap is
                    # equivalent to dropping the tag itself.
                    if result is DROP_NODE or result is UNWRAP_NODE:
                        continue
                    yield result
                    continue

                kept = result not in (DROP_NODE, UNWRAP_NODE)
                frames.append(None if kept else result)
                if kept:
                    ancestors.append((token.get("namespace"), token["name"]))
                    frame_pushed.append(True)
                    yield result
                else:
                    frame_pushed.append(False)
                continue

            if token_type == "EndTag":
                if not frames:
                    # Repaired streams are balanced, but be defensive.
                    yield token
                    continue

                frames.pop()
                pushed = frame_pushed.pop()
                if pushed:
                    ancestors.pop()
                    yield token
                continue

            if dropping():
                # Character/entity/comment tokens inside a dropped element
                # are swallowed along with the element.
                continue

            yield token
