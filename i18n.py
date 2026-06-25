"""i18n.py - Internationalization support for NetLink. (issue #180)

User-facing strings are wrapped with ``_()`` and translated to the language set in
``netlink::language`` (default ``en`` = untranslated). Catalogues live in
``locales/<lang>/LC_MESSAGES/netlink.mo``, compiled from the ``.po`` sources with
``make i18n-compile``. Extend coverage by wrapping more strings, running
``make i18n-extract``, translating the new entries, and recompiling.
"""
from __future__ import annotations

import gettext as _gettext
import os

from netlink import conf
from netlink.log import log

DOMAIN = 'netlink'
LOCALE_DIR = os.path.join(os.path.dirname(__file__), 'locales')

_active: _gettext.NullTranslations = _gettext.NullTranslations()


def setup() -> None:
    """(Re)selects the active translation from netlink::language. Run at startup and on
    rehash. The catalogue is re-read from disk each call so a recompiled .mo (e.g. after
    `make i18n-compile`) takes effect on the next rehash."""
    global _active
    lang = (conf.conf['netlink'].get('language') or 'en').lower()
    if lang in ('en', 'c', 'posix'):
        _active = _gettext.NullTranslations()
        return
    mofile = os.path.join(LOCALE_DIR, lang, 'LC_MESSAGES', DOMAIN + '.mo')
    try:
        with open(mofile, 'rb') as f:
            _active = _gettext.GNUTranslations(f)
        log.debug("i18n: active language set to %r", lang)
    except OSError:
        log.warning("i18n: no translation catalogue for language %r; using untranslated strings.", lang)
        _active = _gettext.NullTranslations()


def _(message: str) -> str:
    """Translates a message to the active language (identity if untranslated)."""
    return _active.gettext(message)
