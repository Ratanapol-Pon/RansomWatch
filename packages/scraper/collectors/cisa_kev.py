import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from packages.scraper.collectors.feed_http import FeedError, FeedHttp
from packages.shared.schemas import ThreatReportCreate

CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"


@dataclass
class Collection:
    reports: list[ThreatReportCreate] = field(default_factory=list)
    fetched: int = 0
    rejected: int = 0
    filtered: int = 0


def parse_kev(body: bytes) -> Collection:
    try:
        catalog = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise FeedError("KEV response is not JSON") from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("vulnerabilities"), list):
        raise FeedError("KEV catalog structure changed")
    rows = catalog["vulnerabilities"]
    if not rows or catalog.get("count") != len(rows):
        raise FeedError("KEV catalog is empty or count does not match")
    result = Collection(fetched=len(rows))
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError("record is not an object")
            cve = row["cveID"]
            if not isinstance(cve, str) or not re.fullmatch(r"CVE-\d{4}-\d{4,}", cve):
                raise ValueError("invalid CVE")
            added = date.fromisoformat(row["dateAdded"])
            title, vendor, product = (
                row[k] for k in ("vulnerabilityName", "vendorProject", "product")
            )
            if not all(isinstance(v, str) and v.strip() for v in (title, vendor, product)):
                raise ValueError("missing title or product")
            result.reports.append(
                ThreatReportCreate(
                    kind="advisory",
                    title=title,
                    source="cisa_kev",
                    source_record_key=cve,
                    source_url=f"{CATALOG_URL}?search_api_fulltext={cve}",
                    cve_ids=[cve],
                    affected_products=[f"{vendor} {product}"],
                    attack_types=["exploitation"],
                    confidence="confirmed",
                    needs_review=False,
                    published_at=datetime.combine(added, datetime.min.time(), tzinfo=UTC),
                    description=row.get("shortDescription"),
                    raw=row,
                )
            )
        except (KeyError, TypeError, ValueError):
            result.rejected += 1
    if not result.reports:
        raise FeedError("KEV response contains no valid records")
    return result


def collect_kev(url: str, http: FeedHttp) -> Collection:
    return parse_kev(http.get_json(url))
