"""Tests for the shared heuristic relevance scorer."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from lib import relevance


class TestTokenOverlapRelevance(unittest.TestCase):
    def test_exact_phrase_scores_high(self):
        score = relevance.token_overlap_relevance("claude code", "Claude Code is great")
        self.assertGreater(score, 0.7)

    def test_no_overlap_scores_zero(self):
        score = relevance.token_overlap_relevance("kubernetes", "a recipe for banana bread")
        self.assertEqual(score, 0.0)

    def test_empty_query_neutral(self):
        self.assertEqual(relevance.token_overlap_relevance("", "anything"), 0.5)
        # Stopword-only query collapses to empty token set -> neutral 0.5
        self.assertEqual(relevance.token_overlap_relevance("the a an", "anything"), 0.5)

    def test_generic_only_match_is_capped(self):
        # If the only overlap is a low-signal token, score stays below the
        # typical relevance threshold (<= 0.24).
        score = relevance.token_overlap_relevance("claude code review", "a generic review of nothing")
        self.assertLessEqual(score, 0.24)

    def test_synonym_expansion(self):
        # "ts" should match "typescript" via the synonym map.
        score = relevance.token_overlap_relevance("ts generics", "typescript generics explained")
        self.assertGreater(score, 0.5)

    def test_low_signal_tokens_constant_present(self):
        self.assertIn("review", relevance.LOW_SIGNAL_QUERY_TOKENS)
        self.assertIn("odds", relevance.LOW_SIGNAL_QUERY_TOKENS)

    def test_prepared_query_equivalence(self):
        pq = relevance.PreparedQuery("claude code")
        a = relevance.token_overlap_relevance(pq, "Claude Code rocks")
        b = relevance.token_overlap_relevance("claude code", "Claude Code rocks")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
