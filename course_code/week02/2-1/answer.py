"""
week02/2-1 课堂练习作答
============================================================
2-1 Function Calling 与 Tool Use：让模型提出动作，让 Runtime 安全执行

本文件包含三部分：
  4.1  不看代码回答协议闭环五问（原作答已修正/补全，标注 [修正] / [补全]）
  4.2  代码：完成一次最小调用（瑞幸协议风格 search_orders）
  4.3  最后的疑问解答

代码走读参考同目录：tool_definition.py / order_schemas.py /
search_orders_tool.py / tool_runtime.py / minimal_tool_loop.py
"""

# ============================================================
# 4.1 两分钟讲清协议闭环
# ============================================================

# ---- 1. Function Calling 与普通函数调用有什么区别？----
# 你的原答：模型决定是否调用工具；返回唯一对应的 tool_call_id；执行前有一堆校验
# （工具是否存在 / 入参是否正确 / 权限是否正确 / 是否高风险 / 执行后输出校验 /
#   异常捕获并区分可否重试：参数类型·权限类型不可重试，网络连接·超时·幂等可重试）
#
# [补全] 再补上「谁在调用」这一层，才是完整区别：
#   普通函数调用：调用方是程序自己，参数由代码写死，调了就一定执行 → 输入可信、没有边界。
#   Function Calling：调用方是模型，模型只「提出」候选动作（Tool Call）：
#     · 参数是模型生成的 JSON 字符串，和用户输入一样属于【不可信数据】；
#     · Tool Call 只是「提议」，不是执行许可 —— 这是与普通函数调用最本质的区别；
#     · 必须经 Runtime 校验通过后才执行 handler，执行结果作为 Tool Result
#       带着【原样的 tool_call_id】写回消息历史，模型再决定下一步。
#   一句话：普通函数调用 = 直接执行；Function Calling = 提议 → 校验 → 受控执行 → 回写。

# ---- 2. 模型侧 Tool 为什么没有 execute()？----
# [补全] 原作答为空。核心是：模型和 Runtime 看到的是【两个不同的对象】。
#   · 模型只需要「公开契约」：name / description / parameters(Input Schema)，
#     用途是【选工具 + 填参数】，它没有任何执行环境，只会输出文本或 JSON；
#   · execute(handler)、output_model、error_model、permission、risk、超时/重试、
#     内部依赖，全部留在 Runtime 侧，模型既看不见也触发不了；
#   · 一旦把 execute/handler 塞进发给模型的 JSON，模型就可能被诱导去构造调用、
#     绕过治理；权限字段一旦可见，等于把「我有没有权限」的决定权交给了模型自己。
#   这就是 pi 源码里 Tool（模型可见，纯数据）与 AgentTool（含 execute，运行时用）
#   必须分离的原因：见 tool_definition.py 中 ToolDefinition 的注释分区，
#   以及 pi_types.ts 的 Tool / AgentTool 两个类型。

# ---- 3. Input、Output 和 Error Schema 分别约束什么？----
# 你的原答：input 约束入参是否规范，output 约束工具输出是否规范，
#           error 约束执行出错的输出规范。
# [修正] 方向对，但漏掉了「各自卡在哪一段边界、失败怎么恢复」这两层，补上：
#   · Input  Schema：卡在 Tool Call → handler 之间 —— 参数是否完整、类型是否正确、
#                    范围是否合理（含跨字段不变量：status 与 created_from 至少给一个）；
#   · Output Schema：卡在 handler → Tool Result 之间 —— 业务函数返回的事实是否稳定、
#                    后续 Loop 能否直接消费（而不是让模型去猜字段）；
#   · Error  Schema：卡在【失败 → 下一轮决策】之间 —— 失败属于哪一类、能否重试、
#                    下一步是模型改参数、人工审批还是直接终止。
#   三者缺任何一个，Agent Loop 都会被迫解析自然语言或猜下一步。
#   另注：error 不是「执行出错的输出」，而是「失败语义的分类协议」（code + retryable）。

# ---- 4. 为什么权限和审批不能作为模型参数？----
# 你的原答：权限信息等用户信息不能让模型看见。
# [修正] 说法偏「不可见」，更准确的根因是「不可信」：
#   · Tool Call 是不可信输入，模型完全可以（也经常）编造
#     「我是管理员」「本次已审批」「风险等级=low」；
#   · 身份、租户、权限、审批记录只能来自【可信上下文 Execution Context】——
#     由登录态或服务间身份注入，而不是由模型填写；
#   · 所以 Input Schema 里绝不能出现 user_id / role / approved 这类字段；
#     Runtime 从 ctx.permissions / ctx.approved_call_ids 取授权依据
#     （见 tool_runtime.py 的 ③④ 两道关卡），让越权调用在 handler 之前就被拒掉。
#   一句话：权限不是「藏起来」，而是「根本不由模型提供」。

