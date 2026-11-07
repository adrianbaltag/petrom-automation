"""Turn an amount printed on an invoice into whole bani (1 leu = 100 bani).

The rule (agreed 2026-11-06): money never has 3 decimals, so the number of
digits after the LAST dot or comma says what that separator means:
    no separator      -> whole lei        100       -> 10000
    1 or 2 digits     -> decimals         199.89    -> 19989
    exactly 3 digits  -> thousands        1.234     -> 123400
Thousands groups (dot, comma or space) must all use one separator, and every
group after the first has exactly 3 digits. Anything else is refused with
AmountError, so a wrong amount is never added silently.
"""

import re

# Spaces Petrom or a PDF tool might use between thousands groups.
_SPACES = (" ", " ", " ")
_LEI_SUFFIX = re.compile(r"\s*lei\s*$", re.IGNORECASE)
_SEPARATORS = ".,"


class AmountError(ValueError):
    """The text is not an amount we can read safely."""


def parse_amount(text):
    """Return the amount in `text` as whole bani (int). Raise AmountError if unclear."""
    if not isinstance(text, str):
        raise AmountError(f"amount is not text: {text!r}")

    clean = text
    for space in _SPACES:
        clean = clean.replace(space, " ")
    clean = _LEI_SUFFIX.sub("", clean).strip()
    if not clean:
        raise AmountError(f"empty amount: {text!r}")
    if not re.fullmatch(r"[0-9., ]+", clean):
        raise AmountError(f"amount has characters other than digits and separators: {text!r}")

    last_sep_index = max(clean.rfind(sep) for sep in _SEPARATORS)
    digits_after = len(clean) - last_sep_index - 1

    if last_sep_index != -1 and digits_after in (1, 2):
        # Decimals: "199.8" -> lei "199", bani "80".
        decimal_sep = clean[last_sep_index]
        lei = _parse_whole_lei(clean[:last_sep_index], forbidden_sep=decimal_sep, original=text)
        decimals = clean[last_sep_index + 1 :]
        if not decimals.isdigit():
            raise AmountError(f"bad decimals in amount: {text!r}")
        return lei * 100 + int(decimals.ljust(2, "0"))

    # No decimals: the whole text is lei, maybe with thousands groups.
    return _parse_whole_lei(clean, forbidden_sep=None, original=text) * 100


def _parse_whole_lei(part, forbidden_sep, original):
    """Read whole lei like '1234', '1.234' or '1 234 567'. Raise AmountError if broken."""
    if part.isdigit():
        return int(part)

    used = {ch for ch in part if not ch.isdigit()}
    if len(used) != 1:
        raise AmountError(f"mixed or missing thousands separators in amount: {original!r}")
    thousands_sep = used.pop()
    if thousands_sep == forbidden_sep:
        raise AmountError(f"same separator for thousands and decimals: {original!r}")

    groups = part.split(thousands_sep)
    first, rest = groups[0], groups[1:]
    if not (1 <= len(first) <= 3 and first.isdigit()):
        raise AmountError(f"bad first thousands group in amount: {original!r}")
    if not all(len(group) == 3 and group.isdigit() for group in rest):
        raise AmountError(f"thousands groups must have 3 digits in amount: {original!r}")
    return int("".join(groups))


def format_lei(bani, suffix=True):
    """Show whole bani the Romanian way: 123456 -> '1.234,56 lei'."""
    lei, rest = divmod(bani, 100)
    text = f"{lei:,}".replace(",", ".") + f",{rest:02d}"
    return f"{text} lei" if suffix else text
