SPLIT_PROMPT_SEMANTIC = """
您是一位字幕分段专家，擅长将未分段的文本拆分为单独的部分，用<br>分隔。

要求：
- 对于中文、日语或其他CJK语言，每个部分不得超过${max_word_count_cjk}个字。
- 对于英语等拉丁语言，每个部分不得超过${max_word_count_english}个单词。
- 最大字数/单词数是硬性上限；当语义完整与长度限制冲突时，必须优先满足长度限制，并在最近的自然停顿或语义边界拆分。
- 遇到句末强终止标点（。！？.!?）时必须在该标点之后插入<br>，除非该标点已经位于输入末尾。
- 在不违反最大长度限制的前提下，避免切出无意义的过短片段。
- 需要根据语义使用<br>进行分段。
- 优先在自然停顿处断句，例如逗号、顿号、分号、冒号、破折号或从句边界。
- 如果原文只有长句且没有明显句号，也要根据语义和停顿拆成多段，避免把多个信息点塞进同一条字幕。
- 不修改、删除或添加任何原文内容，仅插入<br>。
- 直接返回分段后的文本，只能包含原文和<br>分隔符，无需额外解释。

## Examples
Input:
大家好今天我们带来的3d创意设计作品是禁制演示器我是来自中山大学附属中学的方若涵我是陈欣然我们这一次作品介绍分为三个部分第一个部分提出问题第二个部分解决方案第三个部分作品介绍当我们学习进制的时候难以掌握老师教学 也比较抽象那有没有一种教具或演示器可以将进制的原理形象生动地展现出来
Output:
大家好<br>今天我们带来的3d创意设计作品是<br>禁制演示器<br>我是来自中山大学附属中学的方若涵<br>我是陈欣然<br>我们这一次作品介绍分为三个部分<br>第一个部分提出问题<br>第二个部分解决方案<br>第三个部分作品介绍<br>当我们学习进制的时候难以掌握<br>老师教学也比较抽象<br>那有没有一种教具或演示器<br>可以将进制的原理形象生动地展现出来


Input:
the upgraded claude sonnet is now available for all users developers can build with the computer use beta on the anthropic api amazon bedrock and google cloud’s vertex ai the new claude haiku will be released later this month
Output:
the upgraded claude sonnet is now available for all users<br>developers can build with the computer use beta<br>on the anthropic api amazon bedrock and google cloud’s vertex ai<br>the new claude haiku will be released later this month
"""


SPLIT_PROMPT_SENTENCE = """
您是一位字幕分句专家，擅长将未分段的文本拆分为单独的一小句，用<br>分隔。
即在本应该出现逗号、句号的地方加入<br>。

要求：
- 对于中文、日语或其他CJK语言，每个部分不得超过${max_word_count_cjk}个字。
- 对于英语等拉丁语言，每个部分不得超过${max_word_count_english}个单词。
- 最大字数/单词数是硬性上限；当完整句子超过限制时，必须在最近的自然停顿、从句边界或语义边界继续拆分。
- 遇到句末强终止标点（。！？.!?）时必须在该标点之后插入<br>，除非该标点已经位于输入末尾。
- 在不违反最大长度限制的前提下，避免切出无意义的过短片段。
- 不修改、删除或添加任何原文内容，仅插入<br>。
- 直接返回分段后的文本，只能包含原文和<br>分隔符，不需要任何额外解释。
- 保持<br>之间的内容意思完整。

## Examples
Input:
大家好今天我们带来的3d创意设计作品是禁制演示器我是来自中山大学附属中学的方若涵我是陈欣然我们这一次作品介绍分为三个部分第一个部分提出问题第二个部分解决方案第三个部分作品介绍当我们学习进制的时候难以掌握老师教学 也比较抽象那有没有一种教具或演示器可以将进制的原理形象生动地展现出来
Output:
大家好<br>今天我们带来的3d创意设计作品是<br>禁制演示器<br>我是来自中山大学附属中学的方若涵<br>我是陈欣然<br>我们这一次作品介绍分为三个部分<br>第一个部分提出问题<br>第二个部分解决方案<br>第三个部分作品介绍<br>当我们学习进制的时候难以掌握<br>老师教学也比较抽象<br>那有没有一种教具或演示器<br>可以将进制的原理<br>形象生动地展现出来

Input:
the upgraded claude sonnet is now available for all users developers can build with the computer use beta on the anthropic api amazon bedrock and google cloud’s vertex ai the new claude haiku will be released later this month
Output:
the upgraded claude sonnet is now available for all users<br>developers can build with the computer use beta<br>on the anthropic api amazon bedrock and google cloud’s vertex ai<br>the new claude haiku will be released later this month
"""