# ---- 5. 两个同名工具调用乱序完成时，tool_call_id 怎样防止结果错配？----
# 你的原答：工具执行完成后返回结果时会与 call_id 一起返回，
#           需要不同结果时按不同 id 搜索即可。
# [修正] 已经抓到关键点，再把「为什么必须要 id」补上：
#   · 匹配依据不能是「工具名 + 返回顺序」：模型可能在同一条 assistant 消息里
#     提出两个同名调用，区别只有参数和 id（call_A / call_B）；
#   · 并行执行时【完成顺序 ≠ 生成顺序】。若按顺序贴结果，就可能把 paid 贴到 ord_123 上；
#   · 正确做法：让 id 跟着调用对象进入每个异步任务（execute_bound 返回 (call.id, result)），
#     再断言 result.tool_call_id == call.id 兜底（见 tool_batch.py）；
#   · tool_call_id 一次性解决四件事：① 消息协议对应关系 ② 生成/完成顺序解耦
#     ③ 区分成功与失败的恢复对象 ④ 建立 Trace 的父子关系。


# ============================================================
# 4.2 代码：完成一次最小调用（瑞幸协议风格）
# ============================================================
#
# 四步：
#   步骤 1  定义名称、描述和 Input Schema
#   步骤 2  生成模型可见的 Tool JSON，确认没有 handler / 权限 / 内部依赖
#   步骤 3  构造两条不同 tool_call_id 的 Tool Call
#   步骤 4  分别生成 Tool Result，并断言结果 ID 与原调用一致

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ============================================================
# 步骤 1：名称、描述与 Input Schema
# ============================================================

TOOL_NAME = "search_orders"
TOOL_DESCRIPTION = (
    "按订单ID查询当前用户的瑞幸订单详情。"
    "只读取订单；不能取消、退款、修改订单或改变订单状态。"
)
# 治理声明（Runtime 私有，不进模型 JSON）
TOOL_PERMISSION: Literal["order:read", "order:write"] = "order:read"
TOOL_RISK: Literal["low", "medium", "high"] = "low"


class OrderIdInput(BaseModel):
    """模型可填的参数只有订单ID，别的一律不许填。"""

    order_id: str = Field(alias="orderId", min_length=1, description="订单ID")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


# ============================================================
# 瑞幸协议数据结构（模型可见的 Output 事实）
# ============================================================


class OrderStatus(IntEnum):
    """瑞幸订单状态，值与接口文档一一对应。"""

    PENDING_PAYMENT = 10   # 待付款
    ORDER_SUCCESS = 20     # 下单成功
    MAKING = 30            # 制作中
    WAITING_PICKUP = 60    # 等待取餐
    COMPLETED = 80         # 已完成
    CANCELLED = 100        # 已取消


