"""W4 provider abstraction tests — LlmPort + EmbeddingsPort.

No live network calls required.  Live smoke tests are in
``scripts/dev/verify_w4_providers.py``.

Coverage:
- GeminiLlmAdapter: API-key mode + Vertex AI mode construction and error handling.
- LocalEmbeddingsAdapter: construction, model/dim properties, embed contract.
- Settings: vertex provider literal accepted; new vertex_project / vertex_location fields.
- factory.make_llm: vertex provider path wires GeminiLlmAdapter(vertexai=True).
- factory.make_embeddings: local path wires LocalEmbeddingsAdapter.
- LlmPort / EmbeddingsPort structural compliance.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from intercal_shared.config import Settings
from intercal_shared.ports.embeddings import EmbeddingsError, EmbeddingsPort
from intercal_shared.ports.llm import LlmError, LlmPort, LlmResponse

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _isolated_settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


# ──────────────────────────────────────────────────────────────────────────────
# Settings — new W4 fields
# ──────────────────────────────────────────────────────────────────────────────


class TestSettingsW4:
    def test_vertex_provider_literal_accepted(self) -> None:
        cfg = _isolated_settings(llm_provider="vertex", vertex_project="p")
        assert cfg.llm_provider == "vertex"

    def test_vertex_project_default_empty(self) -> None:
        cfg = _isolated_settings()
        assert cfg.vertex_project == ""

    def test_vertex_location_default(self) -> None:
        cfg = _isolated_settings()
        assert cfg.vertex_location == "us-east4"

    def test_vertex_project_and_location_roundtrip(self) -> None:
        cfg = _isolated_settings(
            llm_provider="vertex",
            vertex_project="my-project",
            vertex_location="us-central1",
        )
        assert cfg.vertex_project == "my-project"
        assert cfg.vertex_location == "us-central1"

    def test_all_llm_providers_accepted(self) -> None:
        for provider in ("vertex", "gemini", "groq", "anthropic", "openai"):
            extra = {"vertex_project": "p"} if provider == "vertex" else {}
            cfg = _isolated_settings(llm_provider=provider, **extra)
            assert cfg.llm_provider == provider


# ──────────────────────────────────────────────────────────────────────────────
# GeminiLlmAdapter — construction
# ──────────────────────────────────────────────────────────────────────────────


class TestGeminiLlmAdapterConstruction:
    def test_api_key_mode_raises_on_empty_key(self) -> None:
        pytest.importorskip("google.genai", reason="google-genai not installed")
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            GeminiLlmAdapter(api_key="", vertexai=False)

    def test_api_key_mode_constructs_with_valid_key(self) -> None:
        """GeminiLlmAdapter in API-key mode should construct without network access."""
        pytest.importorskip("google.genai", reason="google-genai not installed")
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        adapter = GeminiLlmAdapter(api_key="fake-key-for-test", vertexai=False)
        assert adapter.model == "gemini-2.5-flash"

    def test_api_key_mode_custom_model(self) -> None:
        pytest.importorskip("google.genai", reason="google-genai not installed")
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        adapter = GeminiLlmAdapter(api_key="fake-key", model="gemini-2.0-flash", vertexai=False)
        assert adapter.model == "gemini-2.0-flash"

    def test_vertex_mode_raises_on_empty_project(self) -> None:
        pytest.importorskip("google.genai", reason="google-genai not installed")
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        with pytest.raises(ValueError, match="VERTEX_PROJECT"):
            GeminiLlmAdapter(vertexai=True, project="")

    def test_vertex_mode_constructs_with_mocked_sdk(self) -> None:
        """Vertex AI mode should construct without real ADC when the SDK client is mocked."""
        pytest.importorskip("google.genai", reason="google-genai not installed")
        import google.genai as real_genai
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        mock_client = MagicMock()
        with patch.object(real_genai, "Client", return_value=mock_client) as mock_cls:
            adapter = GeminiLlmAdapter(
                vertexai=True,
                project="test-project",
                location="us-east4",
            )
            assert adapter.model == "gemini-2.5-flash"
            mock_cls.assert_called_once_with(
                vertexai=True,
                project="test-project",
                location="us-east4",
            )

    def test_vertex_mode_uses_custom_location(self) -> None:
        pytest.importorskip("google.genai", reason="google-genai not installed")
        import google.genai as real_genai
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        mock_client = MagicMock()
        with patch.object(real_genai, "Client", return_value=mock_client) as mock_cls:
            adapter = GeminiLlmAdapter(
                vertexai=True,
                project="test-project",
                location="us-central1",
                model="gemini-2.0-flash",
            )
            assert adapter.model == "gemini-2.0-flash"
            mock_cls.assert_called_once_with(
                vertexai=True,
                project="test-project",
                location="us-central1",
            )


# ──────────────────────────────────────────────────────────────────────────────
# GeminiLlmAdapter — complete() + extract_structured() via mock
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def gemini_adapter_with_mock_client() -> Any:
    """Return a GeminiLlmAdapter (API-key mode) with a mocked SDK client."""
    pytest.importorskip("google.genai", reason="google-genai not installed")
    import google.genai as real_genai
    from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

    mock_client = MagicMock()
    # Patch genai.types.GenerateContentConfig so the adapter can call it
    def _mock_config(**kw: Any) -> dict[str, Any]:
        return kw

    with (
        patch.object(real_genai, "Client", return_value=mock_client),
        patch.object(real_genai.types, "GenerateContentConfig", _mock_config),
    ):
        adapter = GeminiLlmAdapter(api_key="fake-key", vertexai=False)
        # Expose mock_client for test assertions — private access is intentional in tests.
        adapter._client = mock_client  # type: ignore[misc]
        yield adapter, mock_client


class TestGeminiLlmAdapterComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_llm_response(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        adapter, mock_client = gemini_adapter_with_mock_client
        mock_response = MagicMock()
        mock_response.text = "Hello, world!"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        result = await adapter.complete("Say hello")
        assert isinstance(result, LlmResponse)
        assert result.text == "Hello, world!"
        assert result.model == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_complete_with_system_prompt(self, gemini_adapter_with_mock_client: Any) -> None:
        adapter, mock_client = gemini_adapter_with_mock_client
        mock_response = MagicMock()
        mock_response.text = "Answer"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        result = await adapter.complete("Q", system="You are helpful.")
        assert result.text == "Answer"

    @pytest.mark.asyncio
    async def test_complete_raises_llm_error_on_sdk_failure(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        adapter, mock_client = gemini_adapter_with_mock_client
        mock_client.models.generate_content.side_effect = RuntimeError("network error")

        with pytest.raises(LlmError, match="completion failed"):
            await adapter.complete("test")

    @pytest.mark.asyncio
    async def test_complete_empty_response_text(self, gemini_adapter_with_mock_client: Any) -> None:
        """None response.text should be coerced to empty string, not raise."""
        adapter, mock_client = gemini_adapter_with_mock_client
        mock_response = MagicMock()
        mock_response.text = None
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        result = await adapter.complete("test")
        assert result.text == ""

    @pytest.mark.asyncio
    async def test_complete_surfaces_usage_metadata(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        adapter, mock_client = gemini_adapter_with_mock_client
        mock_response = MagicMock()
        mock_response.text = "reply"
        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 10
        mock_usage.candidates_token_count = 5
        mock_response.usage_metadata = mock_usage
        mock_client.models.generate_content.return_value = mock_response

        result = await adapter.complete("test")
        assert result.input_tokens == 10


class TestGeminiLlmAdapterExtractStructured:
    @pytest.mark.asyncio
    async def test_extract_structured_returns_structured_result(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        from intercal_shared.ports.llm import StructuredResult

        adapter, mock_client = gemini_adapter_with_mock_client
        mock_response = MagicMock()
        mock_response.text = '{"name": "Alice", "age": 30}'
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }
        result = await adapter.extract_structured(schema, "Extract person info from: Alice is 30.")
        assert isinstance(result, StructuredResult)
        assert result.data == {"name": "Alice", "age": 30}
        assert result.model == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_extract_structured_passes_response_schema_to_sdk(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        """Adapter should request native server-side schema enforcement."""
        adapter, mock_client = gemini_adapter_with_mock_client
        mock_response = MagicMock()
        mock_response.text = '{"answer": "yes"}'
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        await adapter.extract_structured(schema, "prompt")
        # The patched GenerateContentConfig returns the kwargs dict; inspect the call.
        _, call_kwargs = mock_client.models.generate_content.call_args
        cfg = call_kwargs["config"]
        assert cfg["response_mime_type"] == "application/json"
        assert cfg["response_schema"] == schema

    @pytest.mark.asyncio
    async def test_extract_structured_validates_against_schema(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        """Valid JSON of the WRONG shape must raise after retries are exhausted."""
        from intercal_shared.ports.llm import LlmExtractionError

        adapter, mock_client = gemini_adapter_with_mock_client
        mock_response = MagicMock()
        # Missing required "age"; "name" wrong type.
        mock_response.text = '{"name": 123}'
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }
        with pytest.raises(LlmExtractionError, match="Schema validation failed"):
            await adapter.extract_structured(schema, "prompt")

    @pytest.mark.asyncio
    async def test_extract_structured_retries_then_succeeds(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        """First attempt malformed, second attempt valid -> succeeds via retry."""
        adapter, mock_client = gemini_adapter_with_mock_client
        bad = MagicMock()
        bad.text = "not json"
        bad.usage_metadata = None
        good = MagicMock()
        good.text = '{"answer": "yes"}'
        good.usage_metadata = None
        mock_client.models.generate_content.side_effect = [bad, good]

        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        result = await adapter.extract_structured(schema, "prompt")
        assert result.data == {"answer": "yes"}
        assert mock_client.models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_structured_raises_extraction_error_on_invalid_json(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        from intercal_shared.ports.llm import LlmExtractionError

        adapter, mock_client = gemini_adapter_with_mock_client
        mock_response = MagicMock()
        mock_response.text = "not json at all"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        with pytest.raises(LlmExtractionError, match="non-JSON"):
            await adapter.extract_structured({}, "prompt")

    @pytest.mark.asyncio
    async def test_extract_structured_raises_llm_error_on_sdk_failure(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        adapter, mock_client = gemini_adapter_with_mock_client
        mock_client.models.generate_content.side_effect = RuntimeError("sdk error")

        with pytest.raises(LlmError, match="extraction failed"):
            await adapter.extract_structured({}, "prompt")


# ──────────────────────────────────────────────────────────────────────────────
# LlmPort structural compliance
# ──────────────────────────────────────────────────────────────────────────────


class TestLlmPortCompliance:
    def test_gemini_adapter_is_llm_port(self) -> None:
        pytest.importorskip("google.genai", reason="google-genai not installed")
        from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

        # isinstance check uses Protocol's runtime_checkable metaclass
        assert isinstance(GeminiLlmAdapter(api_key="fake", vertexai=False), LlmPort)

    def test_groq_adapter_is_llm_port(self) -> None:
        pytest.importorskip("groq", reason="groq not installed")
        from intercal_shared.adapters.llm_groq import GroqLlmAdapter

        assert isinstance(GroqLlmAdapter(api_key="fake"), LlmPort)

    def test_anthropic_adapter_is_llm_port(self) -> None:
        pytest.importorskip("anthropic", reason="anthropic not installed")
        from intercal_shared.adapters.llm_anthropic import AnthropicLlmAdapter

        assert isinstance(AnthropicLlmAdapter(api_key="fake"), LlmPort)

    def test_openai_adapter_is_llm_port(self) -> None:
        pytest.importorskip("openai", reason="openai not installed")
        from intercal_shared.adapters.llm_openai import OpenAILlmAdapter

        assert isinstance(OpenAILlmAdapter(api_key="fake"), LlmPort)


# ──────────────────────────────────────────────────────────────────────────────
# LocalEmbeddingsAdapter — construction + embed contract
# ──────────────────────────────────────────────────────────────────────────────


class TestLocalEmbeddingsAdapter:
    def test_constructs_with_mocked_fastembed(self) -> None:
        """LocalEmbeddingsAdapter should construct with a mocked fastembed model."""
        mock_model = MagicMock()
        mock_fastembed = MagicMock()
        mock_fastembed.TextEmbedding.return_value = mock_model

        with patch.dict("sys.modules", {"fastembed": mock_fastembed}):
            import importlib

            import intercal_shared.adapters.embeddings_local as mod

            importlib.reload(mod)
            adapter = mod.LocalEmbeddingsAdapter(model_name="BAAI/bge-small-en-v1.5", dim=384)
            assert adapter.model == "BAAI/bge-small-en-v1.5"
            assert adapter.dim == 384

    def test_model_property(self) -> None:
        mock_model = MagicMock()
        mock_fastembed = MagicMock()
        mock_fastembed.TextEmbedding.return_value = mock_model

        with patch.dict("sys.modules", {"fastembed": mock_fastembed}):
            import importlib

            import intercal_shared.adapters.embeddings_local as mod

            importlib.reload(mod)
            adapter = mod.LocalEmbeddingsAdapter(model_name="BAAI/bge-base-en-v1.5", dim=768)
            assert adapter.model == "BAAI/bge-base-en-v1.5"
            assert adapter.dim == 768

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self) -> None:
        import numpy as np

        mock_model_instance = MagicMock()
        mock_model_instance.embed.return_value = [
            np.array([0.1, 0.2, 0.3]),
            np.array([0.4, 0.5, 0.6]),
        ]
        mock_fastembed = MagicMock()
        mock_fastembed.TextEmbedding.return_value = mock_model_instance

        with patch.dict("sys.modules", {"fastembed": mock_fastembed}):
            import importlib

            import intercal_shared.adapters.embeddings_local as mod

            importlib.reload(mod)
            # dim=3 matches the 3-element mock vectors (the dim guard enforces this).
            adapter = mod.LocalEmbeddingsAdapter(model_name="BAAI/bge-small-en-v1.5", dim=3)
            result = await adapter.embed(["hello", "world"])
            assert len(result) == 2
            assert result[0] == pytest.approx([0.1, 0.2, 0.3])
            assert result[1] == pytest.approx([0.4, 0.5, 0.6])

    @pytest.mark.asyncio
    async def test_embed_empty_input_returns_empty_list(self) -> None:
        mock_model = MagicMock()
        mock_fastembed = MagicMock()
        mock_fastembed.TextEmbedding.return_value = mock_model

        with patch.dict("sys.modules", {"fastembed": mock_fastembed}):
            import importlib

            import intercal_shared.adapters.embeddings_local as mod

            importlib.reload(mod)
            adapter = mod.LocalEmbeddingsAdapter()
            result = await adapter.embed([])
            assert result == []

    @pytest.mark.asyncio
    async def test_embed_raises_embeddings_error_on_failure(self) -> None:
        mock_model_instance = MagicMock()
        mock_model_instance.embed.side_effect = RuntimeError("ONNX error")
        mock_fastembed = MagicMock()
        mock_fastembed.TextEmbedding.return_value = mock_model_instance

        with patch.dict("sys.modules", {"fastembed": mock_fastembed}):
            import importlib

            import intercal_shared.adapters.embeddings_local as mod

            importlib.reload(mod)
            adapter = mod.LocalEmbeddingsAdapter()
            with pytest.raises(EmbeddingsError, match="Local embeddings failed"):
                await adapter.embed(["test"])

    def test_import_error_raised_when_fastembed_missing(self) -> None:
        with patch.dict("sys.modules", {"fastembed": None}):  # type: ignore[dict-item]
            import importlib

            import intercal_shared.adapters.embeddings_local as mod

            importlib.reload(mod)
            with pytest.raises(ImportError, match="fastembed"):
                mod.LocalEmbeddingsAdapter()


# ──────────────────────────────────────────────────────────────────────────────
# EmbeddingsPort structural compliance
# ──────────────────────────────────────────────────────────────────────────────


class TestEmbeddingsPortCompliance:
    def test_local_adapter_is_embeddings_port(self) -> None:
        pytest.importorskip("fastembed", reason="fastembed not installed")
        from intercal_shared.adapters.embeddings_local import LocalEmbeddingsAdapter

        assert isinstance(LocalEmbeddingsAdapter(), EmbeddingsPort)

    def test_openai_adapter_is_embeddings_port(self) -> None:
        pytest.importorskip("openai", reason="openai not installed")
        from intercal_shared.adapters.embeddings_openai import OpenAIEmbeddingsAdapter

        assert isinstance(OpenAIEmbeddingsAdapter(api_key="fake"), EmbeddingsPort)


# ──────────────────────────────────────────────────────────────────────────────
# OpenAIEmbeddingsAdapter — dimension / vector-space safety
# ──────────────────────────────────────────────────────────────────────────────


def _openai_adapter(monkeypatch: Any, *, create_result: Any = None, **kwargs: Any) -> Any:
    """Build an OpenAIEmbeddingsAdapter with a mocked AsyncOpenAI client.

    ``create_result`` (when given) is the object the mocked ``embeddings.create``
    awaitable resolves to; capture the call kwargs on ``adapter._client._create_call``.
    """
    pytest.importorskip("openai", reason="openai not installed")
    import openai
    from intercal_shared.adapters.embeddings_openai import OpenAIEmbeddingsAdapter

    captured: dict[str, Any] = {}

    async def _create(**call_kwargs: Any) -> Any:
        captured.update(call_kwargs)
        return create_result

    mock_client = MagicMock()
    mock_client.embeddings.create = _create
    with patch.object(openai, "AsyncOpenAI", return_value=mock_client):
        adapter = OpenAIEmbeddingsAdapter(api_key="fake", **kwargs)
    adapter._client = mock_client  # type: ignore[attr-defined]
    adapter._captured = captured  # type: ignore[attr-defined]
    return adapter


class TestOpenAIEmbeddingsDimensions:
    def test_native_dim_resolved_from_model(self) -> None:
        pytest.importorskip("openai", reason="openai not installed")
        from intercal_shared.adapters.embeddings_openai import OpenAIEmbeddingsAdapter

        adapter = OpenAIEmbeddingsAdapter(api_key="fake", model_name="text-embedding-3-small")
        assert adapter.dim == 1536

    def test_custom_dim_on_v3_is_allowed(self) -> None:
        pytest.importorskip("openai", reason="openai not installed")
        from intercal_shared.adapters.embeddings_openai import OpenAIEmbeddingsAdapter

        adapter = OpenAIEmbeddingsAdapter(
            api_key="fake", model_name="text-embedding-3-small", dim=384
        )
        assert adapter.dim == 384

    def test_custom_dim_on_ada_002_rejected(self) -> None:
        pytest.importorskip("openai", reason="openai not installed")
        from intercal_shared.adapters.embeddings_openai import OpenAIEmbeddingsAdapter

        with pytest.raises(ValueError, match="does not support a custom embedding dimension"):
            OpenAIEmbeddingsAdapter(api_key="fake", model_name="text-embedding-ada-002", dim=384)

    def test_custom_dim_larger_than_native_rejected(self) -> None:
        pytest.importorskip("openai", reason="openai not installed")
        from intercal_shared.adapters.embeddings_openai import OpenAIEmbeddingsAdapter

        with pytest.raises(ValueError, match="exceeds the native dimension"):
            OpenAIEmbeddingsAdapter(api_key="fake", model_name="text-embedding-3-small", dim=4096)

    @pytest.mark.asyncio
    async def test_embed_forwards_dimensions_for_custom_dim(self, monkeypatch: Any) -> None:
        result = MagicMock()
        result.data = [MagicMock(embedding=[0.0] * 384)]
        adapter = _openai_adapter(
            monkeypatch, create_result=result, model_name="text-embedding-3-small", dim=384
        )
        await adapter.embed(["hello"])
        assert adapter._captured.get("dimensions") == 384  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_embed_omits_dimensions_for_native_dim(self, monkeypatch: Any) -> None:
        result = MagicMock()
        result.data = [MagicMock(embedding=[0.0] * 1536)]
        adapter = _openai_adapter(
            monkeypatch, create_result=result, model_name="text-embedding-3-small"
        )
        await adapter.embed(["hello"])
        assert "dimensions" not in adapter._captured  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_embed_rejects_dim_mismatch_from_api(self, monkeypatch: Any) -> None:
        # API ignores our request and returns native 1536 while we advertise 384.
        result = MagicMock()
        result.data = [MagicMock(embedding=[0.0] * 1536)]
        adapter = _openai_adapter(
            monkeypatch, create_result=result, model_name="text-embedding-3-small", dim=384
        )
        with pytest.raises(EmbeddingsError, match="configured for dim=384"):
            await adapter.embed(["hello"])


class TestLocalEmbeddingsDimGuard:
    @pytest.mark.asyncio
    async def test_embed_rejects_dim_mismatch(self) -> None:
        import numpy as np

        mock_model_instance = MagicMock()
        # Model yields 768-dim but adapter is configured for 384.
        mock_model_instance.embed.return_value = [np.zeros(768)]
        mock_fastembed = MagicMock()
        mock_fastembed.TextEmbedding.return_value = mock_model_instance

        with patch.dict("sys.modules", {"fastembed": mock_fastembed}):
            import importlib

            import intercal_shared.adapters.embeddings_local as mod

            importlib.reload(mod)
            adapter = mod.LocalEmbeddingsAdapter(model_name="BAAI/bge-small-en-v1.5", dim=384)
            with pytest.raises(EmbeddingsError, match="configured for dim=384"):
                await adapter.embed(["test"])


# ──────────────────────────────────────────────────────────────────────────────
# factory.make_llm — vertex provider path
# ──────────────────────────────────────────────────────────────────────────────


class TestMakeLlmVertexPath:
    def test_make_llm_vertex_raises_on_missing_project(self) -> None:
        """Vertex-without-project is now rejected at Settings construction (validator)."""
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="VERTEX_PROJECT"):
            _isolated_settings(llm_provider="vertex", vertex_project="", gcloud_project_id=None)

    def test_make_llm_vertex_constructs_with_mocked_sdk(self) -> None:
        pytest.importorskip("google.genai", reason="google-genai not installed")
        import google.genai as real_genai
        from intercal_shared.factory import make_llm

        mock_client = MagicMock()
        with patch.object(real_genai, "Client", return_value=mock_client) as mock_cls:
            cfg = _isolated_settings(
                llm_provider="vertex",
                vertex_project="my-gcp-project",
                vertex_location="us-east4",
                llm_model="gemini-2.5-flash",
            )
            from intercal_shared.adapters.llm_gemini import GeminiLlmAdapter

            adapter = make_llm(cfg)
            assert isinstance(adapter, GeminiLlmAdapter)
            assert adapter.model == "gemini-2.5-flash"
            mock_cls.assert_called_once_with(
                vertexai=True,
                project="my-gcp-project",
                location="us-east4",
            )

    def test_make_llm_gemini_raises_on_missing_key(self) -> None:
        pytest.importorskip("google.genai", reason="google-genai not installed")
        from intercal_shared.factory import make_llm

        cfg = _isolated_settings(llm_provider="gemini", gemini_api_key=None)
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            make_llm(cfg)

    def test_make_llm_vertex_uses_configured_location(self) -> None:
        pytest.importorskip("google.genai", reason="google-genai not installed")
        import google.genai as real_genai
        from intercal_shared.factory import make_llm

        mock_client = MagicMock()
        with patch.object(real_genai, "Client", return_value=mock_client) as mock_cls:
            cfg = _isolated_settings(
                llm_provider="vertex",
                vertex_project="proj",
                vertex_location="us-central1",
            )
            make_llm(cfg)
            mock_cls.assert_called_once_with(
                vertexai=True,
                project="proj",
                location="us-central1",
            )

    def test_make_llm_vertex_resolves_project_from_gcloud_project_id(self) -> None:
        pytest.importorskip("google.genai", reason="google-genai not installed")
        import google.genai as real_genai
        from intercal_shared.factory import make_llm

        mock_client = MagicMock()
        with patch.object(real_genai, "Client", return_value=mock_client) as mock_cls:
            cfg = _isolated_settings(
                llm_provider="vertex",
                vertex_project="",
                gcloud_project_id="fallback-proj",
            )
            make_llm(cfg)
            mock_cls.assert_called_once_with(
                vertexai=True,
                project="fallback-proj",
                location="us-east4",
            )


# ──────────────────────────────────────────────────────────────────────────────
# JSON Schema validation (dependency-free subset)
# ──────────────────────────────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_accepts_valid_object(self) -> None:
        from intercal_shared.ports.llm import validate_against_schema

        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        }
        validate_against_schema({"name": "x", "age": 3}, schema)  # no raise

    def test_empty_schema_accepts_anything(self) -> None:
        from intercal_shared.ports.llm import validate_against_schema

        validate_against_schema({"whatever": [1, 2]}, {})

    def test_missing_required_raises(self) -> None:
        from intercal_shared.ports.llm import LlmExtractionError, validate_against_schema

        schema = {"type": "object", "required": ["name"]}
        with pytest.raises(LlmExtractionError, match="missing required property 'name'"):
            validate_against_schema({}, schema)

    def test_wrong_type_raises(self) -> None:
        from intercal_shared.ports.llm import LlmExtractionError, validate_against_schema

        schema = {"type": "object", "properties": {"age": {"type": "integer"}}}
        with pytest.raises(LlmExtractionError, match=r"\$.age"):
            validate_against_schema({"age": "not-an-int"}, schema)

    def test_integer_accepts_integral_float_rejects_bool(self) -> None:
        from intercal_shared.ports.llm import LlmExtractionError, validate_against_schema

        schema = {"type": "integer"}
        validate_against_schema(3.0, schema)  # integral float ok
        with pytest.raises(LlmExtractionError):
            validate_against_schema(True, schema)

    def test_enum_enforced(self) -> None:
        from intercal_shared.ports.llm import LlmExtractionError, validate_against_schema

        schema = {"type": "string", "enum": ["a", "b"]}
        validate_against_schema("a", schema)
        with pytest.raises(LlmExtractionError, match="not in enum"):
            validate_against_schema("c", schema)

    def test_array_items_validated(self) -> None:
        from intercal_shared.ports.llm import LlmExtractionError, validate_against_schema

        schema = {"type": "array", "items": {"type": "integer"}}
        validate_against_schema([1, 2, 3], schema)
        with pytest.raises(LlmExtractionError, match=r"\[1\]"):
            validate_against_schema([1, "x"], schema)

    def test_nullable_type_list(self) -> None:
        from intercal_shared.ports.llm import validate_against_schema

        schema = {"type": ["string", "null"]}
        validate_against_schema(None, schema)
        validate_against_schema("x", schema)


# ──────────────────────────────────────────────────────────────────────────────
# Request budget enforcement
# ──────────────────────────────────────────────────────────────────────────────


class TestRequestBudget:
    def test_consumes_until_limit(self) -> None:
        from intercal_shared.ports.llm import InMemoryRequestBudget, LlmBudgetExceededError

        budget = InMemoryRequestBudget(limit=2)
        budget.check_and_consume()
        budget.check_and_consume()
        assert budget.used == 2
        with pytest.raises(LlmBudgetExceededError, match="budget exhausted"):
            budget.check_and_consume()

    def test_zero_limit_disables_cap(self) -> None:
        from intercal_shared.ports.llm import InMemoryRequestBudget

        budget = InMemoryRequestBudget(limit=0)
        for _ in range(1000):
            budget.check_and_consume()  # never raises

    @pytest.mark.asyncio
    async def test_adapter_consumes_budget_on_complete(
        self, gemini_adapter_with_mock_client: Any
    ) -> None:
        from intercal_shared.ports.llm import InMemoryRequestBudget, LlmBudgetExceededError

        adapter, mock_client = gemini_adapter_with_mock_client
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_response.usage_metadata = None
        mock_client.models.generate_content.return_value = mock_response

        budget = InMemoryRequestBudget(limit=1)
        adapter._budget = budget  # type: ignore[attr-defined]
        await adapter.complete("hi")
        assert budget.used == 1
        with pytest.raises(LlmBudgetExceededError):
            await adapter.complete("again")


# ──────────────────────────────────────────────────────────────────────────────
# Error taxonomy classification
# ──────────────────────────────────────────────────────────────────────────────


class TestErrorTaxonomy:
    @pytest.mark.asyncio
    async def test_rate_limit_classified(self, gemini_adapter_with_mock_client: Any) -> None:
        from intercal_shared.ports.llm import LlmRateLimitError

        adapter, mock_client = gemini_adapter_with_mock_client
        mock_client.models.generate_content.side_effect = RuntimeError("429 quota exceeded")
        with pytest.raises(LlmRateLimitError):
            await adapter.complete("x")

    @pytest.mark.asyncio
    async def test_auth_classified(self, gemini_adapter_with_mock_client: Any) -> None:
        from intercal_shared.ports.llm import LlmAuthError

        adapter, mock_client = gemini_adapter_with_mock_client
        mock_client.models.generate_content.side_effect = RuntimeError("401 invalid api key")
        with pytest.raises(LlmAuthError):
            await adapter.complete("x")

    def test_error_hierarchy(self) -> None:
        from intercal_shared.ports.llm import (
            LlmAuthError,
            LlmBudgetExceededError,
            LlmError,
            LlmExtractionError,
            LlmRateLimitError,
            LlmTimeoutError,
        )

        for cls in (
            LlmAuthError,
            LlmRateLimitError,
            LlmTimeoutError,
            LlmBudgetExceededError,
            LlmExtractionError,
        ):
            assert issubclass(cls, LlmError)


# ──────────────────────────────────────────────────────────────────────────────
# Config provider-mode validation
# ──────────────────────────────────────────────────────────────────────────────


class TestConfigValidation:
    def test_vertex_without_project_raises(self) -> None:
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="VERTEX_PROJECT"):
            _isolated_settings(llm_provider="vertex", vertex_project="", gcloud_project_id=None)

    def test_vertex_with_gcloud_project_id_ok(self) -> None:
        cfg = _isolated_settings(
            llm_provider="vertex", vertex_project="", gcloud_project_id="p"
        )
        assert cfg.resolved_vertex_project == "p"

    def test_zero_embeddings_dim_raises(self) -> None:
        import pydantic

        with pytest.raises(pydantic.ValidationError, match="EMBEDDINGS_DIM"):
            _isolated_settings(embeddings_dim=0)

    def test_resolved_adc_prefers_application_credentials(self) -> None:
        cfg = _isolated_settings(
            google_application_credentials="/a.json",
            google_service_account_key="/b.json",
        )
        assert cfg.resolved_adc_credentials == "/a.json"

    def test_resolved_adc_falls_back_to_sa_key(self) -> None:
        cfg = _isolated_settings(google_service_account_key="/b.json")
        assert cfg.resolved_adc_credentials == "/b.json"

    def test_llm_timeout_default(self) -> None:
        cfg = _isolated_settings()
        assert cfg.llm_timeout_seconds == 60.0
