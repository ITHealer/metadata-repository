"""OpenAI-compatible document generator for a LiteLLM model gateway."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Annotated
from urllib.parse import urlparse

from dotenv import find_dotenv, load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.shared_params import ResponseFormatJSONObject, ResponseFormatJSONSchema
from pydantic import Field, ValidationError

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.domain.published import (
    GeneratorMode,
    Provenance,
    PublishedDocument,
)
from metadata_pipeline.domain.review import DocumentStatus, StrictModel
from metadata_pipeline.ports.document_generator import (
    DocumentGenerationError,
    PublicationContext,
)

DEFAULT_BASE_URL = "https://ai-gateway.dev/v1"
DEFAULT_MODEL = "gpt-5.4-nano"
DEFAULT_PROMPT_VERSION = "workflow-neutral-narrative-v2"


class ResponseFormatMode(str, Enum):
    """Structured-output modes commonly supported by OpenAI-compatible gateways."""

    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"


class GatewayConfigurationError(ValueError):
    """Raised when live generator environment variables are invalid or incomplete."""


class _SummaryResponse(StrictModel):
    """The only narrative field the first live vertical slice may change."""

    summary: str = Field(min_length=1)


NarrativeText = Annotated[str, Field(min_length=1)]


class _ApprovedNarrativeResponse(StrictModel):
    """Narrative-only fields that an approved live document may rewrite."""

    summary: str = Field(min_length=1)
    description: str = Field(min_length=1)
    purpose: tuple[NarrativeText, ...] = Field(min_length=1)
    appropriate_use: tuple[NarrativeText, ...] = Field(min_length=1)
    inappropriate_use: tuple[NarrativeText, ...] = Field(min_length=1)
    column_descriptions: dict[str, NarrativeText]
    relationship_meanings: dict[str, NarrativeText]
    rule_descriptions: dict[str, NarrativeText]


@dataclass(frozen=True)
class OpenAICompatibleSettings:
    """Provider-independent settings for a LiteLLM/OpenAI-compatible endpoint."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 60.0
    max_retries: int = 2
    response_format: ResponseFormatMode = ResponseFormatMode.JSON_SCHEMA
    prompt_version: str = DEFAULT_PROMPT_VERSION

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> OpenAICompatibleSettings:
        """Load live settings from exported variables or the nearest local .env file."""
        values = _load_runtime_environment() if environ is None else environ
        api_key = values.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise GatewayConfigurationError("OPENAI_API_KEY is required for live generation")
        base_url = values.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).strip()
        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise GatewayConfigurationError("OPENAI_BASE_URL must be an absolute HTTP(S) URL")
        model = values.get("OPENAI_MODEL", DEFAULT_MODEL).strip()
        if not model:
            raise GatewayConfigurationError("OPENAI_MODEL must not be empty")
        timeout_seconds = _positive_float(values, "OPENAI_TIMEOUT_SECONDS", 60.0)
        max_retries = _non_negative_int(values, "OPENAI_MAX_RETRIES", 2)
        prompt_version = values.get("OPENAI_PROMPT_VERSION", DEFAULT_PROMPT_VERSION).strip()
        if not prompt_version:
            raise GatewayConfigurationError("OPENAI_PROMPT_VERSION must not be empty")
        raw_format = values.get("OPENAI_RESPONSE_FORMAT", ResponseFormatMode.JSON_SCHEMA.value)
        try:
            response_format = ResponseFormatMode(raw_format.strip())
        except ValueError as error:
            supported = ", ".join(item.value for item in ResponseFormatMode)
            raise GatewayConfigurationError(
                f"OPENAI_RESPONSE_FORMAT must be one of: {supported}"
            ) from error
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            response_format=response_format,
            prompt_version=prompt_version,
        )


def _load_runtime_environment() -> Mapping[str, str]:
    """Load a local dotenv without replacing values supplied by the runtime or CI."""
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    return os.environ


