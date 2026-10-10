"""远程瑞幸咖啡 MCP Host：结合 mcp_client + mcp_host，调真实数据。

把 week01/1-8 的模型适配器（OpenAICompatibleProvider）扩展出工具调用能力，
驱动 Agent Loop 调用远程瑞幸 MCP Server（Streamable HTTP）提供的工具
（searchProductForMcp / switchProduct / queryProductDetailInfo / queryShopList ...），
最终返回瑞幸真实门店、商品、价格数据。

# 运行前需要：
#     1. 在 https://open.lkcoffee.com 登录，复制 Token 设置环境变量 LUCKIN_MCP_TOKEN
#     2. 需要一个 OpenAI-compatible 模型密钥，如 DEEPSEEK_API_KEY（复用 week01 的 ModelConfig）
# 注意：瑞幸 MCP 端点除了 Authorization Bearer，还会做 CSRF 校验
#     （未带 CSRF 会返回 403 "missing csrf token"），本模块会自动完成 CSRF 握手。

用法：
    $env:LUCKIN_MCP_TOKEN="<你的Token>"
    $env:DEEPSEEK_API_KEY="<你的密钥>"
    python mcp_host_luckin.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

import httpx
from jsonschema import ValidationError, validate
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

# 复用 mcp_client_v1 的归一化工具（把不可信的 MCP Tool Result 标准化并限长）
from mcp_client_v1 import result_payload

# 让 week01/1-8 的 `app.*` 包可以被 import（复用它的模型适配器）
_WEEK01 = Path(__file__).resolve().parent.parent.parent / "week01" / "1-8"
if str(_WEEK01) not in sys.path:
    sys.path.insert(0, str(_WEEK01))

# 远程瑞幸 MCP 特性
LUCKIN_MCP_URL = os.getenv("LUCKIN_MCP_URL", "https://open.lkcoffee.com/mcp")
LUCKIN_TOKEN_ENV = "LUCKIN_MCP_TOKEN"
# 商品/门店响应可能较大，放宽归一化限长以容纳真实数据
PAYLOAD_MAX_CHARS = 8_000


@dataclass(frozen=True)
class ToolCall:
    """Host 交给 Runtime 执行的一次已解析工具调用。"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelReply:
    """Provider 单轮返回的最终文本或单次工具调用。

    message 保存模型回包里的原始 assistant 消息（含 reasoning_content）。
    思考模式（如 deepseek reasoner）要求把上一轮的 reasoning_content 原样回传，
    因此 Agent Loop 必须回放这条完整消息，而不是只拼装 content + tool_calls。
    """

    text: str | None = None
    tool_call: ToolCall | None = None
    message: dict[str, Any] | None = None


class LLMProvider(Protocol):
    """定义 Agent Loop 所需的模型调用抽象。"""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelReply: ...


class AgentModelProvider:
    """把 week01/1-8 的模型适配器扩展为支持工具调用的 LLMProvider。

    直接复用 OpenAICompatibleProvider 的客户端连接池（按 base_url 缓存）与
    SDK 异常翻译（_translate_error），只补上 week01 基础适配器没有的
    tools / tool_choice 原生工具调用能力。这不修改 week01 的源码。
    """

    def __init__(self, model_name: str = "general-primary") -> None:
        from app.config import MODEL_CONFIGS
        from app.services.providers.openai_compatible import OpenAICompatibleProvider

        self.config = MODEL_CONFIGS[model_name]
        # 复用 week01 适配器：连接池 + 异常翻译都继承自它
        self._adapter = OpenAICompatibleProvider()

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model_tools: list[dict[str, Any]],
    ) -> ModelReply:
        """请求模型，提取首个 Tool Call 或最终文本。"""
        client = self._adapter._client_for(self.config)
        try:
            response = await client.chat.completions.create(
                model=self.config.provider_model,
                messages=messages,
                tools=model_tools,
                tool_choice="auto",
            )
        except Exception as exc:  # noqa: BLE001 - 复用适配器的统一异常翻译
            raise self._adapter._translate_error(exc) from exc

        message = response.choices[0].message
        # 保留原始 assistant 消息（含 reasoning_content），供 Loop 回传给思考型模型
        msg_dict = message.model_dump(exclude_none=True)
        if message.tool_calls:
            call = message.tool_calls[0]
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            return ModelReply(
                tool_call=ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=arguments,
                ),
                message=msg_dict,
            )
        return ModelReply(text=message.content or "", message=msg_dict)


ToolHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolDefinition:
    """Host 侧工具定义，包含模型可见 Schema 与远端调用处理器。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    def to_model_tool(self) -> dict[str, Any]:
        """转换为 OpenAI-compatible 的 function tool 描述。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolRuntime:
    """在调用 MCP Server 前执行工具查找、参数校验与执行轨迹记录。"""

    def __init__(self) -> None:
        self.trace: list[dict[str, Any]] = []

    async def execute(
        self,
        call: ToolCall,
        tools: dict[str, ToolDefinition],
    ) -> dict[str, Any]:
        """校验工具和参数；仅校验通过后才调用对应远端处理器。"""
        tool = tools.get(call.name)
        if not tool:
            return self._reject(call, "TOOL_NOT_FOUND")
        try:
            validate(instance=call.arguments, schema=tool.input_schema)
        except ValidationError as exc:
            return self._reject(call, "INVALID_ARGUMENT", exc.message)

        self.trace.append(
            {"event": "server_call", "tool_call_id": call.id, "name": call.name, "arguments": call.arguments}
        )
        result = await tool.handler(call.id, call.arguments)
        self.trace.append(
            {"event": "tool_result", "tool_call_id": call.id, "name": call.name, "payload": result}
        )
        return result

    def _reject(self, call: ToolCall, code: str, message: str | None = None) -> dict[str, Any]:
        """记录本地拒绝，并返回未触发 Server 调用的结构化错误。"""
        payload = {"ok": False, "code": code}
        if message:
            payload["message"] = message
        self.trace.append(
            {"event": "runtime_rejected", "tool_call_id": call.id, "name": call.name, "payload": payload}
        )
        return payload


async def discover_tools(
    client: Client,
    server_id: str,
) -> dict[str, ToolDefinition]:
    """发现远程瑞幸 MCP 工具，命名空间化为 `luckin_<name>` 后注册为 Host 工具。"""
    result = await client.list_tools()
    definitions: dict[str, ToolDefinition] = {}
    for remote in result.tools:
        qualified_name = f"{server_id}_{remote.name}"

        async def handler(
            tool_call_id: str,
            arguments: dict[str, Any],
            remote_name: str = remote.name,
        ) -> dict[str, Any]:
            """调用原始 MCP 工具名，并将远端结果归一化为 Host Payload。"""
            response = await client.call_tool(remote_name, arguments)
            return {"tool_call_id": tool_call_id, **result_payload(response, PAYLOAD_MAX_CHARS)}

        definitions[qualified_name] = ToolDefinition(
            name=qualified_name,
            description=remote.description or "",
            input_schema=remote.input_schema,
            handler=handler,
        )
    return definitions


SYSTEM_PROMPT = (
    "你连接的是瑞幸咖啡 MCP，其可用工具都带 `luckin_` 前缀。"
    "要查真实数据，必须遵守以下流程，不得编造："
    "1) 先用 luckin_queryShopList(latitude, longitude) 找到门店，拿到 deptId；"
    "2) 再用 luckin_searchProductForMcp(deptId, query) 按用户语义搜索商品；"
    "3) 需要改规格/加料时用 luckin_switchProduct；"
    "4) 最后用 luckin_queryProductDetailInfo(deptId, productId) 拿商品完整详情与价格。"
    "所有工具调用的结果必须来自真实返回，不能猜测。"
)


