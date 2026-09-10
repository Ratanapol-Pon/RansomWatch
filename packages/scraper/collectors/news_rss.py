import hashlib
import re
from datetime import UTC, datetime

import feedparser
from bs4 import BeautifulSoup

from packages.scraper.collectors.cisa_kev import Collection
from packages.scraper.collectors.feed_http import FeedError, FeedHttp
from packages.shared.schemas import ThreatReportCreate
from packages.shared.urls import clean_url

KEYWORDS = {
    "ransomware": (r"\bransomware\b", "แรนซัมแวร์", "เรียกค่าไถ่"),
    "extortion": (r"\bextortion\b", "ขู่กรรโชก"),
    "data_breach": (r"\bdata breach\b", r"\bdata leak", "ข้อมูลรั่ว", "ข้อมูลหลุด"),
    "phishing": (r"\bphishing\b", "ฟิชชิง", "ฟิชชิ่ง"),
    "bec": (r"\bbec\b", "business email compromise", "อีเมลธุรกิจ"),
    "malware": (r"\bmalware\b", r"\binfostealer\b", r"\btrojan\b", "มัลแวร์", "โทรจัน"),
    "ddos": (r"\bddos\b", "denial of service"),
    "defacement": (r"\bdefacement\b", r"\bdefaced\b", "เปลี่ยนแปลงหน้าเว็บไซต์"),
    "exploitation": (r"\bactively exploited\b", r"\bzero.day\b", "ใช้ประโยชน์จากช่องโหว่"),
}
CYBER_TERMS = r"cyber|vulnerabilit|security breach|ช่องโหว่|ไซเบอร์|แฮ็ก|โจมตี|ขโมยข้อมูล"
CVE_PATTERN = r"\bCVE-\d{4}-\d{4,}\b"


def plain_text(value: str) -> str:
    soup = BeautifulSoup(value, "html.parser")
    for element in soup(["script", "style"]):
        element.decompose()
    return " ".join(soup.get_text(" ").split())


def classify(value: str) -> tuple[list[str], list[str]]:
    tags = [
        tag
        for tag, patterns in KEYWORDS.items()
        if any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)
    ]
    cves = sorted(set(re.findall(CVE_PATTERN, value.upper())))
    return tags, cves


def parse_rss(body: bytes, *, source: str, feed_url: str) -> Collection:
    parsed = feedparser.parse(body)
    if not parsed.get("version") or parsed.get("bozo"):
        raise FeedError("RSS/Atom response is malformed or its structure changed")
    if not parsed.entries:
        raise FeedError("RSS/Atom feed unexpectedly contains no entries")
    result = Collection(fetched=len(parsed.entries))
    for entry in parsed.entries:
        title = plain_text(str(entry.get("title") or ""))[:500]
        link = clean_url(entry.get("link"))
        if not title or not link:
            result.rejected += 1
            continue
        summary = plain_text(str(entry.get("summary") or ""))
        combined = title + " " + summary
        tags, cves = classify(combined)
        if not tags and not cves and not re.search(CYBER_TERMS, combined, re.IGNORECASE):
            result.filtered += 1
            continue
        timestamp = entry.get("published_parsed") or dict(entry).get("updated_parsed")
        published = None
        if timestamp:
            try:
                published = datetime(*timestamp[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                pass
        original_id = str(entry.get("id") or link)
        # Store source metadata and a short excerpt, not full articles/content:encoded.
        metadata = {
            "id": original_id,
            "title": entry.get("title"),
            "link": entry.get("link"),
            "published": entry.get("published"),
            "updated": dict(entry).get("updated"),
            "feed_url": feed_url,
            "categories": [tag.get("term") for tag in entry.get("tags", [])],
        }
        result.reports.append(
            ThreatReportCreate(
                kind="news",
                title=title,
                source=source,
                source_record_key=hashlib.sha256(original_id.encode()).hexdigest(),
                source_url=link,
                dark_web_url=clean_url(link, onion_only=True),
                attack_types=tags or ["other"],
                cve_ids=cves,
                country=None,
                confidence="reported",
                needs_review=True,
                published_at=published,
                description=summary[:600] or None,
                raw=metadata,
            )
        )
    if result.rejected and not result.reports and not result.filtered:
        raise FeedError("RSS/Atom feed contains no usable records")
    return result


def collect_rss(url: str, source: str, http: FeedHttp) -> Collection:
    return parse_rss(http.get_rss(url), source=source, feed_url=url)
