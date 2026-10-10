from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

# 验收模型的参数是否符合要求
# 工具调用入参校验
class SearchOrdersInput(StrictModel):
    status: Literal["pending", "paid", "shipped", "cancelled"] | None = None
    created_from: date | None = None
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def require_filter(self) -> "SearchOrdersInput":
        if self.status is None and self.created_from is None:
            raise ValueError("status 与 created_from 至少提供一个")
        return self

# 输出模型
class OrderSummary(StrictModel):
    order_id: str
    status: Literal["pending", "paid", "shipped", "cancelled"]
    created_at: str
    amount_cents: int = Field(ge=0)

# 验收业务函数的返回值
class SearchOrdersOutput(StrictModel):
    orders: list[OrderSummary]
    total: int = Field(ge=0)

# 统一表达错误的方式
class ToolError(StrictModel):
    code: Literal[
        # 参数错误
        "INVALID_ARGUMENT",
        # 工具不存在
        "TOOL_NOT_FOUND",
        # 权限不足
        "PERMISSION_DENIED",
        # 需要用户审批
        "APPROVAL_REQUIRED",
        "TIMEOUT", # 超时
        # 上游错误，只有满足幂等条件的时候，runtime 才能有限的重试
        "UPSTREAM_ERROR",
        "INVALID_OUTPUT", # 业务工具违反的预先定义的返回协议，应记录工程故障，停止执行，不要猜测缺少的字段
    ]
    message: str
    retryable: bool = False