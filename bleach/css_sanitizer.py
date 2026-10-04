import re

import tinycss2
from tinycss2.ast import Declaration
from tinycss2.ast import FunctionBlock
from tinycss2.ast import WhitespaceToken


ALLOWED_CSS_PROPERTIES = frozenset(
    (
        "azimuth",
        "background-color",
        "border-bottom-color",
        "border-collapse",
        "border-color",
        "border-left-color",
        "border-right-color",
        "border-top-color",
        "clear",
        "color",
        "cursor",
        "direction",
        "display",
        "elevation",
        "float",
        "font",
        "font-family",
        "font-size",
        "font-style",
        "font-variant",
        "font-weight",
        "height",
        "letter-spacing",
        "line-height",
        "overflow",
        "pause",
        "pause-after",
        "pause-before",
        "pitch",
        "pitch-range",
        "richness",
        "speak",
        "speak-header",
        "speak-numeral",
        "speak-punctuation",
        "speech-rate",
        "stress",
        "text-align",
        "text-decoration",
        "text-indent",
        "unicode-bidi",
        "vertical-align",
        "voice-family",
        "volume",
        "white-space",
        "width",
    )
)


ALLOWED_SVG_PROPERTIES = frozenset(
    (
        "fill",
        "fill-opacity",
        "fill-rule",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-opacity",
    )
)


# Functions that are allowed to appear in validated declaration values. This
# deliberately excludes "url" (handled separately by the URL policy),
# "expression", "image-set" and anything else that can load resources or
# execute script.
ALLOWED_CSS_VALUE_FUNCTIONS = frozenset(
    (
        "rgb",
        "rgba",
        "hsl",
        "hsla",
        "hwb",
        "calc",
        "min",
        "max",
        "clamp",
    )
)


# Sentinel marking a custom property whose value is invalid (for example
# because of a dependency cycle) at computed-value time.
_INVALID = object()

# Bounds that keep hostile input from causing pathological recursion or
# exponential token growth during var() substitution.
_MAX_SUBSTITUTION_DEPTH = 32
_MAX_REFERENCE_DEPTH = 100
_MAX_SUBSTITUTED_TOKENS = 512

# Token types that must not be serialized adjacent to one another because
# they would merge into a single token (for example "1" + "px" -> "1px").
_MERGEABLE_TOKEN_TYPES = frozenset(
    (
        "ident",
        "function",
        "url",
        "dimension",
        "number",
        "percentage",
        "hash",
        "string",
        "at-keyword",
        "unicode-range",
    )
)

_LENGTH_UNITS = frozenset(
    (
        "px",
        "em",
        "rem",
        "ex",
        "rex",
        "cap",
        "rcap",
        "ch",
        "ic",
        "lh",
        "rlh",
        "vw",
        "vh",
        "vi",
        "vb",
        "vmin",
        "vmax",
        "cm",
        "mm",
        "q",
        "in",
        "pt",
        "pc",
    )
)

_ANGLE_UNITS = frozenset(("deg", "grad", "rad", "turn"))

_TIME_UNITS = frozenset(("s", "ms"))

# CSS Color 4 named colors plus "transparent" and "currentcolor".
_NAMED_COLORS = frozenset(
    (
        "aliceblue antiquewhite aqua aquamarine azure beige bisque black "
        "blanchedalmond blue blueviolet brown burlywood cadetblue chartreuse "
        "chocolate coral cornflowerblue cornsilk crimson cyan darkblue "
        "darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki "
        "darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon "
        "darkseagreen darkslateblue darkslategray darkslategrey darkturquoise "
        "darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue firebrick "
        "floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod "
        "gray green greenyellow grey honeydew hotpink indianred indigo ivory "
        "khaki lavender lavenderblush lawngreen lemonchiffon lightblue "
        "lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen "
        "lightgrey lightpink lightsalmon lightseagreen lightskyblue "
        "lightslategray lightslategrey lightsteelblue lightyellow lime "
        "limegreen linen magenta maroon mediumaquamarine mediumblue "
        "mediumorchid mediumpurple mediumseagreen mediumslateblue "
        "mediumspringgreen mediumturquoise mediumvioletred midnightblue "
        "mintcream mistyrose moccasin navajowhite navy oldlace olive "
        "olivedrab orange orangered orchid palegoldenrod palegreen "
        "paleturquoise palevioletred papayawhip peachpuff peru pink plum "
        "powderblue purple rebeccapurple red rosybrown royalblue saddlebrown "
        "salmon sandybrown seagreen seashell sienna silver skyblue slateblue "
        "slategray slategrey snow springgreen steelblue tan teal thistle "
        "tomato turquoise violet wheat white whitesmoke yellow yellowgreen "
        "transparent currentcolor"
    ).split()
)