@dataclass(frozen=True)
class OpenAICompatibleDocumentGenerator:
    """Use a LiteLLM gateway for bounded narrative rewriting over locked facts."""

    settings: OpenAICompatibleSettings
    client: OpenAI
    baseline_generator: DeterministicDocumentGenerator = DeterministicDocumentGenerator()

    @classmethod
    def from_settings(
        cls,
        settings: OpenAICompatibleSettings,
    ) -> OpenAICompatibleDocumentGenerator:
        """Build the SDK client; LiteLLM owns the actual Bedrock model routing."""
        client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )
        return cls(settings=settings, client=client)

    def generate(self, context: PublicationContext) -> PublishedDocument:
        """Generate structured narrative and preserve every locked source fact."""
        baseline = self.baseline_generator.generate(context)
        live_provenance = Provenance(
            source_schema_path=baseline.provenance.source_schema_path,
            source_review_path=baseline.provenance.source_review_path,
            source_review_commit=baseline.provenance.source_review_commit,
            generator_mode=GeneratorMode.LIVE,
            generator_model=self.settings.model,
            prompt_version=self.settings.prompt_version,
        )
        expected = baseline.model_copy(update={"provenance": live_provenance})
        response_model = (
            _ApprovedNarrativeResponse
            if expected.document_status is DocumentStatus.APPROVED
            else _SummaryResponse
        )
        response_name = (
            "approved_metadata_narrative"
            if expected.document_status is DocumentStatus.APPROVED
            else "published_document_summary"
        )
        messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": (
                    f"Prompt version: {self.settings.prompt_version}. Rewrite only the requested "
                    "narrative fields of a validated ClickHouse metadata document. Use only facts "
                    "in the supplied document, preserve uncertainty and restrictions, keep every "
                    "list cardinality and object key unchanged, and do not invent owners, rules, "
                    "joins, units, values, sources, upstream systems, or confidence. Do not "
                    "mention review, approval, preview, publication, indexing, document_status, "
                    "index_eligible, or any metadata workflow state in narrative text. Return JSON."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": (
                            "Rewrite approved narrative fields without changing facts."
                            if expected.document_status is DocumentStatus.APPROVED
                            else "Return a concise self-contained technical and business summary."
                        ),
                        "output_schema": response_model.model_json_schema(),
                        "published_document": _narrative_source(expected),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ]
        try:
            completion = self.client.chat.completions.create(
                model=self.settings.model,
                messages=messages,
                response_format=_response_format(
                    self.settings.response_format,
                    response_name,
                    response_model.model_json_schema(),
                ),
            )
            content = completion.choices[0].message.content if completion.choices else None
            if not content:
                raise DocumentGenerationError("gateway returned no structured narrative content")
            response = response_model.model_validate_json(content)
            _reject_workflow_state_narrative(response)
        except DocumentGenerationError:
            raise
        except APITimeoutError as error:
            raise DocumentGenerationError(
                f"gateway timed out after {self.settings.timeout_seconds:g}s; "
                f"SDK retries are limited to {self.settings.max_retries}"
            ) from error
        except RateLimitError as error:
            raise DocumentGenerationError(
                f"gateway rate limit persisted after {self.settings.max_retries} SDK retries"
            ) from error
        except APIConnectionError as error:
            raise DocumentGenerationError(
                "gateway connection failed after bounded SDK retries"
            ) from error
        except APIStatusError as error:
            raise DocumentGenerationError(
                f"gateway returned HTTP {error.status_code} after bounded SDK retries"
            ) from error
        except (ValidationError, json.JSONDecodeError) as error:
            raise DocumentGenerationError(
                "gateway returned narrative that violates the structured output contract"
            ) from error
        except OpenAIError as error:
            raise DocumentGenerationError("gateway request failed") from error
        if isinstance(response, _ApprovedNarrativeResponse):
            return _apply_approved_narrative(expected, response)
        return PublishedDocument.model_validate(
            expected.model_copy(update={"summary": response.summary}).model_dump()
        )


def _narrative_source(document: PublishedDocument) -> dict[str, object]:
    """Remove pipeline-only lifecycle fields before sending grounded facts to the model."""
    payload = document.model_dump(mode="json")
    payload.pop("document_status")
    payload.pop("index_eligible")
    return payload


