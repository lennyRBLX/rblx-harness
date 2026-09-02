#!/usr/bin/env python3
"""Reproduce the token-shrink corpus measurements with o200k_base."""

import json
import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HARNESS, "shared", "gates"))
import token_shrink  # noqa: E402


def main():
    try:
        import tiktoken
    except ImportError:
        sys.stderr.write("ENV|tiktoken|install tiktoken==0.9.0 in an isolated eval environment\n")
        return 3
    with open(os.path.join(HERE, "token_shrink_corpus.json"), encoding="utf-8") as handle:
        corpus = json.load(handle)
    encoding = tiktoken.get_encoding(corpus["encoding"])
    saved = 0
    for fixture in corpus["records"]:
        actual = token_shrink.shrink_return(fixture["agent"], fixture["source"])
        before = len(encoding.encode(fixture["source"]))
        after = len(encoding.encode(actual))
        if actual != fixture["expected"] or before != fixture["before_tokens"] or after != fixture["after_tokens"]:
            sys.stderr.write("FAIL|%s|expected output or token count changed\n" % fixture["agent"])
            return 1
        saved += before - after
    sys.stdout.write("PASS|o200k_base|4 roles|%d tokens saved\n" % saved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
