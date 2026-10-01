"""Optional injectable embedding helpers backed by shared asset contracts."""
import sys
from pathlib import Path

SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "two-model-sdd-pipeline" / "scripts"
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))
from asset_recall import embedding_identity, is_valid_vector, embed_text, vector_is_compatible


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
