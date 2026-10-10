// 模型注册，直连 DeepSeek（OpenAI-compatible）。
import {
  createModels,
  createProvider,
  envApiKeyAuth,
  type Model,
} from "@earendil-works/pi-ai";
import {
  openAICompletionsApi,
} from "@earendil-works/pi-ai/api/openai-completions.lazy";

export const gatewayModel: Model<"openai-completions"> = {
  id: "deepseek-chat",
  name: "Agent Default",
  provider: "deepseek",
  api: "openai-completions",
  baseUrl: process.env.GATEWAY_BASE_URL
    ?? "https://api.deepseek.com/v1",
  reasoning: false,
  input: ["text"],
  cost: {
    input: 0,
    output: 0,
    cacheRead: 0,
    cacheWrite: 0,
  },
  contextWindow: 128_000,
  maxTokens: 4096,
};

const provider = createProvider({
  id: "deepseek",
  name: "DeepSeek",
  baseUrl: gatewayModel.baseUrl,
  auth: {
    apiKey: envApiKeyAuth(
      "DeepSeek API key",
      ["DEEPSEEK_API_KEY", "GATEWAY_API_KEY"],
    ),
  },
  models: [gatewayModel],
  api: openAICompletionsApi(),
});

export const models = createModels();
models.setProvider(provider);