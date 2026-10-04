.. _clean-chapter:
.. highlight:: python

=========================
Sanitizing text fragments
=========================

Bleach sanitizes text fragments for use in an HTML context. It provides a
:py:func:`bleach.clean` function and a more configurable
:py:class:`bleach.sanitizer.Cleaner` class with safe defaults.

Given a text fragment, Bleach will parse it according to the HTML5 parsing
algorithm and sanitize tags, attributes, and other aspects. This also handles
unescaped characters and unclosed and misnested tags. The result is text that
can be used in HTML as is.

.. Warning::

   :py:func:`bleach.clean` is for sanitising HTML fragments to use in an HTML
   context--not for use in HTML attributes, CSS, JavaScript, JavaScript
   templates (mustache, handlebars, angular, jsx, etc), JSON, xhtml, SVG, or
   other contexts.

   For example, this is a safe use of ``clean`` output in an HTML context:

   .. code-block:: html

     <p>
       {{ bleach.clean(user_bio) }}
     </p>


   This is **not a safe** use of ``clean`` output in an HTML attribute:

   .. code-block:: html

     <body data-bio="{{ bleach.clean(user_bio) }}">


   If you need to use the output of ``bleach.clean()`` in any other context,
   you need to pass it through an appropriate sanitizer/escaper for that
   context. For example, if you wanted to use the output in an HTML attribute
   value, you would need to pass it through Jinja's or Django's escape function.


.. autofunction:: bleach.clean


Allowed tags (``tags``)
=======================

The ``tags`` kwarg specifies the allowed set of HTML tags. It should be a list,
tuple, or other iterable. Any HTML tags not in this list will be escaped or
stripped from the text.

For example:

.. doctest::

   >>> import bleach

   >>> bleach.clean(
   ...     '<b><i>an example</i></b>',
   ...     tags={'b'},
   ... )
   '<b>&lt;i&gt;an example&lt;/i&gt;</b>'


The default value is a relatively conservative list found in
``bleach.sanitizer.ALLOWED_TAGS``.


.. autodata:: bleach.sanitizer.ALLOWED_TAGS


Allowed Attributes (``attributes``)
===================================

The ``attributes`` kwarg lets you specify which attributes are allowed. The
value can be a list, a callable or a map of tag name to list or callable.

The default value is also a conservative dict found in
``bleach.sanitizer.ALLOWED_ATTRIBUTES``.


.. Note::

   If you allow ``style``, you need to also sanitize css. See
   :ref:`clean-chapter-sanitizing-css` for details.


.. autodata:: bleach.sanitizer.ALLOWED_ATTRIBUTES

.. versionchanged:: 2.0

   Prior to 2.0, the ``attributes`` kwarg value could only be a list or a map.


As a list
---------

The ``attributes`` value can be a list which specifies the list of attributes
allowed for any tag.

For example:

.. doctest::

   >>> import bleach

   >>> bleach.clean(
   ...     '<p class="foo" style="color: red; font-weight: bold;">blah blah blah</p>',
   ...     tags={'p'},
   ...     attributes=['class'],
   ... )
   '<p class="foo">blah blah blah</p>'


As a dict
---------

The ``attributes`` value can be a dict which maps tags to what attributes they can have.

You can also specify ``*``, which will match any tag.

For example, this allows "href" and "rel" for "a" tags, "alt" for the "img" tag
and "class" for any tag (including "a" and "img"):

.. doctest::

   >>> import bleach

   >>> attrs = {
   ...     '*': ['class'],
   ...     'a': ['href', 'rel'],
   ...     'img': ['alt'],
   ... }

   >>> bleach.clean(
   ...    '<img alt="an example" width=500>',
   ...    tags={'img'},
   ...    attributes=attrs
   ... )
   '<img alt="an example">'


Using functions
---------------

You can also use callables that take the tag, attribute name and attribute value
and returns ``True`` to keep the attribute or ``False`` to drop it.

You can pass a callable as the attributes argument value and it'll run for
every tag/attr.

