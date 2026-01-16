import scripts.slack as slack


def test_unescape_cli_text_newlines():
    assert slack.unescape_cli_text("line1\\nline2") == "line1\nline2"


def test_unescape_cli_text_tabs_and_returns():
    assert slack.unescape_cli_text("a\\tb\\r\\n") == "a\tb\r\n"


def test_unescape_cli_text_passes_through_real_newlines():
    text = "line1\nline2"
    assert slack.unescape_cli_text(text) == text
