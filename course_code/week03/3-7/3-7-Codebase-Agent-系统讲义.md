# 3.7 Codebase Agent v3 · 系统讲义

> 配套材料：`course_materials/week03/3-7.pdf`（36 页）、`project3/`（v2 运行时 + 两个样本仓库）
> 阅读方式：按「讲」的顺序线性读。每一讲都是同一套四段式 ——
> **核心知识点 → 模块/函数详解 → 架构设计思想与模式 → 整体演进位置**。
> 代码路径一律相对 `project3/v2/`。

---

## 第 0 讲 · 先建立心智模型：这一节到底在解决什么问题

### 0.1 一句话结论

阶段二解决的是「**模型提出的一次工具调用，能不能被安全地执行**」。
阶段三（本节）解决的是「**把这个能力串成一个能连续思考、执行、观察、纠错、并且能收口的完整任务**」。

### 0.2 用一个生活类比先立住

| 概念 | 类比 |
| --- | --- |
| 阶段二 Runtime | 一个**电工**：你让他接一根线，他检查线径、断电、验电，然后接上。一次一单。 |
| 阶段三 Codebase Agent | 一个**装修队**：领了「把这套房子水电走一遍并出验收报告」的活儿，自己规划步骤、反复进场、遇到墙里有问题要请示业主、干完自己验收、最后交报告。 |
| Loop | 装修队的「开工 → 干活 → 看结果 → 决定下一步」循环 |
| Planning / State | 施工进度表 + 当前进度 |
| Checkpoint | 施工日志（**注意：日志不能撤销已经砸掉的墙**） |
| Sandbox | 只允许在这套房子里施工，不许动邻居家 |
| Harness | 包工头：管预算、管停手、管收口 |
| 审批（HITL） | 砸承重墙必须业主签字 |

### 0.3 两类验收任务

| | 任务一 `understand` | 任务二 `fix_tests` |
| --- | --- | --- |
| 目标 | 找出登录逻辑，写 Markdown 说明文档 | 补测试、读失败日志、修源码、复测 |
| 样本仓库 | `samples/1_login_demo`（只读 + 只写一份文档） | `samples/2_bug_fix/demo-app`（跑测试 + 只改 `src`） |
| 交付物 | `artifacts/login-flow.md` | `src/auth/session-policy.ts` |
| 验收依据 | 文档是否落盘 + 内容是否有文件行号依据 | `run_test` 退出码 + `git_diff` |
| 审批 | 本地表（`via: local`） | LangGraph 图（`via: http`） |

### 0.4 本节的四条硬要求（PDF 第 6 页）

```
可运行   —— 真能跑起来，两类任务端到端验收
可验证   —— 产物、测试、差异、执行记录能复核
可恢复   —— 审批中断、结果不明时，不盲目重放写操作
可继续演进 —— 接新任务改配置，接新能力改代码
```

**这四条是后面所有设计的评判标准。** 每看到一个模块，就问：它贡献了哪一条？

---

## 第 1 讲 · 先看森林：把两类任务各跑一遍

> PDF 第二章 2.1–2.4。先见结果，再拆机制。不要反过来。

### 1.1 目录名对齐（README 的坑，先记住）

| 课纲说法 | 实际路径 |
| --- | --- |
| `sample/1_login_demo` | `samples/1_login_demo` |
| `sample/2_bugfix` | `samples/2_bug_fix/demo-app` |

### 1.2 基线技术栈

```
TypeScript (Node >= 22.19, tsx 直跑)  ——  Agent 与工具运行时   v2/
Python (LangGraph + FastAPI)          ——  审批服务             v2/hitl/
SQLite (node:sqlite)                  ——  本地账本             v2/data/platform.db
```

### 1.3 任务一：三个动作

```bash
cd project3/v2

# ① 领任务开跑（终端 A）
node --import tsx src/cli.ts agent "帮我找出该项目的登录逻辑，并生成 Markdown 说明文档。" \
  --dir ../samples/1_login_demo

# ② 人批（终端 B）—— 注意填的是 pending_approval_id，不是 trace_id
node --import tsx src/cli.ts approvals decide <pending_approval_id> \
  --decision approve --actor trainer-1 --roles maintainer --task understand
node --import tsx src/cli.ts approvals execute <pending_approval_id> --task understand

# ③ 验收
cat ../samples/1_login_demo/artifacts/login-flow.md
node --import tsx src/cli.ts audit --trace-id <trace_id>
```

**两个 id 别混**（这是新手第一坑）：

| id | 标识什么 | 给谁用 |
| --- | --- | --- |
| `trace_id` | **这一整趟 Run** 的编号 | `audit --trace-id` |
| `pending_approval_id` | **那一张等人批的写入单** | `approvals decide` / `approvals execute` |

类比：`trace_id` 是装修队的**工单号**，`pending_approval_id` 是其中**某一张需要业主签字的变更单**。

`decide` 只记录授权（不碰文件），`execute` 才真正落盘。**这是两个动作，不是一步。**

### 1.4 任务二：为什么需要三个终端

```bash
# 终端 1：把审批图起起来（LangGraph 服务，会一直占着终端）
HITL_API_KEY=demo-key HITL_DB=/tmp/hitl-demo.db ../.venv/bin/python -u hitl/service.py

# 确认活着（另开一条命令）
curl -s -H "Authorization: Bearer demo-key" http://127.0.0.1:8383/health

# 终端 2：领任务开跑
HITL_API_KEY=demo-key node --import tsx src/cli.ts agent "给登录会话模块补充测试并修复失败用例" \
  --task fix_tests --dir ../samples/2_bug_fix/demo-app

# 终端 3：逐单批
HITL_API_KEY=demo-key node --import tsx src/cli.ts approvals tickets --task fix_tests
HITL_API_KEY=demo-key node --import tsx src/cli.ts approvals decide <ticketId> \
  --decision approve --actor lead-1 --roles tech_lead --task fix_tests
```

**为什么要三个终端？** 因为任务二把 `run_test` 点名进了审批门口（`config/tasks.yaml:73-76`）。
`run_test` 自带「不需确认」，但它要执行仓库里的 npm script，所以这一趟必须过人。
而审批由**另一台服务**（LangGraph 图）裁定 —— 那台服务得单独占一个终端。

### 1.5 基线红绿状态（验收锚点）

```bash
# 开工前
npm --prefix ../samples/2_bug_fix/demo-app test --silent | grep "ℹ tests\|ℹ pass\|ℹ fail"
# → tests 7 / pass 4 / fail 3

# 跑完之后
# → tests 7 / pass 7 / fail 0
git -C ../samples/2_bug_fix/demo-app diff --stat
# → src/auth/session-policy.ts | 4 +---   1 insertion(+), 3 deletions(-)
```

### 1.6 缺陷本身（先看懂这个 bug，后面所有机制都围绕它）

`samples/2_bug_fix/demo-app/src/auth/session-policy.ts`：

```ts
// 缺陷版本：只比到「哪一天」，没比到「哪一刻」
export function isSessionExpired(session: ExpiringSession, now: Date): boolean {
  const expiresOn = session.expiresAt.slice(0, 10);      // "2026-09-11"
  const currentDay = now.toISOString().slice(0, 10);     // "2026-09-11"
  return expiresOn < currentDay;                          // 同一天 → 永远 false
}
```

三条红用例全落在**同一天**的不同时刻（`tests/session-boundary.test.ts`）：

| 用例 | now | 期望 | 缺陷版实际 |
| --- | --- | --- | --- |
| 到期前仍然有效 | `00:29:59.999Z` | `false` | `false` ✅ |
| 到期时刻视为已过期 | `00:30:00.000Z` | `true` | `false` ❌ |
| 到期后立即失效 | `00:30:00.001Z` | `true` | `false` ❌ |

正确做法（`config/scripts/fix-session-boundary.yaml:33-36`）：

```ts
// 拿整串时间戳比，而不是截成日期字符串比
export function isSessionExpired(session: ExpiringSession, now: Date): boolean {
  return new Date(session.expiresAt).getTime() <= now.getTime();
}
```