For example:

.. doctest::

   >>> import bleach

   >>> def allow_h(tag, name, value):
   ...     return name[0] == 'h'

   >>> bleach.clean(
   ...    '<a href="http://example.com" title="link">link</a>',
   ...    tags={'a'},
   ...    attributes=allow_h,
   ... )
   '<a href="http://example.com">link</a>'


You can also pass a callable as a value in an attributes dict and it'll run for
attributes for specified tags:

.. doctest::

   >>> from urllib.parse import urlparse
   >>> import bleach

   >>> def allow_src(tag, name, value):
   ...     if name in ('alt', 'height', 'width'):
   ...         return True
   ...     if name == 'src':
   ...         p = urlparse(value)
   ...         return (not p.netloc) or p.netloc == 'mydomain.com'
   ...     return False

   >>> bleach.clean(
   ...    '<img src="http://example.com" alt="an example">',
   ...    tags={'img'},
   ...    attributes={
   ...        'img': allow_src
   ...    }
   ... )
   '<img alt="an example">'


.. versionchanged:: 2.0

   In previous versions of Bleach, the callable took an attribute name and a
   attribute value. Now it takes a tag, an attribute name and an attribute
   value.


Allowed protocols (``protocols``)
=================================

If you allow tags that have attributes containing a URI value (like the ``href``
attribute of an anchor tag, you may want to adapt the accepted protocols.

For example, this sets allowed protocols to http, https and smb:

.. doctest::

   >>> import bleach

   >>> bleach.clean(
   ...     '<a href="smb://more_text">allowed protocol</a>',
   ...     protocols={'http', 'https', 'smb'}
   ... )
   '<a href="smb://more_text">allowed protocol</a>'


This adds smb to the Bleach-specified set of allowed protocols:

.. doctest::

   >>> import bleach

   >>> bleach.clean(
   ...     '<a href="smb://more_text">allowed protocol</a>',
   ...     protocols=bleach.ALLOWED_PROTOCOLS | {'smb'}
   ... )
   '<a href="smb://more_text">allowed protocol</a>'


Default protocols are in ``bleach.sanitizer.ALLOWED_PROTOCOLS``.

.. autodata:: bleach.sanitizer.ALLOWED_PROTOCOLS


Stripping markup (``strip``)
============================

By default, Bleach *escapes* tags that aren't specified in the allowed tags list
and invalid markup. For example:

.. doctest::

   >>> import bleach

   >>> bleach.clean('<span>is not allowed</span>')
   '&lt;span&gt;is not allowed&lt;/span&gt;'

   >>> bleach.clean('<b><span>is not allowed</span></b>', tags={'b'})
   '<b>&lt;span&gt;is not allowed&lt;/span&gt;</b>'


If you would rather Bleach stripped this markup entirely, you can pass
``strip=True``:

.. doctest::

   >>> import bleach

   >>> bleach.clean('<span>is not allowed</span>', strip=True)
   'is not allowed'

   >>> bleach.clean('<b><span>is not allowed</span></b>', tags={'b'}, strip=True)
   '<b>is not allowed</b>'


Stripping comments (``strip_comments``)
=======================================

By default, Bleach will strip out HTML comments. To disable this behavior, set
``strip_comments=False``:

.. doctest::

   >>> import bleach

   >>> html = 'my<!-- commented --> html'

   >>> bleach.clean(html)
   'my html'

   >>> bleach.clean(html, strip_comments=False)
   'my<!-- commented --> html'


.. _clean-chapter-sanitizing-css:

Sanitizing CSS
==============

Bleach can sanitize CSS in style attribute values. In order to use this feature,
you have to install additional dependencies::

   pip install 'bleach[css]'

Bleach provides a :py:class:`bleach.css_sanitizer.CSSSanitizer` class that has
a ``sanitize:css`` method. This takes a style attribute value as text and
returns a sanitized version of that value.

For example:

.. doctest::

   >>> import bleach
   >>> from bleach.css_sanitizer import CSSSanitizer

   >>> css_sanitizer = CSSSanitizer(allowed_css_properties=["color", "font-weight"])

   >>> tags = {'p', 'em', 'strong'}
   >>> attrs = {
   ...     '*': ['style']
   ... }

   >>> bleach.clean(
   ...     '<p style="font-weight: heavy;">my html</p>',
   ...     tags=tags,
   ...     attributes=attrs,
   ...     css_sanitizer=css_sanitizer
   ... )
   '<p style="font-weight: heavy;">my html</p>'


Defaults are stored in ``bleach.css_sanitizer.ALLOWED_CSS_PROPERTIES`` and
``bleach.css_sanitizer.ALLOWED_SVG_PROPERTIES``.

.. Note::

   This silently drops ParseError and AtRule tokens in CSS parsing. If you need
   to sanitize style values that have ``@media`` or need to do something with
   CSS parse errors, you should implement your own
   :py:class:`bleach.css_sanitizer.CSSSanitizer`.

.. autodata:: bleach.css_sanitizer.ALLOWED_CSS_PROPERTIES

.. autodata:: bleach.css_sanitizer.ALLOWED_SVG_PROPERTIES

.. autoclass:: bleach.css_sanitizer.CSSSanitizer

.. versionadded:: 5.0


Using ``bleach.sanitizer.Cleaner``
==================================

If you're cleaning a lot of text or you need better control of things, you
should create a :py:class:`bleach.sanitizer.Cleaner` instance.

.. autoclass:: bleach.sanitizer.Cleaner
   :members:

.. versionadded:: 2.0


Node constraints (``constraints``)
==================================

Some rules are awkward to express with per-attribute allow-list callables
because they need the whole element together with its position in the tree:
"links with ``target="_blank"`` must carry specific ``rel`` tokens",
"table-cell ``rowspan``/``colspan`` must stay in range", or "keep an image
only when it has non-empty ``alt`` text".

The ``constraints`` argument adds an explicit, opt-in rule phase. It runs
**after** the regular sanitizing pass (and any ``filters``) against the
**HTML5-repaired** tree. Each rule is a callable receiving one
:py:class:`bleach.constraints.NodeContext` per element. The context exposes
the element's already-filtered attributes and read-only ancestor
information.

A rule can:

* delete node attributes (``ctx.del_attr``),
* restrict token-list attributes such as ``rel`` to a set of tokens,
* adjust a value after type checking (``ctx.set_attr``),
* return a structural action to drop or unwrap the node.

Any value a rule adds or changes is re-run through the same attribute
machinery used by the regular pass, so it cannot bypass the attribute
allow-list, the protocol rules or CSS restrictions. Rules execute in
declaration order and repeat cleaning is idempotent. The phase is disabled by
default; these business rules are never global ``Cleaner`` defaults.

.. autoclass:: bleach.constraints.NodeContext
   :members:

.. autoclass:: bleach.constraints.NodeAction
   :members:

Bundled, opt-in rules
---------------------

This example wires up the three rules from above. Note that ``rel`` and
``target`` must be allowed in ``attributes`` for the rules to keep or add
them.

.. doctest::

   >>> from bleach.sanitizer import Cleaner
   >>> from bleach.constraints import (
   ...     RequireRelForBlankTarget,
   ...     ClampTableCellSpan,
   ...     RequireImageAlt,
   ... )

   >>> TAGS = ['a', 'img', 'table', 'tbody', 'tr', 'td', 'th']
   >>> ATTRS = {
   ...     'a': ['href', 'target', 'rel'],
   ...     'img': ['src', 'alt'],
   ...     'td': ['colspan', 'rowspan'],
   ...     'th': ['colspan', 'rowspan'],
   ... }
   >>> cleaner = Cleaner(
   ...     tags=TAGS,
   ...     attributes=ATTRS,
   ...     constraints=[
   ...         RequireRelForBlankTarget(),
   ...         ClampTableCellSpan(),
   ...         RequireImageAlt(),
   ...     ],
   ... )

``RequireRelForBlankTarget`` matches ``target`` case-insensitively ignoring
surrounding whitespace, strips ``rel`` tokens outside its allow-list, and
appends the required tokens. Links that do not open a new browsing context
are untouched:

.. doctest::

   >>> cleaner.clean('<a href="https://example.com" target="_blank">home</a>')
   '<a href="https://example.com" target="_blank" rel="noopener noreferrer">home</a>'

   >>> cleaner.clean('<a href="https://example.com" target="_blank" rel="stylesheet external">home</a>')
   '<a href="https://example.com" target="_blank" rel="external noopener noreferrer">home</a>'

   >>> cleaner.clean('<a href="https://example.com" target="_self" rel="stylesheet">home</a>')
   '<a href="https://example.com" target="_self" rel="stylesheet">home</a>'

Both the required tokens and the allowed tokens are configurable:

.. doctest::

   >>> rule = RequireRelForBlankTarget(
   ...     required_tokens=('nofollow',),
   ...     allowed_tokens=('nofollow', 'ugc', 'sponsored'),
   ... )

``ClampTableCellSpan`` applies HTML limits by default (``colspan`` up to
1000, ``rowspan`` up to 65534). Over-large values are clamped; values that
are not valid non-negative integers cause the attribute to be deleted (HTML
then treats the span as 1):

.. doctest::

   >>> cleaner.clean("<table><tbody><tr><td colspan='9999'>x</td><td rowspan='zero'>y</td></tr></tbody></table>")
   '<table><tbody><tr><td colspan="1000">x</td><td>y</td></tr></tbody></table>'

Boundary values are kept and out-of-range values are fixed:

.. doctest::

   >>> cleaner.clean("<table><tbody><tr><td colspan='1000' rowspan='65534'>x</td><td colspan='1001' rowspan='65535'>y</td></tr></tbody></table>")
   '<table><tbody><tr><td colspan="1000" rowspan="65534">x</td><td colspan="1000" rowspan="65534">y</td></tr></tbody></table>'

``RequireImageAlt`` drops an image whose ``alt`` is missing, empty or
whitespace-only. Foreign-namespace elements such as SVG ``<image>`` share the
local name but are left alone because the rule defaults to the HTML namespace,
which is preserved through the phase:

.. doctest::

   >>> cleaner.clean('<img src="cat.jpg" alt="a cat"><img src="x.jpg" alt="">')
   '<img src="cat.jpg" alt="a cat">'

Writing your own rule
---------------------

A rule is any callable taking a
:py:class:`bleach.constraints.NodeContext`. It returns
:py:data:`bleach.constraints.NodeAction.DROP` to remove the element and its
subtree, :py:data:`bleach.constraints.NodeAction.UNWRAP` to remove only the
element's tags while keeping its children, or anything else (including
``None``) to keep it. The context provides ``tag``, ``namespace``,
``ancestors`` and ``has_ancestor`` for read-only structural checks.

