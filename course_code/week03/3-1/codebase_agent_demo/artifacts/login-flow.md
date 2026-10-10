# 登录逻辑说明文档

> 本文档基于对源码的实际阅读整理，所有结论均可回溯到下方「引用源码」中列出的文件。
> 项目为最小化实现，登录相关代码仅涉及 3 个文件。

## 1. 文件与职责

| 文件 | 职责 |
| --- | --- |
| `src/routes/login.ts` | 登录入口（路由处理函数），编排「校验密码 → 创建会话 → 返回响应」 |
| `src/services/auth-service.ts` | 凭证校验，包含内存用户表与密码比对逻辑 |
| `src/auth/session.ts` | 会话（Session）创建，生成 token 与过期时间 |

## 2. 调用链

```
loginRoute(payload)                       // src/routes/login.ts
  ├─ verifyPassword(email, password)      // src/services/auth-service.ts
  │    └─ 命中用户 / 抛错 USER_NOT_FOUND / INVALID_PASSWORD
  └─ createSession(user.id)               // src/auth/session.ts
       └─ 返回 { token, userId, expiresAt }
```

调用关系已通过全局检索确认：`loginRoute` 无其他调用方（仓库内未包含 HTTP 框架的注册代码）；
`verifyPassword` 与 `createSession` 各自仅有一个调用点，即 `loginRoute`。

## 3. 入口：`loginRoute`

签名：

```ts
export async function loginRoute(payload: LoginPayload)
```

输入结构 `LoginPayload` 仅含两个字段：

- `email: string`
- `password: string`

执行步骤：

1. 调用 `verifyPassword(payload.email, payload.password)` 校验凭证，**先 await 完成**才继续。
2. 使用返回的 `user.id` 调用 `createSession(user.id)` 创建会话。
3. 返回固定结构：

```ts
{
  status: 200,
  body: {
    message: "login ok",
    sessionToken: session.token,
    userId: user.id,
  },
}
```

注意：响应体中的 `userId` 取自 `verifyPassword` 的返回值，而非 `session` 对象；
`email` 未出现在响应体中。

## 4. 凭证校验：`verifyPassword`

```ts
export async function verifyPassword(email: string, password: string)
```

实现要点：

- 数据源是模块内的常量数组 `USERS`，为**内存硬编码**的单一用户：

  | 字段 | 值 |
  | --- | --- |
  | `id` | `user-1001` |
  | `email` | `alice@example.com` |
  | `passwordHash` | `hash:secret-123` |

- 先按 `email` 查找用户，`find` 未命中则抛出 `Error("USER_NOT_FOUND")`。
- 再进行密码比对：把明文密码拼接前缀构造候选哈希
  `const candidateHash = \`hash:${password}\``，与 `user.passwordHash` 做**字符串全等比较**；
  不一致则抛出 `Error("INVALID_PASSWORD")`。
- 比对成功时返回裁剪后的对象，**不包含** `passwordHash`：

```ts
{ id: user.id, email: user.email }
```

即：密码错误与用户不存在会抛出不同的错误码，调用方（`loginRoute`）内部并未捕获，
错误会以异常形式向上抛出。

## 5. 会话创建：`createSession`

```ts
export function createSession(userId: string)
```

返回一个同步构造的普通对象，实现为纯拼接、无随机数与签名：

```ts
{
  token: `session-${userId}`,                 // 例如 session-user-1001
  userId,
  expiresAt: "2099-01-01T00:00:00.000Z",      // 固定写死的过期时间
}
```

要点：

- token 直接由 `userId` 字符串拼接而成，可预测；更换用户只会改变 token 中的 id 部分。
- `expiresAt` 是**硬编码常量**（2099 年），并非基于当前时间计算，因此实际等同于永不过期。
- 未在该文件或调用链中出现 token 的存储、下发 Cookie 或持久化逻辑。

## 6. 完整登录时序

1. 外部传入 `{ email, password }` 给 `loginRoute`。
2. `verifyPassword` 在 `USERS` 中按 email 查找：
   - 找不到 → 抛 `USER_NOT_FOUND`，登录中断。
   - 找到但 `hash:<password>` 不等于 `passwordHash` → 抛 `INVALID_PASSWORD`，登录中断。
3. 校验成功，返回 `{ id, email }`。
4. `createSession(user.id)` 生成 `session-<userId>` token 与固定过期时间。
5. `loginRoute` 返回 `status: 200`，body 含 `message`、`sessionToken`、`userId`。

## 7. 观察到的实现特征（基于代码事实）

以下为代码中可确认的事实性描述，非推断：

- 密码以明文拼接前缀的形式参与比较（`hash:${password}`），未使用任何真实的哈希算法/加盐。
- 用户数据为硬编码单例，无数据库或外部存储访问。
- `createSession` 无随机性，token 可由 userId 推导。
- 会话过期时间为写死的常量，不随登录时间变化。
- 成功路径固定返回 HTTP `status: 200`；失败路径通过异常抛出，仓库内未见统一的错误码到 HTTP 状态码的映射代码。
- 仓库内未包含 `loginRoute` 的路由注册 / HTTP 框架接入代码，因此请求体解析、错误响应格式在本仓库范围内不可见。

## 8. 引用源码

- `src/routes/login.ts`
- `src/services/auth-service.ts`
- `src/auth/session.ts`