### 1.7 「可反复执行」：离线决策脚本

真模型不照脚本走，可能烧满 12 次工具调用停在 `MAX_TOOL_CALLS`，每趟输出都不一样。
所以要有一套**确定性、不联网、可逐字重跑**的口径：

```bash
node --import tsx src/cli.ts agent "..." --dir ../samples/1_login_demo --decider mock
```

`--decider` 三档（`src/cli.ts:87`）：

| 档位 | 含义 | 没密钥时 |
| --- | --- | --- |
| `real`（默认） | 直连 DeepSeek | 降级到任务条目的离线脚本，**并在开头说破** |
| `auto` | 离线优先，有脚本就用脚本 | 同左 |
| `mock` | **只准离线** | 没脚本直接报 `SCRIPT_REQUIRED` |

**设计思想**：「谁在决策」必须可见。三种口径都会把这一行打在开头，并写进 `decider.selected` 这笔账。
**为什么重要**：如果悄悄换了脑袋，你以为在测真模型，其实跑的是脚本 —— 所有结论都作废。

### 1.8 复原（每次跑完必做）

```bash
rm -rf ../samples/1_login_demo/artifacts
git -C ../samples/2_bug_fix/demo-app checkout -- src/auth/session-policy.ts
git -C ../samples/2_bug_fix/demo-app status --porcelain -uall   # 输出为空＝已复原
pkill -f "hitl/service.py"
```

---

## 第 2 讲 · 第一步：任务进入与配置三层叠加

> PDF 7.2 第一步。主线文件：`src/platform.ts`（只有 91 行，先读它）。

### 2.1 核心知识点：配置不是「读一个文件」，是**三层叠加**

```
platform.yaml（平台默认值）
      ↓  被覆盖
tasks.yaml（这一类任务的条目）
      ↓  被覆盖
命令行 --dir（人这次显式指定的）
```

### 2.2 模块详解：装配一条线（`src/platform.ts:32-69`）

```ts
// ① 读平台配置
const loaded = loadConfig(options.configPath, options.workspace);
// ② 选任务：命令行点名 > 目标里的关键词路由 > 不选（退回阶段二行为）
const selected = resolveTask(loaded, { taskId: options.task, goal: options.goal });
// ③ 三层叠加，优先级：platform.yaml < 任务条目 < 命令行 --dir
const config = selected
  ? applyTask(loaded, selected, options.workspace ? resolve(options.workspace) : undefined)
  : loaded;
// ④⑤ 沙箱与账本
const sandbox = new Sandbox(config.sandbox);
const store = new PlatformStore(config.runtime.database);
// ⑥ 策略引擎：注意 gate 是构造参数，不是工具元数据
const policy = new PolicyEngine(config.policy, sandbox, config.hitl.gate);
// ⑦ 注册表 + 十件工具
const registry = new ToolRegistry();
for (const tool of createRepoTools(config, sandbox)) registry.register(tool);
// ⑧ 启动自检：契约有毛病就在这里炸
const problems = verifyContracts(registry.list());
if (problems.length > 0) throw new Error(`CONTRACT_SELF_CHECK_FAILED: ...`);
// ⑨ Runtime：校验 → 权限 → 预算 → 审批 四道检查的持有者
const runtime = new ToolRuntime(registry, policy, store, createHitlGateway(config.hitl), ...);
```

**这一段就是整个项目的骨架。** 九个动作，缺一不可。

### 2.3 关键设计点 A：`gate` 为什么是构造参数而不是工具元数据

`src/platform.ts:41` → `new PolicyEngine(config.policy, sandbox, config.hitl.gate)`

同一件 `write_file`，在任务一里要过人，在任务三里可以不过人 ——
差别全在 `tasks.yaml` 的那一个条目里。**如果把「要不要过人」写死在工具定义上，就做不到按任务分置。**

注释原文（`src/policy.ts:17`）：
> 门口开关（gate）：按任务类型分置，所以它是构造参数而不是工具元数据。

### 2.4 关键设计点 B：启动自检

`src/platform.ts:46-51`。契约写错是**「看起来一切正常、真要拦时一句都没拦住」**的故障。
所以在装配阶段就念出来，而不是等模型跑到第 5 轮才发现。

### 2.5 任务解释器：`src/tasks.ts`

三个函数，各司其职：

| 函数 | 职责 | 行号 |
| --- | --- | --- |
| `resolveTask` | 选哪类任务：点名 > 关键词路由 > 不选 | `145-153` |
| `matchTask` | 自上而下第一个命中的赢 | `129-138` |
| `applyTask` | 任务知识覆盖平台默认值 | `161-182` |

`applyTask` 做四件覆盖（`src/tasks.ts:161-182`）：

```ts
sandbox: {
  ...config.sandbox,
  root: workspaceOverride ?? task.workspace ?? config.sandbox.root,
  // deny_write 先封，allow_write 再开
  denyWrite:  [...config.sandbox.denyWrite,  ...task.denyWriteExtra],
  allowWrite: [...(config.sandbox.allowWrite ?? []), ...task.allowWriteExtra],
},
runtime: { ...config.runtime, ...task.budget },
tools:   { testCommand: task.testCommand ?? [] },
hitl:    { ...config.hitl, gate: ..., approvers: ..., mode: ... },
```

**「deny 先封，allow 再开」是本节的优化项 1**（PDF 8.5）：
`tests/**` 整体封死（保护已有测试） → `tests/generated/**` 单点放开（允许新增测试）。
靠改测试让红用例变绿这条路被沙箱堵死。

### 2.6 关键设计点 C：环境变量那一层永远最大

`src/tasks.ts:179`：

```ts
mode: hitlModeFromEnv() ?? (task.approval.via === undefined ? config.hitl.mode : ...),
```

注释说得很直白：
> 命令行/环境变量那一层始终最大：同一条命令加个 `HITL_MODE=local` 前缀就能脱离图跑，
> 这是课堂与 CI 的逃生口，不能被任务条目反过来锁住。

**失败时要有逃生口**，这是工程直觉。如果配置写死、服务又起不来，人就卡死了。

### 2.7 路由失败必须抛错，不默默兜底

`src/tasks.ts:129-138`：

```ts
throw new Error(
  `TASK_TYPE_UNMATCHED: 这句话没命中任何任务类型的关键词；已有 ${describeIds(tasks)}。` +
  `要接这类活儿，在 config/tasks.yaml 给对应条目加关键词，或者加一个新条目。`,
);
```

**错误信息要指出「下一步改哪儿」**。这是全项目的一致风格，值得学。

### 2.8 演进位置

这一步是从阶段二「打开一个仓库、用一套固定配置」升级到「**领了任务才知道打开哪个仓库、用哪套预算和审批**」。
`debt_audit`（任务三）是这条设计论据的证明：**纯配置新增的任务类型，TypeScript 一行未改**。

---

## 第 3 讲 · 第二步：准备计划与受控上下文

> PDF 7.2 第二步。主线文件：`src/pi/prompt-client.ts` + `config/prompts.yaml`。

### 3.1 核心知识点：提示词是**模板 + 变量**，缺变量要报错

`config/prompts.yaml:6-12` 声明了六个必填变量：

```yaml
required_variables:
  - tenant_id
  - user_id
  - agent_name
  - task_name
  - task_brief
  - deliverable
```

**这是本节的优化项 3**（PDF 8.5）：清单原本只列了三个，模板实际用了六个 ——
缺变量时**报错**，而不是静默留占位符。

类比前端：`required_variables` 就是 Vue props 的 `required: true`。
静默留 `{{ task_brief }}` 这种空占位符，等于页面上渲染出一堆 `undefined` 还以为是正常的。

### 3.2 模板里那六条工作方式值得逐句读

`config/prompts.yaml:17-27`：

