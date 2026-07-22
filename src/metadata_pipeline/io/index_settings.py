"""Strict runtime settings for embedding and vector index apply."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlparse

from metadata_pipeline.io.runtime_environment import load_runtime_environment

DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSION = 768
DEFAULT_COLLECTION = "metadata__gemini_embedding_001__768"
DEFAULT_OPENAI_BASE_URL = "https://ai-gateway.dev/v1"
DEFAULT_QDRANT_URL = "http://localhost:6333"


class IndexConfigurationError(ValueError):
    """Raised before clients are created when index settings are unsafe."""


@dataclass(frozen=True)
class IndexSettings:
    """Validated provider identity and secret-safe connection settings."""

    enabled: bool
    embedding_provider: str = "openai_compatible"
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    openai_api_key: str = field(default="", repr=False)
    qdrant_url: str = DEFAULT_QDRANT_URL
    qdrant_api_key: str = field(default="", repr=False)
    qdrant_collection: str = DEFAULT_COLLECTION
    timeout_seconds: float = 15.0
    max_retries: int = 2
    retrieval_top_k: int = 3
    minimum_document_hit_rate: float = 0.9

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> IndexSettings:
        """Load disabled defaults without requiring external credentials."""
        values = load_runtime_environment(environ)
        enabled = _boolean(values, "INDEX_APPLY_ENABLED", False)
        provider = values.get("EMBEDDING_PROVIDER", "openai_compatible").strip().lower()
        model = values.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
        dimension = _positive_int(values, "EMBEDDING_DIMENSION", DEFAULT_EMBEDDING_DIMENSION)
        collection = values.get("QDRANT_COLLECTION", DEFAULT_COLLECTION).strip()
        openai_base_url = values.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip()
        openai_key = values.get("OPENAI_API_KEY", "").strip()
        qdrant_url = values.get("QDRANT_URL", DEFAULT_QDRANT_URL).strip()
        qdrant_key = values.get("QDRANT_API_KEY", "").strip()
        if provider != "openai_compatible":
            raise IndexConfigurationError("EMBEDDING_PROVIDER must be 'openai_compatible'")
        if not model:
            raise IndexConfigurationError("EMBEDDING_MODEL must not be empty")
        _absolute_http_url(openai_base_url, "OPENAI_BASE_URL")
        expected_suffix = f"__{_slug(model)}__{dimension}"
        if not collection.endswith(expected_suffix):
            raise IndexConfigurationError(
                "QDRANT_COLLECTION must end with the embedding model and dimension: "
                f"{expected_suffix}"
            )
        if enabled and not qdrant_url:
            raise IndexConfigurationError(
                "QDRANT_URL is required when vector index apply is enabled"
            )
        if enabled:
            _absolute_http_url(qdrant_url, "QDRANT_URL")
        if enabled and not openai_key:
            raise IndexConfigurationError(
                "OPENAI_API_KEY is required when vector index apply is enabled"
            )
        return cls(
            enabled=enabled,
            embedding_provider=provider,
            embedding_model=model,
            embedding_dimension=dimension,
            openai_base_url=openai_base_url,
            openai_api_key=openai_key,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_key,
            qdrant_collection=collection,
            timeout_seconds=_positive_float(values, "INDEX_TIMEOUT_SECONDS", 15.0),
            max_retries=_non_negative_int(values, "INDEX_MAX_RETRIES", 2),
            retrieval_top_k=_positive_int(values, "INDEX_RETRIEVAL_TOP_K", 3),
            minimum_document_hit_rate=_rate(values, "INDEX_MINIMUM_DOCUMENT_HIT_RATE", 0.9),
        )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _absolute_http_url(value: str, name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise IndexConfigurationError(f"{name} must be an absolute HTTP(S) URL")


def _boolean(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name, "").strip().lower()
    if not raw:
        return default
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise IndexConfigurationError(f"{name} must be 'true' or 'false'")


def _positive_int(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name, "").strip()
    try:
        result = int(raw) if raw else default
    except ValueError as error:
        raise IndexConfigurationError(f"{name} must be an integer") from error
    if result <= 0:
        raise IndexConfigurationError(f"{name} must be greater than zero")
    return result


def _non_negative_int(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name, "").strip()
    try:
        result = int(raw) if raw else default
    except ValueError as error:
        raise IndexConfigurationError(f"{name} must be an integer") from error
    if result < 0:
        raise IndexConfigurationError(f"{name} must not be negative")
    return result


def _positive_float(values: Mapping[str, str], name: str, default: float) -> float:
    raw = values.get(name, "").strip()
    try:
        result = float(raw) if raw else default
    except ValueError as error:
        raise IndexConfigurationError(f"{name} must be a number") from error
    if result <= 0:
        raise IndexConfigurationError(f"{name} must be greater than zero")
    return result


def _rate(values: Mapping[str, str], name: str, default: float) -> float:
    result = _positive_float(values, name, default)
    if result > 1:
        raise IndexConfigurationError(f"{name} must be at most 1")
    return result
