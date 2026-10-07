"""Diagnostic comparisons only. Never used by the production source guard."""
import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src import config


def normalize_title(value):
    value = unicodedata.normalize("NFKC", html.unescape(value))
    value = value.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}))
    return " ".join(value.split()).casefold()


def normalize_url(value):
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and (parsed.scheme.lower(), port) not in {("http", 80), ("https", 443)}:
        host += f":{port}"
    if ":" in (parsed.hostname or ""):
        host = f"[{parsed.hostname.lower()}]" + (f":{port}" if port and port not in {80, 443} else "")
    def percent(match):
        char = chr(int(match.group(1), 16))
        return char if char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~" else "%" + match.group(1).upper()
    path = re.sub(r"%([0-9a-fA-F]{2})", percent, parsed.path).rstrip("/")
    # Same tracking-key exclusions as existing evidence dedup; observation only.
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parsed.scheme.lower(), host, path, urlencode(sorted(query)), ""))


def _safe_text(value):
    for secret in (config.DASHSCOPE_API_KEY, config.TAVILY_API_KEY):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", value)[:2000]


def _safe_url(value):
    try:
        parsed = urlsplit(value)
        host = parsed.netloc.rsplit("@", 1)[-1]
        query = [(k, "[REDACTED]" if any(word in k.lower() for word in ("key", "token", "secret", "signature", "credential", "password")) else v)
                 for k, v in parse_qsl(parsed.query, keep_blank_values=True)]
        return _safe_text(urlunsplit((parsed.scheme, host, parsed.path, urlencode(query), "")))
    except ValueError:
        return "[INVALID URL]"


def _title_diff(a, b):
    if b is None:
        return ["no_matching_evidence"]
    if a == b:
        return []
    differences = []
    for name, transform in (
        ("html_entity", html.unescape), ("unicode_nfkc", lambda x: unicodedata.normalize("NFKC", x)),
        ("quote_style", lambda x: x.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}))),
        ("whitespace", lambda x: " ".join(x.split())), ("case", str.casefold),
    ):
        if transform(a) != a or transform(b) != b:
            differences.append(name)
    differences.append("diagnostic_equal" if normalize_title(a) == normalize_title(b) else "non_equivalent_title")
    return differences


def compare_sources(candidates, evidence):
    """Associate by exact URL, diagnostic URL, exact title, then diagnostic title.

    An association is evidence for diagnosis, never permission to accept a Case.
    """
    rows = []
    for index, case in enumerate(candidates):
        title, url = case["name"], case["source"]
        def normalized(value):
            try:
                return normalize_url(value)
            except ValueError:
                return None
        normalized_candidate = normalized(url)
        match, method = None, None
        for name, predicate in (
            ("exact_url", lambda item: url == item["url"]),
            ("normalized_url", lambda item: normalized_candidate is not None and normalized_candidate == normalized(item["url"])),
            ("exact_title", lambda item: title == item["title"]),
            ("normalized_title", lambda item: normalize_title(title) == normalize_title(item["title"])),
        ):
            match = next((i for i, item in enumerate(evidence) if predicate(item)), None)
            if match is not None:
                method = name
                break
        item = evidence[match] if match is not None else None
        exact_title = item is not None and title == item["title"]
        exact_url = item is not None and url == item["url"]
        title_equal = item is not None and normalize_title(title) == normalize_title(item["title"])
        url_equal = item is not None and normalized_candidate is not None and normalized_candidate == normalized(item["url"])
        representation = (url_equal and not exact_url) or (title_equal and not exact_title)
        unsupported = not url_equal or not title_equal
        classification = "exact_match" if exact_title and exact_url else "mixed" if representation and unsupported else "representation_mismatch" if not unsupported else "genuine_mismatch"
        rows.append({
            "case_id": None, "node": "case_research", "stage": "source_validation", "candidate_index": index,
            "candidate_title": _safe_text(title), "candidate_url": _safe_url(url),
            "matched_evidence_index": match, "evidence_match_method": method,
            "evidence_title": _safe_text(item["title"]) if item else None,
            "evidence_url": _safe_url(item["url"]) if item else None,
            "title_exact_match": exact_title, "url_exact_match": exact_url,
            "normalized_title_equal": title_equal, "normalized_url_equal": url_equal,
            "title_diff_summary": _title_diff(title, item["title"] if item else None),
            "url_diff_summary": [] if exact_url else ["diagnostic_equal" if url_equal else "unsupported_url_identity"],
            "classification": classification,
            "genuine_mismatch_scope": "relative_to_retrieved_evidence; not proof of hallucination" if unsupported else None,
        })
    return rows
