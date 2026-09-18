from collections.abc import Callable

"""
结构化输出失败后的自动修复机制 repair loop
"""
ModelCall = Callable[
    [list[dict[str, str]], dict[str, object]],
    str,
]

# 记录每次失败详情的
class RepairAttempt(BaseModel):
    attempt: int
    # # 模型输出的前 500 个字符（用于记录日志，不存全量避免内存爆炸）
    output_preview: str
    # 校验失败的具体原因列表
    issues: list[ValidationIssue]

# 自定义异常 把所有的失败记录 attempts 挂在异常对象上
class StructuredOutputFailure(RuntimeError):
    def __init__(self, attempts: list[RepairAttempt]):
        super().__init__(
            f"structured output failed after {len(attempts)} calls"
        )
        self.attempts = attempts

# 
def decide_with_repair(
    task: str,
    call_model: ModelCall,
    max_repairs: int = 2,
) -> AgentDecision:
    messages = [
        {
            "role": "system",
            "content": "根据 AgentDecision 协议决定搜索或结束。",
        },
        {"role": "user", "content": task},
    ]
    # 失败列表
    attempts: list[RepairAttempt] = []

    for call_index in range(max_repairs + 1):
        raw_output = call_model(
            messages,
            # schema 直接传入到model的API中
            AgentDecision.model_json_schema(),
        )
        # 拿到输出 本地校验
        validation = validate_decision(raw_output)
        # 有效直接返回
        if validation.valid:
            assert validation.decision is not None
            return validation.decision

        # 记录失败准备修复
        attempts.append(
            RepairAttempt(
                attempt=call_index + 1,
                output_preview=raw_output[:500],
                issues=validation.issues,
            )
        )
        # 最后一次重试修复，没成功抛出异常
        if call_index == max_repairs:
            raise StructuredOutputFailure(attempts)

        # 自我纠错部分
        # extend是python的基础语法，将一个可迭代对象中的元素
        # 逐个添加到当前列表的末尾
        messages.extend(
            [
                # 模型错误添加到messages
                {"role": "assistant", "content": raw_output[:2000]},
                # 输入错误原因以及修改提示词 模型下一轮进行自我修复
                {
                    "role": "user",
                    "content": build_repair_message(
                        validation.issues
                    ),
                },
            ]
        )

    raise AssertionError("unreachable")


def build_repair_message(
    issues: list[ValidationIssue],
) -> str:
    # 把对象转成标准的python字典
    details = [issue.model_dump() for issue in issues]

    # 返回修复提示词
    return (
        "上一份输出未通过 AgentDecision 校验。\n"
        f"校验错误：{json.dumps(details, ensure_ascii=False)}\n"
        "请保持原任务含义不变，只修正 JSON 语法、字段、"
        "类型或字段组合。只返回修正后的 JSON。"
    )