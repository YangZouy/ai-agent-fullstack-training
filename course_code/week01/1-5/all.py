"""
处理返回失败的情况，最终保证给上层返回一个格式统一
且可控的结果对象
"""

def safe_decide(
    task: str,
    call_model: ModelCall,
    # 缓存答案
    cached: CachedAnswer | None,
    # 返回结果用于是对象 保证调用方不用写try-except
) -> DecisionResult:
    try:
        # 正常路径
        decision = decide_with_repair(
            task=task,
            call_model=call_model,
            max_repairs=2,
        )
        return DecisionResult(
            status="ok",
            source="model",
            decision=decision,
            message=None,
        )
    # 降级路径 捕获结构化输出异常
    except StructuredOutputFailure as exc:
        # 使用新的缓存
        cached_decision = use_cache_if_fresh(cached, task)

        if cached_decision is not None:
            return DecisionResult(
                status="degraded",
                source="cache",
                decision=cached_decision,
                message="模型输出异常，当前结果来自有效缓存。",
                repair_attempts=len(exc.attempts),
            )
        # 缓存没有 使用失败处理
        return failed_result(len(exc.attempts))