import sys
import types

from core.lure_vision import identify_lure_photo


def test_identify_lure_photo_requires_api_key():
    result = identify_lure_photo(b"fake-bytes", "jpg", api_key="")
    assert result == {"error": "No ANTHROPIC_API_KEY configured in Streamlit secrets."}


def test_identify_lure_photo_reports_missing_package(monkeypatch):
    # The 'anthropic' package isn't in this project's requirements yet in a
    # dev environment that hasn't installed it - identify_lure_photo() must
    # fail soft with a clear message, not raise, so the Lure Inventory page
    # can show it and fall back to manual entry.
    monkeypatch.setitem(sys.modules, "anthropic", None)  # forces ImportError on `import anthropic`
    result = identify_lure_photo(b"fake-bytes", "jpg", api_key="sk-fake")
    assert "anthropic" in result["error"]


def _install_fake_anthropic(monkeypatch, tool_input=None, raise_error=None):
    """Install a minimal fake `anthropic` module in sys.modules so
    identify_lure_photo()'s call shape can be verified without a real API
    key or network access."""
    captured = {}

    class _FakeToolUseBlock:
        type = "tool_use"
        name = "identify_lure"

        def __init__(self, input_):
            self.input = input_

    class _FakeResponse:
        def __init__(self, content):
            self.content = content

    class _FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            if raise_error:
                raise raise_error
            return _FakeResponse([_FakeToolUseBlock(tool_input or {})])

    class _FakeAnthropic:
        def __init__(self, api_key=None):
            captured["api_key"] = api_key
            self.messages = _FakeMessages()

    fake_module = types.SimpleNamespace(Anthropic=_FakeAnthropic)
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    return captured


def test_identify_lure_photo_returns_parsed_tool_input(monkeypatch):
    expected = {
        "visible": True, "brand": "Strike King", "product_name": "Thunder Cricket Swimjig",
        "search_query": "Strike King Thunder Cricket Swimjig", "notes": "",
    }
    captured = _install_fake_anthropic(monkeypatch, tool_input=expected)

    result = identify_lure_photo(b"fake-bytes", "png", api_key="sk-fake")

    assert result == expected
    assert captured["api_key"] == "sk-fake"
    assert captured["tool_choice"] == {"type": "tool", "name": "identify_lure"}
    image_block = captured["messages"][0]["content"][0]
    assert image_block["source"]["media_type"] == "image/png"


def test_identify_lure_photo_defaults_unknown_extension_to_jpeg(monkeypatch):
    captured = _install_fake_anthropic(monkeypatch, tool_input={"visible": False})
    identify_lure_photo(b"fake-bytes", "bmp", api_key="sk-fake")
    image_block = captured["messages"][0]["content"][0]
    assert image_block["source"]["media_type"] == "image/jpeg"


def test_identify_lure_photo_handles_api_error(monkeypatch):
    _install_fake_anthropic(monkeypatch, raise_error=RuntimeError("boom"))
    result = identify_lure_photo(b"fake-bytes", "jpg", api_key="sk-fake")
    assert "Lure identification failed" in result["error"]
    assert "boom" in result["error"]


def test_identify_lure_photo_handles_no_tool_use_block(monkeypatch):
    captured = _install_fake_anthropic(monkeypatch)
    captured  # unused, just documenting we don't need to inspect it here

    class _FakeTextBlock:
        type = "text"

    class _FakeResponse:
        content = [_FakeTextBlock()]

    class _FakeMessages:
        def create(self, **kwargs):
            return _FakeResponse()

    class _FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = _FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_FakeAnthropic))
    result = identify_lure_photo(b"fake-bytes", "jpg", api_key="sk-fake")
    assert "didn't return a structured answer" in result["error"]
