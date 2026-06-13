import types
import unittest
from unittest.mock import patch

from app.core.subtitle_processor.optimize import SubtitleOptimizer


class SubtitleOptimizerPromptTests(unittest.TestCase):
    def test_optimizer_filters_document_prompt_in_correction_mode(self):
        optimizer = object.__new__(SubtitleOptimizer)
        optimizer.model = "test-model"
        optimizer.temperature = 0.3
        optimizer.timeout = 30
        optimizer.use_cache = False
        optimizer.custom_prompt = "prompt terms"
        optimizer.batch_context_enabled = False
        optimizer.batch_context_max_chars = 0
        optimizer.usage_callback = None
        optimizer.client = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda **_: types.SimpleNamespace(
                        choices=[
                            types.SimpleNamespace(
                                message=types.SimpleNamespace(
                                    content='{"1": "Yixuan arrives"}'
                                )
                            )
                        ]
                    )
                )
            )
        )

        with patch(
            "app.core.subtitle_processor.optimize.filter_document_prompt_for_text",
            return_value="candidate terms",
        ) as filter_prompt:
            result = optimizer._optimize_chunk({"1": "Yee Xuan arrives"})

        filter_prompt.assert_called_once_with(
            "prompt terms",
            "Yee Xuan arrives",
            mode="correction",
        )
        self.assertEqual(result, {"1": "Yixuan arrives"})


if __name__ == "__main__":
    unittest.main()