```
1. 先定位，再阅读。用 search_code 或 list_files 找到候选文件，然后用 read_file 读它们。
   不要凭文件名猜内容，也不要在没读过代码之前描述实现。
2. 一次只做一个小步。改代码前先用 git_status 拍一张现状，改完再拍一张。
3. 判断对错以 run_test 的退出码为准，不以自己读代码的印象为准。
4. 写文件优先用 apply_patch，整文件重写只用于新建文件。
5. 收尾必须交付一段人话结论。
6. 预算有限：信息够了就立刻产出交付物 —— 停在那里等于一份交付物都没交。
```

**第 3 条和第 6 条是最值钱的两条：**
- 第 3 条把「验收权」从模型手里拿走，交给程序。
- 第 6 条承认「模型会为了更全而耗尽预算」这个真实失败模式，并给出反制指令。

### 3.3 「边界」那一段：把错误码教给模型

`config/prompts.yaml:29-39`：

```
- 工具返回 deny 或 confirm 时，读 reason 字段，按它给的原因改变做法，原样重试没有意义。
- 收到 INVALID_ARGUMENT 或 CONTRACT_ 开头的拒绝时：错误里点名的那个字段就是问题所在，
  只改它，其余字段保持原样。同一份参数重发第二遍会被判成重复调用，第三次直接停摆。
- 上下文有限。工具输出被截断时按提示的 offset 或 path 缩小范围续读。
- 早期步骤会被压成一行摘要（以 [上下文压缩] 开头）。摘要只说明"调了哪个工具、参数是什么、
  结果码与规模多大"，不含正文：要基于代码内容下结论，就照抄摘要里的参数重新调用，
  或者明说你看不到那段原文。
```

**这是「提示词与实现对齐」的范例**：提示词里提到的每一个机制（截断、压缩、重复调用护栏、契约前缀），
代码里都真实存在。反过来，如果提示词说了代码没做的事，模型会照着做然后撞墙。

### 3.4 变量来源：`task_brief` 和 `deliverable` 从哪来

答：从**任务条目**来（`config/tasks.yaml` 的 `brief` / `deliverable` 字段）。

```
config/tasks.yaml  understand.brief ──┐
                                      ├─→ 渲染进 prompts.yaml 的 {{ task_brief }}
config/tasks.yaml  understand.deliverable ─→ {{ deliverable }}
```

所以 PDF 说：「提示词带上任务简报与交付物路径：**领了任务就按那一类说话**」。

### 3.5 验收口径

- `prompts.yaml` 改一行，下一轮提示词跟着变（模板驱动，不是硬编码）
- 离线脚本路径与真实模型**共用同一份上下文**（后面第 7 讲会看到只有决策器不同）
- 输入超预算时本轮不发请求，停止原因可查

---

## 第 4 讲 · 让工具调用有契约（PDF 第四章）

> 主线文件：`src/contract.ts`（299 行，本节最值得精读的文件）。

### 4.1 核心知识点：契约分**两层**，两层的写法不一样，因为**受众不一样**

```
第一层 · 声明式边界  —— 写在工具的 TypeBox 参数定义里（minimum / maximum / minLength / minItems）
                     —— 受众：模型。这是它唯一能看见的说明书，也是上游校验器的依据。

第二层 · 语义规则    —— 写在 src/contract.ts 里
                     —— 受众：Runtime。拦的是「schema 全对、沙箱也放行，但注定办不成事」的参数。
```

**关键洞察（PDF 4.2 全文第一句）：模型展示与执行校验使用同一份工具定义。**

类比前端：表单校验。**第一层**是 `<input min="1" max="500">` + 输入框下面的提示文字 ——
用户（模型）看得见，浏览器也会自动校验。**第二层**是提交后的业务校验 ——
「这个用户名已被占用」，HTML 属性表达不了，只能写 JS。

### 4.2 十件工具的 risk 分档

`src/tools/index.ts:9` 一句话说清：

```ts
/** 十件仓库工具：六件读、两件写、两件执行，risk 直接决定策略与审批分支。 */
```

| risk | 工具 | 策略 |
| --- | --- | --- |
| `read` | `list_files` `search_code` `read_file` `read_directory` `git_diff` `git_status` | 自动执行 |
| `write` | `write_file` `apply_patch` | 按任务策略进审批 |
| `execute` | `run_test` `run_command` | 按任务策略进审批 |

> 注：`domain.ts:3` 里 `RiskLevel = "read" | "write" | "high"`，而 PDF 写的是 `read / write / execute`。
> 代码里执行类标注为 `"high"`。**这是文档与代码的一处不一致**，以代码为准。

### 4.3 第二层的六条语义规则（`src/contract.ts:108-123`）

```ts
const RULES: Record<string, ContractRule[]> = {
  read_file:      [pathMustBeRelative("path"), pathMustNotBeDirectory("path", "read_directory")],
  read_directory: [pathMustBeRelative("path")],
  list_files:     [pathMustBeRelative("path"), globMustMatchRelativePaths("pattern")],
  search_code:    [pathMustBeRelative("path"), globMustMatchRelativePaths("glob"), searchPatternMustCompile()],
  write_file:     [pathMustBeRelative("path"), pathMustNotBeDirectory("path", "read_directory")],
  apply_patch:    [pathMustBeRelative("path"), patchMustChangeSomething()],
  run_test:       [pathMustBeRelative("test_file")],
  run_command:    [commandMustNotBeBlank()],
  git_diff:       [pathMustBeRelative("path")],
  git_status:     [],
};
```

每条规则的形状（`src/contract.ts:14-24`）：

```ts
export interface ContractRule {
  code: string;     // 统一 CONTRACT_ 前缀：审计里一眼分得清是契约拦的、策略拦的、还是工具自己报的
  fields: string[]; // 这条规则读哪几个字段 —— 启动自检据此抓字段名手误
  why: string;      // 给人看的一句话：这条规则为什么存在
  violated(args, context): boolean;
  message(args, context): string;  // 违规时念给模型听的那句：点名哪个字段、给出正确写法
}
```

**`why` 字段是这六条规则的精华**，逐条读一遍你就懂了为什么需要第二层：

| 规则码 | 拦什么 | 为什么必须有（原文摘录） |
| --- | --- | --- |
| `CONTRACT_PATH_MUST_BE_RELATIVE` | 绝对路径 | 「绝对路径会把本机目录结构写进审计与审批指纹，换台机器就对不上」 |
| `CONTRACT_PATH_IS_DIRECTORY` | 以 `/` 结尾 | 「读它只会拿到一句操作系统给的 EISDIR；看目录结构该用 `read_directory`」 |
| `CONTRACT_GLOB_NEVER_MATCHES` | glob 以 `/` 开头 | 「比对用的是相对路径，以 `/` 开头就没有任何文件能命中，白扫一轮」 |
| `CONTRACT_PATTERN_NOT_REGEX` | 括号不配对 | 「与其让工具报错，不如在门口说清两种写法」 |
| `CONTRACT_PATCH_NO_CHANGES` | edits 全是空操作 | 「空操作也要占用一次审批额度」 |
| `CONTRACT_COMMAND_BLANK` | 命令只有空白 | 「会真的起一个 shell，退出码 0，什么也没做 —— 审批单上却已经花掉一次人工确认」 |

最后一条尤其妙：**它拦的不是错误，是浪费。**

### 4.4 契约违规的回喂：三段式

`src/runtime.ts:88-92`：

```ts
return this.reject(
  request, "INVALID_ARGUMENT",
  `${detail}\n${describeContractFor(tool)}\n只改上面点名的字段，其余字段保持原样；同一份参数重发会被判成 REPEATED_TOOL_CALL。`,
);
```

三段：**错在哪 → 合格长什么样 → 下一步怎么做**。
上游校验器只说「这个字段不合格」，`describeContractFor`（`src/contract.ts:264-272`）补上「合格长什么样」。

### 4.5 启动自检：三个检查（`src/contract.ts:149-212`）

```ts
export function verifyContracts(tools: RegisteredTool[]): string[] {
  return [...verifyToolSchemas(tools), ...verifyContractRules(tools)];
}
```

