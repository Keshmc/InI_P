"""Sentiment analysis service with cloud NLP and local fallback."""

from __future__ import annotations

from dataclasses import dataclass
import re

from google.cloud import language_v1


@dataclass
class SentimentResult:
    """Result payload for one sentiment analysis call."""

    score: float
    magnitude: float
    status: str
    error: str
    provider: str


class SentimentAnalyzer:
    """Analyze sentiment for arbitrary text."""

    def __init__(
        self,
        use_mock: bool = False,
        max_chars: int = 4000,
        fallback_to_mock_on_error: bool = True,
    ) -> None:
        self.use_mock = use_mock
        self.max_chars = max_chars
        self.fallback_to_mock_on_error = fallback_to_mock_on_error
        self._client: language_v1.LanguageServiceClient | None = None

    @property
    def client(self) -> language_v1.LanguageServiceClient:
        """Lazy init cloud NLP client."""
        if self._client is None:
            self._client = language_v1.LanguageServiceClient()
        return self._client

    def analyze(self, text: str) -> SentimentResult:
        """Analyze text and return score/magnitude.

        Score range: -1.0 .. +1.0
        Magnitude range: 0.0 .. +inf
        """
        clipped = (text or "").strip()[: self.max_chars]
        if not clipped:
            return SentimentResult(
                score=0.0,
                magnitude=0.0,
                status="warning",
                error="No text for sentiment analysis.",
                provider="none",
            )

        if self.use_mock:
            return self._analyze_mock(clipped)

        try:
            document = language_v1.Document(content=clipped, type_=language_v1.Document.Type.PLAIN_TEXT)
            response = self.client.analyze_sentiment(request={"document": document})
            score = float(response.document_sentiment.score)
            magnitude = float(response.document_sentiment.magnitude)
            return SentimentResult(
                score=score,
                magnitude=magnitude,
                status="success",
                error="",
                provider="google-cloud-language",
            )
        except Exception as exc:  # noqa: BLE001
            if self.fallback_to_mock_on_error:
                fallback = self._analyze_mock(clipped)
                fallback.status = "warning"
                fallback.error = f"Cloud sentiment failed, fallback used: {exc}"
                return fallback

            return SentimentResult(
                score=0.0,
                magnitude=0.0,
                status="error",
                error=f"Sentiment analysis failed: {exc}",
                provider="google-cloud-language",
            )

    @staticmethod
    def _analyze_mock(text: str) -> SentimentResult:
        positive_words = {
            "good",
            "great",
            "strong",
            "growth",
            "beat",
            "bullish",
            "optimistic",
            "up",
            "surge",
            "record",
            "profit",
            "improve",
            "positive",
            "gain",
        }
        negative_words = {
            "bad",
            "weak",
            "loss",
            "miss",
            "bearish",
            "down",
            "drop",
            "fall",
            "risk",
            "lawsuit",
            "negative",
            "decline",
            "cut",
            "warn",
        }

        tokens = re.findall(r"[A-Za-z]+", text.lower())
        if not tokens:
            return SentimentResult(
                score=0.0,
                magnitude=0.0,
                status="warning",
                error="No tokens extracted for mock sentiment.",
                provider="mock",
            )

        pos_count = sum(token in positive_words for token in tokens)
        neg_count = sum(token in negative_words for token in tokens)
        matched = pos_count + neg_count

        if matched == 0:
            return SentimentResult(
                score=0.0,
                magnitude=0.05,
                status="success",
                error="",
                provider="mock",
            )

        score = (pos_count - neg_count) / matched
        magnitude = min(matched / max(len(tokens), 1) * 3.0, 2.0)

        return SentimentResult(
            score=round(float(score), 4),
            magnitude=round(float(magnitude), 4),
            status="success",
            error="",
            provider="mock",
        )
