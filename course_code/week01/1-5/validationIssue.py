# 单个校验错误
class ValidationIssue(BaseModel):
    path: str
    code: str
    message: str

# 整个校验结果
class DecisionValidation(BaseModel):
    valid: bool
    decision: AgentDecision | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)

"""
当解析失败时，Pydantic 会抛出 ValidationError，
需要把它“翻译”成自己定义的 ValidationIssue 列表。
"""
def validate_decision(raw_output: str) -> DecisionValidation:
    try:
        decision = AgentDecision.model_validate_json(raw_output)
        return DecisionValidation(
            valid=True,
            decision=decision,
        )
    except ValidationError as exc:
        issues = [
            ValidationIssue(
                path=".".join(str(part) for part in item["loc"]),
                code=item["type"],
                message=item["msg"],
            )
            for item in exc.errors(
                include_url=False,
                include_input=False,
            )
        ]
        return DecisionValidation(
            valid=False,
            issues=issues,
        )