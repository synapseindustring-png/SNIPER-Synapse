import json
from dataclasses import dataclass
from html.parser import HTMLParser

from django.conf import settings


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    title: str
    text: str
    links: tuple[str, ...]
    structured_data: tuple[dict, ...]


class _TextExtractor(HTMLParser):
    IGNORED_TAGS = {"script", "style", "noscript", "svg", "template"}
    MAX_JSON_LD_CHARS = 200_000

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored_depth = 0
        self.in_title = False
        self.title_parts = []
        self.text_parts = []
        self.links = []
        self.json_ld_parts = []
        self.current_json_ld = None
        self.json_ld_chars = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "script":
            script_type = next(
                (value for key, value in attrs if key.lower() == "type"), ""
            )
            if (script_type or "").split(";", 1)[0].strip().casefold() == "application/ld+json":
                self.current_json_ld = []
        if tag in self.IGNORED_TAGS:
            self.ignored_depth += 1
        if tag == "title" and not self.ignored_depth:
            self.in_title = True
        if tag == "a" and not self.ignored_depth:
            href = next((value for key, value in attrs if key.lower() == "href"), None)
            if href and len(href) <= 2000:
                self.links.append(href)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "script" and self.current_json_ld is not None:
            value = "".join(self.current_json_ld).strip()
            if value:
                self.json_ld_parts.append(value)
            self.current_json_ld = None
        if tag == "title":
            self.in_title = False
        if tag in self.IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data):
        if self.current_json_ld is not None:
            remaining = self.MAX_JSON_LD_CHARS - self.json_ld_chars
            if remaining > 0:
                chunk = data[:remaining]
                self.current_json_ld.append(chunk)
                self.json_ld_chars += len(chunk)
        if self.ignored_depth:
            return
        compact = " ".join(data.split())
        if not compact:
            return
        self.text_parts.append(compact)
        if self.in_title:
            self.title_parts.append(compact)


def extract_html_text(body: bytes, content_type_header: str = "") -> tuple[str, str]:
    document = extract_html_document(body, content_type_header)
    return document.title, document.text


def extract_html_document(body: bytes, content_type_header: str = "") -> ExtractedDocument:
    charset = "utf-8"
    if "charset=" in content_type_header.lower():
        charset = content_type_header.lower().split("charset=", 1)[1].split(";", 1)[0].strip()
    try:
        html = body.decode(charset, errors="replace")
    except LookupError:
        html = body.decode("utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(html)
    title = " ".join(parser.title_parts)[:500]
    text = "\n".join(parser.text_parts)[: settings.CRAWLER_MAX_TEXT_CHARS]
    structured_data = []
    for raw_value in parser.json_ld_parts:
        try:
            value = json.loads(raw_value)
        except (TypeError, ValueError):
            continue
        pending = list(value) if isinstance(value, list) else [value]
        while pending and len(structured_data) < 100:
            item = pending.pop(0)
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                pending.extend(graph)
            structured_data.append(item)
    return ExtractedDocument(
        title=title,
        text=text,
        links=tuple(dict.fromkeys(parser.links)),
        structured_data=tuple(structured_data),
    )
