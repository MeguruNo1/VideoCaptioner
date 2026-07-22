import re
from pathlib import Path


DEFAULT_DESCRIPTION_TEMPLATE = """所有版权归原作者所有
视频不代表译者观点
In case of infringement, please contact for deletion.
字幕使用AI工具辅助翻译加上自己编的
搬运视频有节选

原视频上传于 ${upload_date}
原视频标题：${title}
原作者：${author_line}
原简介：
${description}"""

DESCRIPTION_TEMPLATE_VARIABLES = {
    "upload_date": "格式化后的上传日期",
    "title": "原视频标题",
    "author": "原作者或频道名称",
    "author_url": "原作者或频道主页链接",
    "author_line": "原作者名称及主页链接",
    "description": "原视频简介",
    "video_url": "原视频链接",
}

_TEMPLATE_VARIABLE_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def format_upload_date(upload_date) -> str:
    value = str(upload_date or "").strip()
    if not value:
        return ""
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]} 年 {value[4:6]} 月 {value[6:8]} 日"
    return value


def find_unknown_template_variables(template: str) -> list[str]:
    variables = set(_TEMPLATE_VARIABLE_PATTERN.findall(str(template or "")))
    return sorted(variables - DESCRIPTION_TEMPLATE_VARIABLES.keys())


def render_description_txt(info_dict: dict, template: str | None = None) -> str:
    title = str(info_dict.get("title") or "")
    author = str(info_dict.get("uploader") or info_dict.get("channel") or "")
    homepage = str(info_dict.get("uploader_url") or info_dict.get("channel_url") or "")
    author_line = f"{author} ({homepage})" if homepage else author
    description = str(info_dict.get("description") or "")
    upload_date = format_upload_date(info_dict.get("upload_date"))
    video_url = str(
        info_dict.get("webpage_url")
        or info_dict.get("original_url")
        or info_dict.get("url")
        or ""
    )

    custom_template = str(template or "")
    effective_template = (
        custom_template if custom_template.strip() else DEFAULT_DESCRIPTION_TEMPLATE
    )
    unknown_variables = find_unknown_template_variables(effective_template)
    if unknown_variables:
        names = ", ".join(f"${{{name}}}" for name in unknown_variables)
        raise ValueError(f"视频信息文本模板包含未知变量: {names}")

    values = {
        "upload_date": upload_date,
        "title": title,
        "author": author,
        "author_url": homepage,
        "author_line": author_line,
        "description": description,
        "video_url": video_url,
    }
    return _TEMPLATE_VARIABLE_PATTERN.sub(
        lambda match: values[match.group(1)], effective_template
    )


def write_description_txt_file(
    info_dict: dict,
    work_dir: Path,
    filename_stem: str,
    template: str | None = None,
) -> str:
    description_path = work_dir / f"{filename_stem}.txt"
    work_dir.mkdir(parents=True, exist_ok=True)
    with open(description_path, "w", encoding="utf-8") as file:
        file.write(render_description_txt(info_dict, template=template))
    return str(description_path)
