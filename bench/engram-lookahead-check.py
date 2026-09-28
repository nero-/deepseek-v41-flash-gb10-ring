#!/usr/bin/env python3
"""Check lookahead addresses against the upstream CPU integer oracle."""
import json
import numpy as np
from b12x.sequence.engram.geometry import build_geometry
from b12x.sequence.engram.reference import hash_reference
from dsv41_engram_readahead import hash_prompt_rows

geometry = build_geometry()
token_map = list(range(geometry.compressed_vocab_size))
rng = np.random.default_rng(413)
tokens = rng.integers(0, len(token_map), 1031).tolist()
compressed = np.asarray(tokens, dtype=np.int64)
checks = 0
for i, layer in enumerate(geometry.layer_ids):
    expected = hash_reference(tokens, [True] * len(tokens), [0, len(tokens)], [0],
                              [[-1, -1, -1]], token_map, geometry, layer).numpy()
    for begin, end in ((0, 1), (0, 7), (1, 14), (2, 38), (3, 33), (31, 1031), (1000, 1031)):
        actual = hash_prompt_rows(compressed, begin, end, geometry, i, token_map[2])
        assert np.array_equal(actual, expected[begin:end]), (layer, begin, end)
        checks += actual.size
print(json.dumps({"status": "PASS", "exact_hash_addresses": checks, "cases": 14}))
