"""The dashboard table: one row per active company for one month.

Each row has the month's invoice total, the max that applies to that month, the % of the
max and a colour level. All maths uses whole bani, so the 50% and 75% edges are exact.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

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


def has_max(max_bani):
    """True if the max can give a % (also used by firme.update_company)."""
    # A max of 0 can't give a %. M5 will refuse it on input; until then it counts as unset.
    return max_bani is not None and max_bani > 0


def status_for(total_bani, max_bani):
    """Colour level for a month total against its max."""
    if not has_max(max_bani):
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
    if not has_max(max_bani):
        return None
    return total_bani * 100 // max_bani


def today():
    """Today's date from this computer's clock. Tests replace this to fix the date."""
    return date.today()


def current_month(day=None):
    """The month of `day` (default: today) as 'YYYY-MM'."""
    day = day or today()
    return f"{day.year:04d}-{day.month:02d}"


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


def edit_max_inputs(conn, luna):
    """{company id: max box text} for the edit window, from the max that applies in `luna`.

    The route passes this month, whatever month the table shows: a new max is saved from
    this month on, so the box must start from this month's max. "5.000,00", "" if unset.
    """
    boxes = {}
    for rec in conn.execute(ROWS_SQL, {"luna": luna}):
        max_bani = rec["max_bani"]
        boxes[rec["id"]] = format_lei(max_bani, suffix=False) if has_max(max_bani) else ""
    return boxes


# --- M6 filters: last 7 / 30 days, a calendar range, a past month ----------------------

# How many days the "Ultimele N zile" buttons may ask for.
DAY_FILTERS = (7, 30)

FILTER_UNKNOWN = "Filtru necunoscut. Reîncarcă pagina și încearcă din nou."
FILTER_ONE_ONLY = "Alege un singur filtru o dată."
BOTH_DATES = "Alege ambele date: „De la” și „Până la”."
BAD_DATE = "Dată greșită. Alege data din calendar."
BAD_MONTH = "Lună greșită. Alege luna din listă."
WRONG_ORDER = "„De la” trebuie să fie înainte de „Până la” sau în aceeași zi."
FUTURE_DATE = "Nu poți alege o dată din viitor."
FUTURE_MONTH = "Nu poți alege o lună din viitor."

# Exactly 'YYYY-MM-DD' / 'YYYY-MM'. date.fromisoformat alone would also take '20261107'.
DAY_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
MONTH_PATTERN = re.compile(r"\d{4}-\d{2}")

RANGE_SQL = """
SELECT f.id, f.cui, f.nume,
       (SELECT COALESCE(SUM(total_bani), 0) FROM facturi
         WHERE firma_id = f.id AND data_factura BETWEEN :de AND :pana) AS total_bani
FROM firme f
WHERE f.arhivat = 0
ORDER BY f.nume
"""


class PeriodError(Exception):
    """A filter the page sent can't be used. `mesaj` is the Romanian text for her."""

    def __init__(self, mesaj):
        super().__init__(mesaj)
        self.mesaj = mesaj


@dataclass(frozen=True)
class Period:
    """What the table shows: one month (`luna` set) or a date range (`start`..`end`)."""

    titlu: str
    luna: str | None = None
    start: date | None = None
    end: date | None = None


def last_days(days, day):
    """The last `days` days ending on `day`, both included: 7 on 7 Nov = 1..7 Nov."""
    return day - timedelta(days=days - 1), day


def _parse_day(text):
    if not DAY_PATTERN.fullmatch(text):
        raise PeriodError(BAD_DATE)
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise PeriodError(BAD_DATE) from None


def _parse_month(text, day):
    if not MONTH_PATTERN.fullmatch(text) or not 1 <= int(text[5:]) <= 12:
        raise PeriodError(BAD_MONTH)
    if text > current_month(day):  # 'YYYY-MM' text sorts in date order
        raise PeriodError(FUTURE_MONTH)
    return text


def range_label(start, end):
    """'1 – 7 noiembrie 2026', '9 octombrie – 7 noiembrie 2026', across years both years."""
    end_text = f"{end.day} {MONTHS_RO[end.month - 1]} {end.year}"
    if start == end:
        return end_text
    if start.year != end.year:
        start_text = f"{start.day} {MONTHS_RO[start.month - 1]} {start.year}"
    elif start.month != end.month:
        start_text = f"{start.day} {MONTHS_RO[start.month - 1]}"
    else:
        start_text = str(start.day)
    return f"{start_text} – {end_text}"


def _range_period(start, end):
    return Period(titlu=range_label(start, end), start=start, end=end)


def period_from_args(args, day):
    """Turn the page's query (`luna`, `zile`, or `de` + `pana`) into a Period.

    Nothing sent means this month. Raises PeriodError with a Romanian message.
    """
    sent = [key for key in ("luna", "zile", "de", "pana") if key in args]
    if ("luna" in sent or "zile" in sent) and len(sent) > 1:
        raise PeriodError(FILTER_ONE_ONLY)

    if "zile" in args:
        if args["zile"] not in {str(n) for n in DAY_FILTERS}:
            raise PeriodError(FILTER_UNKNOWN)
        return _range_period(*last_days(int(args["zile"]), day))

    if "de" in args or "pana" in args:
        de_text, pana_text = args.get("de", "").strip(), args.get("pana", "").strip()
        if not de_text or not pana_text:
            raise PeriodError(BOTH_DATES)
        start, end = _parse_day(de_text), _parse_day(pana_text)
        if start > day or end > day:
            raise PeriodError(FUTURE_DATE)
        if start > end:
            raise PeriodError(WRONG_ORDER)
        return _range_period(start, end)

    luna = _parse_month(args["luna"], day) if "luna" in args else current_month(day)
    return Period(titlu=month_label(luna), luna=luna)


def range_rows(conn, start, end):
    """One dict per active company: its invoice total from `start` to `end`, both included.

    No max, % or colour: a max is per month, so it can't be compared with a 7-day total.
    """
    params = {"de": start.isoformat(), "pana": end.isoformat()}
    return [
        {
            "id": rec["id"],
            "cui": rec["cui"],
            "nume": rec["nume"],
            "total_bani": rec["total_bani"],
            "suma_text": format_lei(rec["total_bani"]),
            "stare": "",
        }
        for rec in conn.execute(RANGE_SQL, params)
    ]


def month_choices(conn, day):
    """The month dropdown: this month back to the oldest invoice's month, newest first.

    Archived companies' invoices count too: restoring a company brings its history back.
    """
    newest = current_month(day)
    oldest = conn.execute("SELECT substr(MIN(data_factura), 1, 7) FROM facturi").fetchone()[0]
    if oldest is None or oldest > newest:
        oldest = newest
    year, month = day.year, day.month
    choices = []
    while f"{year:04d}-{month:02d}" >= oldest:
        luna = f"{year:04d}-{month:02d}"
        choices.append({"luna": luna, "text": month_label(luna)})
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return choices


def archived_count(conn):
    """How many companies are archived: the page shows "Firme arhivate (N)" when N > 0."""
    return conn.execute("SELECT COUNT(*) FROM firme WHERE arhivat = 1").fetchone()[0]
