from html.parser import HTMLParser
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    title: str
    text: str
    links: tuple[str, ...]


class _TextExtractor(HTMLParser):
    IGNORED_TAGS = {"script", "style", "noscript", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored_depth = 0
        self.in_title = False
        self.title_parts = []
        self.text_parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
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
        if tag == "title":
            self.in_title = False
        if tag in self.IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data):
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
    return ExtractedDocument(title=title, text=text, links=tuple(dict.fromkeys(parser.links)))
