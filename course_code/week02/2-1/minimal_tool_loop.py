import asyncio
import json
import os

from openai import OpenAI

from execution_context import ExecutionContext
from search_orders_tool import DemoOrderService, SEARCH_ORDERS
from tool_messages import ToolCall
from tool_runtime import ToolRuntime

MAX_STEPS = 4

# 创建客户端
def create_client() -> OpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("请先设置 DEEPSEEK_API_KEY 环境变量")
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


async def run_order_agent(
    user_text: str,
    runtime: "ToolRuntime",
    ctx: "ExecutionContext",
    client: OpenAI,
) -> str:
    messages = [
        {"role": "system", "content": "你是订单助手，不得编造订单。"},
        {"role": "user", "content": user_text},
    ]

    for step in range(1, MAX_STEPS + 1):
        # 过滤可见工具 权限前置
        # 每次循环都重新计算visible_tools
        # 因为ctx可能在循环中更新
        visible_tools = runtime.model_tools(ctx)
        print(f"\n=== 第 {step} 轮：计算当前可见工具 ===")
        print([tool["function"]["name"] for tool in visible_tools])
        print("=== 请求 DeepSeek ===")
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            tools=visible_tools,
            # 模型决定调工具还是直接回答
            tool_choice="auto",
            extra_body={"thinking": {"type": "disabled"}},
        )

        assistant = response.choices[0].message
        # 对象转字典 剔除None的字段
        messages.append(assistant.model_dump(exclude_none=True))
        tool_calls = assistant.tool_calls or []

        if not tool_calls:
            print("模型未返回 Tool Call，Agent Loop 结束。")
            return assistant.content or ""

        print(f"模型返回 {len(tool_calls)} 个 Tool Call。")
        for raw_call in tool_calls:
            call = ToolCall(
                id=raw_call.id,
                name=raw_call.function.name,
                arguments_json=raw_call.function.arguments,
            )
            print(
                f"执行 Runtime: id={call.id}, name={call.name}, "
                f"arguments={call.arguments_json}"
            )
            result = await runtime.execute(call, ctx)
            messages.append(result.to_model_message())
            print(f"写回 Tool Result: {result.content}")

    raise RuntimeError("agent exceeded maximum steps")

# 追踪事件
async def trace_writer(event: dict) -> None:
    print(f"Runtime Trace: {json.dumps(event, ensure_ascii=False)}")


async def main() -> None:
    # 创建运行时
    runtime = ToolRuntime(trace_writer)
    # 工具注册
    runtime.register(SEARCH_ORDERS)
    # 身份\权限\服务
    ctx = ExecutionContext(
        user_id="user_demo",
        tenant_id="tenant_demo",
        permissions=frozenset({"order:read"}),
        trace_id="trace_demo_002",
        order_service=DemoOrderService(),
    )
    # Agent loop
    answer = await run_order_agent(
        "查一下我昨天创建、还没有支付的订单。",
        runtime,
        ctx,
        create_client(),
    )
    print("\n=== 最终回答 ===")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