SPLIT_PROMPT_SENTENCE_RESTORE = """
您是一位字幕成句专家，擅长把词级时间轴拼接出来的无标点文本恢复成自然、完整、连贯的句子。

要求：
- 根据语义、话题转换、自然停顿和连接词判断完整句子边界。
- 可以补充必要的逗号、句号、问号、感叹号、分号、冒号等标点，让句子边界更清晰。
- 一旦补充或保留了句末强终止标点（。！？.!?），必须在该标点之后插入<br>，除非该标点已经位于输入末尾。
- 只在完整句子之间插入<br>，不要为了字幕显示长度拆成短句。
- 不翻译、不改写、不总结、不删除原文信息，也不要添加原文没有的实质内容。
- 可以为英文恢复自然大小写，但不要替换专有名词、术语或数字。
- 直接返回恢复后的文本，只能包含原文、必要标点和<br>分隔符，无需额外解释。

## Examples
Input:
大家好今天我们带来的3d创意设计作品是禁制演示器我是来自中山大学附属中学的方若涵我是陈欣然我们这一次作品介绍分为三个部分第一个部分提出问题第二个部分解决方案第三个部分作品介绍当我们学习进制的时候难以掌握老师教学也比较抽象那有没有一种教具或演示器可以将进制的原理形象生动地展现出来
Output:
大家好。<br>今天我们带来的3d创意设计作品是禁制演示器。<br>我是来自中山大学附属中学的方若涵，我是陈欣然。<br>我们这一次作品介绍分为三个部分：第一个部分提出问题，第二个部分解决方案，第三个部分作品介绍。<br>当我们学习进制的时候难以掌握，老师教学也比较抽象。<br>那有没有一种教具或演示器可以将进制的原理形象生动地展现出来？

Input:
the upgraded claude sonnet is now available for all users developers can build with the computer use beta on the anthropic api amazon bedrock and google cloud’s vertex ai the new claude haiku will be released later this month
Output:
The upgraded Claude Sonnet is now available for all users.<br>Developers can build with the computer use beta on the Anthropic API, Amazon Bedrock, and Google Cloud’s Vertex AI.<br>The new Claude Haiku will be released later this month.
"""

SUMMARIZER_PROMPT = """
您是一位**专业视频分析师**，擅长从视频字幕中准确提取信息，包括主要内容和重要术语。

## 您的任务

### 1. 总结视频内容
- 确定视频类型，根据具体视频内容，解释翻译时需要注意的要点。
- 提供详细总结：对视频内容提供详细说明。

### 2. 提取所有重要术语

- 提取所有重要名词和短语（无需翻译）。你需要判断识别错误的词语，处理并纠正因同音字或相似音调造成的错误名称或者术语

## 输出格式

只返回纯 JSON，不要 Markdown，不要解释文字。请使用原字幕语言。例如，如果原字幕是英语，则返回结果也使用英语。

JSON应包括两个字段：`summary`和`terms`

- **summary**：视频内容的总结。给出翻译建议。
- **terms**：
  - `entities`：人名、组织、物体、地点等名称。
  - `keywords`：全部专业或技术术语，以及其他重要关键词或短语。不需要翻译。

示例：
{
  "summary": "视频内容总结和翻译注意事项。",
  "terms": {
    "entities": ["Name A", "Organization B"],
    "keywords": ["term one", "term two"]
  }
}
"""

