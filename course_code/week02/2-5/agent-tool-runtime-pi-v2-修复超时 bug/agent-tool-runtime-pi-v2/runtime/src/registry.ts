import type { ExecutionContext, ManagedTool, RegisteredTool } from "./domain.js";
import { toModelToolName } from "./name-mapping.js";
import type { PolicyEngine } from "./policy.js";

export class ToolRegistry {
  // internalName 唯一。保证不会重复注册同一个内部工具。
  private readonly byInternalName = new Map<string, RegisteredTool>();
  // 投影后的 modelName 唯一。
  private readonly byModelName = new Map<string, RegisteredTool>();

  register(tool: ManagedTool): RegisteredTool {
    const internalName = tool.metadata.internalName;
    if (this.byInternalName.has(internalName)) {
      throw new Error(`Tool already registered: ${internalName}`);
    }
    const modelName = toModelToolName(internalName);
    if (this.byModelName.has(modelName)) {
      throw new Error(`Model tool-name collision: ${modelName}`);
    }
    const registered = { ...tool, modelName };
    this.byInternalName.set(internalName, registered);
    this.byModelName.set(modelName, registered);
    return registered;
  }

  get(internalName: string): RegisteredTool {
    const tool = this.byInternalName.get(internalName);
    if (!tool) throw new Error(`Tool not found: ${internalName}`);
    return tool;
  }

  getByModelName(modelName: string): RegisteredTool {
    const tool = this.byModelName.get(modelName);
    if (!tool) throw new Error(`Tool not found: ${modelName}`);
    return tool;
  }

  list(): RegisteredTool[] {
    return [...this.byInternalName.values()];
  }

  // 快照使用policyEngine来裁剪（根据角色权限、agent白名单、租户前缀决定哪些工具可以出现在该次对话中）
  snapshot(context: ExecutionContext, policy: PolicyEngine): RegisteredTool[] {
    return this.list().filter((tool) => policy.isVisible(context, tool.metadata.internalName));
  }
}
