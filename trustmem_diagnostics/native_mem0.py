"""Optional native Mem0 OSS adapter; inference and ranking stay inside Mem0.

Qualified against the locally pinned mem0ai==1.0.11. Importing the core benchmark
does not require these dependencies. Text transport is injected solely for metering.
"""
import json
import os
from pathlib import Path
import threading

_MODEL = None
_MODEL_PATH = None
_LOCK = threading.Lock()


class ClientConfig:
    def __init__(self, client=None, **kwargs):
        self.client = client


class NativeTransport:
    def __init__(self, config):
        self.client = config.client
        self.failures = []

    def generate_response(self, messages, response_format=None, **kwargs):
        try:
            if self.client is None:
                raise RuntimeError("No writer transport is available in this read-only session")
            return self.client(messages)
        except Exception as error:
            self.failures.append(type(error).__name__)
            raise


class Mem0Store:
    """Actual infer=True add, native search, native explicit update and disk reopen."""
    capabilities = frozenset({"add_inferred", "add_raw", "search", "get_all", "update"})

    def __init__(self, directory, embedding_path, client=None):
        global _MODEL, _MODEL_PATH
        os.environ["MEM0_TELEMETRY"] = "False"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from importlib.metadata import version
        if version("mem0ai") != "1.0.11":
            raise RuntimeError("Adapter qualification pins mem0ai==1.0.11; qualify another version explicitly")
        from fastembed import TextEmbedding
        from mem0.configs.base import MemoryConfig
        from mem0.embeddings import fastembed
        from mem0.llms.configs import LlmConfig
        from mem0.memory import main
        from mem0.utils.factory import LlmFactory
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        path = str(Path(embedding_path).resolve())
        if _MODEL is None:
            _MODEL = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", specific_model_path=path,
                local_files_only=True, threads=2, providers=["CPUExecutionProvider"])
            _MODEL_PATH = path
        elif _MODEL_PATH != path:
            raise ValueError("One pinned local embedding model per process")
        class OfflineEmbedding:
            def __init__(self, model_name):
                if model_name != "BAAI/bge-small-en-v1.5":
                    raise ValueError("Unsupported embedding configuration")
            def embed(self, texts):
                with _LOCK:
                    return list(_MODEL.embed(texts))
        fastembed.TextEmbedding = OfflineEmbedding
        provider = "trustmem_metered"
        if provider not in LlmFactory.provider_to_class:
            LlmFactory.register_provider(provider, f"{__name__}.NativeTransport", ClientConfig)
        config = MemoryConfig.model_validate(dict(version="v1.1",
            history_db_path=str(directory / "history.sqlite"),
            llm=dict(provider="langchain", config={}),
            embedder=dict(provider="fastembed", config=dict(model="BAAI/bge-small-en-v1.5", embedding_dims=384)),
            vector_store=dict(provider="qdrant", config=dict(path=str(directory / "qdrant"),
                collection_name="trustmem", embedding_model_dims=384))))
        config.llm = LlmConfig.model_construct(provider=provider, config=dict(client=client))
        if main.MEM0_TELEMETRY:
            raise RuntimeError("Mem0 imported with telemetry enabled")
        self.memory = main.Memory(config)
        self.directory = directory

    def add(self, text, *, infer=True, metadata=None):
        previous = len(self.memory.llm.failures)
        result = self.memory.add([dict(role="user", content=text)], user_id="trustmem-user",
            metadata=metadata, infer=infer)
        # Mem0 can swallow update transport failures; preserve them as failures.
        if len(self.memory.llm.failures) != previous:
            raise RuntimeError("Native writer transport failed; inspect raw metered call log")
        return result

    def search(self, query, limit=5):
        return self.memory.search(query, user_id="trustmem-user", limit=limit)

    def all(self):
        return self.memory.get_all(user_id="trustmem-user", limit=1000)

    def update(self, memory_id, text):
        return self.memory.update(memory_id, data=text)

    def close(self):
        self.memory.vector_store.client.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fresh-process native Mem0 read; no writer client")
    parser.add_argument("--store", required=True)
    parser.add_argument("--embedding-path", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    store = Mem0Store(args.store, args.embedding_path)
    try:
        print(json.dumps(dict(search=store.search(args.query, args.limit), inventory=store.all())))
    finally:
        store.close()


if __name__ == "__main__":
    main()