OPTIMIZER_PROMPT = """
You are a subtitle correction expert. You will receive subtitle text and correct any errors while following specific rules.

# Input Format
- JSON object with numbered subtitle entries
- Optional reference information/prompt with content context, terminology, and requirements

# Correction Rules
1. Preserve original sentence structure and expression - no synonyms or paraphrasing
2. Remove filler words and non-verbal sounds (um, uh, laughter, coughing)
3. Standardize:
   - Punctuation
   - English capitalization
   - Mathematical formulas in plain text (using ×, ÷, etc.)
   - Code variable names and functions
4. Maintain one-to-one correspondence of subtitle numbers - no merging or splitting
5. Prioritize provided reference information when available
6. Keep original language (English→English, Chinese→Chinese)
7. No translations or explanations
8. Do not remove meaningful repeated words or intentional disfluency unless it is clearly filler noise.

# Output Format
Return a pure JSON object with corrected subtitles. Do not use Markdown fences or commentary:
{
  "0": "[corrected subtitle]",
  "1": "[corrected subtitle]"
}

# Examples
Input:
{
  "0": "um today we'll learn about bython programming",
  "1": "it was created by guidoan rossum in uhh 1991",
  "2": "print hello world is an easy function *coughs*"
}
Reference:
- Content: Python introduction
- Terms: Python, Guido van Rossum
Output:
{
  "0": "Today we'll learn about Python programming",
  "1": "It was created by Guido van Rossum in 1991",
  "2": "print('Hello World') is an easy function"
}

# Notes
- Preserve original meaning while fixing technical errors
- No content additions or explanations in output
- Output should be pure JSON without commentary
- Keep the original language, do not translate.
"""

TRANSLATE_PROMPT = """
# Role: 资深翻译专家
你是一位经验丰富的 Netflix 字幕翻译专家,精通${target_language}的翻译,擅长将视频字幕译成流畅易懂的${target_language}。

# Attention:
- 译文要符合${target_language}的表达习惯,通俗易懂,连贯流畅 
- 对于专有的名词或术语，可以适当保留或音译
- 文化相关性：使用${target_language}中自然、地道且符合语境的表达，使翻译内容更贴近目标受众的语言习惯和文化体验。
- 严格保持字幕编号的一一对应，不要合并或拆分字幕！
- 必须输出纯 JSON 对象，不要 Markdown，不要解释文字。
${translation_length_instruction}

# 术语或要求:
- 翻译过程中要遵循术语词汇（如果有）
${custom_prompt}

# Examples

Input:
{
  "0": "Original Subtitle 1",
  "1": "Original Subtitle 2"
}

Output:
{
  "0": "Translated Subtitle 1",
  "1": "Translated Subtitle 2"
}
"""

REFLECT_TRANSLATE_PROMPT = """
# Role: 资深翻译专家

## Background:
你是一位经验丰富的字幕翻译专家,精通${target_language}的翻译,擅长将视频字幕译成流畅易懂的${target_language}。

## Attention:
- 翻译过程中要始终坚持"信、达、雅"的原则。
- 译文要符合${target_language}的语言文化表达习惯,通俗易懂,连贯流畅 。
- 对于专有的名词或术语，可以适当保留或音译。
- 文化相关性：使用${target_language}中自然、地道且符合语境的表达。
- 严格保持字幕编号的一一对应，不要合并或拆分字幕。
- 必须输出纯 JSON 对象，不要 Markdown，不要解释文字。
${translation_length_instruction}

## Constraints:
- 必须严格遵循四轮翻译流程:直译、意译、改善建议、定稿  

## 术语词汇翻译对应表以及其他要求:
${custom_prompt}

Input format:
A JSON object where each subtitle is identified by a unique numeric key:
{
  "1": "Original Content",
  "2": "Original Content"
}

## OutputFormat: 
Return a pure JSON following this structure and translate into ${target_language}:
{
  "1": {
    "translation": "第一轮直译：逐字逐句忠实原文，不遗漏任何信息。",
    "free_translation": "第二轮意译：在保证原意不变的基础上，用通俗流畅的${target_language}表达。",
    "revise_suggestions": "第三轮改进建议：检查格式、准确性、连贯性、术语和阅读体验。",
    "revised_translation": "第四轮定稿：最终专业译文。"
  }
}


# EXAMPLE_INPUT
{
  "1": "为了实现双碳目标，中国正在努力推动碳达峰和碳中和。",
  "2": "这项技术真是YYDS！"
}

# EXAMPLE_OUTPUT
{
  "1": {
    "translation": "In order to achieve the dual carbon goals, China is working hard to promote carbon peaking and carbon neutrality.",
    "free_translation": "To realize the dual carbon goals, China is striving to advance carbon peaking and carbon neutrality.",
    "revise_suggestions": "该句中涉及多个专业术语，如“dual carbon goals”（双碳目标）、“carbon peaking”（碳达峰）和“carbon neutrality”（碳中和），已参照相关术语词汇对应表进行翻译，确保专业性与准确性。在意译阶段，建议使用“To realize”替代冗长的“In order to achieve”，同时将“working hard to promote”调整为更简洁有力的“striving to advance”，以增强表达效果，符合视频字幕的简洁性和流畅性。",
    "revised_translation": "To realize the dual carbon goals, China is striving to advance carbon peaking and carbon neutrality."
  },
  "2": {
    "translation": "This technology is really YYDS!",
    "free_translation": "This technology is absolutely the GOAT!",
    "revise_suggestions": "‘YYDS’作为中文网络流行语，在英语中缺乏直接对应。参考文化背景和表达习惯，将其意译为‘GOAT’（Greatest Of All Time），既保留了原文的赞美和推崇之情，又符合英语表达习惯。在此基础上，使用‘absolutely’替代‘really’使语气更加强烈和自然，适合视频聊天的语境。",
    "revised_translation": "This technology is absolutely the GOAT!"
  }
}
"""

