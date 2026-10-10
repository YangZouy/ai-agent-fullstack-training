import asyncio
from datetime import date

from execution_context import ExecutionContext
from order_schemas import OrderSummary, SearchOrdersInput, SearchOrdersOutput, ToolError
from tool_definition import ToolDefinition

# 工具函数 参数：输入（模型生成）
async def search_orders(
    args: SearchOrdersInput,
    # 运行时上下文，含user_id
    ctx: "ExecutionContext",
) -> SearchOrdersOutput:
    rows = await ctx.order_service.search(
        # 安全边界：不让模型决定查谁的数据
        user_id=ctx.user_id,
        status=args.status,
        created_from=args.created_from,
        limit=args.limit,
    )

    # 返回输出模型
    return SearchOrdersOutput(
        # 输出校验
        orders=[OrderSummary.model_validate(row) for row in rows],
        total=len(rows),
    )

# 工具定义
SEARCH_ORDERS = ToolDefinition(
    name="search_orders",
    description=(
        "按当前用户、订单状态和创建日期查询订单。"
        "只读取订单；不能取消、退款或修改订单。"
    ),
    input_model=SearchOrdersInput,
    output_model=SearchOrdersOutput,
    # 统一错误结构，方便上层处理
    error_model=ToolError,
    permission="order:read",
    # 风险等级
    risk="low",
    # 超时控制
    timeout_seconds=5,
    max_retries=2,
    # 幂等：读操作重试无副作用
    idempotent=True,
    # 执行函数
    handler=search_orders,
)


class DemoOrderService:
    _records = [
        {
            "user_id": "user_demo",
            "order_id": "ord_1001",
            "status": "pending",
            "created_at": "2026-08-18T10:30:00+08:00",
            "amount_cents": 2999,
        },
        {
            "user_id": "user_other",
            "order_id": "ord_1002",
            "status": "pending",
            "created_at": "2026-08-18T11:00:00+08:00",
            "amount_cents": 1599,
        },
    ]

    async def search(
        self,
        *,
        user_id: str,
        status: str | None,
        created_from: date | None,
        limit: int,
    ) -> list[dict]:
        print(
            "[业务查询] "
            f"user_id={user_id}, status={status}, "
            f"created_from={created_from}, limit={limit}"
        )
        records = [
            record
            for record in self._records
            if record["user_id"] == user_id
            and (status is None or record["status"] == status)
            and (
                created_from is None
                or date.fromisoformat(record["created_at"][:10]) >= created_from
            )
        ]
        return [
            {
                key: value
                for key, value in record.items()
                # 提出user_id，脱敏
                if key != "user_id"
            }
            for record in records[:limit]
        ]


async def main() -> None:
    args = SearchOrdersInput(status="pending", limit=10)
    # 模拟运行时注入的上下文——身份、权限、链路等
    ctx = ExecutionContext(
        user_id="user_demo",
        tenant_id="tenant_demo",
        # 不可变、可哈希、适合做集合判断
        permissions=frozenset({"order:read"}),
        trace_id="trace_demo_001",
        order_service=DemoOrderService(),
    )

    print("=== 1. ToolDefinition 装配结果 ===")
    print(SEARCH_ORDERS.to_model_tool())
    print("=== 2. 参数来源 ===")
    print(f"模型参数 args: {args.model_dump()}")
    print(
        "运行时上下文 ctx: "
        f"user_id={ctx.user_id}, tenant_id={ctx.tenant_id}, trace_id={ctx.trace_id}"
    )
    print("=== 3. Handler 执行过程 ===")
    output = await SEARCH_ORDERS.handler(args, ctx)
    print("=== 4. Output Schema 验收后的结果 ===")
    validated_output = SEARCH_ORDERS.output_model.model_validate(output)
    print(validated_output.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
