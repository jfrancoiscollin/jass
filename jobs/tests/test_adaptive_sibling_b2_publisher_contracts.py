#!/usr/bin/env python3
from __future__ import annotations

import unittest

from jobs.tools import adaptive_sibling_b2_allocation_input as allocation
from jobs.tools import adaptive_sibling_b2_readout as readout
from jobs.tools import adaptive_sibling_b2_teacher_publish as teacher_publish
from jobs.tools import adaptive_sibling_b2_terminal_publish as terminal_publish


class PublisherContractBindingTests(unittest.TestCase):
    def test_teacher_publication_schema_is_exact_downstream_schema(self) -> None:
        self.assertEqual(teacher_publish.PUBLICATION_SCHEMA,
                         allocation.MERGE_PUBLICATION_SCHEMA)

    def test_terminal_publisher_consumes_exact_terminal_schema_and_verdict_map(self) -> None:
        self.assertEqual(readout.TERMINAL_SCHEMA,
                         "jass.adaptive_sibling_b2_terminal_readout.v1")
        self.assertEqual(terminal_publish.ALLOWED_VERDICTS, {
            "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1",
            "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1",
            "B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1",
        })


if __name__ == "__main__":
    unittest.main()
