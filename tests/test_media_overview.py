"""Regression tests for external media synopsis formatting."""

import unittest

from bulkrr_text import clean_media_overview


class MediaOverviewTests(unittest.TestCase):
    def test_plain_text_unchanged(self):
        self.assertEqual(clean_media_overview("A detective investigates."), "A detective investigates.")

    def test_html_breaks_and_entities(self):
        self.assertEqual(clean_media_overview("Part one&lt;br&gt;Part two &amp; three"), "Part one\nPart two & three")

    def test_paragraph_markup(self):
        self.assertEqual(clean_media_overview("<p>First</p><p>Second</p>"), "First\nSecond")

    def test_missing_description(self):
        self.assertEqual(clean_media_overview(None), "No synopsis available.")

    def test_nested_entities_and_spacing(self):
        self.assertEqual(clean_media_overview("One &amp; two&lt;br&gt;Three"), "One & two\nThree")

    def test_discards_style_contents(self):
        self.assertEqual(clean_media_overview("<style>body{color:red}</style>Story"), "Story")

    def test_strips_untrusted_markup(self):
        self.assertEqual(clean_media_overview("<b>Action</b> <script>ignored</script>"), "Action")


if __name__ == "__main__":
    unittest.main()