class _Base(BaseModel):
    """所有输出模型公共配置。

    - populate_by_name:      允许用字段名或 alias 赋值
    - extra="ignore":        接口多返回字段时不报错（向前兼容）
    - str_strip_whitespace:  字符串自动去首尾空格
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )


class TakeMealCodeInfo(_Base):
    code: str | None = Field(default=None, description="取餐码")
    take_order_id: str | None = Field(default=None, alias="takeOrderId", description="取餐单ID")


class ShopInfo(_Base):
    dept_id: int | None = Field(default=None, alias="deptId", description="门店ID")
    dept_name: str | None = Field(default=None, alias="deptName", description="门店名称")
    address: str | None = Field(default=None, description="门店地址")
    dept_tags: list[str] | None = Field(default=None, alias="deptTags", description="门店标签")
    longitude: float | None = Field(default=None, description="门店经度")
    latitude: float | None = Field(default=None, description="门店纬度")
    work_time_start: str | None = Field(default=None, alias="workTimeStart", description="营业开始时间")
    work_time_end: str | None = Field(default=None, alias="workTimeEnd", description="营业结束时间")
    distance: float | None = Field(default=None, description="距离，单位千米")
    number: str | None = Field(default=None, description="门店编号")


class ProductInfo(_Base):
    product_id: int | None = Field(default=None, alias="productId", description="商品ID")
    sku_code: str | None = Field(default=None, alias="skuCode", description="商品SKU编码")
    name: str | None = Field(default=None, description="商品名称")
    amount: int | None = Field(default=None, description="商品数量")
    addition_desc: str | None = Field(default=None, alias="additionDesc", description="商品附属备注描述")
    big_pic_url: str | None = Field(default=None, alias="bigPicUrl", description="商品大图URL")
    breviary_pic_url: str | None = Field(default=None, alias="breviaryPicUrl", description="商品缩略图URL")
    order_pay_amount: float | None = Field(default=None, alias="orderPayAmount", description="订单支付金额")


class DispatchInfo(_Base):
    dispatcher_name: str | None = Field(default=None, alias="dispatcherName", description="配送员姓名")
    dispatcher_mobile: str | None = Field(default=None, alias="dispatcherMobile", description="配送员手机号")
    dispatch_about_time: str | None = Field(default=None, alias="dispatchAboutTime", description="预计配送时间")
    destination_distance: float | None = Field(default=None, alias="destinationDistance", description="配送距离")


class OrderCommodity(_Base):
    commodity_id: int | None = Field(default=None, alias="commodityId", description="商品ID")
    commodity_code: str | None = Field(default=None, alias="commodityCode", description="商品编码")
    commodity_name: str | None = Field(default=None, alias="commodityName", description="商品名称")
    payable_money: float | None = Field(default=None, alias="payableMoney", description="应付金额")
    pay_money: float | None = Field(default=None, alias="payMoney", description="实付金额")


class LuckinOrder(_Base):
    """顶层订单。未支付订单的 productInfoList 可能为 null，所以做 Optional。"""

    order_id: str = Field(alias="orderId", description="订单ID")
    order_status: OrderStatus = Field(alias="orderStatus", description="订单状态")
    order_status_name: str | None = Field(default=None, alias="orderStatusName", description="订单状态名称")
    about_time: int | None = Field(default=None, alias="aboutTime", description="预计取餐/送达时间戳")
    take_meal_time: str | None = Field(default=None, alias="takeMealTime", description="实际取餐时间")

    take_meal_code_info: TakeMealCodeInfo | None = Field(default=None, alias="takeMealCodeInfo", description="取餐码信息")
    shop_info: ShopInfo | None = Field(default=None, alias="shopInfo", description="门店信息")
    dispatch_info: DispatchInfo | None = Field(default=None, alias="dispatchInfo", description="配送信息")

    product_info_list: list[ProductInfo] | None = Field(
        default=None, alias="productInfoList", description="商品信息列表，待付款订单可能为 null"
    )
    order_commodity_list: list[OrderCommodity] | None = Field(
        default=None, alias="orderCommodityList", description="订单商品列表"
    )

    order_type: str | None = Field(default=None, alias="orderType", description="订单类型")
    customer_params: dict[str, Any] | None = Field(default=None, alias="customerParams", description="自定义参数")


class ToolError(BaseModel):
    """统一失败语义：code 决定谁负责恢复，retryable 决定 Runtime 能不能重试。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    code: Literal[
        "INVALID_ARGUMENT",   # 模型改参数后可再试
        "TOOL_NOT_FOUND",     # 工具不存在
        "NOT_FOUND",          # 业务数据不存在
        "PERMISSION_DENIED",  # 不可重试，应停止或切换身份
        "APPROVAL_REQUIRED",  # 需人工确认
        "TIMEOUT",            # 幂等才可重试
        "UPSTREAM_ERROR",     # 幂等才可重试
        "INVALID_OUTPUT",     # 工具违反返回协议 → 工程故障，不要猜字段
    ]
    message: str
    retryable: bool = False


# ============================================================
# 步骤 2：生成模型可见的 Tool JSON
# ============================================================

