"""Optional injectable embedding helpers."""
import hashlib
import math

def embedding_identity(model, source_hash):
    if not isinstance(model, str) or not model or not isinstance(source_hash, str) or not source_hash:
        raise ValueError("model and source_hash are required")
    return hashlib.sha256((model + "\0" + source_hash).encode()).hexdigest()


def is_valid_vector(vector):
    """Return whether *vector* is a finite, non-zero numeric vector.

    Embedding records cross a JSON/process boundary, so accepting a value that
    merely looks iterable is unsafe.  In particular, NaN, infinity, an empty
    vector, and a zero vector make cosine ranking undefined.
    """
    if not isinstance(vector, list) or not vector:
        return False
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in vector):
        return False
    return any(value != 0 for value in vector)

def embed_text(text, encoder=None):
    if not isinstance(text, str): raise ValueError("text must be a string")
    if encoder is None: raise RuntimeError("embedding encoder is unavailable")
    vector = encoder(text)
    if not isinstance(vector, (list, tuple)) or not vector or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector) or not any(x != 0 for x in vector):
        raise ValueError("encoder returned an invalid vector")
    return [float(x) for x in vector]


def vector_is_compatible(record, identity=None, *, model=None, source_hash=None, dimension=None):
    """Validate a stored vector and its deterministic content identity.

    ``identity`` is retained as a compatibility argument for callers that
    already derive it.  When model/source data is available, the value is
    always recomputed; an arbitrary caller supplied identity cannot make a
    record valid.
    """
    if not isinstance(record, dict):
        return False
    vector = record.get("vector")
    if not is_valid_vector(vector):
        return False
    if dimension is not None and len(vector) != dimension:
        return False
    record_model = record.get("model")
    record_source_hash = record.get("source_hash")
    if not isinstance(record_model, str) or not record_model or not isinstance(record_source_hash, str) or not record_source_hash:
        return False
    if model is not None and record_model != model:
        return False
    if source_hash is not None and record_source_hash != source_hash:
        return False
    expected = embedding_identity(record_model, record_source_hash)
    return record.get("identity") == expected and (identity is None or identity == expected)


def main(argv=None):
    """Validate and print an injected embedding record without network I/O.

    Model execution belongs to the caller and can be supplied through
    ``embed_text`` with an injected encoder. This CLI only materializes a
    deterministic record once the vector and source identity are explicit.
    """
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Validate an injected template embedding")
    parser.add_argument("--model", required=True)
    parser.add_argument("--source-hash", required=True)
    parser.add_argument("--vector", required=True, help="JSON numeric vector")
    args = parser.parse_args(argv)
    try:
        vector = json.loads(args.vector)
        if not is_valid_vector(vector):
            raise ValueError("vector must be a finite, non-zero JSON list")
        record = {
            "model": args.model,
            "source_hash": args.source_hash,
            "identity": embedding_identity(args.model, args.source_hash),
            "vector": vector,
        }
        print(json.dumps(record, ensure_ascii=False, allow_nan=False))
        return 0
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        print("template-embed: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
