"""Unit tests for the LiteLLM/OpenAI-compatible document adapter."""

import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from metadata_pipeline.adapters.generator.openai_compatible import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    GatewayConfigurationError,
    OpenAICompatibleDocumentGenerator,
    OpenAICompatibleSettings,
    ResponseFormatMode,
)
from metadata_pipeline.domain.published import GeneratorMode
from metadata_pipeline.domain.review import DocumentStatus
from metadata_pipeline.ports.document_generator import (
    DocumentGenerationError,
    PublicationContext,
)
from metadata_pipeline.validation.published import validate_published_document


def test_settings_use_gateway_defaults_and_allow_model_override() -> None:
    defaults = OpenAICompatibleSettings.from_env({"OPENAI_API_KEY": "gateway-test-key"})
    assert defaults.base_url == DEFAULT_BASE_URL
    assert defaults.model == DEFAULT_MODEL
    assert defaults.response_format is ResponseFormatMode.JSON_SCHEMA

    override = OpenAICompatibleSettings.from_env(
        {
            "OPENAI_API_KEY": "gateway-test-key",
            "OPENAI_MODEL": "bedrock/another-model-alias",
            "OPENAI_RESPONSE_FORMAT": "json_object",
        }
    )
    assert override.model == "bedrock/another-model-alias"
    assert override.response_format is ResponseFormatMode.JSON_OBJECT


def test_settings_reject_missing_key_without_exposing_a_secret() -> None:
    with pytest.raises(GatewayConfigurationError, match="OPENAI_API_KEY is required"):
        OpenAICompatibleSettings.from_env({"OPENAI_API_KEY": ""})


def test_settings_load_local_dotenv_without_overriding_exported_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=dotenv-test-key\nOPENAI_BASE_URL=https://dotenv-gateway.test/v1\n",
        encoding="utf-8",
    )

    dotenv_settings = OpenAICompatibleSettings.from_env()

    assert dotenv_settings.api_key == "dotenv-test-key"
    assert dotenv_settings.base_url == "https://dotenv-gateway.test/v1"

    monkeypatch.setenv("OPENAI_API_KEY", "exported-test-key")
    exported_settings = OpenAICompatibleSettings.from_env()

    assert exported_settings.api_key == "exported-test-key"


@pytest.mark.parametrize("response_format", ["json_schema", "json_object"])
def test_gateway_generates_only_summary_through_chat_completions(
    publication_context: PublicationContext,
    response_format: str,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-5.4-nano",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"summary": "Orders support lifecycle analysis at order grain."}
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    settings = OpenAICompatibleSettings.from_env(
        {
            "OPENAI_API_KEY": "gateway-test-key",
            "OPENAI_RESPONSE_FORMAT": response_format,
        }
    )
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        max_retries=0,
        http_client=http_client,
    )
    try:
        document = OpenAICompatibleDocumentGenerator(settings, client).generate(publication_context)
    finally:
        client.close()

    body = captured["body"]
    assert isinstance(body, dict)
    assert captured["path"] == "/v1/chat/completions"
    assert captured["authorization"] == "Bearer gateway-test-key"
    assert body["model"] == "gpt-5.4-nano"
    assert body["response_format"]["type"] == response_format
    assert document.summary == "Orders support lifecycle analysis at order grain."
    assert document.provenance.generator_mode is GeneratorMode.LIVE
    assert document.provenance.generator_model == "gpt-5.4-nano"
    assert document.provenance.prompt_version == "approved-narrative-v1"
    total_amount = next(column for column in document.columns if column.name == "total_amount")
    assert total_amount.unit == "VND"


