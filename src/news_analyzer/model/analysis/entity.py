"""Entity extraction service with cloud NLP and local fallback."""

from __future__ import annotations

from dataclasses import dataclass
import re

from google.cloud import language_v1


@dataclass
class EntityItem:
    """Single extracted named entity."""

    name: str
    entity_type: str
    salience: float


@dataclass
class EntityResult:
    """Entity extraction result payload."""

    entities: list[EntityItem]
    status: str
    error: str
    provider: str


class EntityAnalyzer:
    """Analyze named entities for arbitrary text."""

    def __init__(
        self,
        use_mock: bool = False,
        max_chars: int = 4000,
        max_entities: int = 30,
        fallback_to_mock_on_error: bool = True,
    ) -> None:
        self.use_mock = use_mock
        self.max_chars = max_chars
        self.max_entities = max_entities
        self.fallback_to_mock_on_error = fallback_to_mock_on_error
        self._client: language_v1.LanguageServiceClient | None = None

    @property
    def client(self) -> language_v1.LanguageServiceClient:
        """Lazy init cloud NLP client."""
        if self._client is None:
            self._client = language_v1.LanguageServiceClient()
        return self._client

    def analyze(self, text: str) -> EntityResult:
        """Extract entities from text."""
        clipped = (text or "").strip()[: self.max_chars]
        if not clipped:
            return EntityResult(
                entities=[],
                status="warning",
                error="No text for entity extraction.",
                provider="none",
            )

        if self.use_mock:
            return self._analyze_mock(clipped)

        try:
            document = language_v1.Document(content=clipped, type_=language_v1.Document.Type.PLAIN_TEXT)
            response = self.client.analyze_entities(request={"document": document})
            entities = [
                EntityItem(
                    name=item.name,
                    entity_type=language_v1.Entity.Type(item.type_).name,
                    salience=float(item.salience),
                )
                for item in response.entities[: self.max_entities]
            ]
            return EntityResult(
                entities=entities,
                status="success",
                error="",
                provider="google-cloud-language",
            )
        except Exception as exc:  # noqa: BLE001
            if self.fallback_to_mock_on_error:
                fallback = self._analyze_mock(clipped)
                fallback.status = "warning"
                fallback.error = f"Cloud entity extraction failed, fallback used: {exc}"
                return fallback

            return EntityResult(
                entities=[],
                status="error",
                error=f"Entity extraction failed: {exc}",
                provider="google-cloud-language",
            )

    def _analyze_mock(self, text: str) -> EntityResult:
        # Simple fallback: collect title-case and all-uppercase tokens.
        candidates: dict[str, float] = {}
        for token in text.split():
            clean = token.strip(".,!?;:\"'()[]{}")
            if len(clean) < 3:
                continue
            if clean.istitle() or clean.isupper():
                candidates.setdefault(clean, 0.1)
                candidates[clean] += 0.02

        items = sorted(candidates.items(), key=lambda pair: pair[1], reverse=True)[: self.max_entities]
        entities = [
            EntityItem(name=name, entity_type=self._guess_type(name), salience=min(round(score, 4), 1.0))
            for name, score in items
        ]

        return EntityResult(
            entities=entities,
            status="success",
            error="",
            provider="mock",
        )

    @staticmethod
    def _guess_type(name: str) -> str:
        if re.fullmatch(r"[A-Z]{2,6}", name):
            return "ORGANIZATION"
        if any(ch.isdigit() for ch in name):
            return "OTHER"
        return "PERSON"
