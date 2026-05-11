import re
from pathlib import Path


def format_upload_date(upload_date) -> str:
    value = str(upload_date or "").strip()
    if not value:
        return ""
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]} 年 {value[4:6]} 月 {value[6:8]} 日"
    return value


def render_description_txt(info_dict: dict) -> str:
    title = str(info_dict.get("title") or "")
    author = str(info_dict.get("uploader") or info_dict.get("channel") or "")
    homepage = str(info_dict.get("uploader_url") or info_dict.get("channel_url") or "")
    author_text = f"{author} ({homepage})" if homepage else author
    description = str(info_dict.get("description") or "")
    upload_date = format_upload_date(info_dict.get("upload_date"))

    return "\n".join(
        [
            "所有版权归原作者所有",
            "视频不代表译者观点",
            "In case of infringement, please contact for deletion.",
            "字幕使用AI工具辅助翻译加上自己编的",
            "搬运视频有节选",
            "",
            f"原视频上传于 {upload_date}",
            f"原视频标题：{title}",
            f"原作者：{author_text}",
            "原简介：",
            description,
        ]
    )


def write_description_txt_file(
    info_dict: dict, work_dir: Path, filename_stem: str
) -> str:
    description_path = work_dir / f"{filename_stem}.txt"
    work_dir.mkdir(parents=True, exist_ok=True)
    with open(description_path, "w", encoding="utf-8") as file:
        file.write(render_description_txt(info_dict))
    return str(description_path)
