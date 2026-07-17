import unicodedata


LEXICON_VERSION = "zh-finance-v1"

POSITIVE_TERMS = {
    "優於預期": 2.0,
    "創新高": 1.8,
    "上修": 1.6,
    "轉盈": 1.6,
    "強勁": 1.4,
    "擴產": 1.3,
    "成長": 1.2,
    "受惠": 1.2,
    "訂單增加": 1.2,
    "買超": 1.0,
    "資金流入": 1.0,
    "回溫": 0.9,
}
NEGATIVE_TERMS = {
    "低於預期": -2.0,
    "創新低": -1.8,
    "下修": -1.6,
    "轉虧": -1.6,
    "衰退": -1.4,
    "減產": -1.3,
    "訂單減少": -1.2,
    "賣超": -1.0,
    "資金流出": -1.0,
    "降溫": -0.9,
    "裁員": -1.1,
    "違約": -1.8,
}
NEGATIONS = {"未", "不", "無", "非", "尚未", "未見"}
INTENSIFIERS = {"大幅": 1.5, "顯著": 1.4, "強烈": 1.3, "持續": 1.2}

_PHRASES = tuple(
    sorted(
        {*POSITIVE_TERMS, *NEGATIVE_TERMS, *NEGATIONS, *INTENSIFIERS},
        key=lambda value: (-len(value), value),
    )
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def normalize_sentiment_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text)).lower()
    return " ".join(normalized.split())


def tokenize_sentiment_text(text: str) -> list[str]:
    normalized = normalize_sentiment_text(text)
    tokens: list[str] = []
    index = 0
    while index < len(normalized):
        match = next(
            (phrase for phrase in _PHRASES if normalized.startswith(phrase, index)),
            None,
        )
        if match is None:
            tokens.append(normalized[index])
            index += 1
        else:
            tokens.append(match)
            index += len(match)
    return tokens


def score_news_text(text: str) -> float:
    tokens = tokenize_sentiment_text(text)
    total = 0.0
    sentiments = {**POSITIVE_TERMS, **NEGATIVE_TERMS}
    for index, token in enumerate(tokens):
        if token not in sentiments:
            continue
        prefix = tokens[max(0, index - 3) : index]
        multiplier = max(
            [INTENSIFIERS[value] for value in prefix if value in INTENSIFIERS],
            default=1.0,
        )
        multiplier = min(multiplier, 2.0)
        sign = -1.0 if any(value in NEGATIONS for value in prefix) else 1.0
        total += sentiments[token] * multiplier * sign
    return 100.0 * _clamp(total / 4.0, -1.0, 1.0)