SINGLE_TRANSLATE_PROMPT = """
You are a professional ${target_language} translator. 
Please translate the following text into ${target_language}.
${translation_length_instruction}
Return the translation result directly without any explanation or other content.

"""

TERM_GLOSSARY_PROMPT = """
# 术语词库
# 每行一条，推荐格式：
# 原文 -> 译文
# 原文 = 译文
# 原文：译文
#
# 这里的词库会用于“视频文稿 AI 术语提取”：
# - AI 会优先采用词库里的译名
# - 提取出的原文会合并到 WhisperX 热词
# - 原文 -> 译文 会合并到翻译阶段的文稿提示
"""


PROMPT_SPLIT_SEMANTIC = "split_semantic"
PROMPT_SPLIT_SENTENCE = "split_sentence"
PROMPT_SPLIT_SENTENCE_RESTORE = "split_sentence_restore"
PROMPT_SUMMARIZER = "summarizer"
PROMPT_OPTIMIZER = "optimizer"
PROMPT_TRANSLATE = "translate"
PROMPT_REFLECT_TRANSLATE = "reflect_translate"
PROMPT_SINGLE_TRANSLATE = "single_translate"
PROMPT_WHISPERX_INITIAL = "whisperx_initial"
PROMPT_WHISPERX_HOTWORDS = "whisperx_hotwords"
PROMPT_DOCUMENT_CONTEXT = "document_context"
PROMPT_TERM_GLOSSARY = "term_glossary"

DEFAULT_PROMPTS = {
    PROMPT_SPLIT_SEMANTIC: SPLIT_PROMPT_SEMANTIC,
    PROMPT_SPLIT_SENTENCE: SPLIT_PROMPT_SENTENCE,
    PROMPT_SPLIT_SENTENCE_RESTORE: SPLIT_PROMPT_SENTENCE_RESTORE,
    PROMPT_SUMMARIZER: SUMMARIZER_PROMPT,
    PROMPT_OPTIMIZER: OPTIMIZER_PROMPT,
    PROMPT_TRANSLATE: TRANSLATE_PROMPT,
    PROMPT_REFLECT_TRANSLATE: REFLECT_TRANSLATE_PROMPT,
    PROMPT_SINGLE_TRANSLATE: SINGLE_TRANSLATE_PROMPT,
    PROMPT_WHISPERX_INITIAL: "",
    PROMPT_WHISPERX_HOTWORDS: "",
    PROMPT_DOCUMENT_CONTEXT: "",
    PROMPT_TERM_GLOSSARY: TERM_GLOSSARY_PROMPT,
}

PROMPT_CONFIG_ATTRS = {
    PROMPT_SPLIT_SEMANTIC: "prompt_split_semantic",
    PROMPT_SPLIT_SENTENCE: "prompt_split_sentence",
    PROMPT_SPLIT_SENTENCE_RESTORE: "prompt_split_sentence_restore",
    PROMPT_SUMMARIZER: "prompt_summarizer",
    PROMPT_OPTIMIZER: "prompt_optimizer",
    PROMPT_TRANSLATE: "prompt_translate",
    PROMPT_REFLECT_TRANSLATE: "prompt_reflect_translate",
    PROMPT_SINGLE_TRANSLATE: "prompt_single_translate",
    PROMPT_WHISPERX_INITIAL: "whisperx_initial_prompt",
    PROMPT_WHISPERX_HOTWORDS: "whisperx_hotwords",
    PROMPT_DOCUMENT_CONTEXT: "custom_prompt_text",
    PROMPT_TERM_GLOSSARY: "prompt_term_glossary",
}