.. doctest::

   >>> from bleach.constraints import NodeAction

   >>> def unwrap_span(ctx):
   ...     if ctx.tag == 'span':
   ...         return NodeAction.UNWRAP
   ...     return NodeAction.KEEP
   ...
   >>> Cleaner(tags=['span', 'b'], constraints=[unwrap_span]).clean(
   ...     '<span>a <b>b</b></span>'
   ... )
   'a <b>b</b>'

An ancestor-aware rule:

.. doctest::

   >>> def drop_link_in_b(ctx):
   ...     if ctx.tag == 'a' and ctx.has_ancestor('b'):
   ...         return NodeAction.DROP
   ...     return NodeAction.KEEP
   ...
   >>> Cleaner(
   ...     tags=['a', 'b'],
   ...     attributes={'a': ['href']},
   ...     constraints=[drop_link_in_b],
   ... ).clean('<b><a href="x">in</a></b><a href="y">out</a>')
   '<b></b><a href="y">out</a>'

New values cannot bypass safety checks. Here an injected ``onclick`` is
removed because it is not in the allow-list, and a ``javascript:`` URL set by
a rule is dropped by the protocol check:

.. doctest::

   >>> def add_handler(ctx):
   ...     ctx.set_attr('onclick', 'alert(1)')
   ...     return NodeAction.KEEP
   ...
   >>> Cleaner(
   ...     tags=['a'],
   ...     attributes={'a': ['href']},
   ...     constraints=[add_handler],
   ... ).clean('<a href="https://example.com">x</a>')
   '<a href="https://example.com">x</a>'

