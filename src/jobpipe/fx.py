"""ECB daily reference rates → EUR conversion.

Two layers, deliberately split so :mod:`jobpipe.normalise` stays HTTP-free:

* :func:`load_rates` — side-effecting, locally cached. Fetches the ECB
  ``eurofxref.zip`` (a single one-row CSV listing latest rates for ~30
  currencies, all quoted as ``1 EUR = X CCY``). Re-uses an on-disk cache
  while it is younger than :data:`CACHE_TTL`.
* :func:`convert_to_eur` — pure. Takes a rates dict and a DataFrame whose
  ``salary_*_eur`` columns currently hold *native* currency (the
  source adapters leave conversion for this step) and rewrites them in
  EUR.

When a country has no known currency (or the rate is missing from ECB),
the salary columns are left null and a warning is logged. Strict schema
allows nullable salary fields, so the run continues.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

ECB_ZIP_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref.zip"
ECB_CSV_NAME = "eurofxref.csv"

# Adzuna country (ISO-3166-1 alpha-2) → ISO-4217 currency. Eurozone countries
# map to EUR, which load_rates() pins at 1.0. The 19 entries below cover every
# country Adzuna currently serves; benchmark adapters in P4 may add more.
COUNTRY_CURRENCY: dict[str, str] = {
    "AT": "EUR",
    "BE": "EUR",
    "DE": "EUR",
    "ES": "EUR",
    "FR": "EUR",
    "IE": "EUR",
    "IT": "EUR",
    "NL": "EUR",
    "AU": "AUD",
    "BR": "BRL",
    "CA": "CAD",
    "CH": "CHF",
    "GB": "GBP",
    "IN": "INR",
    "MX": "MXN",
    "NZ": "NZD",
    "PL": "PLN",
    "SG": "SGD",
    "US": "USD",
    "ZA": "ZAR",
}

DEFAULT_CACHE_PATH = Path("data") / "fx" / "eurofxref.csv"
CACHE_TTL = timedelta(hours=24)

SALARY_COLUMNS: tuple[str, ...] = (
    "salary_min_eur",
    "salary_max_eur",
    "salary_annual_eur_p50",
)


def load_rates(
    cache_path: Path | None = None,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> dict[str, float]:
    """Return a ``{currency_code: rate_per_eur}`` dict.

    Refreshes the on-disk cache when older than :data:`CACHE_TTL`. The
    returned mapping always contains ``EUR: 1.0`` so callers can divide
    uniformly without branching on the eurozone case.
    """
    cache = cache_path or DEFAULT_CACHE_PATH
    current = now or datetime.now(UTC)

    if cache.exists():
        mtime = datetime.fromtimestamp(cache.stat().st_mtime, tz=UTC)
        if current - mtime < CACHE_TTL:
            return _parse_csv(cache.read_text(encoding="utf-8"))

    csv_text = _fetch_csv(client)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(csv_text, encoding="utf-8")
    return _parse_csv(csv_text)


def _fetch_csv(client: httpx.Client | None) -> str:
    own = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        r = http.get(ECB_ZIP_URL)
        r.raise_for_status()
    finally:
        if own:
            http.close()

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        return zf.read(ECB_CSV_NAME).decode("utf-8")


def _parse_csv(text: str) -> dict[str, float]:
    """Parse the ECB daily CSV: header ``Date, USD, JPY, ...``; one data row."""
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(c.strip() for c in row)]
    if len(rows) < 2:
        raise ValueError("ECB CSV malformed: expected header + at least one data row")

    header = [h.strip() for h in rows[0]]
    data = [c.strip() for c in rows[1]]
    rates: dict[str, float] = {"EUR": 1.0}
    for code, value in zip(header[1:], data[1:], strict=False):
        if not code or not value or value.upper() == "N/A":
            continue
        try:
            rates[code] = float(value)
        except ValueError:
            continue
    return rates


def convert_to_eur(df: pd.DataFrame, rates: dict[str, float]) -> pd.DataFrame:
    """Rewrite ``salary_*_eur`` columns from native currency into EUR.

    Pure: returns a new DataFrame. Rows for which a rate cannot be resolved
    (unknown country, currency not in ECB feed) have their salary columns
    set to NaN and the situation is logged once.
    """
    out = df.copy()
    if out.empty:
        return out

    currencies = out["country"].str.upper().map(COUNTRY_CURRENCY)
    rate_per_eur = currencies.map(rates).astype(float)

    has_salary = out["salary_min_eur"].notna() | out["salary_max_eur"].notna()
    missing_mask = rate_per_eur.isna() & has_salary
    if missing_mask.any():
        unresolved = sorted(
            {
                code if isinstance(code, str) else "<unknown-country>"
                for code in currencies[missing_mask].fillna("<unknown-country>").tolist()
            }
        )
        logger.warning(
            "fx: no ECB rate for %s; %d row(s) left null",
            unresolved,
            int(missing_mask.sum()),
        )

    for col in SALARY_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce") / rate_per_eur
    return out
