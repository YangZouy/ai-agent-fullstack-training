import { Type } from "typebox";

export function createGitStatusTool(sandbox: Sandbox): ManagedTool {
  return {
    metadata: {
      internalName: "open_blog",          // 模型名默认同形（含合法字符）
      description: "打开我的个人博客并返回页面标题与正文摘要，例如 https://zyydgrbk.top",
      version: "1.0.0",
      parameters: Type.Object({}, { additionalProperties: false }),  // 无参数
      risk: "read",                       // 只读外部网页
      permissions: ["web:read"],          // 新增权限点
      requiresConfirmation: false,
      timeoutMs: 10_000,                  // 网络请求要留足
      maxRetries: 2,
      idempotent: true,
      source: "local",
    },
    async handler({ signal }) {
      const response = await fetch("https://zyydgrbk.top", { signal });
      // 提取标题/摘要文本返回（不要返回整份 HTML）
    }
  };
}
