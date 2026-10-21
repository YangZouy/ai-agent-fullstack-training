import {
  createModels,
  createProvider,
  envApiKeyAuth,
  type ApiKeyAuth,
  type Model,
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/compat";
import type { PlatformConfig } from "../config.js";

// 直接用配置里的静态 key 构造 ApiKeyAuth，避免依赖环境变量。
function configApiKeyAuth(key: string): ApiKeyAuth {
  return {
    name: "DeepSeek API key (platform.yaml)",
    async resolve() {
      return { auth: { apiKey: key } };
    },
  };
}

export function createGatewayProvider(config: PlatformConfig) {
  const model: Model<"openai-completions"> = {
    id: config.model.id,
    name: config.model.name,
    api: "openai-completions",
    provider: config.model.providerId,
    baseUrl: config.gateway.baseUrl,
    reasoning: false,
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
    name: "DeepSeek API",
    baseUrl: config.gateway.baseUrl,
    auth: {
      // 优先读配置里的 api_key；未配置时回退到 api_key_env 指向的环境变量
      apiKey: config.gateway.apiKey
        ? configApiKeyAuth(config.gateway.apiKey)
        : envApiKeyAuth("DeepSeek API key", [config.gateway.apiKeyEnv]),
    },
    models: [model],
    api: openAICompletionsApi(),
  });
}

export function createGatewayModels(config: PlatformConfig) {
  const models = createModels();
  models.setProvider(createGatewayProvider(config));
  const model = models.getModel(config.model.providerId, config.model.id);
  if (!model) throw new Error(`Gateway model not found: ${config.model.id}`);
  return { models, model };
}