| 检查 | 抓什么 | 为什么 |
| --- | --- | --- |
| schema 不是对象 | `参数定义不是对象 schema，上游校验器无从校验` | 基础 |
| `additionalProperties !== false` | `模型多塞的键会一路进 handler` | 多余字段不该静默通过 |
| 字段没有 `description` | `schema 是模型唯一能看到的说明书` | 没说明 = 模型瞎猜 |
| `limit` 没写下/上界 | `0 与负数会直接被上游纠正成空结果` / `一次调用就能塞满上下文窗口` | 两端都要卡 |
| 规则挂在不存在的工具上 | `这条规则永远不会生效` | **死代码检测** |
| 规则读的字段不在 schema 里 | `规则会永远拿到 undefined` | **字段名手误检测** |
| 工具没有任何语义规则 | `确认它是否真的无参数可错` | 提醒补 |

**最后三条是自检的真正价值**：它们抓的是「写了规则但规则从来没生效」这种最阴的 bug。

### 4.6 验收（PDF 4.4）

| 场景 | 期望 |
| --- | --- |
| `read_file` 的 `path` 传成数字 `42` | handler 调用次数为 **0**，返回 `INVALID_ARGUMENT` |
| 路径 `../../outside.txt` | **类型正确**但仍被工作区边界拒绝，错误来自正确的检查层 |
| `started: false` | 确认执行尚未发生 |

第三行是重点：`INVALID_ARGUMENT` 的返回体里有 `execution: { started: false }` ——
**「我没执行」这件事本身要能被证明**。

---

## 第 5 讲 · 第三步：Runtime 四道检查

> PDF 7.2 第三步。主线文件：`src/runtime.ts`（624 行，全项目最大的文件）。

### 5.1 核心知识点：四道检查，顺序不可换

```
参数校验(contract) → 权限(policy) → 预算(loop-guard) → 审批(hitl) → 执行
```

**为什么这个顺序？**
- 校验在前：参数都不合法，谈什么权限？
- 权限在预算前：没权限的人不该消耗预算。
- 预算在审批前：预算都不够了，不该去惊动人。
- 审批在最后：只有确定「这事值得做且做得起」了，才去问人。

类比：机场安检。**验票（参数）→ 证件（权限）→ 登机口时间（预算）→ 特殊物品申报（审批）→ 上飞机。**
顺序反了就是「先把人放上飞机再查票」。

### 5.2 `prepare()`：前三道（`src/runtime.ts:70-120`）

```ts
prepare(request: InvokeRequest): PreparedCall | InvocationResult {
  // ① 工具存在吗
  try { tool = this.registry.getByModelName(request.modelName); }
  catch { return this.reject(request, "TOOL_NOT_FOUND", "没有注册该工具"); }

  // ② 结构层校验：字段名、类型、边界
  try { validatedArgs = validateToolArguments(toolToPi(tool), callToPi(...)); }
  catch (error) { return this.reject(request, "INVALID_ARGUMENT", `${detail}\n${describeContractFor(tool)}...`); }

  // ③ 语义层：schema 表达不了、又注定办不成事的参数
  const breach = findContractBreach(tool, validatedArgs, request.context);
  if (breach) return this.reject(request, breach.code, breach.reason, validatedArgs);

  // ④ 策略：可见性 → 权限 → plan 模式 → 沙箱路径 → 审批门口
  const decision = this.policy.evaluate(request.context, tool, validatedArgs);
  if (decision.action === "deny")    return this.reject(...);
  if (decision.action === "confirm") return this.openApproval(...);
  if (decision.code === "APPROVAL_GATE_OFF") { /* 放行但单独留一条审计 */ }

  const prepared: PreparedCall = { ...request, tool, validatedArgs };
  this.prepared.set(request.toolCallId, prepared);
  return prepared;
}
```

### 5.3 策略引擎的五道判断（`src/policy.ts:31-79`）

```ts
evaluate(context, tool, args, options): PolicyDecision {
  // ① 可见性：工具在不在当前 Agent 白名单里        → TOOL_NOT_VISIBLE
  // ② 权限：角色有没有这件工具要求的 permission      → RBAC_DENIED
  // ③ plan 模式：plan 下禁止非 read                  → PLAN_MODE_DENIED
  // ④ 沙箱路径：三个路径参数过 inspect               → PATH_OUT_OF_WORKSPACE / PATH_DENY_*
  // ⑤ 审批门口：gate 三态                            → APPROVAL_REQUIRED / APPROVAL_GATE_OFF / OK
}
```

第 ④ 步有个细节值得注意（`src/policy.ts:10-11`）：

```ts
/** 十件仓库工具里承载路径的入参名。策略层只认这三个键，其余参数不含路径。 */
const PATH_ARGUMENTS = ["path", "file_path", "test_file"];
```

**集中声明「哪些参数是路径」**，避免每件工具各写各的漏掉一个。

### 5.4 `gate` 三态（本讲最重要的概念）

| gate | 行为 | 审计 |
| --- | --- | --- |
| `auto` | 工具自带的 `requiresConfirmation` 说了算 | 正常 |
| `none` | 一个都不拦 | **单独记一条 `APPROVAL_GATE_OFF`** |
| `[工具名单]` | 在 `auto` 之上**追加**：点名的即使自带不需确认也要过人 | 正常 |

`src/policy.ts:65-76`：

```ts
if (this.gate.mode === "none" && tool.metadata.requiresConfirmation) {
  // 放行，但"这次没人看过"必须以一条独立的审计记录下来，不能混在 OK 里。
  return { action: "allow", code: "APPROVAL_GATE_OFF", reason: "本类任务的 approval.gate=none：..." };
}
const listedByTask = this.gate.tools.includes(tool.modelName);
if ((tool.metadata.requiresConfirmation || listedByTask) && !options.approvalSatisfied) {
  return { action: "confirm", code: "APPROVAL_REQUIRED", reason: "..." };
}
```

**「没人看着」和「没记录」是两件事**（`config/tasks.yaml:95` 原文）。
任务三 `debt_audit` 就是 `gate: none` —— 一次检索、一份新报告，不动任何已有文件。

### 5.5 审批单的指纹：批的是「这次这个参数」

`src/store.ts:32-52`：

```ts
export function approvalDigest(input: {
  traceId, toolCallId, toolName, context, args
}): string {
  return createHash("sha256").update(canonicalJson({
    trace_id: input.traceId,
    tool_call_id: input.toolCallId,
    tool_name: input.toolName,
    user_id: input.context.userId,
    tenant_id: input.context.tenantId,
    workspace: input.context.workspace ?? "",   // ← 关键
    args: input.args,
  })).digest("hex");
}
```

**指纹盖住了六个维度**，其中 `workspace` 那一行注释最直白（`src/domain.ts:15`）：
> 审批指纹要盖住它：批"往这个仓库写"不等于批"往任何仓库写"。

而 `canonicalJson`（`src/store.ts:20-30`）把对象键排序后再序列化 ——
**保证 `{a:1,b:2}` 和 `{b:2,a:1}` 得到同一个哈希**，否则换个字段顺序就对不上账。

### 5.6 执行授权单：批准了也不许直接跑（`src/runtime.ts:343-398`）

`executeApproval` 是**硬路径**，七步缺一不可：

```ts
// ① 单子存在且状态是 approved
if (!approval || approval.status !== "approved") return failure("APPROVAL_NOT_EXECUTABLE", ...);

// ② 重算指纹，比对 —— 参数变了旧审批失效
const expected = approvalDigest({...});
if (expected !== approval.args_digest || canonicalJson(args) !== canonicalJson(storedArgs))
  return failure("APPROVAL_BINDING_MISMATCH", "工具参数已变化，旧审批失效");

// ③ 一次性领取：同一张单只能被一条执行路径领走
if (!this.store.claimApproval(id)) return failure("APPROVAL_NOT_EXECUTABLE", "审批已被其他执行者占用");

// ④⑤ 审批单里的参数是从数据库读回来的，没有任何上游校验器看过它 —— 契约与策略重跑一遍
const breach = findContractBreach(tool, validatedArgs, context);
if (breach) { ... return failure(breach.code, breach.reason); }
const policy = this.policy.evaluate(context, tool, validatedArgs, { approvalSatisfied: true });
if (policy.action !== "allow") { ... return failure(policy.code, policy.reason); }

// ⑥ 执行
const result = await this.executePrepared({...});
// ⑦ 记账：consumed 或 failed
this.store.finishApproval(id, result.ok ? "consumed" : "failed", ...);
```

