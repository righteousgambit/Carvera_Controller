"""Translation binding lifecycle without launching the controller."""

from carveracontroller import translation


def test_missing_catalog_uses_plain_text_fallback():
    language = translation.Lang("missing-test-catalog")
    assert language._("Tool [1] & holder") == "Tool [1] & holder"


def test_translation_bindings_are_instance_local():
    first, second = translation.Lang("en"), translation.Lang("en")
    calls = []
    first.fbind("_", lambda *args: calls.append(args), ("widget",))
    second.switch_lang("en")
    assert calls == []
    first.switch_lang("en")
    assert calls == [(("widget",), None, None)]


def test_unbinding_during_dispatch_does_not_skip_other_observers():
    language = translation.Lang("en")
    calls = []

    def first(*args):
        calls.append("first")
        language.funbind("_", first, ())

    def second(*args):
        calls.append("second")

    language.fbind("_", first, ())
    language.fbind("_", second, ())
    language.switch_lang("en")
    language.switch_lang("en")
    assert calls == ["first", "second", "second"]


def test_translation_proxy_resolves_the_current_translator(monkeypatch):
    proxy = translation.TrProxy()
    language = translation.Lang("en")
    language.ugettext = lambda text: "translated:" + text
    monkeypatch.setattr(translation, "_translator", language)
    assert proxy._("Tool") == "translated:Tool"


def test_language_retains_actual_kivy_observable_inheritance():
    from kivy.lang import Observable

    assert isinstance(translation.Lang("en"), Observable)
