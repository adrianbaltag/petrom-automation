"""The dashboard table: one row per active company for one month.

Each row has the month's invoice total, the max that applies to that month, the % of the
max and a colour level. All maths uses whole bani, so the 50% and 75% edges are exact.
"""

import logging
from datetime import date

from petrom_dashboard.money import format_lei

logger = logging.getLogger(__name__)

# Colour levels. The page turns each one into a row colour plus a text label.
STATUS_OK = "ok"  # up to 50%: white
STATUS_WARNING = "atentie"  # over 50%, up to 75%: orange
STATUS_CRITICAL = "critic"  # over 75%: red
STATUS_OVER = "peste"  # 100% or more: red + "PESTE LIMITĂ"
STATUS_UNSET = "nesetat"  # no max: grey + "Max nesetat"

LABELS = {
    STATUS_OK: "",
    STATUS_WARNING: "Peste 50%",
    STATUS_CRITICAL: "Peste 75%",
    STATUS_OVER: "PESTE LIMITĂ",
    STATUS_UNSET: "Max nesetat",
}

MONTHS_RO = (
    "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
    "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie",
)  # fmt: skip

# The max for a month is the latest one set in that month or before it
# ("each month copies the previous month's max"). Months are 'YYYY-MM' text,
# so comparing them as text puts them in date order.
ROWS_SQL = """
SELECT f.id, f.cui, f.nume,
       (SELECT COALESCE(SUM(total_bani), 0) FROM facturi
         WHERE firma_id = f.id AND substr(data_factura, 1, 7) = :luna) AS total_bani,
       (SELECT max_bani FROM limite
         WHERE firma_id = f.id AND luna <= :luna
         ORDER BY luna DESC LIMIT 1) AS max_bani
FROM firme f
WHERE f.arhivat = 0
ORDER BY f.nume
"""


def _has_max(max_bani):
    # A max of 0 can't give a %. M5 will refuse it on input; until then it counts as unset.
    return max_bani is not None and max_bani > 0


def status_for(total_bani, max_bani):
    """Colour level for a month total against its max."""
    if not _has_max(max_bani):
        return STATUS_UNSET
    if total_bani >= max_bani:
        return STATUS_OVER
    if total_bani * 100 > max_bani * 75:
        return STATUS_CRITICAL
    if total_bani * 100 > max_bani * 50:
        return STATUS_WARNING
    return STATUS_OK


def percent_of_max(total_bani, max_bani):
    """Whole % of the max, rounded down (99,99% shows as 99%). None if there is no max."""
    if not _has_max(max_bani):
        return None
    return total_bani * 100 // max_bani


def current_month(today=None):
    """This month as 'YYYY-MM', from this computer's clock."""
    today = today or date.today()
    return f"{today.year:04d}-{today.month:02d}"


def month_label(luna):
    """'2026-11' -> 'noiembrie 2026'."""
    year, month = luna.split("-")
    return f"{MONTHS_RO[int(month) - 1]} {year}"


def month_rows(conn, luna):
    """One dict per active company for the month `luna` ('YYYY-MM')."""
    rows = []
    for rec in conn.execute(ROWS_SQL, {"luna": luna}):
        total, max_bani = rec["total_bani"], rec["max_bani"]
        if max_bani is not None and max_bani <= 0:
            logger.warning(
                "Company %s has a max of %s for %s; shown as unset", rec["cui"], max_bani, luna
            )
        status = status_for(total, max_bani)
        percent = percent_of_max(total, max_bani)
        has_max = percent is not None
        rows.append(
            {
                "id": rec["id"],
                "cui": rec["cui"],
                "nume": rec["nume"],
                "total_bani": total,
                "max_bani": max_bani if has_max else None,
                "procent": percent,
                "stare": status,
                "eticheta": LABELS[status],
                "suma_text": format_lei(total),
                "max_text": format_lei(max_bani) if has_max else LABELS[STATUS_UNSET],
                "procent_text": f"{percent}%" if has_max else "—",
            }
        )
    return rows
