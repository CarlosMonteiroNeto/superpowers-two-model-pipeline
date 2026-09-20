import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from template_embed import embed_text, embedding_identity, vector_is_compatible


class EmbeddingIdentityTests(unittest.TestCase):
    def test_identity_changes_with_model_or_source_hash(self):
        self.assertNotEqual(embedding_identity("model-a", "hash-a"), embedding_identity("model-b", "hash-a"))
        self.assertNotEqual(embedding_identity("model-a", "hash-a"), embedding_identity("model-a", "hash-b"))

    def test_rejects_stale_mismatched_and_nonfinite_vectors(self):
        identity = embedding_identity("model-a", "hash-a")
        self.assertTrue(vector_is_compatible({"identity": identity, "model": "model-a", "source_hash": "hash-a", "vector": [1.0, 0.0]}, identity))
        self.assertFalse(vector_is_compatible({"identity": embedding_identity("model-b", "hash-a"), "model": "model-b", "source_hash": "hash-a", "vector": [1.0]}, identity))
        self.assertFalse(vector_is_compatible({"identity": identity, "model": "model-a", "source_hash": "hash-a", "vector": [float("nan")]}, identity))
        self.assertFalse(vector_is_compatible({"identity": identity, "model": "model-a", "source_hash": "hash-a", "vector": [0.0, 0.0]}, identity))

    def test_encoder_rejects_zero_and_nonfinite_vectors(self):
        with self.assertRaises(ValueError):
            embed_text("query", encoder=lambda _text: [0.0, 0.0])
        with self.assertRaises(ValueError):
            embed_text("query", encoder=lambda _text: [float("inf")])


if __name__ == "__main__":
    unittest.main()
