"""Node constraints: a post-cleaning rule phase.

Constraints run after the sanitizing filter (and any other html5lib filters,
including :class:`bleach.linkifier.LinkifyFilter`) against the HTML5-repaired
tree. Each constraint receives a :class:`NodeContext` exposing the element's
already-filtered attributes together with read-only ancestor information.

A constraint can:

* delete node attributes,
* restrict token-list attributes (e.g. ``rel``) to an allow-list of tokens,
* adjust values that passed type checking (e.g. clamp ``colspan``),
* return a structural action to drop or unwrap the node.

Any value a constraint adds or changes is re-checked by the same attribute
machinery used by the regular cleaning pass, so it cannot bypass the
attribute allow-list, the protocol rules or CSS restrictions.

Constraints are opt-in: :class:`bleach.sanitizer.Cleaner` enables no business
rules by default.
"""

from bleach.sanitizer import BleachSanitizerFilter


class NodeAction:
    """Structural actions a constraint can return.

    Returning any other value (including ``None``) means "keep the node".
    """

    #: Keep the node and the attribute mutations already applied to the context
    KEEP = "keep"

    #: Drop the node together with its entire subtree
    DROP = "drop"

    #: Drop only the node's opening and closing tags, keeping its children
    UNWRAP = "unwrap"


def _split_tokens(value):
    """Splits a whitespace-separated token list, lower-cased and de-duped."""
    seen = set()
    tokens = []
    for token in value.split():
        lowered = token.lower()
        if lowered not in seen:
            seen.add(lowered)
            tokens.append(lowered)
    return tokens


class NodeContext:
    """Context handed to a single constraint for a single element.

    The attribute mapping on the context is the post-cleaning mapping:
    attributes that failed the allow-list, protocol or CSS checks are already
    gone. Mutating methods (:meth:`set_attr`, :meth:`del_attr`) mark the
    element so the filter re-runs the safety checks on the resulting
    attributes before serialization.

    Instances are single-use and must not be retained by constraints.
    """

    def __init__(self, token, ancestors):
        self._token = token
        self._data = token.get("data") or {}
        # tuple of (namespace, local name), root first; read-only
        self.ancestors = tuple(ancestors)
        self.dirty = False

    @property
    def tag(self):
        """Local name of the element, e.g. ``"a"``."""
        return self._token["name"]

    @property
    def namespace(self):
        """Element namespace URI (``None`` for HTML elements)."""
        return self._token.get("namespace")

    def has_ancestor(self, name, namespace=None):
        """Whether an element with the name is among the ancestors."""
        return (namespace, name) in self.ancestors

    def has_attr(self, name, namespace=None):
        return (namespace, name) in self._data

    def get_attr(self, name, default=None, namespace=None):
        return self._data.get((namespace, name), default)

    def set_attr(self, name, value, namespace=None):
        """Sets an attribute value; the new value is re-checked for safety."""
        if not isinstance(value, str):
            raise TypeError("attribute values must be strings")
        self._data[(namespace, name)] = value
        self._token["data"] = self._data
        self.dirty = True
        return self

    def del_attr(self, name, namespace=None):
        """Deletes an attribute if present."""
        if self._data.pop((namespace, name), None) is not None:
            self.dirty = True
        return self


class BleachConstraintFilter(BleachSanitizerFilter):
    """html5lib filter applying node constraints as the final cleaning phase.

    It must be stacked after :class:`bleach.sanitizer.BleachSanitizerFilter`
    and any other filters; see :class:`bleach.sanitizer.Cleaner`.
    """

    def __init__(self, source, constraints, **kwargs):
        super().__init__(source, **kwargs)
        # Accept both plain callables and objects implementing __call__.
        self.constraints = list(constraints)

    def _resanitize_attrs(self, token):
        """Runs every attribute through the shared safety checks."""
        data = token.get("data")
        if not data:
            return
        checked = {}
        for namespaced_name, value in data.items():
            new_value = self.sanitize_attribute(
                token["name"], namespaced_name, value
            )
            if new_value is not None:
                checked[namespaced_name] = new_value
        token["data"] = checked

    def _apply_constraints(self, token, ancestors):
        """Resanitizes attrs, runs the rules in order; returns the action."""
        # Rules must see only already-filtered attributes. This is also what
        # catches attributes introduced by upstream filters such as
        # LinkifyFilter.
        self._resanitize_attrs(token)

        ctx = NodeContext(token, ancestors)
        action = NodeAction.KEEP
        for rule in self.constraints:
            result = rule(ctx)
            if result in (NodeAction.DROP, NodeAction.UNWRAP):
                # Later rules win for the structural decision, but attribute
                # mutations from earlier rules remain in effect.
                action = result

        if ctx.dirty:
            # Added/changed values cannot bypass protocol and CSS checks.
            self._resanitize_attrs(token)

        return action

    def __iter__(self):
        # Stack of (namespace, name, action) for open StartTags. While at
        # least one open element is being dropped, everything below it is
        # swallowed.
        open_stack = []

        for token in super(BleachSanitizerFilter, self).__iter__():
            token_type = token["type"]

            if token_type in ("StartTag", "EmptyTag"):
                dropping = any(
                    action == NodeAction.DROP for _, _, action in open_stack
                )
                if dropping:
                    if token_type == "StartTag":
                        open_stack.append(
                            (
                                token.get("namespace"),
                                token["name"],
                                NodeAction.DROP,
                            )
                        )
                    continue

                ancestors = [(ns, name) for ns, name, _ in open_stack]
                action = self._apply_constraints(token, ancestors)

                if token_type == "EmptyTag":
                    # Empty elements have no children, so unwrap == drop.
                    if action != NodeAction.DROP:
                        yield token
                    continue

                open_stack.append(
                    (token.get("namespace"), token["name"], action)
                )
                if action not in (NodeAction.DROP, NodeAction.UNWRAP):
                    yield token

            elif token_type == "EndTag":
                # Match the end tag against the open stack by name instead of
                # blindly popping: HTML5 tree repair can emit end tags that
                # implicitly close several implicitly-opened elements, and a
                # dropped open tag has no end tag token at all.
                for index in range(len(open_stack) - 1, -1, -1):
                    _ns, name, action = open_stack[index]
                    if name == token["name"]:
                        del open_stack[index:]
                        if action in (NodeAction.DROP, NodeAction.UNWRAP):
                            break
                        yield token
                        break
                else:
                    # End tag matching nothing open (tree repairs usually
                    # prevent this)--leave the stack untouched and emit it.
                    yield token

            else:
                if any(
                    action == NodeAction.DROP for _, _, action in open_stack
                ):
                    continue
                yield token