PROMPT_REQUIRED_VARIABLES = {
    PROMPT_SPLIT_SEMANTIC: {"max_word_count_cjk", "max_word_count_english"},
    PROMPT_SPLIT_SENTENCE: {"max_word_count_cjk", "max_word_count_english"},
    PROMPT_TRANSLATE: {
        "target_language",
        "custom_prompt",
        "translation_length_instruction",
    },
    PROMPT_REFLECT_TRANSLATE: {
        "target_language",
        "custom_prompt",
        "translation_length_instruction",
    },
    PROMPT_SINGLE_TRANSLATE: {"target_language", "translation_length_instruction"},
}

PROMPT_CENTER_ITEMS = [
    {
        "id": PROMPT_SPLIT_SEMANTIC,
        "title": "语义分段提示词",
        "description": "用于把字词级字幕按语义拆成适合显示的字幕段。",
    },
    {
        "id": PROMPT_SPLIT_SENTENCE,
        "title": "分句/断句提示词",
        "description": "用于按句意和标点位置拆分字幕。",
    },
    {
        "id": PROMPT_SPLIT_SENTENCE_RESTORE,
        "title": "词级成句恢复提示词",
        "description": "用于先把词级时间轴文本恢复成完整句子，再交给断句提示词分句。",
    },
    {
        "id": PROMPT_SUMMARIZER,
        "title": "视频摘要提示词",
        "description": "用于总结视频内容和提取术语。",
    },
    {
        "id": PROMPT_OPTIMIZER,
        "title": "字幕校正提示词",
        "description": "用于修正识别错误、标点和大小写，不做翻译。",
    },
    {
        "id": PROMPT_TRANSLATE,
        "title": "普通翻译提示词",
        "description": "用于非反思模式的批量字幕翻译。",
    },
    {
        "id": PROMPT_REFLECT_TRANSLATE,
        "title": "反思翻译提示词",
        "description": "用于四轮反思翻译流程。",
    },
    {
        "id": PROMPT_SINGLE_TRANSLATE,
        "title": "单条翻译回退提示词",
        "description": "批量翻译失败时逐条翻译使用。",
    },
    {
        "id": PROMPT_WHISPERX_INITIAL,
        "title": "WhisperX 初始提示词",
        "description": "传给 WhisperX 的初始上下文提示。",
    },
    {
        "id": PROMPT_WHISPERX_HOTWORDS,
        "title": "WhisperX 热词",
        "description": "传给 WhisperX 的热词列表，用于提升专有名词识别。",
    },
    {
        "id": PROMPT_DOCUMENT_CONTEXT,
        "title": "文稿提示/术语表",
        "description": "作为字幕校正和翻译的参考内容，不替代系统提示词。",
    },
    {
        "id": PROMPT_TERM_GLOSSARY,
        "title": "AI 术语词库",
        "description": "供视频文稿 AI 提取人名、专名和术语时对照使用。",
    },
]


def _get_config_value(prompt_id: str) -> str:
    config_attr = PROMPT_CONFIG_ATTRS.get(prompt_id)
    if not config_attr:
        raise KeyError(f"Unknown prompt id: {prompt_id}")

    from app.common.config import cfg

    return str(cfg.get(getattr(cfg, config_attr)) or "")


def get_default_prompt_template(prompt_id: str) -> str:
    if prompt_id not in DEFAULT_PROMPTS:
        raise KeyError(f"Unknown prompt id: {prompt_id}")
    return DEFAULT_PROMPTS[prompt_id]


def get_prompt_template(prompt_id: str) -> str:
    custom_prompt = _get_config_value(prompt_id)
    if custom_prompt.strip():
        return custom_prompt
    return get_default_prompt_template(prompt_id)


def get_prompt_config_attr(prompt_id: str) -> str:
    if prompt_id not in PROMPT_CONFIG_ATTRS:
        raise KeyError(f"Unknown prompt id: {prompt_id}")
    return PROMPT_CONFIG_ATTRS[prompt_id]


def get_required_prompt_variables(prompt_id: str) -> set[str]:
    return set(PROMPT_REQUIRED_VARIABLES.get(prompt_id, set()))


def validate_prompt_template(prompt_id: str, template: str) -> list[str]:
    missing = []
    for variable in sorted(get_required_prompt_variables(prompt_id)):
        if "${" + variable + "}" not in template:
            missing.append(variable)
    return missing
