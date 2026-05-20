import re


DEFAULT_PROFANITY_ROOTS = (
    "fuck",
    "shit",
    "bitch",
    "damn",
)

DEFAULT_PROFANITY_SUFFIXES = (
    "ing",
    "ed",
    "er",
    "ers",
    "es",
    "s",
)

DEFAULT_PROFANITY_MASK = "[ _ ]"


def mask_english_profanity(
    text: str,
    roots: tuple[str, ...] = DEFAULT_PROFANITY_ROOTS,
    suffixes: tuple[str, ...] = DEFAULT_PROFANITY_SUFFIXES,
    mask: str = DEFAULT_PROFANITY_MASK,
) -> str:
    if not text:
        return text

    suffix_pattern = "|".join(re.escape(suffix) for suffix in suffixes)
    root_pattern = "|".join(re.escape(root) for root in roots)
    pattern = re.compile(
        rf"(?<![A-Za-z])(?P<root>{root_pattern})(?P<suffix>{suffix_pattern})?(?![A-Za-z])",
        re.IGNORECASE,
    )

    def replace(match: re.Match) -> str:
        suffix = match.group("suffix") or ""
        return f"{mask}{suffix}"

    return pattern.sub(replace, text)
