"""Deterministic punctuation normalization shared by GUI and MCP exports."""


def normalize_cjk_quotes(text: str) -> str:
    """Use corner brackets for quotation marks while preserving apostrophes."""
    if not text:
        return text
    translated = text.translate(str.maketrans({"“": "「", "”": "」", "‘": "『", "’": "』"}))
    result = []
    double_open = True
    single_open = True
    for index, character in enumerate(translated):
        if character == '"':
            result.append("「" if double_open else "」")
            double_open = not double_open
        elif character == "'":
            previous = translated[index - 1] if index else ""
            following = translated[index + 1] if index + 1 < len(translated) else ""
            if previous.isalnum() and following.isalnum():
                result.append(character)
            else:
                result.append("『" if single_open else "』")
                single_open = not single_open
        else:
            result.append(character)
    return "".join(result)