_URL_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _strip_whitespace(tokens):
    """Returns the token list without leading/trailing whitespace tokens."""
    start = 0
    end = len(tokens)
    while start < end and tokens[start].type == "whitespace":
        start += 1
    while end > start and tokens[end - 1].type == "whitespace":
        end -= 1
    return tokens[start:end]


def _is_color_value(tokens):
    tokens = _strip_whitespace(tokens)
    if len(tokens) != 1:
        return False
    token = tokens[0]
    if token.type == "hash":
        return len(token.value) in (3, 4, 6, 8) and all(
            char in _HEX_DIGITS for char in token.value
        )
    if token.type == "ident":
        return token.lower_value in _NAMED_COLORS
    if token.type == "function":
        return token.lower_name in ("rgb", "rgba", "hsl", "hsla", "hwb")
    return False


def _is_length_value(tokens):
    tokens = _strip_whitespace(tokens)
    if len(tokens) != 1:
        return False
    token = tokens[0]
    if token.type == "dimension":
        return token.lower_unit in _LENGTH_UNITS
    if token.type == "number":
        return token.value == 0
    if token.type == "function":
        return token.lower_name in ("calc", "min", "max", "clamp")
    return False


def _is_percentage_value(tokens):
    tokens = _strip_whitespace(tokens)
    return len(tokens) == 1 and tokens[0].type == "percentage"


def _is_number_value(tokens):
    tokens = _strip_whitespace(tokens)
    return len(tokens) == 1 and tokens[0].type == "number"


def _is_angle_value(tokens):
    tokens = _strip_whitespace(tokens)
    return (
        len(tokens) == 1
        and tokens[0].type == "dimension"
        and tokens[0].lower_unit in _ANGLE_UNITS
    )


def _is_time_value(tokens):
    tokens = _strip_whitespace(tokens)
    return (
        len(tokens) == 1
        and tokens[0].type == "dimension"
        and tokens[0].lower_unit in _TIME_UNITS
    )


def _is_string_value(tokens):
    tokens = _strip_whitespace(tokens)
    return len(tokens) == 1 and tokens[0].type == "string"


def _is_any_value(tokens):
    return bool(_strip_whitespace(tokens))


#: Value types that can be used with ``allowed_css_variables``. Each
#: validator takes a list of tinycss2 tokens (the resolved custom property
#: value) and returns whether the value is allowed.
CSS_VARIABLE_VALUE_TYPES = {
    "color": _is_color_value,
    "length": _is_length_value,
    "percentage": _is_percentage_value,
    "number": _is_number_value,
    "angle": _is_angle_value,
    "time": _is_time_value,
    "string": _is_string_value,
    "any": _is_any_value,
}


