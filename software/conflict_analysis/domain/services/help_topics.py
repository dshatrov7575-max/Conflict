"""Sanitized, locale/version-exact HelpTopic authoring and resolution."""

from __future__ import annotations

import hashlib
from html import escape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit


ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h2",
    "h3",
    "h4",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
}
VOID_TAGS = {"br"}
DROP_CONTENT_TAGS = {"script", "style", "iframe", "object", "embed", "svg", "math"}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
}
SAFE_URL_SCHEMES = {"", "http", "https", "mailto"}


class HelpTopicResolutionError(LookupError):
    """A stable UI key did not resolve to the exact requested topic version."""


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in DROP_CONTENT_TAGS:
            self.drop_depth += 1
            return
        if self.drop_depth or tag not in ALLOWED_TAGS:
            return
        rendered: list[str] = []
        for name, value in attrs:
            name = name.lower()
            if name.startswith("on") or name not in ALLOWED_ATTRIBUTES.get(tag, set()):
                continue
            value = value or ""
            if name == "href" and not _safe_url(value):
                continue
            rendered.append(f' {name}="{escape(value, quote=True)}"')
        self.parts.append(f"<{tag}{''.join(rendered)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DROP_CONTENT_TAGS:
            if self.drop_depth:
                self.drop_depth -= 1
            return
        if not self.drop_depth and tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.drop_depth:
            self.parts.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if not self.drop_depth:
            self.parts.append(f"&amp;{escape(name)};")

    def handle_charref(self, name: str) -> None:
        if not self.drop_depth:
            self.parts.append(f"&amp;#{escape(name)};")


def _safe_url(value: str) -> bool:
    compact = "".join(value.split())
    if compact.lower().startswith(("javascript:", "data:", "vbscript:")):
        return False
    return urlsplit(value).scheme.lower() in SAFE_URL_SCHEMES


def sanitize_help_html(raw_html: str) -> str:
    """Return deterministic allowlist-sanitized HTML suitable for persistence."""

    if not isinstance(raw_html, str):
        raise TypeError("Help HTML must be text.")
    parser = _Sanitizer()
    parser.feed(raw_html)
    parser.close()
    return "".join(parser.parts)


def sanitized_help_checksum(sanitized_html: str) -> str:
    return hashlib.sha256(sanitized_html.encode("utf-8")).hexdigest()


def resolve_help_topic(
    *,
    workspace: Any,
    ui_key: str,
    locale: str,
    version: str,
) -> Any:
    """Resolve one stable UI key to one exact published locale/version topic."""

    from domain.models import UIHelpBinding

    try:
        binding = UIHelpBinding.objects.select_related("help_topic").get(
            workspace=workspace,
            ui_key=ui_key,
            locale=locale,
            version=version,
            help_topic__locale=locale,
            help_topic__version=version,
            help_topic__publication_status="PUBLISHED",
        )
    except UIHelpBinding.DoesNotExist as exc:
        raise HelpTopicResolutionError(
            f"No published HelpTopic binding for {ui_key!r}/{locale!r}/{version!r}."
        ) from exc
    return binding.help_topic
