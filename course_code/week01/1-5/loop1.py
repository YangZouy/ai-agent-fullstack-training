MAX_STEPS = 4

def run_knowledge_agent(
    task: str,# 用户的初始问题
    call_model: ModelCall, # 调用大模型的函数（可注入，方便测试）
    search_docs: Callable[[str], str],# 搜索文档的工具函数（可注入）
    cached: CachedAnswer | None = None,# 可选的缓存答案（用于加速或测试）
) -> str:
    observations: list[str] = []

    for _ in range(MAX_STEPS):
        # 构建上下文（Context）
        context = task
        # 如果已经有了搜索资料，就把它们拼接到原始问题后面，一起发给大模型
        if observations:
            context += "\n\n已获得资料：\n" + "\n".join(observations)

        # 调用大模型，并强制模型输出JSON Schema 格式的数据，然后解析成对象
        result = safe_decide(
            task=context,
            call_model=call_model,
            # 只有在第一轮且没资料时才用缓存
             cached=cached if not observations else None,
        )

        # 错误处理与决策
        if result.status == "failed":
            raise RuntimeError(result.message)

        decision = result.decision
        assert decision is not None

        # 如果模型决定结束，直接返回答案
        if decision.action == "finish":
            assert decision.answer is not None
            return decision.answer

        # 如果模型决定去搜索，就提取查询词，调用 search_docs 函数，
        # 把搜到的结果放进 observations 列表中，进入下一轮循环。
        assert decision.query is not None
        observations.append(search_docs(decision.query))

    raise RuntimeError("agent exceeded maximum steps")

# 单元测试
def test_invalid_output_never_calls_tool():
    calls = 0

    def invalid_model(_messages, _schema):
        return '{"action": "delete_docs"}'

    def search_docs(_query):
        nonlocal calls
        calls += 1
        return "不应执行"

    try:
        run_knowledge_agent(
            task="查询差旅报销材料",
            call_model=invalid_model,
            search_docs=search_docs,
        )
    except RuntimeError:
        pass

    assert calls == 0