.. doctest::

   >>> def to_javascript(ctx):
   ...     if ctx.tag == 'a':
   ...         ctx.set_attr('href', 'javascript:alert(1)')
   ...     return NodeAction.KEEP
   ...
   >>> Cleaner(
   ...     tags=['a'],
   ...     attributes={'a': ['href']},
   ...     constraints=[to_javascript],
   ... ).clean('<a href="https://example.com">x</a>')
   '<a>x</a>'

linkify integration
-------------------

The constraint phase is stacked after all ``filters``, so links created or
changed by :class:`bleach.linkifier.LinkifyFilter` also pass through the
final constraints:

.. doctest::

   >>> from bleach import callbacks
   >>> from bleach.linkifier import LinkifyFilter
   >>> cleaner = Cleaner(
   ...     tags=TAGS,
   ...     attributes=ATTRS,
   ...     filters=[
   ...         lambda source: LinkifyFilter(
   ...             source,
   ...             callbacks=[callbacks.target_blank, callbacks.nofollow],
   ...         )
   ...     ],
   ...     constraints=[RequireRelForBlankTarget()],
   ... )
   >>> cleaner.clean('see https://example.com please')
   'see <a href="https://example.com" target="_blank" rel="nofollow noopener noreferrer">https://example.com</a> please'

