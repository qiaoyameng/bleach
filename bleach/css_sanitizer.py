import tinycss2
from tinycss2.color3 import parse_color


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


# Value types that allowed CSS custom properties (variables) can be declared
# with. Each type maps to a whitelist grammar that the fully-resolved variable
# value must match before it may be substituted into a declaration.
ALLOWED_CSS_VARIABLE_VALUE_TYPES = frozenset(
    (
        "color",
        "length",
        "percentage",
        "number",
        "length-percentage",
        "string",
    )
)


_LENGTH_UNITS = frozenset(
    (
        "px",
        "em",
        "rem",
        "ex",
        "ch",
        "vw",
        "vh",
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


# URL schemes allowed in url() constructs that appear in resolved values.
# Relative urls (no scheme) are also allowed.
_SAFE_URL_SCHEMES = frozenset(("", "http", "https"))


# Functions that must never survive var() substitution
_FORBIDDEN_FUNCTIONS = frozenset(("expression",))


# Bound on var() nesting/expansion so pathological input cannot cause
# unbounded recursion
_MAX_VAR_DEPTH = 32


# Bound on the number of tokens in a substituted value so that variables
# referencing variables cannot cause exponential expansion
_MAX_VALUE_TOKENS = 256


# Sentinel for a variable whose value cannot be resolved to something valid
# (undefined in this block, cyclic dependency, unsafe constructs, or fails
# its declared value type)
_INVALID = object()


def _significant(tokens):
    """Returns tokens with whitespace and comments removed"""
    return [token for token in tokens if token.type not in ("whitespace", "comment")]


def _stripped(tokens):
    """Returns tokens with leading and trailing whitespace/comments removed"""
    start = 0
    end = len(tokens)
    while start < end and tokens[start].type in ("whitespace", "comment"):
        start += 1
    while end > start and tokens[end - 1].type in ("whitespace", "comment"):
        end -= 1
    return tokens[start:end]


def _single_token(tokens):
    tokens = _significant(tokens)
    return tokens[0] if len(tokens) == 1 else None


def _validate_color(tokens):
    token = _single_token(tokens)
    return token is not None and parse_color(token) is not None


def _validate_length(tokens):
    token = _single_token(tokens)
    if token is None:
        return False
    if token.type == "dimension":
        return token.lower_unit in _LENGTH_UNITS
    # A bare zero is a valid length in CSS
    return token.type == "number" and token.value == 0


def _validate_percentage(tokens):
    token = _single_token(tokens)
    return token is not None and token.type == "percentage"


def _validate_number(tokens):
    token = _single_token(tokens)
    return token is not None and token.type == "number"


def _validate_length_percentage(tokens):
    return _validate_length(tokens) or _validate_percentage(tokens)


def _validate_string(tokens):
    token = _single_token(tokens)
    return token is not None and token.type == "string"


_VARIABLE_VALUE_VALIDATORS = {
    "color": _validate_color,
    "length": _validate_length,
    "percentage": _validate_percentage,
    "number": _validate_number,
    "length-percentage": _validate_length_percentage,
    "string": _validate_string,
}


def _url_scheme(url):
    """Returns the lowercased scheme of a url, or "" for relative urls"""
    for i, char in enumerate(url):
        if char == ":":
            return url[:i].strip().lower()
        if char in "/?#":
            break
    return ""


def _contains_unsafe_constructs(tokens):
    """Returns True if the token tree holds dangerous functions or urls

    Walks the tinycss2 token tree (functions and blocks) looking for
    forbidden functions like expression() and for url() constructs with
    disallowed schemes, so that variables cannot become a channel for
    smuggling dangerous values past the sanitizer.
    """
    for token in tokens:
        if token.type == "url":
            if _url_scheme(token.value) not in _SAFE_URL_SCHEMES:
                return True
        elif token.type == "bad url":
            return True
        elif token.type == "function":
            if token.lower_name in _FORBIDDEN_FUNCTIONS:
                return True
            if token.lower_name == "url":
                # url() with a quoted argument shows up as a function block
                argument = _single_token(token.arguments)
                if argument is None or argument.type != "string":
                    return True
                if _url_scheme(argument.value) not in _SAFE_URL_SCHEMES:
                    return True
            elif _contains_unsafe_constructs(token.arguments):
                return True
        elif token.type in ("[] block", "() block", "{} block"):
            if _contains_unsafe_constructs(token.content):
                return True
    return False


def _split_var_arguments(arguments):
    """Splits var() arguments into (name, fallback_tokens)

    Returns (None, None) if the arguments don't start with a custom property
    name. fallback_tokens is None when no fallback was provided.
    """
    significant = _significant(arguments)
    if not significant or significant[0].type != "ident":
        return None, None
    name = significant[0].value
    if not name.startswith("--"):
        return None, None
    # Blocks and functions are single tokens at this level, so any top-level
    # comma literal separates the name from the fallback
    for i, token in enumerate(arguments):
        if token.type == "literal" and token.value == ",":
            return name, arguments[i + 1 :]
    return name, None


def _contains_var_function(tokens):
    """Returns True if the token tree contains a var() function"""
    for token in tokens:
        if token.type == "function":
            if token.lower_name == "var":
                return True
            if _contains_var_function(token.arguments):
                return True
        elif token.type in ("[] block", "() block", "{} block"):
            if _contains_var_function(token.content):
                return True
    return False


class _CustomPropertyResolver:
    """Resolves CSS custom properties declared in a single style block

    Only variables listed in ``allowed_css_variables`` (a dict mapping
    ``--name`` to a value type like ``"color"`` or ``"length"``) are
    resolved. Variables from external stylesheets or ancestor inheritance
    are intentionally not resolved: references to them either use the var()
    fallback or cause the referencing declaration to be dropped.
    """

    def __init__(self, declarations, allowed_css_variables):
        self.allowed_css_variables = allowed_css_variables
        # Effective definition per variable name, honoring cascade order and
        # !important within this declaration block: an !important definition
        # beats a normal one, and between equally important definitions the
        # last one wins
        self._definitions = {}
        for index, token in enumerate(declarations):
            if token.type != "declaration":
                continue
            name = token.name
            if not name.startswith("--") or name not in allowed_css_variables:
                continue
            key = (token.important, index)
            if name not in self._definitions or key > self._definitions[name][0]:
                self._definitions[name] = (key, token.value)
        # Cache of resolved values: name -> token list or _INVALID
        self._resolved = {}

    def resolve_variable(self, name, stack=()):
        """Returns the resolved value tokens for a variable, or _INVALID"""
        if name in self._resolved:
            return self._resolved[name]
        if name in stack or len(stack) >= _MAX_VAR_DEPTH:
            # Cyclic dependency: per spec, every variable in the cycle is
            # invalid at computed-value time
            return _INVALID
        entry = self._definitions.get(name)
        if entry is None:
            return _INVALID
        value = self._substitute(entry[1], stack + (name,))
        if value is None or _contains_unsafe_constructs(value):
            value = _INVALID
        else:
            value = _stripped(value)
            validator = _VARIABLE_VALUE_VALIDATORS[self.allowed_css_variables[name]]
            if not value or not validator(value):
                value = _INVALID
        self._resolved[name] = value
        return value

    def _expand_var(self, function_token, stack, depth):
        """Expands a var() function token to a token list, or None"""
        name, fallback = _split_var_arguments(function_token.arguments)
        if name is not None and name in self.allowed_css_variables:
            resolved = self.resolve_variable(name, stack)
            if resolved is not _INVALID:
                return list(resolved)
        if fallback is None:
            return None
        value = self._substitute(fallback, stack, depth + 1)
        if value is None:
            return None
        return _stripped(value)

    def _substitute(self, tokens, stack=(), depth=0):
        """Substitutes var() references in a token list

        Returns the new token list, or None if a var() reference could not
        be resolved and has no fallback.
        """
        if depth > _MAX_VAR_DEPTH:
            return None
        new_tokens = []
        for token in tokens:
            if len(new_tokens) > _MAX_VALUE_TOKENS:
                return None
            if token.type == "function" and token.lower_name == "var":
                expanded = self._expand_var(token, stack, depth)
                if expanded is None:
                    return None
                new_tokens.extend(expanded)
            elif token.type == "function":
                arguments = self._substitute(token.arguments, stack, depth)
                if arguments is None:
                    return None
                token.arguments = arguments
                new_tokens.append(token)
            elif token.type in ("[] block", "() block", "{} block"):
                content = self._substitute(token.content, stack, depth)
                if content is None:
                    return None
                token.content = content
                new_tokens.append(token)
            else:
                new_tokens.append(token)
        return new_tokens

    def substitute(self, tokens):
        """Substitutes var() references in a declaration value token list"""
        return self._substitute(tokens)


class CSSSanitizer:
    def __init__(
        self,
        allowed_css_properties=ALLOWED_CSS_PROPERTIES,
        allowed_svg_properties=ALLOWED_SVG_PROPERTIES,
        allowed_css_variables=None,
    ):
        self.allowed_css_properties = allowed_css_properties
        self.allowed_svg_properties = allowed_svg_properties
        if allowed_css_variables is None:
            allowed_css_variables = {}
        for name, value_type in allowed_css_variables.items():
            if not name.startswith("--"):
                raise ValueError(
                    "CSS variable names must start with '--': %r" % (name,)
                )
            if value_type not in ALLOWED_CSS_VARIABLE_VALUE_TYPES:
                raise ValueError(
                    "Unknown CSS variable value type %r for %r; expected one of %s"
                    % (value_type, name, sorted(ALLOWED_CSS_VARIABLE_VALUE_TYPES))
                )
        self.allowed_css_variables = dict(allowed_css_variables)

    def sanitize_css(self, style):
        """Sanitizes css in style tags"""
        parsed = tinycss2.parse_declaration_list(style)

        if not parsed:
            return ""

        resolver = None
        if self.allowed_css_variables:
            resolver = _CustomPropertyResolver(parsed, self.allowed_css_variables)

        new_tokens = []
        for token in parsed:
            if token.type == "declaration":
                if token.name.startswith("--"):
                    # Custom property definitions are consumed by the
                    # resolver and never emitted
                    continue
                if (
                    token.lower_name in self.allowed_css_properties
                    or token.lower_name in self.allowed_svg_properties
                ):
                    if resolver is not None and _contains_var_function(token.value):
                        value = resolver.substitute(token.value)
                        if (
                            value is None
                            or not _significant(value)
                            or _contains_unsafe_constructs(value)
                        ):
                            continue
                        token.value = value
                    new_tokens.append(token)
            elif token.type in ("comment", "whitespace"):
                if new_tokens and new_tokens[-1].type != token.type:
                    new_tokens.append(token)

            # NOTE(willkg): We currently don't handle AtRule or ParseError and
            # so both get silently thrown out

        if not new_tokens:
            return ""

        return tinycss2.serialize(new_tokens).strip()
