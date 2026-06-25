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

# Loaded translation catalogues, keyed by language code.
_catalogues: dict = {}
_active: _gettext.NullTranslations = _gettext.NullTranslations()


def _load(lang: str) -> _gettext.NullTranslations:
    if lang not in _catalogues:
        try:
            _catalogues[lang] = _gettext.translation(DOMAIN, LOCALE_DIR, languages=[lang])
        except OSError:
            log.warning("i18n: no translation catalogue for language %r; using untranslated strings.", lang)
            _catalogues[lang] = _gettext.NullTranslations()
    return _catalogues[lang]


def setup() -> None:
    """(Re)selects the active translation from netlink::language. Run at startup and on rehash."""
    global _active
    lang = (conf.conf['netlink'].get('language') or 'en').lower()
    if lang in ('en', 'c', 'posix'):
        _active = _gettext.NullTranslations()
    else:
        _active = _load(lang)
        log.debug("i18n: active language set to %r", lang)


def _(message: str) -> str:
    """Translates a message to the active language (identity if untranslated)."""
    return _active.gettext(message)
