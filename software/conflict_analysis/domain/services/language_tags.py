"""RFC 5646 well-formedness and deterministic language-tag casing.

This module deliberately validates syntax, not IANA registration or preferred
value substitutions.  The closed grandfathered production is the only part of
the RFC grammar that necessarily contains a registry-defined list.
"""

from __future__ import annotations

import re


MAX_CANONICAL_LENGTH = 255


class LanguageTagValidationError(ValueError):
    """A language tag is not a well-formed value accepted by the caller."""

    def __init__(self, message: str, *, code: str = "invalid") -> None:
        super().__init__(message)
        self.code = code


_ASCII_TAG_RE = re.compile(r"^[A-Za-z0-9-]+$")
_ALPHA_RE = re.compile(r"^[A-Za-z]+$")
_ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")

# RFC 5646, section 2.1, grandfathered production.  The values are also the
# deterministic spelling used for those otherwise opaque productions.
_GRANDFATHERED = {
    value.lower(): value
    for value in (
        "en-GB-oed",
        "i-ami",
        "i-bnn",
        "i-default",
        "i-enochian",
        "i-hak",
        "i-klingon",
        "i-lux",
        "i-mingo",
        "i-navajo",
        "i-pwn",
        "i-tao",
        "i-tay",
        "i-tsu",
        "sgn-BE-FR",
        "sgn-BE-NL",
        "sgn-CH-DE",
        "art-lojban",
        "cel-gaulish",
        "no-bok",
        "no-nyn",
        "zh-guoyu",
        "zh-hakka",
        "zh-min",
        "zh-min-nan",
        "zh-xiang",
    )
}


def _reject(message: str, *, code: str = "invalid") -> None:
    raise LanguageTagValidationError(message, code=code)


def _is_alpha(value: str, length: int | range) -> bool:
    allowed = value.__len__() == length if isinstance(length, int) else len(value) in length
    return allowed and _ALPHA_RE.fullmatch(value) is not None


def _is_alnum(value: str, lengths: range) -> bool:
    return len(value) in lengths and _ALNUM_RE.fullmatch(value) is not None


def _is_variant(value: str) -> bool:
    return (
        _is_alnum(value, range(5, 9))
        or (
            len(value) == 4
            and value[0].isdigit()
            and _ALNUM_RE.fullmatch(value) is not None
        )
    )


def canonicalize_language_tag(value: str, *, allow_und: bool = False) -> str:
    """Return the RFC 5646 well-formed tag with deterministic casing.

    Registration, suppress-script, and preferred-value checks are intentionally
    outside this syntax-only authority.  ``und`` is valid RFC syntax, but is
    rejected by default because ordinary Project creation requires an explicit
    language identity.
    """

    if not isinstance(value, str):
        _reject("Language tag must be a string.")
    if not value:
        _reject("Language tag is required.", code="required")
    if len(value) > MAX_CANONICAL_LENGTH:
        _reject(
            f"Language tag exceeds {MAX_CANONICAL_LENGTH} characters.",
            code="too_long",
        )
    if any(character.isspace() for character in value):
        _reject("Language tag must not contain whitespace.")
    if "_" in value:
        _reject("Language tag must use hyphens, not underscores.")
    if _ASCII_TAG_RE.fullmatch(value) is None:
        _reject("Language tag contains a non-ASCII or otherwise invalid character.")

    lower_value = value.lower()
    grandfathered = _GRANDFATHERED.get(lower_value)
    if grandfathered is not None:
        return grandfathered

    subtags = value.split("-")
    if any(not subtag for subtag in subtags):
        _reject("Language tag contains an empty subtag.")

    # privateuse = "x" 1*("-" (1*8alphanum))
    if subtags[0].lower() == "x":
        if len(subtags) == 1 or any(
            not _is_alnum(subtag, range(1, 9)) for subtag in subtags[1:]
        ):
            _reject("Private-use language tag is malformed.")
        canonical = "-".join(subtag.lower() for subtag in subtags)
        if len(canonical) > MAX_CANONICAL_LENGTH:
            _reject(
                f"Language tag exceeds {MAX_CANONICAL_LENGTH} characters.",
                code="too_long",
            )
        return canonical

    index = 0
    language = subtags[index]
    if not _is_alpha(language, range(2, 9)):
        _reject("Primary language subtag is malformed.")
    canonical_parts = [language.lower()]
    index += 1

    # Only a two- or three-letter language can be followed by up to three
    # extlang subtags.
    if len(language) in (2, 3):
        extlang_count = 0
        while (
            index < len(subtags)
            and extlang_count < 3
            and _is_alpha(subtags[index], 3)
        ):
            canonical_parts.append(subtags[index].lower())
            index += 1
            extlang_count += 1

    if index < len(subtags) and _is_alpha(subtags[index], 4):
        script = subtags[index]
        canonical_parts.append(script[0].upper() + script[1:].lower())
        index += 1

    if index < len(subtags):
        region = subtags[index]
        if _is_alpha(region, 2):
            canonical_parts.append(region.upper())
            index += 1
        elif len(region) == 3 and region.isascii() and region.isdigit():
            canonical_parts.append(region)
            index += 1

    variants: set[str] = set()
    while index < len(subtags) and _is_variant(subtags[index]):
        variant = subtags[index].lower()
        if variant in variants:
            _reject(f"Duplicate variant subtag {subtags[index]!r}.")
        variants.add(variant)
        canonical_parts.append(variant)
        index += 1

    singletons: set[str] = set()
    while index < len(subtags):
        singleton = subtags[index].lower()
        if len(singleton) != 1 or not singleton.isalnum() or singleton == "x":
            break
        if singleton in singletons:
            _reject(f"Duplicate extension singleton {subtags[index]!r}.")
        singletons.add(singleton)
        canonical_parts.append(singleton)
        index += 1
        extension_count = 0
        while (
            index < len(subtags)
            and len(subtags[index]) != 1
            and _is_alnum(subtags[index], range(2, 9))
        ):
            canonical_parts.append(subtags[index].lower())
            index += 1
            extension_count += 1
        if extension_count == 0:
            _reject(f"Extension {singleton!r} has no extension subtag.")

    if index < len(subtags) and subtags[index].lower() == "x":
        canonical_parts.append("x")
        index += 1
        private_count = 0
        while index < len(subtags) and _is_alnum(subtags[index], range(1, 9)):
            canonical_parts.append(subtags[index].lower())
            index += 1
            private_count += 1
        if private_count == 0:
            _reject("Private-use sequence has no private-use subtag.")

    if index != len(subtags):
        _reject(f"Language tag subtag {subtags[index]!r} is malformed or misordered.")

    canonical = "-".join(canonical_parts)
    if len(canonical) > MAX_CANONICAL_LENGTH:
        _reject(
            f"Language tag exceeds {MAX_CANONICAL_LENGTH} characters.",
            code="too_long",
        )
    if canonical == "und" and not allow_und:
        _reject(
            "The 'und' language tag is reserved for explicit legacy restoration.",
            code="und_forbidden",
        )
    return canonical
