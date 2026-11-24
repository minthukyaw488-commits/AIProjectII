"""
Local embedding model.

Primary: sentence-transformers with BAAI/bge-m3 (multilingual, validated in
the prototype). This is the production default and is used automatically
wherever the model can be loaded.

Fallback: a corpus-fitted TF-IDF (character n-gram) vectoriser. It needs no
model download, works offline, and handles Korean reasonably via character
n-grams, so the retrieval demo stays meaningful even where huggingface.co is
unreachable. Both run fully offline at query time - no cloud call ever.
"""
from __future__ import annotations
import os
from typing import List, Sequence

from . import config


class _TfidfEmbedder:
    """Offline fallback: corpus-fitted TF-IDF over character n-grams.

    Must be fit() on the document corpus before encoding queries so that the
    vocabulary and IDF weights are shared between documents and questions.
    """

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        # char_wb n-grams work for Korean without a dedicated tokenizer.
        self._vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                    min_df=1, sublinear_tf=True)
        self._fitted = False

    def fit(self, corpus: Sequence[str]):
        self._vec.fit(corpus)
        self._fitted = True

    def encode(self, texts, **_) -> List[List[float]]:
        single = isinstance(texts, str)
        batch = [texts] if single else list(texts)
        if not self._fitted:          # allow encode-before-fit (fit on the fly)
            self.fit(batch)
        mat = self._vec.transform(batch).toarray()
        vecs = [row.astype(float).tolist() for row in mat]
        return vecs[0] if single else vecs


class EmbeddingModel:
    """Thin wrapper that hides which backend is active."""

    def __init__(self, model_name: str = config.EMBED_MODEL):
        self.model_name = model_name
        self.backend = "fallback-tfidf"
        self._model = None            # TF-IDF is created lazily in fit()
        try:
            from sentence_transformers import SentenceTransformer
            # Force CPU: on Apple Silicon the MPS (Metal) backend crashes with a
            # bus error when called from Streamlit's worker thread. CPU is fast
            # enough for short welfare queries and avoids that entirely.
            # 평가용 대량 임베딩은 EMBED_DEVICE=cuda 로 GPU 사용 가능(서비스 기본값은 cpu 그대로)
            self._model = SentenceTransformer(model_name,
                                              device=os.environ.get("EMBED_DEVICE", "cpu"))
            self.backend = f"sentence-transformers:{model_name}"
        except Exception as exc:  # package missing or model download blocked
            print(f"[embeddings] '{model_name}' unavailable "
                  f"({exc.__class__.__name__}); using offline TF-IDF fallback. "
                  f"Real bge-m3 is used automatically where it can be loaded.")
            self._model = _TfidfEmbedder()

    @property
    def is_neural(self) -> bool:
        return self.backend.startswith("sentence-transformers")

    def fit(self, corpus: Sequence[str]):
        """Prepare the backend on the document corpus (no-op for bge-m3)."""
        if not self.is_neural:
            self._model.fit(corpus)

    def encode(self, texts, normalize: bool = True):
        if self.is_neural:
            return self._model.encode(texts, normalize_embeddings=normalize)
        return self._model.encode(texts)


if __name__ == "__main__":
    m = EmbeddingModel()
    m.fit(["기초연금 신청 방법", "치매안심센터 무료 검진"])
    v = m.encode(["기초연금 어떻게 신청하나요?"])
    print("backend:", m.backend, "| vector dim:", len(v[0]))
