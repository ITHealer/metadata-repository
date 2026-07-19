"""Unit tests for the LiteLLM/OpenAI-compatible document adapter."""

import json

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
from metadata_pipeline.ports.document_generator import (
    DocumentGenerationError,
    PublicationContext,
)


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
        with pytest.raises(DocumentGenerationError, match="valid structured summary"):
            OpenAICompatibleDocumentGenerator(settings, client).generate(publication_context)
    finally:
        client.close()