def test_gateway_rejects_invalid_structured_response(
    publication_context: PublicationContext,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-5.4-nano",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "not-json"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    settings = OpenAICompatibleSettings(api_key="gateway-test-key", max_retries=0)
    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(DocumentGenerationError, match="structured output contract"):
            OpenAICompatibleDocumentGenerator(settings, client).generate(publication_context)
    finally:
        client.close()


def test_approved_document_rewrites_full_narrative_but_locks_facts(
    publication_context: PublicationContext,
) -> None:
    approved_review = publication_context.review.model_copy(
        update={
            "owner": "commerce-owner",
            "reviewer": "analytics-reviewer",
            "document_status": DocumentStatus.APPROVED,
        }
    )
    approved_context = PublicationContext(
        schema=publication_context.schema,
        table=publication_context.table,
        review=approved_review,
        source_schema_path=publication_context.source_schema_path,
        source_review_path=publication_context.source_review_path,
        source_review_commit=publication_context.source_review_commit,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-approved",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-5.4-nano",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "summary": "Each row represents one reviewed order.",
                                    "description": "Reviewed order facts for lifecycle analysis.",
                                    "purpose": [
                                        f"Rewritten purpose {index}."
                                        for index, _ in enumerate(
                                            approved_context.review.business.purpose,
                                            start=1,
                                        )
                                    ],
                                    "appropriate_use": [
                                        f"Rewritten appropriate use {index}."
                                        for index, _ in enumerate(
                                            approved_context.review.business.appropriate_use,
                                            start=1,
                                        )
                                    ],
                                    "inappropriate_use": [
                                        f"Rewritten inappropriate use {index}."
                                        for index, _ in enumerate(
                                            approved_context.review.business.inappropriate_use,
                                            start=1,
                                        )
                                    ],
                                    "column_descriptions": {
                                        "created_at": "UTC creation timestamp for the order.",
                                        "customer_id": (
                                            "Customer identifier used by the logical join."
                                        ),
                                        "order_id": "Stable identifier for one order.",
                                        "order_status": "Current recorded lifecycle status.",
                                        "total_amount": "Order total in VND after discounts.",
                                        "updated_at": "UTC timestamp of the latest update.",
                                    },
                                    "relationship_meanings": {
                                        "orders_to_customers": "Links each order to its customer."
                                    },
                                    "rule_descriptions": {
                                        "Cancelled orders remain present": (
                                            "Cancelled status does not delete the row."
                                        )
                                    },
                                }
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    settings = OpenAICompatibleSettings(api_key="gateway-test-key", max_retries=0)
    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        document = OpenAICompatibleDocumentGenerator(settings, client).generate(approved_context)
    finally:
        client.close()

    assert document.summary == "Each row represents one reviewed order."
    assert document.columns[0].description != (
        approved_context.review.columns["created_at"].description
    )
    total_amount = next(column for column in document.columns if column.name == "total_amount")
    assert total_amount.data_type == "Decimal(18, 2)"
    assert total_amount.unit == "VND"
    assert document.relationships[0].join_condition == (
        "orders.customer_id = customers.customer_id"
    )
    assert document.relationships[0].cardinality.value == "many_to_one"
    assert not validate_published_document(
        approved_context,
        document,
        Path("catalog/commerce_demo/generated/published/orders.md"),
    )


def test_structured_contract_failure_is_not_retried(
    publication_context: PublicationContext,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-invalid",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-5.4-nano",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "{}"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    settings = OpenAICompatibleSettings(api_key="gateway-test-key", max_retries=2)
    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        max_retries=2,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(DocumentGenerationError, match="structured output contract"):
            OpenAICompatibleDocumentGenerator(settings, client).generate(publication_context)
    finally:
        client.close()
    assert calls == 1


def test_rate_limit_uses_bounded_sdk_retry_and_actionable_error(
    publication_context: PublicationContext,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={"retry-after": "0"},
            json={"error": {"message": "limited", "type": "rate_limit_error"}},
        )

    settings = OpenAICompatibleSettings(api_key="gateway-test-key", max_retries=1)
    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        max_retries=1,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(DocumentGenerationError, match="rate limit persisted after 1"):
            OpenAICompatibleDocumentGenerator(settings, client).generate(publication_context)
    finally:
        client.close()
    assert calls == 2
