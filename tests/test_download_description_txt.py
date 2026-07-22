import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from app.core.utils.download_description import (
    DEFAULT_DESCRIPTION_TEMPLATE,
    find_unknown_template_variables,
    format_upload_date,
    render_description_txt,
    write_description_txt_file,
)


class DownloadDescriptionTxtTests(unittest.TestCase):
    def test_format_upload_date_converts_yyyymmdd(self):
        self.assertEqual(format_upload_date("20260509"), "2026 年 05 月 09 日")

    def test_render_description_txt_uses_all_metadata(self):
        text = render_description_txt(
            {
                "upload_date": "20260509",
                "title": "示例标题",
                "uploader": "示例作者",
                "uploader_url": "https://example.com/uploader",
                "description": "第一行简介\n第二行简介",
            }
        )

        self.assertEqual(
            text,
            "\n".join(
                [
                    "所有版权归原作者所有",
                    "视频不代表译者观点",
                    "In case of infringement, please contact for deletion.",
                    "字幕使用AI工具辅助翻译加上自己编的",
                    "搬运视频有节选",
                    "",
                    "原视频上传于 2026 年 05 月 09 日",
                    "原视频标题：示例标题",
                    "原作者：示例作者 (https://example.com/uploader)",
                    "原简介：",
                    "第一行简介\n第二行简介",
                ]
            ),
        )

    def test_render_description_txt_omits_missing_homepage_and_description(self):
        text = render_description_txt(
            {
                "upload_date": "",
                "title": "示例标题",
                "channel": "频道作者",
            }
        )

        self.assertIn("原视频上传于 ", text)
        self.assertIn("原作者：频道作者", text)
        self.assertNotIn("频道作者 (", text)
        self.assertTrue(text.endswith("原简介：\n"))

    def test_render_description_txt_supports_custom_template_variables(self):
        text = render_description_txt(
            {
                "upload_date": "20260509",
                "title": "示例标题",
                "uploader": "示例作者",
                "uploader_url": "https://example.com/uploader",
                "description": "简介",
                "webpage_url": "https://example.com/video",
            },
            template=(
                "${title}\n${author}\n${author_url}\n${author_line}\n"
                "${upload_date}\n${video_url}\n${description}"
            ),
        )

        self.assertEqual(
            text,
            "\n".join(
                [
                    "示例标题",
                    "示例作者",
                    "https://example.com/uploader",
                    "示例作者 (https://example.com/uploader)",
                    "2026 年 05 月 09 日",
                    "https://example.com/video",
                    "简介",
                ]
            ),
        )

    def test_empty_template_uses_default_template(self):
        self.assertEqual(
            render_description_txt({"title": "示例标题"}, template=""),
            render_description_txt({"title": "示例标题"}, DEFAULT_DESCRIPTION_TEMPLATE),
        )

    def test_unknown_template_variables_are_rejected(self):
        self.assertEqual(
            find_unknown_template_variables("${title} ${unknown} ${missing}"),
            ["missing", "unknown"],
        )
        with self.assertRaisesRegex(ValueError, "未知变量"):
            render_description_txt({}, "${unknown}")

    def test_write_description_txt_file_writes_utf8_text_in_download_dir(self):
        work_dir = Path("download-dir")
        mocked_open = mock_open()
        with patch.object(Path, "mkdir") as mocked_mkdir, patch(
            "builtins.open", mocked_open
        ):
            path = Path(
                write_description_txt_file(
                    {
                        "title": '标题<>:"/\\|?*',
                        "uploader": "作者",
                        "description": "简介",
                    },
                    work_dir,
                    "video_title",
                )
            )

            self.assertEqual(path.parent, work_dir)
            self.assertEqual(path.name, "video_title.txt")
            mocked_mkdir.assert_called_once_with(parents=True, exist_ok=True)
            mocked_open.assert_called_once_with(path, "w", encoding="utf-8")
            mocked_open().write.assert_called_once()
            written_text = mocked_open().write.call_args.args[0]
            self.assertIn("原视频标题：标题<>:\"/\\|?*", written_text)


if __name__ == "__main__":
    unittest.main()
