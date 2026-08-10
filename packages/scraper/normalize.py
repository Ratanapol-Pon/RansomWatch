import re
import unicodedata

_STRIP_TOKENS = {
    unicodedata.normalize("NFKC", t) for t in ("co", "ltd", "pcl", "plc", "จำกัด", "มหาชน")
}
_PUNCT = re.compile(r"[^\w\sก-๙]", re.UNICODE)


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFKC", name or "").lower()
    s = _PUNCT.sub(" ", s)
    tokens = [t for t in s.split() if t not in _STRIP_TOKENS]
    return " ".join(tokens)
