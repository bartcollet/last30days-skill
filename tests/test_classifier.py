"""Tests for the domain classifier that hard-gates keyless sources."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import last30days
from last30days import classify_domain, DOMAIN_EXTRA_SOURCES, ALL_EXTRA_SOURCES


class TestClassifyDomain(unittest.TestCase):
    def test_technical(self):
        for topic in ("Claude Code MCP", "AI coding agents", "react server components",
                      "python async", "github actions"):
            self.assertEqual(classify_domain(topic), "TECHNICAL", topic)

    def test_societal(self):
        for topic in ("2026 US election", "stock market crash", "interest rate decision"):
            self.assertEqual(classify_domain(topic), "SOCIETAL", topic)

    def test_person(self):
        for topic in ("Andrej Karpathy", "Sam Altman", "@levelsio"):
            self.assertEqual(classify_domain(topic), "PERSON", topic)

    def test_general_fallback(self):
        for topic in ("best coffee grinder", "longevity supplements"):
            self.assertEqual(classify_domain(topic), "GENERAL", topic)

    def test_empty_is_general(self):
        self.assertEqual(classify_domain(""), "GENERAL")
        self.assertEqual(classify_domain("   "), "GENERAL")


class TestDomainGate(unittest.TestCase):
    def test_technical_runs_hn_github_not_polymarket(self):
        extra = DOMAIN_EXTRA_SOURCES["TECHNICAL"]
        self.assertIn("hackernews", extra)
        self.assertIn("github", extra)
        self.assertNotIn("polymarket", extra)

    def test_societal_runs_polymarket_only(self):
        extra = DOMAIN_EXTRA_SOURCES["SOCIETAL"]
        self.assertEqual(extra, {"polymarket"})

    def test_person_skips_hn(self):
        extra = DOMAIN_EXTRA_SOURCES["PERSON"]
        self.assertNotIn("hackernews", extra)
        self.assertIn("github", extra)
        self.assertIn("polymarket", extra)

    def test_general_runs_all(self):
        self.assertEqual(DOMAIN_EXTRA_SOURCES["GENERAL"], ALL_EXTRA_SOURCES)

    def test_all_extra_sources_complete(self):
        self.assertEqual(ALL_EXTRA_SOURCES, {"hackernews", "github", "polymarket"})


if __name__ == "__main__":
    unittest.main()
