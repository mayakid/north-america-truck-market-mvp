"""Domain-specific exceptions surfaced by the API and CLI."""


class RecommenderError(Exception):
    """Base class for expected application errors."""


class IncompleteInputError(RecommenderError):
    def __init__(self, missing_fields: list[str], message: str | None = None) -> None:
        self.missing_fields = missing_fields
        super().__init__(message or f"Missing required fields: {', '.join(missing_fields)}")


class InvalidInputError(RecommenderError):
    """The supplied value violates the supported product scope."""


class DataUnavailableError(RecommenderError):
    """Required BTS data or feature snapshots are unavailable."""


class ModelUnavailableError(RecommenderError):
    """The trained ranker artifact is unavailable or incompatible."""


class ExternalServiceError(RecommenderError):
    """An external LLM or retrieval service failed."""