.. versionadded:: 6.4.0


html5lib Filters (``filters``)
------------------------------

Bleach sanitizing is implemented as an html5lib filter. The consequence of this
is that we can pass the streamed content through additional specified filters
after the :py:class:`bleach.sanitizer.BleachSanitizerFilter` filter has run.

This lets you add data, drop data and change data as it is being serialized back
to a unicode.

Documentation on html5lib Filters is here:
http://html5lib.readthedocs.io/en/latest/movingparts.html#filters

Trivial Filter example:

.. doctest::

   >>> from bleach.sanitizer import Cleaner
   >>> from bleach.html5lib_shim import Filter

   >>> class MooFilter(Filter):
   ...     def __iter__(self):
   ...         for token in Filter.__iter__(self):
   ...             if token['type'] in ['StartTag', 'EmptyTag'] and token['data']:
   ...                 for attr, value in token['data'].items():
   ...                     token['data'][attr] = 'moo'
   ...             yield token
   ...
   >>> ATTRS = {
   ...     'img': ['rel', 'src']
   ... }
   ...
   >>> TAGS = {'img'}
   >>> cleaner = Cleaner(tags=TAGS, attributes=ATTRS, filters=[MooFilter])
   >>> dirty = 'this is cute! <img src="http://example.com/puppy.jpg" rel="nofollow">'
   >>> cleaner.clean(dirty)
   'this is cute! <img src="moo" rel="moo">'


.. Warning::

   Filters change the output of cleaning. Make sure that whatever changes the
   filter is applying maintain the safety guarantees of the output.

.. versionadded:: 2.0


Using ``bleach.sanitizer.BleachSanitizerFilter``
================================================

``bleach.clean`` creates a ``bleach.sanitizer.Cleaner`` which creates a
``bleach.sanitizer.BleachSanitizerFilter`` which does the sanitizing work.

``BleachSanitizerFilter`` is an html5lib filter and can be used anywhere you can
use an html5lib filter.

.. autoclass:: bleach.sanitizer.BleachSanitizerFilter