# ---------------------------------------------------------------------------
# Built-in, opt-in rules
# ---------------------------------------------------------------------------


class RequireRelForBlankTarget:
    """Ensures links opening in a new browsing context carry rel tokens.

    When the element (by default an ``a``) has ``target="_blank"`` (matched
    case-insensitively, ignoring surrounding whitespace), its ``rel`` token
    list is restricted to ``allowed_tokens`` and extended with any missing
    ``required_tokens``.

    Nothing is enforced when the element does not open in a new browsing
    context.
    """

    def __init__(
        self,
        required_tokens=("noopener", "noreferrer"),
        allowed_tokens=(
            "noopener",
            "noreferrer",
            "nofollow",
            "ugc",
            "sponsored",
            "external",
            "help",
            "prev",
            "next",
            "search",
            "license",
            "author",
            "tag",
            "bookmark",
        ),
        tag="a",
        target_attr="target",
        rel_attr="rel",
        namespace=None,
    ):
        self.required = tuple(token.lower() for token in required_tokens)
        # De-dupe while preserving order
        self.allowed = _split_tokens(" ".join(allowed_tokens))
        self.tag = tag
        self.target_attr = target_attr
        self.rel_attr = rel_attr
        self.namespace = namespace

    def __call__(self, ctx):
        if ctx.tag != self.tag or ctx.namespace is not self.namespace:
            return NodeAction.KEEP

        target = ctx.get_attr(self.target_attr)
        if target is None or target.strip().lower() != "_blank":
            return NodeAction.KEEP

        rel = ctx.get_attr(self.rel_attr, default="")
        allowed = set(self.allowed)
        tokens = [token for token in _split_tokens(rel) if token in allowed]
        for required in self.required:
            if required not in tokens:
                tokens.append(required)

        if tokens:
            ctx.set_attr(self.rel_attr, " ".join(tokens))
        else:
            ctx.del_attr(self.rel_attr)
        return NodeAction.KEEP


class ClampTableCellSpan:
    """Restricts ``rowspan``/``colspan`` of table cells to valid ranges.

    Values must be non-negative integers (HTML integer parsing rules apply,
    so surrounding whitespace is tolerated). Values larger than the maximum
    are clamped; values below the minimum or unparsable values cause the
    attribute to be deleted--HTML treats a missing span attribute as ``1``.

    Defaults follow HTML limits: ``colspan`` up to 1000 and ``rowspan`` up to
    65534.
    """

    def __init__(
        self,
        tags=("td", "th"),
        max_colspan=1000,
        max_rowspan=65534,
        min_span=1,
        namespace=None,
    ):
        self.tags = frozenset(tags)
        self.namespace = namespace
        self.limits = {
            "colspan": (min_span, max_colspan),
            "rowspan": (min_span, max_rowspan),
        }

    def __call__(self, ctx):
        if ctx.tag not in self.tags or ctx.namespace is not self.namespace:
            return NodeAction.KEEP

        for attr, (minimum, maximum) in self.limits.items():
            value = ctx.get_attr(attr)
            if value is None:
                continue

            stripped = value.strip()
            if not stripped.isdigit():
                ctx.del_attr(attr)
                continue

            number = int(stripped)
            if number < minimum:
                ctx.del_attr(attr)
            elif number > maximum:
                ctx.set_attr(attr, str(maximum))
            elif stripped != value:
                # Normalize values that parse fine but carry surrounding
                # whitespace (valid per HTML integer parsing rules).
                ctx.set_attr(attr, str(number))
        return NodeAction.KEEP


class RequireImageAlt:
    """Drops image elements that have no non-empty ``alt`` attribute.

    Whitespace-only values count as missing. Foreign-namespace elements such
    as SVG ``<image>`` are left alone because the rule defaults to the HTML
    namespace.
    """

    def __init__(self, tag="img", alt_attr="alt", namespace=None):
        self.tag = tag
        self.alt_attr = alt_attr
        self.namespace = namespace

    def __call__(self, ctx):
        if ctx.tag != self.tag or ctx.namespace is not self.namespace:
            return NodeAction.KEEP

        alt = ctx.get_attr(self.alt_attr)
        if alt is None or not alt.strip():
            return NodeAction.DROP
        return NodeAction.KEEP