# 工具的结构化定义（对应课程 tool_definition.py 的 ToolDefinition，
# 但本练习不实现 Registry / Snapshot / 重试框架，所以只保留最小字段）
@dataclass(frozen=True)
class LuckinSearchTool:
    # ---- 模型可见（公开契约）----
    name: str = TOOL_NAME
    description: str = TOOL_DESCRIPTION
    input_model: type[BaseModel] = OrderIdInput
    output_model: type[BaseModel] = LuckinOrder
    error_model: type[BaseModel] = ToolError
    # ---- Runtime 私有（模型不可见）----
    permission: str = TOOL_PERMISSION
    risk: str = TOOL_RISK

    def to_model_tool(self) -> dict:
        """唯一出口：只吐公开契约。handler / 权限 / 风险 / 内部依赖都不在这里。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_model.model_json_schema(),
            },
        }


SEARCH_ORDERS_TOOL = LuckinSearchTool()


def step2_model_visible_json() -> dict:
    tool_json = SEARCH_ORDERS_TOOL.to_model_tool()
    # 自检：模型 JSON 里绝不能出现这些字段（对照 4.3 审查清单第 2 条）
    leaked = {"handler", "permission", "risk", "output_model", "error_model"} & set(tool_json["function"])
    assert not leaked, f"治理信息泄漏给模型: {leaked}"
    return tool_json


# ============================================================
# 步骤 3：构造两条不同 tool_call_id 的 Tool Call
# ============================================================


class ToolCall(BaseModel):
    """Runtime 内部结构，不是模型发明的类：由 raw_call 的三元组包出来。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    arguments_json: str


def build_tool_calls() -> list[ToolCall]:
    return [
        ToolCall(id="call_A", name=TOOL_NAME, arguments_json='{"orderId":"ord_1001"}'),
        ToolCall(id="call_B", name=TOOL_NAME, arguments_json='{"orderId":"ord_1002"}'),
    ]


# ============================================================
# 步骤 4：生成 Tool Result 并断言 ID 配对
# ============================================================

_ORDER_DB: dict[str, dict[str, Any]] = {
    "ord_1001": {
        "orderId": "ord_1001",
        "orderStatus": 20,
        "orderStatusName": "下单成功",
        "aboutTime": 1790000000,
        "takeMealCodeInfo": {"code": "A123", "takeOrderId": "tk_1001"},
        "shopInfo": {"deptId": 100, "deptName": "瑞幸·国贸店", "address": "北京市朝阳区", "distance": 0.8},
        "productInfoList": [
            {"productId": 1, "skuCode": "SKU-STL", "name": "生椰拿铁", "amount": 1, "orderPayAmount": 19.9}
        ],
        "orderCommodityList": [
            {"commodityId": 1, "commodityCode": "C-STL", "commodityName": "生椰拿铁",
             "payableMoney": 19.9, "payMoney": 19.9}
        ],
        "orderType": "self_pickup",
        "customerParams": {"note": "少冰"},
    },
    "ord_1002": {
        "orderId": "ord_1002",
        "orderStatus": 80,
        "orderStatusName": "已完成",
        "takeMealCodeInfo": {"code": "B456", "takeOrderId": "tk_1002"},
        "shopInfo": {"deptId": 100, "deptName": "瑞幸·国贸店", "address": "北京市朝阳区", "distance": 0.8},
        "productInfoList": [
            {"productId": 2, "skuCode": "SKU-LAT", "name": "厚乳拿铁", "amount": 1, "orderPayAmount": 22.0}
        ],
        "orderCommodityList": [
            {"commodityId": 2, "commodityCode": "C-LAT", "commodityName": "厚乳拿铁",
             "payableMoney": 22.0, "payMoney": 22.0}
        ],
        "orderType": "self_pickup",
    },
}


async def search_orders_handler(args: OrderIdInput) -> LuckinOrder:
    """真实业务动作：只读订单。注意 user_id 之类的身份信息不在这里，见下方疑问解答。"""
    await asyncio.sleep(0.05)                       # 模拟一次网络往返
    row = _ORDER_DB.get(args.order_id)
    if row is None:
        raise LookupError(f"order not found: {args.order_id}")
    return LuckinOrder.model_validate(row)


async def execute(call: ToolCall) -> dict:
    """极简 Runtime：校验入参 → 执行 handler → 校验输出 / 构造结构化错误 → 带上原 ID 返回。"""
    # Input Schema 校验（不信任模型给的 JSON 字符串）
    try:
        args = OrderIdInput.model_validate_json(call.arguments_json)
    except Exception as exc:
        error = ToolError(code="INVALID_ARGUMENT", message=str(exc))
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps({"error": error.model_dump()}, ensure_ascii=False),
        }

    try:
        output = await search_orders_handler(args)
    except LookupError:
        error = ToolError(code="NOT_FOUND", message="订单不存在或不属于当前用户")
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps({"error": error.model_dump()}, ensure_ascii=False),
        }

    # Output Schema 验收（此处 handler 已返回模型实例，生产中应对裸 dict 再 model_validate 一次）
    output = LuckinSearchTool.output_model.model_validate(output)
    return {
        "role": "tool",
        "tool_call_id": call.id,        # ← 必须带回原 ID
        "content": output.model_dump_json(by_alias=True),
    }


