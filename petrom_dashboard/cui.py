"""One cleanup rule for CUIs, shared by the PDF reader and the "Adaugă firmă" form.

The app finds a company by comparing CUI text exactly, so both ways into the database
must clean a CUI the same way: "RO 046 133 455" and "46133455" are one company.
"""

import re

_SPACES = re.compile(r"\s+")  # also non-breaking and thin spaces, and tabs
_RO_PREFIX = re.compile(r"^RO", re.IGNORECASE)


def clean_cui(text):
    """Drop the RO prefix, every kind of space and leading zeros. '' if nothing is left.

    A real CUI never starts with 0 (they are plain numbers), so a leading 0 is padding.
    """
    no_spaces = _SPACES.sub("", text or "")
    return _RO_PREFIX.sub("", no_spaces).lstrip("0")
