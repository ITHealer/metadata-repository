"""OpenAI-compatible document generator for a LiteLLM model gateway."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from openai import OpenAI, OpenAIError
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.shared_params import ResponseFormatJSONObject, ResponseFormatJSONSchema
from pydantic import Field, ValidationError

from metadata_pipeline.adapters.generator.deterministic import DeterministicDocumentGenerator
from metadata_pipeline.domain.published import GeneratorMode, Provenance, PublishedDocument
from metadata_pipeline.domain.review import StrictModel
from metadata_pipeline.ports.document_generator import (
    DocumentGenerationError,
    PublicationContext,
)

DEFAULT_BASE_URL = "https://ai-gateway.urbox.dev/v1"
DEFAULT_MODEL = "gpt-5.4-nano"


class ResponseFormatMode(str, Enum):
    """Structured-output modes commonly supported by OpenAI-compatible gateways."""

    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"


class GatewayConfigurationError(ValueError):
    """Raised when live generator environment variables are invalid or incomplete."""


class _SummaryResponse(StrictModel):
    """The only narrative field the first live vertical slice may change."""

    summary: str = Field(min_length=1)


@dataclass(frozen=True)
class OpenAICompatibleSettings:
    """Provider-independent settings for a LiteLLM/OpenAI-compatible endpoint."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 60.0
    max_retries: int = 2
    response_format: ResponseFormatMode = ResponseFormatMode.JSON_SCHEMA

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> OpenAICompatibleSettings:
        """Load live settings without logging or persisting the gateway credential."""
        values = os.environ if environ is None else environ
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
        )


@dataclass(frozen=True)
class OpenAICompatibleDocumentGenerator:
    """Use a LiteLLM gateway to rewrite summary text without changing source facts."""

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
        """Generate a validated summary and preserve every deterministic source field."""
        baseline = self.baseline_generator.generate(context)
        live_provenance = Provenance(
            source_schema_path=baseline.provenance.source_schema_path,
            source_review_path=baseline.provenance.source_review_path,
            source_review_commit=baseline.provenance.source_review_commit,
            generator_mode=GeneratorMode.LIVE,
            generator_model=self.settings.model,
        )
        expected = baseline.model_copy(update={"provenance": live_provenance})
        messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": (
                    "Rewrite only the summary of a validated ClickHouse metadata document. "
                    "Use only facts in the supplied document, preserve uncertainty, and do not "
                    "invent owners, rules, joins, units, sources, or upstream systems. Return JSON."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Return a concise self-contained summary.",
                        "output_schema": _SummaryResponse.model_json_schema(),
                        "published_document": expected.model_dump(mode="json"),
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
                response_format=_response_format(self.settings.response_format),
            )
            content = completion.choices[0].message.content if completion.choices else None
            if not content:
                raise DocumentGenerationError("gateway returned no summary content")
            summary = _SummaryResponse.model_validate_json(content)
        except DocumentGenerationError:
            raise
        except (OpenAIError, ValidationError, json.JSONDecodeError) as error:
            raise DocumentGenerationError(
                "gateway failed to return a valid structured summary"
            ) from error
        return PublishedDocument.model_validate(
            expected.model_copy(update={"summary": summary.summary}).model_dump()
        )


def _response_format(mode: ResponseFormatMode) -> ResponseFormat:
    if mode is ResponseFormatMode.JSON_OBJECT:
        value: ResponseFormatJSONObject = {"type": "json_object"}
        return value
    value_schema: ResponseFormatJSONSchema = {
        "type": "json_schema",
        "json_schema": {
            "name": "published_document_summary",
            "description": "A summary grounded only in validated metadata facts.",
            "schema": _SummaryResponse.model_json_schema(),
            "strict": True,
        },
    }
    return value_schema


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
