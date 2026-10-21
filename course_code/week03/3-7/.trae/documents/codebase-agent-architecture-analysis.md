# 3-7 仓库全面架构与功能分析 —— 交付计划

## Context

用户要求对 `d:\study\ai-agent-fullstack-training\course_code\week03\3-7`（即 `project3` Codebase Agent 项目）进行**全面的架构与功能分析**，按 6 个维度结构化输出：核心功能定位 / 整体架构设计（含架构图）/ 技术栈说明 / 完整使用指南 / 核心流程解析 / 可扩展点说明。

要求：内容准确对应仓库实际代码，避免脱离代码的主观推断。

**当前状态**：全部源码已通读完毕（30 个 TS 源文件 + Python HITL 服务 + 配置 + 样例 + 讲义 + README），目录结构已通过 Glob 复核确认。本任务为"分析报告交付"，**不涉及任何代码修改**。

## 交付物

1. **内联架构图**：通过 `PureShowWidget` 渲染分层架构 SVG（6 层纵向结构 + 外部依赖），遵循 dynamic-ui 规范（green 主题、neutral+brand 双色、边界虚线容器）。
2. **对话内结构化分析报告**：6 个维度完整输出。

## 执行步骤

### 步骤 1：渲染架构图（PureShowWidget）
- viewBox `0 0 760 830`，6 层边界 + 外部依赖层：
  - **入口层**：CLI 入口（commander）、pi 扩展点（coding-agent-extension）
  - **装配层**：配置加载（config.ts/tasks.ts）、注册+契约自检（registry/contract verifyContracts）、策略·沙箱·账本（policy/sandbox/store）
  - **Loop 层**：runAgentLoop、决策器（real/auto/mock）、上下文压缩（context-budget）
  - **治理层**（c-brand 焦点，四道检查横排）：① 参数校验 → ② 契约+策略 → ③ 预算守卫 → ④ 审批门口
  - **工具层**：读工具 ×6、写/执行 ×4
  - **外部依赖**：SQLite 账本（audit/trace/approvals/tickets）、LangGraph 审批服务
- 主干箭头 A3/A4/A5 用 `--brand`，入口/外联箭头用中性色，标准三角 marker
- 关键引用文件：`src/platform.ts`、`src/cli.ts`、`src/runtime.ts`、`src/pi/agent-runner.ts`、`hitl/graph.py`

### 步骤 2：输出 6 维度分析报告

**1. 核心功能定位**
- 业务场景：受治理的 AI 编码智能体（Codebase Agent）——AI 直接操作真实代码仓库，但全程受"两层契约 + 四道检查 + 全量审计 + 人工审批"约束
- 解决的问题：让 AI 编码从"不可控的补全助手"变为"可审计、可审批、可评估的企业级生产工具"
- 用户群体：开发者/维护者（trainer-1/maintainer 角色）、审批人（approvers: maintainer/tech_lead）、评估场景
- 核心能力边界：十件仓库工具（6 读 + 2 写 + 2 执行 + git）、受沙箱路径红线约束、写/执行必须过策略与审批、模型不可见的治理层

**2. 整体架构设计**
- 目录结构树（基于 Glob 复核结果）
- 分层架构：入口层 → 装配层 → Loop 层 → 治理层 → 工具层 → 外部依赖，层间调用关系
- 关键组件调用链：CLI/pi → `buildPlatform()` → `runManagedAgent` → `ToolRuntime.invoke` → PolicyEngine/Sandbox → 工具 → SQLite 落库；审批经 `gateForPi` → LangGraph 服务
- 配置三层叠加：`platform.yaml` < `tasks.yaml` 条目 < CLI `--dir`；`HITL_MODE` 环境变量最大

**3. 技术栈说明**
- TypeScript + Node.js（node:sqlite 内置）、pi Agent 框架（@earendil-works/pi-* 0.87.1）、commander CLI、TypeBox schema、yaml 配置、vitest/tsx
- Python + Starlette（HTTP 门面）、LangGraph 1.2.11（审批图 + interrupt + checkpointer）
- DeepSeek 模型（deepseek-v4-flash）、离线决策脚本（scripted）
- 各项选型作用说明

**4. 完整使用指南**
- 前置环境：Node ≥ 20.x（node:sqlite 需 22+ 内置或 20 experimental）、Python ≥ 3.x
- 依赖安装：`npm install`（v2 目录）、`pip install -r hitl/requirements.txt`
- 构建/检查/测试脚本：`npm run build / check / test`
- 配置修改：platform.yaml / tasks.yaml / prompts.yaml / scripts
- 启动运行：CLI 三终端演示（agent 终端 + 离线决策终端 + HITL 审批终端）、pi 入口、切回离线、`approvals list/decide`、`eval` 评估
- 常见问题排查：HITL 服务未启动、无 eligible approver、decider 降级（MODEL_UNAVAILABLE/SCRIPT_REQUIRED）、沙箱路径违规、审批服务连不上

**5. 核心流程解析（2 个场景）**
- 场景一（understand / 离线）：CLI agent 命令 → `resolveTask` 路由 → 决策器（scripted 离线脚本）→ `runAgentLoop` → 每轮 tool_call 走四道检查 → `search_code`/`read_file` → 写交付物 → `verifyDeliverable` 回读审计
- 场景二（fix_tests / HITL）：运行 `run_test` 触发 `gate: [run_test]` → 审批门口 → HTTP 到 LangGraph `check_eligible → request_human(interrupt) → check_approver` → 人工 `/resume` 决议 → 回传 → claim 一次性消费 → 契约/策略重跑 → 执行 → 审计落库

**6. 可扩展点说明**
- `tasks.yaml` 纯配置新增任务（如 debt_audit 示例）
- 注册新工具：registry 双 Map + contract.ts 语义规则 + 策略权限 + TypeBox schema
- 决策器三档（real/auto/mock）可插拔，降级必说破
- HITL `via: local/http` 切换、approvers 名单配置
- `prompts.yaml` 提示词模板（Prompts Registry / local）
- pi 扩展点新增入口（managed-* 参数）
- 适配注意事项：risk 三档为 read/write/high（文档曾写 execute，以代码为准）、路径相对化契约、契约自检失败即启动失败、deliverable 三布尔（delivered/model_claims/claim_without_evidence）

## 验证方式

- 架构图中各框与代码文件一一对应（文件链接核对）
- 报告事实均来自已读源码：配置优先级、四道检查顺序、审批指纹六维、工具清单、决策器降级口径、README 操作步骤
- 完成后用户可对照 [README.md](file:///d:/study/ai-agent-fullstack-training/course_code/week03/3-7/project3/README.md) 复跑验证使用指南

## 不做的事

- 不修改任何源代码/配置
- 不创建额外文件（报告直接在对话输出；架构图为内联 widget）
