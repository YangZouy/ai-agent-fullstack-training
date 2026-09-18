from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentDecision(BaseModel):
    model_config = ConfigDict(
        # 禁止输出schema里没定义的字段
        extra="forbid",
        # 严格类型模式，类型错误会直接报错，不会自动转换
        strict=True,
    )

    action: Literal["search_docs", "finish"] = Field(
        description="下一步是搜索资料还是结束回答"
    )
    query: str | None = Field(
        # 必填
        ...,
        min_length=1,
        max_length=200,
        description="搜索时使用；结束时为 null",
    )
    answer: str | None = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="结束时使用；搜索时为 null",
    )

    # 前面字段约束只能保证单个字段合法
    # 该函数可以保证字段之间组合合法
    # mode=after表示在所有字段都通过基础类型校验后，再执行这个函数。
    @model_validator(mode="after")
    def check_action_fields(self) -> "AgentDecision":
        if self.action == "search_docs":
            if not self.query or self.answer is not None:
                raise ValueError(
                    "search_docs requires query and answer must be null"
                )

        if self.action == "finish":
            if not self.answer or self.query is not None:
                raise ValueError(
                    "finish requires answer and query must be null"
                )

        return self

# 将上面约束转换为标准JSON Schema
AgentDecision.model_json_schema()

raw_output = """
{
    "action": "search_docs",
    "query": "你好",
    "answer": null
}
"""

# 校验模型输出
decision = AgentDecision.model_validate_json(raw_output)

print(decision.action)
print(decision.query)
print(decision.model_dump())
