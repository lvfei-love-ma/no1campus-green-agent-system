"""Agent 构建：知识库检索工具 + 当前会话的有限短期记忆。"""

from __future__ import annotations

from tools.vector_retrieve_tools import vector_retrieve

BASE_PROMPT = """你是“绿知助手”，一个面向大学生的绿色校园与低碳生活知识问答助手。

## 回答要求
- 先调用知识库检索工具，再基于检索到的资料回答；资料没有覆盖的问题，直接说明
  “知识库暂时没有找到足够信息”，并给出不涉及具体政策条款或精确数字的通用建议。
- 不要编造政策名称、文号、数据、机构表态或来源链接。引用资料时使用工具返回的
  标题与来源名称，不要自造来源。
- 回答中的具体数值（温度、比例、天数、金额、标准编号等）只能来自检索到的资料；
  资料没写就不要补充行业常见说法，也不要凭经验估算。
- 回答面向日常校园生活，具体、可执行、语气积极，优先给 2–4 条能马上做到的建议。
- 使用简洁的中文 Markdown（短段落、必要时用列表），不要输出与问题无关的寒暄。

## 工具使用规则
- 拿到问题直接调用检索工具；需要比较多个子主题时，可以多次检索。
- 调用工具时不要输出“我来检索一下”这类过程性文字。
- 工具返回空结果或报错时，如实说明知识库暂时没有足够资料。
"""

MEMORY_HEADER = """
## 当前会话的最近对话（仅供理解指代与追问，不是知识库证据）
"""


def build_system_prompt(memory_text: str = "") -> str:
    prompt = BASE_PROMPT
    if memory_text:
        prompt += MEMORY_HEADER + memory_text + "\n"
        prompt += "如果本轮问题依赖上文，请结合上述对话理解；但事实性结论仍须来自知识库检索结果。\n"
    return prompt


def build_agent(memory_text: str = ""):
    from langchain.agents import create_agent

    from models.llm import get_llm

    return create_agent(
        get_llm(),
        tools=[vector_retrieve],
        system_prompt=build_system_prompt(memory_text),
    )