第 ④ 步的注释是全文金句（`src/runtime.ts:375-376`）：
> 审批单里的参数是从数据库读回来的，没有任何上游校验器看过它。
> 契约与策略在这条路上要重跑一遍：**批"往 src/a.ts 写"不等于批"往任何地方写"，
> 也不等于批"这个参数本身是合法的"。**

第 ③ 步对应 PDF 6.2 的「同一审批单只允许一条路径领取」——
**重复批准或重复执行不能重复写入。**

### 5.7 演进位置

这一步是阶段二 Runtime 的直接复用 + 扩展：

| 阶段二 | 阶段三新增 |
| --- | --- |
| 参数校验 | + 语义契约层 |
| 权限 | + 按任务分置的 gate |
| — | **预算**（新增） |
| 审批落本地表 | + 审批可挂 LangGraph 图 + 指纹绑定 + 一次性领取 |

---

## 第 6 讲 · 第四步：在沙箱边界内执行

> PDF 7.2 第四步。主线文件：`src/sandbox.ts`（208 行）。

### 6.1 核心知识点：四类判定在同一个入口做完

`src/sandbox.ts:44-49` 注释原文：
> 仓库工具的边界。四类判定在同一个入口做完：路径是否落在工作区内、是否命中禁止读取清单、
> 写操作是否命中禁止写入清单、以及是否落在允许例外名单里。

```ts
inspect(input: string, options: { write?: boolean } = {}): Violation | undefined {
  const absolutePath = this.absolute(input);
  const real = this.canonical(absolutePath);
  // ① 工作区边界
  if (!this.isInside(real)) return { code: "PATH_OUT_OF_WORKSPACE", reason: `路径 ${input} 解析到工作区 ${this.root} 之外` };
  const rel = this.relativeOf(real) || ".";
  // ② 禁读
  if (matchesAny(rel, this.config.denyRead)) return { code: "PATH_DENY_READ", ... };
  // ③ 禁写（④ 允许例外在其上开口子）
  if (options.write && matchesAny(rel, this.config.denyWrite)) {
    if (!matchesAny(rel, this.config.allowWrite ?? [])) return { code: "PATH_DENY_WRITE", ... };
  }
  return undefined;
}
```

### 6.2 三个容易踩的坑（代码里都有注释说明）

**坑一：符号链接。** `src/sandbox.ts:54-57`：

```ts
// root 自己也要展开：macOS 的 /var 是指向 /private/var 的符号链接，
// 候选路径走 realpath 而 root 不走，会让工作区内的每个路径都被判成越界。
const resolved = resolve(config.root);
this.root = existsSync(resolved) ? realpathSync.native(resolved) : resolved;
```

不用 realpath 展开，`../../outside.txt` 这种路径就绕过去了 ——
因为字符串上看不出它其实指向工作区外。**必须解析到真实路径再比对。**

**坑二：路径还不存在。** `canonical()`（`src/sandbox.ts:68-81`）用「最近已存在祖先」策略：
从路径往上找，找到第一个真实存在的祖先，展开它，再把剩下的部分原样拼回去。
否则新建文件的路径（还不存在）没法 realpath，会被误判成越界。

**坑三：子进程能拿到密钥。** `src/sandbox.ts:117-120`：

```ts
commandEnv(): NodeJS.ProcessEnv {
  const pattern = new RegExp(this.config.secretEnvPattern, "i");
  return Object.fromEntries(Object.entries(process.env).filter(([key]) => !pattern.test(key)));
}
```

配合 `platform.yaml:115` 的 `secret_env_pattern: "(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)$"`。
**模型可以 `run_command`，但拿不到网关密钥。**

### 6.3 命令执行：超时与强制结束（`src/sandbox.ts:122-203`）

```ts
const timer = setTimeout(() => {
  timedOut = true;
  kill("SIGTERM");
  // killGraceMs 之后再补一刀 SIGKILL —— 给子进程一个体面退出的机会，但不无限等
  killTimer = setTimeout(() => kill("SIGKILL"), this.config.killGraceMs);
}, timeoutMs);
```

返回体 `ExecResult` 六件套（`src/sandbox.ts:34-42`）：

```ts
export interface ExecResult {
  exit_code: number | null;   // 退出码
  signal: string | null;      // 被哪个信号杀的
  stdout: string;             // 标准输出
  stderr: string;             // 标准错误
  truncated: boolean;         // 是否被截断
  timed_out: boolean;         // 是否超时  ← 验收要查这一位
  duration_ms: number;
}
```

### 6.4 重试策略：一个反直觉但正确的决定

`src/runtime.ts:482-484`：

```ts
// 基准用 risk == read（而不是仅仅 idempotent）做最终兑底：即使配置把写操作
// 误标成 idempotent，写操作也绝不会因超时重试。
tool.metadata.risk === "read",
```

**为什么？** 超时意味着**结果不可知**（可能已经写进去了，也可能没有）。
重试一个非幂等的写操作 = 放大「幽灵副作用」风险。

`src/runtime.ts:583-586` 同理：
> 超时默认不再标记为 retryable……超时意味着结果不可知，重试非幂等操作会放大"幽灵副作用"风险。

### 6.5 验收

| 场景 | 期望 |
| --- | --- |
| `../../outside.txt` | 被边界拒绝，错误来自**正确的检查层**（`PATH_OUT_OF_WORKSPACE`，不是 `PATH_DENY_WRITE`） |
| 超时命令 | 被结束，结果里 `timed_out: true` |
| `package.json` 等 | 被 `deny_write` 拒绝，拒绝原因当工具结果喂回模型，它得换路 |

---

## 第 7 讲 · 第五步：保存结果与上下文压缩（PDF 第五章）

> 主线文件：`src/context-budget.ts`（236 行）+ `src/loop-guard.ts`（128 行）。

### 7.1 核心知识点：**两套账本**

```
给模型看的   —— 整份工具输出（截断只影响它看到的量）
给审计看的   —— 按行截断的头部 + 全量哈希
```

`src/runtime.ts:553-555` 注释：
> 模型拿到的是整份工具输出，数据库拿到的是按行截断的那一份加全量哈希。
> 两边不是一份文本，这件事必须写在账上，不然事后对账会以为审计丢了内容。

### 7.2 为什么不用 pi 自带的 `compact()`

`src/context-budget.ts:10-12` 原文：
> 为什么不用 pi 自带的 compact()：它要调一次模型生成摘要，摘要文字每次跑都不一样，
> 离线跑（脚本决策器）根本没有可用的摘要模型，课后复现和评估器对账都无从下手。
> 这里的压缩**不请模型帮忙，纯按规则裁剪，同一份输入永远得到同一份输出**。

**这是本讲最重要的设计判断。** 压缩必须确定性 —— 否则评估报告无法对账。

### 7.3 压缩规则：一行摘要

`renderContext`（`src/context-budget.ts:149-175`）：

```ts
const { pinned, steps } = splitSteps(messages);
if (steps.length <= rules.keepRecentTurns) return { messages, ... };   // 还不够多，不压

const summarized = steps.slice(0, steps.length - rules.keepRecentTurns);
const kept        = steps.slice(steps.length - rules.keepRecentTurns);
const summaries   = summarized.map((step, index) => summarizeStep(index + 1, step));
const rendered    = [...pinned, summaryMessage(summaries), ...kept.flat()];

// 摘要行本身也要占地方。旧步骤都很短的时候，"压缩"反而更长——那就别压，逐字留着。
if (charsAfter >= charsBefore) return { messages, ... };
```

