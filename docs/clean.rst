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


Node constraints (``constraints``)
==================================

The per-attribute allow-list and attribute callbacks work on one attribute at
a time, so rules that combine several values are awkward:

* a ``target="_blank"`` link that *must* carry specific ``rel`` tokens,
* a table cell whose ``rowspan``/``colspan`` must be an int in a range,
* an ``img`` kept only when ``alt`` is present and non-empty.

The ``constraints`` argument adds a second, tree-aware phase that runs
**after** the sanitizer and any ``filters`` (including
``LinkifyFilter``). Each constraint is a plain callable::

    def rule(attrs, context): ...

* ``attrs`` is the mapping of attributes that already survived the
  allow-list, URI protocol, SVG IRI and CSS checks, keyed by
  ``(namespace, name)``. The rule may delete attributes, trim token lists or
  replace values that already passed type validation.
* ``context`` is a read-only :class:`bleach.constraints.NodeContext`: the
  element's ``name``, its ``namespace``, its token type and an
  ``ancestors`` tuple of ``(namespace, name)`` pairs taken from the
  **HTML5-repaired** tree (so mis-nested tags look like what a browser would
  build).

The rule returns:

* ``None`` (or it just mutates ``attrs`` in place) to keep the node,
* a replacement ``attrs`` dict,
* :data:`bleach.constraints.DROP_NODE` to remove the element and everything
  inside it, or
* :data:`bleach.constraints.UNWRAP_NODE` to remove just the start/end tags
  while keeping the children.

Rules run in **declaration order**; once a rule drops or unwraps a node,
later rules do not see it.

.. Warning::

   Any value a rule *adds* or replaces is run back through the same security
   checks. A rule cannot introduce a disallowed attribute, a ``javascript:``
   URL, or CSS that the configured ``css_sanitizer`` would remove. Rules can
   only operate inside the policy you configure on the ``Cleaner``.

Small helpers are provided in :mod:`bleach.constraints`:
:func:`~bleach.constraints.get_attr`,
:func:`~bleach.constraints.set_attr`,
:func:`~bleach.constraints.del_attr`,
:func:`~bleach.constraints.get_tokens`,
:func:`~bleach.constraints.set_tokens`,
:func:`~bleach.constraints.constrain_tokens` and
:func:`~bleach.constraints.ensure_rel_tokens`.

These rules are **not** global defaults--you declare and order them per
``Cleaner``. Here is a configuration for the three rules above:

.. testsetup:: constraints

   from bleach.sanitizer import Cleaner
   from bleach.constraints import (
       DROP_NODE,
       del_attr,
       ensure_rel_tokens,
       get_attr,
       set_attr,
   )

   def require_rel_for_target_blank(required=("noopener", "noreferrer")):
       def rule(attrs, context):
           if context.name == "a" and get_attr(attrs, "target", default="") == "_blank":
               ensure_rel_tokens(attrs, required)
       return rule

   def clamp_table_span(name, minimum=1, maximum=65534):
       def rule(attrs, context):
           if context.name not in ("td", "th") or (None, name) not in attrs:
               return
           raw = get_attr(attrs, name)
           try:
               value = int(raw, 10)
           except (TypeError, ValueError):
               del_attr(attrs, name)
               return
           if value < minimum:
               del_attr(attrs, name)
           elif value > maximum:
               set_attr(attrs, name, str(maximum))
       return rule

   def drop_images_without_alt(attrs, context):
       if context.name == "img" and not get_attr(attrs, "alt", default="").strip():
           return DROP_NODE

   cleaner = Cleaner(
       tags={"a", "img", "table", "tbody", "tr", "td", "th"},
       attributes={
           "a": ["href", "target", "rel"],
           "img": ["src", "alt"],
           "td": ["rowspan", "colspan"],
           "th": ["rowspan", "colspan"],
       },
       constraints=[
           require_rel_for_target_blank(),
           clamp_table_span("colspan"),
           clamp_table_span("rowspan"),
           drop_images_without_alt,
       ],
   )

.. doctest:: constraints

   >>> cleaner.clean('<a href="https://example.com" target="_blank">x</a>')
   '<a href="https://example.com" target="_blank" rel="noopener noreferrer">x</a>'
   >>> cleaner.clean('<a href="https://example.com" target="_self">x</a>')
   '<a href="https://example.com" target="_self">x</a>'
   >>> cleaner.clean('<img src="p.jpg" alt="puppy">')
   '<img src="p.jpg" alt="puppy">'
   >>> cleaner.clean('x <img src="p.jpg"> y')
   'x  y'
   >>> cleaner.clean('<table><tbody><tr><td colspan="99999">x</td></tr></tbody></table>')
   '<table><tbody><tr><td colspan="65534">x</td></tr></tbody></table>'
   >>> cleaner.clean('<table><tbody><tr><td colspan="0">x</td></tr></tbody></table>')
   '<table><tbody><tr><td>x</td></tr></tbody></table>'

Boundary cases worth knowing about:

* Token rules are case-insensitive but preserve casing; running the rule on
  output that already contains the tokens must not duplicate or change
  anything (idempotence).
* Non-integer and out-of-range span values are removed by the example rule;
  values above the maximum are clamped instead.
* ``alt=""`` and whitespace-only ``alt`` are treated as empty.
* An ``UNWRAP_NODE`` on an empty element (``img``) has nothing to keep, so the
  element is dropped.
* Added values are re-validated: a rule that sets ``href`` to
  ``"javascript:alert(1)"`` causes the attribute to be removed, and a rule
  that sets ``style`` still goes through the ``CSSSanitizer``.
* Namespaces are preserved; ``context.namespace`` is the SVG/MathML namespace
  for foreign content, and namespaced attributes keep their
  ``(namespace, name)`` keys.

Because constraints run after ``filters``, links created or edited by
``LinkifyFilter`` are subject to the same final constraints:

.. code-block:: python

   import functools
   from bleach.linkifier import LinkifyFilter

   def open_in_new_tab(attrs, new=False):
       if (None, "href") in attrs:
           attrs[(None, "target")] = "_blank"
       return attrs

   cleaner = Cleaner(
       tags={"a"},
       attributes={"a": ["href", "target", "rel"]},
       filters=[functools.partial(LinkifyFilter, callbacks=[open_in_new_tab])],
       constraints=[require_rel_for_target_blank()],
   )
   cleaner.clean("see https://example.com")
   # 'see <a href="https://example.com" target="_blank"
   #  rel="noopener noreferrer">https://example.com</a>'

.. versionadded:: 6.4

.. autoclass:: bleach.constraints.NodeContext
   :members:

.. autoclass:: bleach.constraints.NodeConstraintFilter
   :members:


Using ``bleach.sanitizer.BleachSanitizerFilter``
================================================

``bleach.clean`` creates a ``bleach.sanitizer.Cleaner`` which creates a
``bleach.sanitizer.BleachSanitizerFilter`` which does the sanitizing work.

``BleachSanitizerFilter`` is an html5lib filter and can be used anywhere you can
use an html5lib filter.

.. autoclass:: bleach.sanitizer.BleachSanitizerFilter
