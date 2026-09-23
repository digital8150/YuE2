"""Static checks for the user-facing Studio shell.

The checks deliberately avoid a browser dependency.  They catch accidental
leaks of engine terminology and stale HTML/JavaScript event wiring in a fast
unit-test run.
"""

from __future__ import annotations

import html
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "yue2_app" / "static"


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "template"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def _static_files(suffixes: tuple[str, ...]) -> list[Path]:
    if not STATIC.is_dir():
        raise AssertionError(f"missing static frontend directory: {STATIC}")
    return sorted(path for path in STATIC.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


def _read(paths: list[Path]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


class StaticFrontendContractTests(unittest.TestCase):
    def test_internal_engine_names_do_not_leak_into_static_frontend(self) -> None:
        files = _static_files((".html", ".js", ".mjs", ".css"))
        self.assertTrue(files, "expected HTML/JS/CSS files under yue2_app/static")
        text = _read(files).casefold()
        for forbidden in ("comfyui", "workflow", "checkpoint", "yue2_3b_int8_convrot", "sheetsage2"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_required_korean_copy_is_visible(self) -> None:
        html_files = _static_files((".html",))
        self.assertTrue(html_files, "expected an HTML entrypoint under yue2_app/static")
        parser = _VisibleText()
        for path in html_files:
            parser.feed(path.read_text(encoding="utf-8"))
        visible = html.unescape(" ".join(parser.parts))

        # Keep these as user concepts rather than implementation labels.  A
        # small wording change (for example, "생성하기") should not break the
        # contract while the key Korean UI remains present.
        for copy in ("가사", "스타일", "생성", "라이브러리"):
            with self.subTest(copy=copy):
                self.assertIn(copy, visible)

    def test_html_behavior_hooks_are_implemented_in_javascript(self) -> None:
        html_files = _static_files((".html",))
        js_text = _read(_static_files((".js", ".mjs"))).casefold()
        self.assertTrue(js_text.strip(), "expected JavaScript behavior under yue2_app/static")

        hook_words = re.compile(
            r"(?:nav|tab|submit|generate|download|upload|mode|advanced|simple|cover|form|search|clear|filter|remove|audio-file)",
            re.IGNORECASE,
        )
        hooks: set[str] = set()
        for path in html_files:
            source = path.read_text(encoding="utf-8")
            # IDs and hash links are useful only when they describe an action
            # or navigation target; layout-only IDs are intentionally ignored.
            for value in re.findall(r"\bid\s*=\s*['\"]([^'\"]+)['\"]", source, re.IGNORECASE):
                # SVG sprite symbol IDs are presentation assets, not behavior
                # hooks that JavaScript needs to implement.
                if value.casefold().startswith("icon-"):
                    continue
                if hook_words.search(value):
                    hooks.add(value.casefold())
            for value in re.findall(
                r"\bdata-(?:action|target|tab|nav|view|view-link|route|download|mode-option|library-mode)\s*=\s*['\"]([^'\"]+)['\"]",
                source,
                re.IGNORECASE,
            ):
                hooks.add(value.casefold())
            for value in re.findall(r"\bhref\s*=\s*['\"]#([^'\"]+)['\"]", source, re.IGNORECASE):
                if value.casefold().startswith("icon-"):
                    continue
                if hook_words.search(value):
                    hooks.add(value.casefold())
            for expression in re.findall(r"\bonclick\s*=\s*['\"]([^'\"]+)['\"]", source, re.IGNORECASE):
                hooks.update(name.casefold() for name in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", expression))

        self.assertTrue(hooks, "expected obvious navigation/submit/download hooks in HTML")
        for hook in sorted(hooks):
            with self.subTest(hook=hook):
                self.assertIn(hook, js_text)

    def test_health_and_all_library_filter_match_the_api_contract(self) -> None:
        js_text = _read(_static_files((".js", ".mjs")))
        self.assertIn('payload.engine !== "online"', js_text)
        self.assertIn('state.library.mode !== "all"', js_text)


if __name__ == "__main__":
    unittest.main()
