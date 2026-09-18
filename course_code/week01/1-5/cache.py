from datetime import datetime, timedelta, timezone
from hashlib import sha256


SCHEMA_VERSION = "agent-decision-v1"

# 对应缓存部分
class CachedAnswer(BaseModel):
    # 存问题的哈希值
    task_key: str
    # 缓存答案
    answer: str = Field(min_length=1, max_length=4000)
    created_at: datetime
    schema_version: str

# 把用户输入转化成一个固定长度的字符串（哈希值）
def make_task_key(task: str) -> str:
    normalized = " ".join(task.split()).strip().lower()
    return sha256(normalized.encode("utf-8")).hexdigest()

# 缓存有效性
def use_cache_if_fresh(
    cached: CachedAnswer | None,
    task: str,
    max_age: timedelta = timedelta(minutes=5),
) -> AgentDecision | None:
    # 缓存不存在
    if cached is None:
        return None
    # 任务不匹配
    if cached.task_key != make_task_key(task):
        return None
    # schema版本不一致
    if cached.schema_version != SCHEMA_VERSION:
        return None
    # 时区无效
    if cached.created_at.tzinfo is None:
        return None
    # 缓存是否过期
    age = datetime.now(timezone.utc) - cached.created_at
    if age < timedelta(0) or age > max_age:
        return None

    # 返回缓存
    return AgentDecision(
        # 设置为finish，缓存里只有最终答案，无搜索
        action="finish",
        query=None,
        answer=cached.answer,
    )