**最后那个判断很妙**：如果压缩反而更长，就**不压**。「逐字保留」比「看起来压过」更重要。

摘要的格式（`src/context-budget.ts:98-117`）：

```
第1步 search_code(pattern=login, path=src) → OK · 12 行 / 486 字符
第2步 read_file(path=src/routes/login.ts) → OK · 30 行 / 890 字符
```

**参数照抄进摘要，模型才能原样重发；不写结果正文，避免摘要本身又长成一个新的上下文包袱。**

配套的系统提示词（`config/prompts.yaml:37-39`）告诉模型：
> 摘要只说明"调了哪个工具、参数是什么、结果码与规模多大"，不含正文：
> 要基于代码内容下结论，就照抄摘要里的参数重新调用，或者明说你看不到那段原文。

### 7.4 审计截断：绝不从行中间切

`clipForAudit`（`src/context-budget.ts:216-236`）：

```ts
for (const line of lines) {
  if (kept.length >= rules.auditMaxLines) break;   // 30 行
  if (chars + line.length + 1 > rules.auditMaxChars) break;  // 4000 字符
  kept.push(line);
  chars += line.length + 1;
}
```

返回的 `AuditClip` 五件套：

```ts
{ text, truncated, total_lines, total_chars, kept_lines, full_sha256 }
```

**`full_sha256` 是「可验证」这条硬要求的落点**：
事后要证明「模型当时看到的就是这一份」，拿哈希对哈希即可，不必把 12k 字符塞进数据库。

### 7.5 预算与护栏（`src/loop-guard.ts`）

六条预算（`src/loop-guard.ts:59-67`）：

```ts
shouldStop(pendingApprovalId?: string): StopDecision {
  if (pendingApprovalId)                            return stop("AWAITING_APPROVAL", "工具调用正在等待人工审批");
  if (this.turns >= this.budget.maxTurns)           return stop("MAX_TURNS", ...);
  if (this.toolCalls >= this.budget.maxToolCalls)   return stop("MAX_TOOL_CALLS", ...);
  if (this.totalTokens >= this.budget.maxTotalTokens) return stop("MAX_TOKENS", ...);
  if (this.costUsd >= this.budget.maxCostUsd)       return stop("MAX_COST", ...);
  if (Date.now() - this.startedAt >= this.budget.maxDurationMs) return stop("MAX_DURATION", ...);
  return { stop: false, code: "CONTINUE", reason: "预算允许继续" };
}
```

**第一条最特殊：有待审批单就停。** 这是「审批前暂停」这条硬要求的落点。

重复调用护栏（`src/loop-guard.ts:40-44`）：

```ts
const signature = `${toolName}:${canonicalJson(args)}`;
const count = (this.repeatedCalls.get(signature) ?? 0) + 1;
if (count > this.budget.maxRepeatedCall) return deny("REPEATED_TOOL_CALL", "检测到相同工具与参数的重复调用");
```

配合 `platform.yaml:33` 的 `max_repeated_call: 2` 与提示词里的「第三次直接停摆」。

### 7.6 一个隐蔽的记账 bug 及修复（值得学）

`src/loop-guard.ts:95-104`：

```ts
/**
 * 累计进 Token 预算的只算"这一轮新算的那部分"：prompt + completion。
 *
 * 为什么不用 pi 报的 totalTokens：它等于 input + output + cacheRead + cacheWrite，
 * 而同一批 prompt 既进 input 又进 cacheWrite，等于一份上下文算了两遍；轮数一多，
 * 这个双份累加会先撞上 max_total_tokens，Agent 就被自己记的账拦在半路。
 */
export function freshTokensOf(usage: { input: number; output: number }): number {
  return usage.input + usage.output;
}
```

**这是「计量口径」层面的 bug**：不是代码写错，是**算的东西不对**。
这类 bug 只能靠「想清楚到底在数什么」发现。

`context-budget.ts:138-144` 还有一个同类的：
> 用 pi 的 `estimateTokens`……不用 `estimateContextTokens`：后者一发现 assistant 消息带着
> provider 回报的 usage，就直接把那个 usage 数当结果返回 —— 压缩前后取的是同一条 assistant 消息的 usage，
> 数字永远相等，也就回答不了"这次渲染到底省下了多少"。

### 7.7 验收

| 场景 | 期望 |
| --- | --- |
| 长日志入库 | 按行截断且带 `full_sha256`；模型看到 `truncated: true` |
| 第三轮时 | 第一步原文不在上下文里，只剩一行摘要；调用与结果**配对完整** |
| 字符数 vs Token 数 | 字符数用于文本上限，**不能替代精确 Token 数** |

---

## 第 8 讲 · 第六步：检查继续还是结束

> PDF 7.2 第六步。主线文件：`src/deliverable.ts`（149 行）。

### 8.1 核心知识点：**结束 ≠ 完成，证据齐了才算交付**

判断只能以审计为准，**不能听模型自述**。

`src/deliverable.ts:56-59` 原文：
> 为什么不看最终回答：最终回答是模型生成的文本，它可以（并且真的发生过）在
> `PATCH_CONTEXT_NOT_FOUND` 之后写下"复跑全绿"。**审计是 Runtime 写的，模型改不动。**

### 8.2 三个布尔值，含义各不相同

```ts
delivered:              boolean;  // 交付物是否真的被写进去了（只看审计）
model_claims:           boolean;  // 模型在最终回答里说交付物存在（证据只有它自己）
claim_without_evidence: boolean;  // 说了但没做 —— 评估器要的就是这一位
```

`claim_without_evidence = claimsPath && lastSuccess === undefined`

README 里提到 pi 入口的那次：文件没落盘，但 pi 的 Loop **自己宣布审批已通过** ——
所以交付物那一行写「自述无据 是」。

### 8.3 一次「尝试写交付物」在账上有两种样子

`src/deliverable.ts:92-100`：

```ts
/**
 * 一次"尝试写交付物"在账上有两种样子：真跑过的那次记在 tool_execution，
 * 被策略拦在门口（等审批、被契约拒）的那次只留下一条 policy_decision。
 * 两种都要进 attempts——评估器要看的就是"它试了几次、每次卡在哪"，
 * 只看跑成功的那次等于没看。
 */
const writes = audit
  .filter((row) => (row.event_type === "tool_execution" || row.event_type === "policy_decision") && WRITE_TOOLS.has(row.tool_name))
  .filter((row) => !expectedPath || pathOf(row) === expectedPath);
const successes  = writes.filter((row) => row.event_type === "tool_execution" && row.code === "OK");
const lastSuccess = successes[successes.length - 1];
```

只看成功那次，等于把「被拦了三次」这个最重要的事实藏起来了。

### 8.4 两条入口印同一句话

`src/deliverable.ts:144-149`：

```ts
export function deliverableLine(v: DeliverableVerification): string {
  return (
    `[交付物] ${v.expected_path ?? "(本类任务未声明)"} · 写入 ${v.delivered ? "有账可查" : "无账可查"}` +
    ` · 模型自述 ${v.model_claims ? "提到" : "未提到"} · 自述无据 ${v.claim_without_evidence ? "是" : "否"}`
  );
}
```

注释：「两条入口留同一类事件：事后翻账时，CLI 跑的那趟和 pi 跑的那趟要能放在一起比。」

### 8.5 Loop 的三个收口钩子（`src/pi/agent-runner.ts`）

| 钩子 | 位置 | 职责 |
| --- | --- | --- |
| `beforeToolCall` | `136-164` | 预算护栏 → 审批门口。被拦死时给 `terminate: true` |
| `finishTurn` | `169-183` | 预算够了没？模型还要不要工具？ |
| `afterToolCall` | `165-168` | 记账 |

`finishTurn` 里判断「模型是否还要工具」（`src/pi/agent-runner.ts:178`）：