async def run_agent(
    provider: LLMProvider,
    runtime: ToolRuntime,
    tools: dict[str, ToolDefinition],
    user_input: str,
    max_rounds: int = 6,
) -> str:
    """持续执行模型决策、Runtime 调用和结果回写，直到模型返回文本。"""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]
    model_tools = [tool.to_model_tool() for tool in tools.values()]

    for round_no in range(1, max_rounds + 1):
        reply = await provider.complete(messages, model_tools)
        if reply.text is not None:
            print("LOOP", round_no, "final")
            return reply.text
        if reply.tool_call is None:
            raise RuntimeError("MODEL_REPLY_INVALID")

        print("LOOP", round_no, "tool_call", reply.tool_call.name)
        # 回放模型原始 assistant 消息（含 reasoning_content），思考型模型需要它
        if reply.message:
            messages.append(reply.message)
        tool_result = await runtime.execute(reply.tool_call, tools)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": reply.tool_call.id,
                "content": json.dumps(tool_result, ensure_ascii=False),
            }
        )
        runtime.trace.append(
            {"event": "result_written_to_context", "round": round_no, "tool_call_id": reply.tool_call.id}
        )

    raise RuntimeError("MAX_ROUNDS_EXCEEDED")


async def build_luckin_http_client(token: str) -> httpx.AsyncClient:
    """构造带瑞幸认证上下文的 httpx 客户端。

    瑞幸 MCP 端点不仅要求 `Authorization: Bearer <token>`，还会做 CSRF 校验
    （裸请求返回 403 "missing csrf token"）。这里先 GET 首页拿到会话 cookie
    （csrfToken / SSID），再把 cookie 里的 csrf 作为 `X-CSRF-Token` 回传，
    与 Bearer 一起交给 MCP 客户端使用。
    """
    client = httpx.AsyncClient(follow_redirects=True, timeout=30.0)
    home_text = ""
    try:
        resp = await client.get("https://open.lkcoffee.com/")
        home_text = resp.text
    except Exception:  # noqa: BLE001 - 握手失败不致命，仍尝试连接
        pass
    csrf = client.cookies.get("csrfToken")
    if not csrf:
        match = re.search(r"window\._csrf\s*=\s*'([^']+)'", home_text)
        if match:
            csrf = match.group(1)
    client.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        }
    )
    if csrf:
        client.headers["X-CSRF-Token"] = csrf
    return client


async def main() -> None:
    """连接远程瑞幸 MCP，发现工具并运行真实点单 Agent Loop。"""
    token = os.getenv(LUCKIN_TOKEN_ENV, "").strip()
    if not token:
        print(f"LIVE SKIP：未设置 {LUCKIN_TOKEN_ENV}。")
        print("请在 https://open.lkcoffee.com 登录后复制 Token，再设此环境变量即可查真实数据。")
        return

    http_client = await build_luckin_http_client(token)
    async with Client(streamable_http_client(LUCKIN_MCP_URL, http_client=http_client)) as client:
        tools = await discover_tools(client, "luckin")
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        print("PROTOCOL", client.protocol_version)
        print("TOOLS", sorted(tools))
        print("RESOURCES", [str(item.uri) for item in resources.resources])
        print("PROMPTS", [item.name for item in prompts.prompts])

        runtime = ToolRuntime()

        if "DEEPSEEK_API_KEY" not in os.environ:
            print("LIVE SKIP：设置 DEEPSEEK_API_KEY 后运行真实 Agent Loop")
            print(json.dumps(runtime.trace, ensure_ascii=False, indent=2))
            return

        answer = await run_agent(
            provider=AgentModelProvider(),
            runtime=runtime,
            tools=tools,
            user_input=(
                "厦门观音山海西金谷广场T3店（经纬度 118.08891, 24.479627）有一杯生椰拿铁。"
                "请查最近门店确认 deptId -> 搜索生椰拿铁 -> 把规格切到大杯 -> 查最终商品详情，"
                "并用中文小结真实拿到的商品名、规格与预估到手价。"
            ),
        )
        print("LIVE", answer)
        print(json.dumps(runtime.trace, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())