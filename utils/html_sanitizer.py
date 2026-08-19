import bleach

ALLOWED_HTML_TAGS = {
    "p", "br", "strong", "em", "u", "h1", "h2", "h3",
    "ul", "ol", "li", "a", "blockquote", "pre", "code", "span",
}
ALLOWED_HTML_ATTRS = {"a": ["href", "target", "rel"], "span": ["class"]}


def validate_safe_html(value: str) -> str:
    """Strip all HTML tags/attrs not in whitelist. Ponytail: shared, expand tag set if Quill adds new ones."""
    if not isinstance(value, str):
        return value
    return bleach.clean(
        value,
        tags=ALLOWED_HTML_TAGS,
        attributes=ALLOWED_HTML_ATTRS,
        strip=True,
        strip_comments=True,
    )