```ts
const askedForWork = turn.message.content.some((part) => part.type === "toolCall");
stop = askedForWork
  ? { stop: false, code: "CONTINUE", reason: "预算允许继续" }
  : { stop: true, code: "COMPLETED", reason: "模型给出最终回答，Loop 正常收口" };
```

**「模型不再要求工具 = 它给的就是最终回答」** —— 这就是 Loop 收口的判据。

`beforeToolCall` 里那段注释解释了为什么要 `terminate`（`src/pi/agent-runner.ts:156-157`）：
> 人工拒了、图连不上、没人有资格批——这三条路都给 terminate：这一批工具结果之后 Loop 就收口，
> 最终回答停在"被拦死"这个事实上。**让模型接着讲一个和结局相反的收尾，是 Harness 不该纵容的事。**

### 8.6 验收

| 场景 | 期望 |
| --- | --- |
| Agent 正常结束但交付物不存在 | 验收判失败，状态与原因可查 |
| 预算耗尽 | 停止并保留停止原因；**未完成任务不会被计为完成** |
| 没有模型调用的测试 | 标「不适用」，而不是虚报 |

---

## 第 9 讲 · 人工确认：LangGraph 审批图（PDF 第六章）

> 主线文件：`hitl/graph.py`（112 行）+ `src/hitl/client.ts`（167 行）。

### 9.1 核心知识点：**两个正交的维度**

```
gate（过不过人）  ←→  via（谁来裁定）
```

| | `gate` | `via` |
| --- | --- | --- |
| 问的问题 | 这道门开不开？ | 批的人由谁判定？ |
| 取值 | `auto` / `none` / 工具名单 | `local` / `http` |
| 谁能覆盖 | `tasks.yaml` | **环境变量 `HITL_MODE` 永远最大** |

`config/tasks.yaml:24` 原文：
> gate 与 via 是正交的两维：**关掉门口不等于放开审批，换成图也不等于门口开着。**

### 9.2 图的结构（`hitl/graph.py:101-112`）

```python
graph.add_edge(START, "check_eligible")
graph.add_conditional_edges("check_eligible", _after_eligibility, {END: END, "request_human": "request_human"})
graph.add_edge("request_human", "check_approver")
graph.add_edge("check_approver", END)
```

```
START → check_eligible ──(rejected)──→ END
              │
         (awaiting_human)
              ↓
        request_human  ←── interrupt() 图在这里停住等人
              ↓
        check_approver ──→ END (approved / rejected)
```

### 9.3 三道门，各管一件事

**第一道门 `check_eligible`（`hitl/graph.py:34-51`）：这单连人都没找对，就不必打扰人。**

```python
if not approvers:
    return {"status": "rejected", "code": "NO_APPROVER_CONFIGURED",
            "feedback": "这张单没有配审批名单（approvers 为空），谁批都不算数"}
if not set(approvers) & set(roles):
    return {"status": "rejected", "code": "NO_ELIGIBLE_APPROVER",
            "feedback": f"发起人角色 ... 与审批名单 ... 没有交集，这张单没人有资格批"}
```

**「名单为空 = 失败关闭」**：宁可开不了工，也不要「看起来有人把关」。

**第二道门 `request_human`（`hitl/graph.py:54-75`）：图在这里停住。**

```python
decision = interrupt({
    "kind": "approval",
    "ticket_id": state["ticket_id"],
    "tool_name": state["tool_name"],
    "args_digest": state["args_digest"],     # ← 给人看的是参数指纹
    "workspace": state["workspace"],
    "risk": state.get("risk", ""),
    "approvers": state.get("approvers", []),
    "actions": ["approve", "reject"],
}) or {}
```

**`interrupt()` 是 LangGraph 的人在回路机制**：图执行到这里暂停，状态落 checkpoint；
人答复后从断点继续。**服务重启、审批人在另一个终端答复，都接得上。**

**第三道门 `check_approver`（`hitl/graph.py:78-94`）：批的人得对得上规则。**

```python
if state.get("code") not in ("approve", "reject"): return ... "INVALID_DECISION"
if not state.get("decided_by") or state["decided_by"] == state.get("user_id"):
    return {"status": "rejected", "code": "SELF_APPROVAL_DENIED", "feedback": "审批人不能是发起人自己"}
if not set(approvers) & set(actor_roles):
    return {"status": "rejected", "code": "APPROVER_ROLE_DENIED", "feedback": "审批人角色 ... 不在审批名单 ... 里"}
```

**「审批人不能是发起人自己」** —— 这是最基本的制衡，写在图里而不是写在提示词里。

### 9.4 「谁能批」不写在任何一段提示词里

README 那句话值得背下来：
> **"谁能批"不写在任何一段提示词里，改的是 `config/tasks.yaml` 的 `approval.approvers`。**

**规则必须是代码/配置，不能是自然语言。** 提示词里的规则，模型可以「理解偏差」；
配置里的规则，程序不会商量。

### 9.5 失败关闭：图不在 = 没批准

`src/hitl/client.ts:140-144`：

```ts
// 连不上必须说清楚：这张图是审批的唯一权威，它不在就等于没有批准，不能当成"批过了"。
throw new HitlGatewayError(
  "HITL_UNREACHABLE",
  `审批服务 ${this.config.baseUrl} 不可达：先起 hitl/service.py（${...}）`,
);
```

`src/runtime.ts:266` 那行注释更狠：
> 图不在或连不上，一律当成"没有人批准"，**不能当成"批过了"**。

两种失败的表现：

```json
{ "stop": true, "code": "HITL_KEY_MISSING", "reason": "审批服务需要环境变量 HITL_API_KEY" }
{ "stop": true, "code": "HITL_UNREACHABLE", "reason": "审批服务 http://127.0.0.1:8383 不可达：先起 hitl/service.py（fetch failed）" }
```

**两种情况下样本仓库都未被改动。** 这是「可恢复」这条硬要求的落点。

### 9.6 三条拦截路的共同点（`src/runtime.ts:201-212`）

```ts
const block = (code: string, message: string, terminate = true) => {
  // 三条拦截路（没人有资格批、图连不上、人工拒绝）都有同一个共同点：
  // 这张单已经拿到终局了，Loop 不该再为它挂着"待审批"。
  this.settleApproval(request.context.traceId, approvalId);
  return { block: true, code, message, reason: ..., ...(terminate ? { terminate: true } : {}) };
};
```

**拿到终局就必须摘掉「待审批」标记**。留在 pending 的话，监控上看着像「在等人」，
实际上永远不会有审批人收到这张单。

### 9.7 本地表 vs 图：两条路的区别

| | 本地表（`HITL_MODE=disabled`） | 图（`via: http`） |
| --- | --- | --- |
| 裁定人 | CLI 自己 | LangGraph 图 |
| 会不会等 | **不会** —— Loop 当场收口 | 会 —— 轮询到终局 |
| 后续 | 手动 `decide` + `execute`，一次只推进一步 | Loop 自己往下走 |
| 门口 | **照旧生效**（只是换裁定人） | 照旧生效 |

README 那句总结：
> `HITL_MODE` 这一层永远大过 `tasks.yaml`，但它**只换裁定人，不动门口**。

### 9.8 验收红线（README 第 116-139 行）

把批单的人换成名单外的角色：

```bash
node --import tsx src/cli.ts approvals decide <ticketId> \
  --decision approve --actor dev-9 --roles developer --task fix_tests
```

```json
{
  "ticketId": "...", "status": "rejected", "code": "APPROVER_ROLE_DENIED",
  "decidedBy": "dev-9",
  "feedback": "审批人角色 developer 不在审批名单 maintainer、tech_lead 里"
}
```

跑 agent 的终端当场收口，收口码就是图给的那一个。

---

## 第 10 讲 · 评估入口与工程复盘（PDF 第八章）

> 主线文件：`src/eval.ts`（261 行）。

### 10.1 一条命令