def _reject_workflow_state_narrative(
    response: _SummaryResponse | _ApprovedNarrativeResponse,
) -> None:
    """Reject reserved lifecycle terms that would become stale after candidate promotion."""
    reserved_terms = ("needs_review", "needs review", "document_status", "index_eligible")
    for value in _narrative_values(response):
        normalized = value.casefold()
        if any(term in normalized for term in reserved_terms):
            raise DocumentGenerationError(
                "gateway narrative mentions metadata workflow state; regenerate without review or "
                "indexing status"
            )


def _narrative_values(
    response: _SummaryResponse | _ApprovedNarrativeResponse,
) -> tuple[str, ...]:
    if isinstance(response, _SummaryResponse):
        return (response.summary,)
    return (
        response.summary,
        response.description,
        *response.purpose,
        *response.appropriate_use,
        *response.inappropriate_use,
        *response.column_descriptions.values(),
        *response.relationship_meanings.values(),
        *response.rule_descriptions.values(),
    )


def _response_format(
    mode: ResponseFormatMode,
    name: str,
    schema: dict[str, object],
) -> ResponseFormat:
    if mode is ResponseFormatMode.JSON_OBJECT:
        value: ResponseFormatJSONObject = {"type": "json_object"}
        return value
    value_schema: ResponseFormatJSONSchema = {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "description": "Narrative grounded only in validated metadata facts.",
            "schema": schema,
            "strict": True,
        },
    }
    return value_schema


def _apply_approved_narrative(
    baseline: PublishedDocument,
    response: _ApprovedNarrativeResponse,
) -> PublishedDocument:
    _require_same_length("purpose", baseline.purpose, response.purpose)
    _require_same_length("appropriate_use", baseline.appropriate_use, response.appropriate_use)
    _require_same_length(
        "inappropriate_use",
        baseline.inappropriate_use,
        response.inappropriate_use,
    )
    _require_exact_keys(
        "column_descriptions",
        {column.name for column in baseline.columns},
        set(response.column_descriptions),
    )
    _require_exact_keys(
        "relationship_meanings",
        {relationship.name for relationship in baseline.relationships},
        set(response.relationship_meanings),
    )
    _require_exact_keys(
        "rule_descriptions",
        {rule.name for rule in baseline.business_rules},
        set(response.rule_descriptions),
    )
    updated = baseline.model_copy(
        update={
            "summary": response.summary,
            "description": response.description,
            "purpose": response.purpose,
            "appropriate_use": response.appropriate_use,
            "inappropriate_use": response.inappropriate_use,
            "columns": tuple(
                column.model_copy(update={"description": response.column_descriptions[column.name]})
                for column in baseline.columns
            ),
            "relationships": tuple(
                relationship.model_copy(
                    update={"meaning": response.relationship_meanings[relationship.name]}
                )
                for relationship in baseline.relationships
            ),
            "business_rules": tuple(
                rule.model_copy(update={"description": response.rule_descriptions[rule.name]})
                for rule in baseline.business_rules
            ),
        }
    )
    return PublishedDocument.model_validate(updated.model_dump())


def _require_same_length(field: str, expected: tuple[str, ...], actual: tuple[str, ...]) -> None:
    if len(expected) != len(actual):
        raise DocumentGenerationError(
            f"gateway narrative changed {field} cardinality: expected {len(expected)}, "
            f"found {len(actual)}"
        )


def _require_exact_keys(field: str, expected: set[str], actual: set[str]) -> None:
    if expected != actual:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise DocumentGenerationError(
            f"gateway narrative changed {field} keys; missing={missing}, unexpected={unexpected}"
        )


def _positive_float(values: Mapping[str, str], name: str, default: float) -> float:
    try:
        parsed = float(values.get(name, str(default)))
    except ValueError as error:
        raise GatewayConfigurationError(f"{name} must be a number") from error
    if parsed <= 0:
        raise GatewayConfigurationError(f"{name} must be greater than zero")
    return parsed


def _non_negative_int(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        parsed = int(values.get(name, str(default)))
    except ValueError as error:
        raise GatewayConfigurationError(f"{name} must be an integer") from error
    if parsed < 0:
        raise GatewayConfigurationError(f"{name} must be zero or greater")
    return parsed
