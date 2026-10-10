async def invoke_many(
    runtime: ToolRuntime,
    snapshot: ToolSnapshot,
    # 模型一次返回多个tool_calls
    calls: list[ToolCall],
    context: ExecutionContext,
) -> list[ToolResultMessage]:
    # 必须顺序执行的工具 只要有一个就全部串行
    must_run_in_order = any(
        snapshot.tools.get(call.name)
        and snapshot.tools[call.name].execution_mode == "sequential"
        for call in calls
    )

    if must_run_in_order:
        return [
            await runtime.invoke(snapshot, call, context)
            for call in calls
        ]

    return await asyncio.gather(
        *(runtime.invoke(snapshot, call, context) for call in calls)
    )