```bash
node --import tsx src/cli.ts eval                     # 跑 tasks.yaml 里的全部任务类型
node --import tsx src/cli.ts eval --case fix_tests    # 只跑点名的
node --import tsx src/cli.ts eval --decider real      # 显式指定连真模型
```

报告落两份：`artifacts/eval_report.md` 与 `artifacts/eval_report.json`。

### 10.2 三个关键设计

**① 隔离**：每次评估使用独立工作副本与独立账本（`project3/.eval-runs/<时间>-<任务>/`），
避免互相污染。

**② 执行状态与验收结论分开记**：

| | 含义 |
| --- | --- |
| 执行状态 | 已完成 / 待审批 / 已停止 |
| 验收结论 | 交付物有没有账 |

**「待审批的任务绝不会被计为完成，自动生成报告不等于自动批准。」**（README 原文）

**③ 报告字段齐全**（PDF 8.5 优化项 2 的要求）：
任务名 / Run ID / 决策来源 / 执行状态与停止原因 / 验收结论 / 工具调用与审批次数 /
耗时与 token / 产物与差异引用 / 未覆盖项。

### 10.3 四个失败案例复盘（PDF 8.2）

| 案例 | 现象 | 处理规则 |
| --- | --- | --- |
| 一 · 参数错误 | `write_file` 缺 `content` | 参数错误、**handler 零调用**、文件不变；错误携带调用编号进下一轮 |
| 二 · 测试失败 | 测试进程结束但没通过 | **测试进程结束 ≠ 修复完成**；修完程序检查，再用原失败场景复验 |
| 三 · 审批中断 | 恢复后会不会错用旧授权 | 核对有效期、补丁、文件状态、授权条件；**目标文件变化就重新核对** |
| 四 · 执行结果没保存 | 文件已改但没记录 | 已应用→确认现场补记；未应用→复核后处理；无法判断→**保留现场，人工接管** |

案例四的三分支是「可恢复」这条要求的完整表达：
> **核心要求：状态与执行事实一致，避免盲目重放。**

### 10.4 Checkpoint 不能撤销文件修改

PDF 7.3 那句话要记住：
> **Checkpoint 保存状态，不能撤销文件修改。**
> LangGraph Checkpoint 恢复审批流程；完整任务另需保存计划与执行证据。

类比：施工日志能告诉你「昨天砸了哪面墙」，但**不能把墙变回去**。

### 10.5 工程师 vs AI 的分工（PDF 8.4）

| 你必须能 | 具体 |
| --- | --- |
| **能解释** | Loop、Runtime、Harness、Sandbox、Checkpoint 的职责 |
| **能追踪** | 输入 → 决策 → 校验 → 执行 → 回写 → 完成检查 |
| **能修复** | 未校验执行、旧审批复用、结果丢失、写操作误重放 |
| **能验证** | 用测试证明关键边界有效 |

### 10.6 本节的已知限制（诚实清单，PDF 8.3）

| 已补齐 | 待接入 |
| --- | --- |
| `cli eval` 评估入口 | 严格真实模型模式 |
| `allow_write_extra` 允许写入例外 | 部分上下文规则 |
| 提示词变量清单校验 | |
| 清理遗留 `config/gateway.yaml` | |
| 任务一样本补读中间件 | |

> **预置失败测试验证修复，不能证明测试生成能力。**
> **单次成功是样本证据；稳定性需要固定任务集与多次记录。**

---

## 附录 A · 十件工具契约速查

| 工具 | 输入说明什么 | 输出包含什么 | risk |
| --- | --- | --- | --- |
| `list_files` | 相对目录、匹配条件、数量上限 | 文件路径列表，是否截断 | read |
| `search_code` | 搜索内容、搜索范围、结果上限 | 命中文件、行号、片段，是否截断 | read |
| `read_file` | 文件路径、可选起始行与读取范围 | 文件内容、实际行号范围，是否截断 | read |
| `read_directory` | 目录路径 | 当前目录的直接子项及类型 | read |
| `write_file` | 文件路径、写入内容、覆盖规则 | 写入路径、创建或覆盖结果 | write |
| `apply_patch` | 目标文件、补丁内容 | 应用结果、变更摘要；失败时说明匹配问题 | write |
| `run_test` | 允许的测试目标或配置标识 | 退出码、测试摘要、输出日志，是否超时 | execute |
| `run_command` | 命令及参数、工作目录、超时 | 退出码、标准输出、标准错误，是否超时 | execute |
| `git_diff` | 可选的路径范围 | 实际差异、涉及的文件，是否截断 | read |
| `git_status` | 可选的路径范围 | 已修改、未跟踪等文件状态 | read |

参数用 **TypeBox** 定义，执行前统一经过 contract 校验。

## 附录 B · 错误码速查

| 前缀 | 来源 | 例子 |
| --- | --- | --- |
| `CONTRACT_*` | 语义契约层 | `CONTRACT_PATH_MUST_BE_RELATIVE`、`CONTRACT_PATCH_NO_CHANGES` |
| `INVALID_ARGUMENT` | 结构校验层 | 类型错、缺必填 |
| `PATH_*` | 沙箱 | `PATH_OUT_OF_WORKSPACE`、`PATH_DENY_WRITE`、`PATH_DENY_READ` |
| `TOOL_NOT_VISIBLE` / `RBAC_DENIED` | 策略 | 白名单 / 权限 |
| `APPROVAL_*` | 审批 | `APPROVAL_REQUIRED`、`APPROVAL_BINDING_MISMATCH`、`APPROVAL_NOT_EXECUTABLE`、`APPROVAL_GATE_OFF`、`APPROVAL_TIMEOUT` |
| `NO_APPROVER_*` / `APPROVER_ROLE_DENIED` / `SELF_APPROVAL_DENIED` / `HUMAN_REJECTED` | LangGraph 图 | 谁能批 |
| `HITL_*` | 审批客户端 | `HITL_KEY_MISSING`、`HITL_UNREACHABLE`、`HITL_DISABLED` |
| `MAX_*` / `REPEATED_TOOL_CALL` / `AWAITING_APPROVAL` | Loop 护栏 | 预算 |
| `MODEL_UNAVAILABLE` / `SCRIPT_REQUIRED` / `DECIDER_MODE` | 决策器选择 | 谁在决策 |
| `TASK_TYPE_*` / `TASK_FIELD_MISSING` | 任务解释器 | 路由 |
| `TOOL_TIMEOUT` | 执行 | 超时 |

## 附录 C · 自检清单（能不能讲清）

读完这份讲义，试着不看书回答下面 12 个问题。答不上来的回去看对应讲次。

1. `trace_id` 和 `pending_approval_id` 分别标识什么？（第 1 讲）
2. 配置的优先级是哪三层？谁最大？（第 2 讲）
3. 为什么 `gate` 是 `PolicyEngine` 的构造参数而不是工具元数据？（第 2 讲）
4. 契约为什么分两层？第二层拦的是什么？（第 4 讲）
5. `CONTRACT_COMMAND_BLANK` 拦的是错误还是浪费？为什么值得拦？（第 4 讲）
6. Runtime 四道检查的顺序是什么？为什么是这个顺序？（第 5 讲）
7. 审批指纹盖住了哪六个维度？为什么必须盖住 `workspace`？（第 5 讲）
8. 批准之后为什么还要重跑契约与策略？（第 5 讲）
9. 为什么超时不重试写操作？（第 6 讲）
10. 为什么不用 pi 自带的 `compact()`？（第 7 讲）
11. `delivered`、`model_claims`、`claim_without_evidence` 三者区别？（第 8 讲）
12. `gate` 和 `via` 为什么是正交的？图连不上时当成什么？（第 9 讲）

---

## 本节的最终一句话

PDF 第九章：
> 阶段二：建立**受控工具执行基础设施**。
> 阶段三：连接 **Loop、计划、状态、沙箱、Harness 与审批**。
> 完整任务链：**理解目标 → 执行操作 → 观察结果 → 处理偏差 → 验证完成**。
> 项目完成度由**产物、测试、差异与执行记录**支持。