async def run_parallel_out_of_order() -> list[dict]:
    """故意让 call_B 先完成，验证「完成顺序 ≠ 生成顺序」时结果仍然不会错配。"""
    calls = build_tool_calls()
    delays = {"call_A": 0.30, "call_B": 0.10}       # A 先发出但后完成
    finished_order: list[str] = []

    async def bound(call: ToolCall) -> dict:
        await asyncio.sleep(delays[call.id])
        finished_order.append(call.id)
        return await execute(call)

    results = await asyncio.gather(*(bound(c) for c in calls))
    print(f"  生成顺序: {[c.id for c in calls]}")
    print(f"  完成顺序: {finished_order}")

    # 步骤 4 的核心断言：按 ID 配对，而不是按顺序配对
    for call, result in zip(calls, results):
        assert result["tool_call_id"] == call.id, f"结果错配: {call.id} -> {result['tool_call_id']}"

    by_id = {r["tool_call_id"]: r for r in results}
    for call in calls:
        payload = json.loads(by_id[call.id]["content"])
        print(f"  {call.id} -> {call.arguments_json} -> orderId={payload.get('orderId')}, "
              f"status={payload.get('orderStatus')}")

    # 反面对照：若按「完成顺序」贴回「生成顺序」（不看 ID），就会错配
    by_id_tmp = {r["tool_call_id"]: r for r in results}
    completion_ordered = [by_id_tmp[cid] for cid in finished_order]
    mispaired = {c.id: r["tool_call_id"] for c, r in zip(calls, completion_ordered)}
    print(f"  [X] 只按完成顺序贴回 -> {mispaired}  <- call_A 拿到了 call_B 的结果")
    return results


async def main() -> None:
    print("=== 步骤 1：名称 / 描述 / Input Schema ===")
    print(f"  name        = {TOOL_NAME}")
    print(f"  description = {TOOL_DESCRIPTION}")
    print(f"  Input 字段  = {list(OrderIdInput.model_fields)}")

    print("\n=== 步骤 2：模型可见的 Tool JSON ===")
    print(json.dumps(step2_model_visible_json(), ensure_ascii=False, indent=2))
    print("  自检通过：无 handler / permission / risk / 内部依赖")

    print("\n=== 步骤 3 + 4：两条 Tool Call → Tool Result（乱序完成）===")
    await run_parallel_out_of_order()
    print("\n  断言通过：每条 Tool Result 都带回原始 tool_call_id")


if __name__ == "__main__":
    asyncio.run(main())


# ============================================================
# 4.3 最后的疑问
# ============================================================

# 问：构造 Tool Call —— 这个不是模型返回的吗？我自己怎么构造呢？
#
# 答：两条路径都要会，而且「自己构造」是课程要求的能力（课堂练习 4.2 第 3 步）。
#
#   (a) 真实链路：从模型响应里取，不自己拼
#       模型返回 assistant.tool_calls，每个 raw_call 是 {id, function:{name, arguments}}。
#       我们只做一次「协议对象 → 运行时对象」的转换：
#           ToolCall(id=raw_call.id,
#                    name=raw_call.function.name,
#                    arguments_json=raw_call.function.arguments)
#       见 minimal_tool_loop.py 第 60~65 行。
#       所以 ToolCall 是 Runtime 的内部结构，不是模型发明的类；
#       id 由服务端生成，我们只负责原样传递，绝不改写。
#
#   (b) 确定性验收（CLI / 单测）：绕过模型，手工构造
#       目的不是替代模型，而是把「模型输出」当作一个可伪造的输入，
#       用来固定验证 Runtime 的入参校验、权限、重试和结果配对是否正确。
#       本文件 step3/step4 就是这种写法：模型不在场，Runtime 也必须行为正确。
#       这正是课程说的「CLI 绕开模型，确定性验收 Runtime」。
#
#   为什么必须有 (b)？因为模型输出是概率的，测不稳；
#   而 Runtime 是确定性的，必须能被确定性地证明 —— 尤其是
#   「非法调用不会进入 handler」「结果不会错配」这两条验收重点。
#
#   顺带回答：为什么 id 不能自己编？因为真实链路里 id 是模型的 Tool Call 与服务端
#   Tool Result 之间唯一的对账凭证；自己编的 id 只能用在测试输入侧，
#   写回模型的那条 Tool Result 必须引用原调用的 id。
