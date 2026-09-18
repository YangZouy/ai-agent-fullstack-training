import json
from openai import OpenAI

class DeepSeekChatAdapter(ModelAdapter):
    name = "deepseek-v4-flash-chat"
    capabilities = ModelCapabilities(
        chat_completions=True,
        responses=False,
        # ds不支持原生schema 这里直接采用JSON方式
        structured_output="json_mode",
        tool_calling=True,
        # ds的thinking模式可能会忽略采样参数
        supports_temperature=True,  # 仅 non-thinking 生效
        supports_top_p=True,         # 仅 non-thinking 生效
    )

    def __init__(self, api_key: str) -> None:
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            # 设置硬性超时时间
            timeout=30.0,
            max_retries=0,
        )

    def generate(self, request: ModelRequest) -> ModelResult:
        system = request.system
        kwargs: dict[str, Any] = {}

        # 将Schema序列化后注入到prompt中
        if request.output_schema:
            system += (
                "\n必须输出 json，并符合此 JSON Schema：\n"
                + json.dumps(request.output_schema, ensure_ascii=False)
            )
            # 开启response_format为json_object
            kwargs["response_format"] = {"type": "json_object"}

        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.top_p is not None:
            kwargs["top_p"] = request.top_p

        raw = self.client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": request.user},
            ],
            max_tokens=request.max_output_tokens,
            extra_body={"thinking": {"type": "disabled"}},
            **kwargs,
        )

        choice = raw.choices[0]
        text = choice.message.content or ""
        usage = raw.usage

        data = json.loads(text) if request.output_schema else None
        return ModelResult(
            kind="structured" if data is not None else "text",
            text=text,
            data=data,
            finish_reason=choice.finish_reason,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            request_id=raw.id,
        )