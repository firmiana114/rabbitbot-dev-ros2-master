from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Union
import uvicorn

app = FastAPI()

# 定义消息结构
class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

# 定义请求体结构
class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    user: Optional[str] = None

# 定义响应结构 (简化版)
class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str

class ChatUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: List[ChatChoice]
    usage: ChatUsage

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest):
    # 这里是你处理逻辑的地方
    # 例如，将 messages 发送到你的模型，获取回复
    print(f"Received request for model: {request.model}")
    print(f"Messages: {request.messages}")

    # 模拟一个简单的回复
    last_user_message = next((m.content for m in reversed(request.messages) if m.role == "user"), "Hello!")
    response_content = f"Echo: {last_user_message}"

    # 构造响应
    response = ChatCompletionResponse(
        id="chatcmpl-12345",
        object="chat.completion",
        created=1677858242, # 模拟时间戳
        model=request.model,
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=response_content),
                finish_reason="stop"
            )
        ],
        usage=ChatUsage(
            prompt_tokens=sum(len(m.content.split()) for m in request.messages),
            completion_tokens=len(response_content.split()),
            total_tokens=sum(len(m.content.split()) for m in request.messages) + len(response_content.split())
        )
    )

    return response