class CSSSanitizer:
    """Sanitizes CSS in style attributes.

    :arg iterable allowed_css_properties: set of CSS properties that are
        allowed in style attributes

    :arg iterable allowed_svg_properties: set of SVG properties that are
        allowed in style attributes

    :arg dict allowed_css_variables: optional mapping of CSS custom property
        names (for example ``"--accent"``; the ``"--"`` prefix is added if
        missing) to a value type. The value type is either one of the names
        in ``CSS_VARIABLE_VALUE_TYPES`` (``"color"``, ``"length"``,
        ``"percentage"``, ``"number"``, ``"angle"``, ``"time"``,
        ``"string"`` or ``"any"``) or a callable taking a list of tinycss2
        tokens and returning whether the value is allowed.

        When this is set, custom properties are resolved within the single
        style declaration block being sanitized: ``var()`` references
        (including nested fallbacks) are substituted, override order and
        ``!important`` within the block are honored and dependency cycles
        are dropped. External stylesheets and ancestor inheritance are
        deliberately not resolved; references to variables that can't be
        determined locally use their fallback if it's valid, otherwise the
        declaration is removed.

        Resolved values must pass the declared value type whitelist, a
        whitelist of safe functions and the URL policy, so variables can't
        be used to smuggle dangerous functions into allowed properties.

        When this is not set (the default), custom property declarations
        are dropped and declaration values are passed through unchanged,
        exactly as before.

    :arg iterable allowed_url_protocols: protocols allowed in ``url()``
        when ``allowed_css_variables`` is set. Defaults to ``()`` which
        drops all URLs. Relative URLs are allowed when this is non-empty.

    """

    def __init__(
        self,
        allowed_css_properties=ALLOWED_CSS_PROPERTIES,
        allowed_svg_properties=ALLOWED_SVG_PROPERTIES,
        allowed_css_variables=None,
        allowed_url_protocols=(),
    ):
        self.allowed_css_properties = allowed_css_properties
        self.allowed_svg_properties = allowed_svg_properties
        self.allowed_css_variables = self._normalize_allowed_variables(
            allowed_css_variables
        )
        self.allowed_url_protocols = frozenset(
            protocol.lower() for protocol in allowed_url_protocols
        )

    def _normalize_allowed_variables(self, allowed_css_variables):
        normalized = {}
        for name, value_type in (allowed_css_variables or {}).items():
            if not name.startswith("--"):
                name = "--" + name
            if isinstance(value_type, str):
                if value_type not in CSS_VARIABLE_VALUE_TYPES:
                    raise ValueError(
                        "Unknown CSS variable value type: %r" % value_type
                    )
                validator = CSS_VARIABLE_VALUE_TYPES[value_type]
            elif callable(value_type):
                validator = value_type
            else:
                raise TypeError(
                    "CSS variable value type must be a string or callable: "
                    "%r" % (value_type,)
                )
            normalized[name] = validator
        return normalized

    def sanitize_css(self, style):
        """Sanitizes css in style tags"""
        parsed = tinycss2.parse_declaration_list(style)

        if not parsed:
            return ""

        if self.allowed_css_variables:
            new_tokens = self._sanitize_tokens_with_variables(parsed)
        else:
            new_tokens = []
            for token in parsed:
                if token.type == "declaration":
                    if (
                        token.lower_name in self.allowed_css_properties
                        or token.lower_name in self.allowed_svg_properties
                    ):
                        new_tokens.append(token)
                elif token.type in ("comment", "whitespace"):
                    if new_tokens and new_tokens[-1].type != token.type:
                        new_tokens.append(token)

                # NOTE(willkg): We currently don't handle AtRule or ParseError
                # and so both get silently thrown out

        if not new_tokens:
            return ""

        return tinycss2.serialize(new_tokens).strip()

    def _sanitize_tokens_with_variables(self, parsed):
        declarations = [token for token in parsed if token.type == "declaration"]

        # Cascade custom property definitions within this declaration block:
        # the last definition wins and "!important" beats normal ones.
        definitions = {}
        for index, token in enumerate(declarations):
            if (
                token.name.startswith("--")
                and token.name in self.allowed_css_variables
            ):
                sort_key = (token.important, index)
                previous = definitions.get(token.name)
                if previous is None or sort_key > previous[0]:
                    definitions[token.name] = (sort_key, token)

        raw_values = {
            name: declaration.value
            for name, (sort_key, declaration) in definitions.items()
        }

        # Resolve all defined variables. Values that are invalid (dependency
        # cycles, unresolvable references, failed validation) end up marked
        # with the _INVALID sentinel.
        resolved = {}
        for name in raw_values:
            self._resolve_variable(name, raw_values, resolved, [])

        valid_variables = {
            name: value
            for name, value in resolved.items()
            if value is not None and value is not _INVALID
        }

        new_tokens = []
        for token in parsed:
            if token.type == "declaration":
                if token.name.startswith("--"):
                    # Custom property: only emit the winning definition and
                    # only if its resolved value is valid.
                    definition = definitions.get(token.name)
                    if (
                        definition is not None
                        and definition[1] is token
                        and token.name in valid_variables
                    ):
                        value = [self._whitespace(token)] + valid_variables[
                            token.name
                        ]
                        if token.important:
                            value = value + [self._whitespace(token)]
                        new_tokens.append(
                            self._rebuild_declaration(token, value)
                        )
                elif (
                    token.lower_name in self.allowed_css_properties
                    or token.lower_name in self.allowed_svg_properties
                ):
                    value = token.value
                    if self._contains_var(value):
                        value = self._substitute_variables(
                            value, raw_values, resolved, [], 0
                        )
                        if value is None:
                            # Unresolvable variable with no valid fallback.
                            continue
                    if not self._validate_value_safety(value):
                        continue
                    new_tokens.append(self._rebuild_declaration(token, value))
            elif token.type in ("comment", "whitespace"):
                if new_tokens and new_tokens[-1].type != token.type:
                    new_tokens.append(token)

        return new_tokens

    def _resolve_variable(self, name, raw_values, resolved, stack):
        """Resolves a custom property to its final token list.

        Returns the resolved tokens, None for variables that aren't defined
        in this declaration block (external stylesheets and inherited values
        are not resolved) or _INVALID for cyclic/invalid definitions.

        """
        if name in resolved:
            return resolved[name]
        if name not in raw_values:
            return None
        if len(stack) >= _MAX_REFERENCE_DEPTH:
            # Absurdly long reference chain: treat as unresolvable rather
            # than blowing the Python recursion limit.
            return None
        if name in stack:
            # Dependency cycle: every variable in the cycle is invalid.
            for member in stack[stack.index(name) :]:
                resolved[member] = _INVALID
            return _INVALID

        stack.append(name)
        substituted = self._substitute_variables(
            raw_values[name], raw_values, resolved, stack, 0
        )
        stack.pop()

        if resolved.get(name) is _INVALID:
            # Marked invalid by a cycle detected further down the stack.
            return _INVALID

        value = _strip_whitespace(substituted) if substituted is not None else []
        if (
            value
            and self._validate_value_safety(value)
            and self.allowed_css_variables[name](value)
        ):
            resolved[name] = value
        else:
            resolved[name] = _INVALID
        return resolved[name]

    def _substitute_variables(self, tokens, raw_values, resolved, stack, depth):
        """Substitutes var() references in a token list.

        Returns the new token list or None if a reference can't be resolved
        and has no valid fallback.

        """
        if depth > _MAX_SUBSTITUTION_DEPTH:
            return None
        new_tokens = []
        for token in tokens:
            if token.type == "function" and token.lower_name == "var":
                replacement = self._resolve_var_function(
                    token, raw_values, resolved, stack, depth
                )
                if replacement is None:
                    return None
                new_tokens.extend(replacement)
            elif token.type == "function":
                arguments = self._substitute_variables(
                    token.arguments, raw_values, resolved, stack, depth + 1
                )
                if arguments is None:
                    return None
                new_tokens.append(
                    FunctionBlock(
                        token.source_line,
                        token.source_column,
                        token.name,
                        token.lower_name,
                        arguments,
                    )
                )
            elif token.type in ("() block", "[] block", "{} block"):
                content = self._substitute_variables(
                    token.content, raw_values, resolved, stack, depth + 1
                )
                if content is None:
                    return None
                new_tokens.append(
                    type(token)(token.source_line, token.source_column, content)
                )
            else:
                new_tokens.append(token)

            if len(new_tokens) > _MAX_SUBSTITUTED_TOKENS:
                return None

        return self._separate_merged_tokens(new_tokens)

    def _resolve_var_function(self, fn_token, raw_values, resolved, stack, depth):
        """Resolves a single var() function token to replacement tokens."""
        arguments = _strip_whitespace(fn_token.arguments)
        if not arguments or arguments[0].type != "ident":
            return None
        name = arguments[0].value
        if not name.startswith("--"):
            return None

        fallback = None
        rest = _strip_whitespace(arguments[1:])
        if rest:
            if rest[0].type == "literal" and rest[0].value == ",":
                fallback = _strip_whitespace(rest[1:])
            else:
                # Malformed var() invocation.
                return None

        value = self._resolve_variable(name, raw_values, resolved, stack)
        if value is None or value is _INVALID:
            if not fallback:
                return None
            return self._substitute_variables(
                fallback, raw_values, resolved, stack, depth + 1
            )
        return value

    def _contains_var(self, tokens):
        for token in tokens:
            if token.type == "function":
                if token.lower_name == "var":
                    return True
                if self._contains_var(token.arguments):
                    return True
            elif token.type in ("() block", "[] block", "{} block"):
                if self._contains_var(token.content):
                    return True
        return False

    def _validate_value_safety(self, tokens):
        """Validates resolved tokens against the function and URL policy."""
        for token in tokens:
            token_type = token.type
            if token_type == "function":
                if token.lower_name == "url":
                    arguments = _strip_whitespace(token.arguments)
                    if (
                        len(arguments) != 1
                        or arguments[0].type != "string"
                        or not self._url_allowed(arguments[0].value)
                    ):
                        return False
                elif token.lower_name not in ALLOWED_CSS_VALUE_FUNCTIONS:
                    return False
                if not self._validate_value_safety(token.arguments):
                    return False
            elif token_type == "url":
                if not self._url_allowed(token.value):
                    return False
            elif token_type in ("bad-url", "bad-string", "error"):
                return False
            elif token_type in ("() block", "[] block", "{} block"):
                if not self._validate_value_safety(token.content):
                    return False
        return True

    def _url_allowed(self, url):
        url = url.strip()
        if not url or any(ord(char) < 0x20 or ord(char) == 0x7F for char in url):
            return False
        match = _URL_SCHEME_RE.match(url)
        if match is None:
            # Relative URL: allow only when the caller allows some protocols.
            return bool(self.allowed_url_protocols)
        return match.group(1).lower() in self.allowed_url_protocols

    def _separate_merged_tokens(self, tokens):
        """Inserts whitespace so adjacent tokens can't merge on serialize."""
        separated = []
        for token in tokens:
            if (
                separated
                and separated[-1].type in _MERGEABLE_TOKEN_TYPES
                and token.type in _MERGEABLE_TOKEN_TYPES
            ):
                separated.append(self._whitespace(token))
            separated.append(token)
        return separated

    def _whitespace(self, source_token):
        return WhitespaceToken(
            getattr(source_token, "source_line", 0),
            getattr(source_token, "source_column", 0),
            " ",
        )

    def _rebuild_declaration(self, declaration, value):
        return Declaration(
            declaration.source_line,
            declaration.source_column,
            declaration.name,
            declaration.lower_name,
            value,
            declaration.important,
        )
