import {
  createProvider,
  envApiKeyAuth,
  type Model,
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/compat";
import type { PlatformConfig } from "../config.js";

// 厂商差异收在这一份compat中，加新厂商需要加一个分支
function modelCompat(providerId: string) {
  if (providerId === "deepseek") {
    return {
      supportsStore: false,
      supportsDeveloperRole: false,
      maxTokensField: "max_tokens",
      // DeepSeek 是"默认开思考"的模型：不指定思考档位时 pi-ai 会下发 thinking: {type: "disabled"}。
      requiresReasoningContentOnAssistantMessages: true,
      thinkingFormat: "deepseek",
      supportsStrictMode: true,
    }
  }
  // 智谱 GLM 走 OpenAI 兼容端点，但不是"默认开思考"：不开 thinking，回复也不带 reasoning content。
  return {
    supportsStore: false,
    supportsDeveloperRole: false,
    maxTokensField: "max_tokens",
    requiresReasoningContentOnAssistantMessages: false,
    supportsStrictMode: false,
  };
}

export function createGatewayProvider(config: PlatformConfig) {
  const isDeepseek = config.model.providerId === "deepseek";
  const model: Model<"openai-completions"> = {
    id: config.model.id,
    name: config.model.name,
    api: "openai-completions",
    provider: config.model.providerId,
    baseUrl: config.gateway.baseUrl,
    // DeepSeek 是"默认开思考"的模型。这里声明它确实支持推理，并把 compat 钉成 deepseek：
    // 没指定思考档位时 pi-ai 会下发 thinking: {type: "disabled"}，也就是"关闭思考"；
    // 想打开得显式抬思考档位（pi 的 thinkingLevel / reasoning）。
    reasoning: isDeepseek,
    compat: modelCompat(config.model.providerId),
    input: ["text"],
    cost: {
      input: config.model.inputPerMillion,
      output: config.model.outputPerMillion,
      cacheRead: config.model.cacheReadPerMillion,
      cacheWrite: config.model.inputPerMillion,
    },
    contextWindow: config.model.contextWindow,
    maxTokens: config.model.maxTokens,
  };
  return createProvider({
    id: config.model.providerId,
    name: "DeepSeek",
    baseUrl: config.gateway.baseUrl,
    auth: {
      apiKey: envApiKeyAuth(`${config.model.name} API key`, [config.gateway.apiKeyEnv]),
    },
    models: [model],
    api: openAICompletionsApi(),
  });
}
