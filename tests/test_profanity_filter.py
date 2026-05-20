import unittest

from app.core.utils.profanity_filter import mask_english_profanity


class ProfanityFilterTests(unittest.TestCase):
    def test_masks_root_word(self):
        self.assertEqual(mask_english_profanity("Fuck!"), "[ _ ]!")

    def test_preserves_common_suffix(self):
        self.assertEqual(mask_english_profanity("Fucking great"), "[ _ ]ing great")

    def test_masks_multiple_words_case_insensitive(self):
        self.assertEqual(
            mask_english_profanity("shit, BITCHES and fuckers"),
            "[ _ ], [ _ ]ES and [ _ ]ers",
        )

    def test_does_not_mask_inside_regular_words(self):
        self.assertEqual(mask_english_profanity("firetruck"), "firetruck")


if __name__ == "__main__":
    unittest.main()
