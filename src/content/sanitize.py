from bs4 import BeautifulSoup, Comment


DANGEROUS_TAGS = {
    "base",
    "embed",
    "form",
    "iframe",
    "input",
    "link",
    "meta",
    "object",
    "script",
    "select",
    "textarea",
}

UNWRAP_TAGS = {"html", "head", "body"}
URI_ATTRS = {"action", "formaction", "href", "src", "xlink:href"}


def sanitize_article_html(content: str, strip_style_tags: bool = True) -> str:
    soup = BeautifulSoup(content or "", "html.parser")

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in list(soup.find_all(True)):
        name = (tag.name or "").lower()
        if name == "style" and strip_style_tags:
            tag.decompose()
            continue
        if name in DANGEROUS_TAGS:
            tag.decompose()
            continue
        if name in UNWRAP_TAGS:
            tag.unwrap()
            continue

        for attr, value in list(tag.attrs.items()):
            attr_name = attr.lower()
            if attr_name.startswith("on") or attr_name in {"srcdoc", "style"}:
                del tag.attrs[attr]
                continue
            if attr_name in URI_ATTRS and _is_unsafe_uri(value):
                del tag.attrs[attr]

    return str(soup).strip()


def _is_unsafe_uri(value) -> bool:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    lowered = str(value or "").strip().lower().replace("\x00", "")
    if lowered.startswith(("javascript:", "vbscript:")):
        return True
    if lowered.startswith("data:") and not lowered.startswith("data:image/"):
        return True
    return False
