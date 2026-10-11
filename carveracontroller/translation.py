# This module provides translation functionality for the Carvera Controller
# application that can be shared across all modules in the application.

from __future__ import annotations

import gettext
import locale
import os
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:

    class Observable:
        """The Kivy C-extension interface used by Lang.

        Kivy ships no typing declaration for Observable. Its documented fbind
        contract returns an integer uid; funbind removes a callback and returns
        None. Runtime inheritance still uses the actual Kivy class below.
        """

        def __init__(self) -> None: ...

        def fbind(self, name: str, func: Callable[..., object], *args: object, **kwargs: object) -> int | None: ...

        def funbind(self, name: str, func: Callable[..., object], *args: object, **kwargs: object) -> None: ...
else:
    from kivy.lang import Observable

LANGS = {
    "en": "English",
    "zh-CN": "中文简体(Simplified Chinese)",
}


class Lang(Observable):
    def __init__(self, defaultlang: str) -> None:
        super().__init__()
        self.observers: list[tuple[Callable[..., object], object, dict[str, object]]] = []
        self.ugettext: Callable[[str], str] = gettext.NullTranslations().gettext
        self.lang = defaultlang
        self.switch_lang(self.lang)

    def _(self, text: str) -> str:
        return self.ugettext(text)

    def fbind(self, name: str, func: Callable[..., object], *largs: object, **kwargs: object) -> int | None:
        args = largs[0] if len(largs) == 1 else largs
        if name == "_":
            self.observers.append((func, args, kwargs))
            return None
        return super().fbind(name, func, *largs, **kwargs)

    def funbind(self, name: str, func: Callable[..., object], *largs: object, **kwargs: object) -> None:
        args = largs[0] if len(largs) == 1 else largs
        if name == "_":
            key = (func, args, kwargs)
            if key in self.observers:
                self.observers.remove(key)
        else:
            super().funbind(name, func, *largs, **kwargs)

    def switch_lang(self, lang: str) -> None:
        # get the right locales directory, and instanciate a gettext
        locale_dir = os.path.join(os.path.dirname(__file__), "locales")
        locales: gettext.NullTranslations
        try:
            locales = gettext.translation(lang, locale_dir, languages=[lang])
        except (OSError, EOFError, ValueError):
            locales = gettext.NullTranslations()
        self.ugettext = locales.gettext
        self.lang = lang

        # update all the kv rules attached to this text
        for func, largs, kwargs in tuple(self.observers):
            func(largs, None, None)


# Proxy class is needed to allow for from carveracontroller.translation import tr.
# Without proxy, the initialization of the translation module would fail
# because the tr object is copied from the module to the caller's namespace
# before the translation is initialized.
class TrProxy:
    def _(self, text: str) -> str:
        if _translator is None:
            raise RuntimeError("Translation not initialized")
        return _translator._(text)

    def __getattr__(self, name: str) -> Any:
        if _translator is None:
            raise RuntimeError("Translation not initialized")
        return getattr(_translator, name)


_translator: Lang | None = Lang("en")
tr = TrProxy()


def init(langname: str | None = None) -> None:
    if langname is None or langname not in LANGS:
        try:
            default_locale = locale.getdefaultlocale()
            if default_locale is not None and default_locale[0] is not None:
                for lang_key in LANGS:
                    if default_locale[0][0:2] in lang_key:
                        langname = lang_key
                        break
        except:
            pass
    if langname is None:
        langname = "en"

    global _translator
    _translator = Lang(langname)
