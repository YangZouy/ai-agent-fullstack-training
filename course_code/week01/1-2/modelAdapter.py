from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

# 显式区分结果类型：纯文本 结构化数据（JSON） 函数调用 模型拒答
ResultKind = Literal["text", "structured", "tool_calls", "refusal"]

@dataclass(frozen=True)
class ModelCapabilities:
    # 是否支持/v1/chat/completions
    chat_completions: bool
    # 是否支持/v1/responses
    responses: bool
    # 支持哪种层级的结构化输出
    structured_output: Literal["native_schema", "json_mode", "prompt_only"]
    # 是否支持function calling
    tool_calling: bool
    supports_temperature: bool
    supports_top_p: bool

@dataclass(frozen=True)
class ModelRequest:
    system: str
    user: str
    max_output_tokens: int = 1024
    temperature: float | None = None
    top_p: float | None = None
    # 添加到prompt中的schema格式
    output_schema: dict[str, Any] | None = None

@dataclass
class ModelResult:
    kind: ResultKind
    # 模型返回的str
    text: str | None = None
    # 通过json解析后的python字典类型
    data: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # stop：正常结束 length：截断 content_filter:安全策略拦截 tool_calls:工具调用
    finish_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    request_id: str | None = None

class ModelAdapter(ABC):
    name: str
    capabilities: ModelCapabilities

    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResult:
        raise NotImplementedError