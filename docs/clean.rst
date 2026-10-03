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


Combining fragments (``id_namespace``)
======================================

When several user-supplied fragments end up on the same page, two fragments
can both use ``id="title"``, and links such as ``<a href="#title">`` can end
up pointing at the wrong fragment's element. Pass ``id_namespace`` to prefix
every ``id`` in a fragment with ``<id_namespace>-`` and rewrite the
fragment's own ID references to match::

    >>> import bleach
    >>> TAGS = {'h1', 'a'}
    >>> ATTRS = {'h1': ['id'], 'a': ['href']}
    >>> bleach.clean('<h1 id="title">Hi</h1><a href="#title">top</a>',
    ...              tags=TAGS, attributes=ATTRS, id_namespace='frag1')
    '<h1 id="frag1-title">Hi</h1><a href="#frag1-title">top</a>'

Clean each fragment with its own namespace and the references in the merged
page can never cross-link. Forward references (a link appearing before its
target) are rewritten as well.

The rewriting only touches attributes that survived cleaning:

* ``id`` itself
* same-document references in ``href`` (``#fragment`` only--an external URL
  such as ``https://example.com/page#fragment`` is left alone), ``usemap``
  and the space-separated tokens of ``ping``
* single ID references: ``for``, ``form`` and the single-value
  ``aria-*`` IDREF attributes (``aria-activedescendant``, ``aria-details``,
  ``aria-errormessage``)
* space-separated ID reference lists: ``headers``, ``aria-labelledby``,
  ``aria-describedby``, ``aria-controls``, ``aria-owns`` and ``aria-flowto``

Duplicate ids inside one fragment are resolved deterministically in document
order: the first occurrence keeps ``<namespace>-<id>`` and later occurrences
become ``<namespace>-<id>-2``, ``<namespace>-<id>-3`` and so on. References
always bind to the first occurrence--the same element a browser resolves
them to.

Re-cleaning an already namespaced fragment with the same ``id_namespace``
does not stack a second prefix on it.

Unresolved references
---------------------

By default an ID reference whose target doesn't exist in the cleaned
fragment (for example because the element carrying the target was removed
by cleaning) is left untouched. Pass ``dangling_idref_callback`` with a
callable to remove such references instead; the callable is invoked once
per unresolved reference as ``callback(tag, attribute, reference)``::

    >>> def report(tag, attribute, reference):
    ...     print(tag, attribute, reference)
    ...
    >>> bleach.clean('<label for="missing">Label</label>',
    ...              tags={'label'}, attributes={'label': ['for']},
    ...              id_namespace='frag1',
    ...              dangling_idref_callback=report)
    label for missing
    '<label>Label</label>'

SVG references
--------------

Local SVG references such as ``fill="url(#grad)"`` and
``<use href="#icon">`` are only rewritten when you also pass
``svg_references=True``--they require the corresponding SVG tags and
attributes to be allowed. External ``url(...)`` values are never treated as
local references, and CSS text (such as a ``<style>`` element) is never
parsed or rewritten.

.. versionadded:: 6.4.0


Using ``bleach.sanitizer.BleachSanitizerFilter``
================================================

``bleach.clean`` creates a ``bleach.sanitizer.Cleaner`` which creates a
``bleach.sanitizer.BleachSanitizerFilter`` which does the sanitizing work.

``BleachSanitizerFilter`` is an html5lib filter and can be used anywhere you can
use an html5lib filter.

.. autoclass:: bleach.sanitizer.BleachSanitizerFilter
