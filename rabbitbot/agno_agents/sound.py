from dataclasses import dataclass
from os import getenv
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel

from agno.models.openai.like import OpenAILike
from agno.utils.log import log_debug

@dataclass
class RealtimeSound(OpenAILike):

    id: str = "not-set"
    name: str = "RealtimeSound"
    provider: str = "RealtimeSound"

    api_key: Optional[str] = getenv("REALTIME_SOUND_API_KEY") or "EMPTY"
    base_url: Optional[str] = getenv("REALTIME_SOUND_BASE_URL", "http://localhost:8000/v1")

    temperature: float = 0.7
    top_p: float = 0.8
    presence_penalty: float = 1.5
    top_k: Optional[int] = None
    enable_thinking: Optional[bool] = None

    def __post_init__(self):
        if not self.base_url:
            raise ValueError("REALTIME_SOUND_API_KEY must be set via environment variable or explicit initialization")
        if self.id == "not-set":
            raise ValueError("Model ID must be set via environment variable or explicit initialization")

        body: Dict[str, Any] = {}
        if self.top_k is not None:
            body["top_k"] = self.top_k
        if self.enable_thinking is not None:
            body["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        self.extra_body = body or None

    def get_request_params(
        self,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        request_kwargs = super().get_request_params(
            response_format=response_format, tools=tools, tool_choice=tool_choice
        )

        realtime_sound_body: Dict[str, Any] = {}
        if self.top_k is not None:
            realtime_sound_body["top_k"] = self.top_k
        if self.enable_thinking is not None:
            realtime_sound_body.setdefault("chat_template_kwargs", {})["enable_thinking"] = self.enable_thinking

        if realtime_sound_body:
            existing_body = request_kwargs.get("extra_body") or {}
            request_kwargs["extra_body"] = {**existing_body, **realtime_sound_body}

        if request_kwargs:
            log_debug(f"Calling {self.provider} with request parameters: {request_kwargs}", log_level=2)
        return request_kwargs


@dataclass
class RealtimeSTT(OpenAILike):

    id: str = "not-set"
    name: str = "RealtimeSTT"
    provider: str = "RealtimeSTT"

    api_key: Optional[str] = getenv("REALTIME_STT_API_KEY") or "EMPTY"
    base_url: Optional[str] = getenv("REALTIME_STT_BASE_URL", "http://localhost:8000/v1")

    temperature: float = 0.7
    top_p: float = 0.8
    presence_penalty: float = 1.5
    top_k: Optional[int] = None
    enable_thinking: Optional[bool] = None

    def __post_init__(self):
        if not self.base_url:
            raise ValueError("REALTIME_STT_API_KEY must be set via environment variable or explicit initialization")
        if self.id == "not-set":
            raise ValueError("Model ID must be set via environment variable or explicit initialization")

        body: Dict[str, Any] = {}
        if self.top_k is not None:
            body["top_k"] = self.top_k
        if self.enable_thinking is not None:
            body["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        self.extra_body = body or None

    def get_request_params(
        self,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        request_kwargs = super().get_request_params(
            response_format=response_format, tools=tools, tool_choice=tool_choice
        )

        realtime_sound_body: Dict[str, Any] = {}
        if self.top_k is not None:
            realtime_sound_body["top_k"] = self.top_k
        if self.enable_thinking is not None:
            realtime_sound_body.setdefault("chat_template_kwargs", {})["enable_thinking"] = self.enable_thinking

        if realtime_sound_body:
            existing_body = request_kwargs.get("extra_body") or {}
            request_kwargs["extra_body"] = {**existing_body, **realtime_sound_body}

        if request_kwargs:
            log_debug(f"Calling {self.provider} with request parameters: {request_kwargs}", log_level=2)
        return request_kwargs


@dataclass
class RealtimeTTS(OpenAILike):

    id: str = "not-set"
    name: str = "RealtimeTTS"
    provider: str = "RealtimeTTS"

    api_key: Optional[str] = getenv("REALTIME_TTS_API_KEY") or "EMPTY"
    base_url: Optional[str] = getenv("REALTIME_TTS_BASE_URL", "http://localhost:8000/v1")

    temperature: float = 0.7
    top_p: float = 0.8
    presence_penalty: float = 1.5
    top_k: Optional[int] = None
    enable_thinking: Optional[bool] = None

    def __post_init__(self):
        if not self.base_url:
            raise ValueError("REALTIME_TTS_API_KEY must be set via environment variable or explicit initialization")
        if self.id == "not-set":
            raise ValueError("Model ID must be set via environment variable or explicit initialization")

        body: Dict[str, Any] = {}
        if self.top_k is not None:
            body["top_k"] = self.top_k
        if self.enable_thinking is not None:
            body["chat_template_kwargs"] = {"enable_thinking": self.enable_thinking}
        self.extra_body = body or None

    def get_request_params(
        self,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        request_kwargs = super().get_request_params(
            response_format=response_format, tools=tools, tool_choice=tool_choice
        )

        realtime_sound_body: Dict[str, Any] = {}
        if self.top_k is not None:
            realtime_sound_body["top_k"] = self.top_k
        if self.enable_thinking is not None:
            realtime_sound_body.setdefault("chat_template_kwargs", {})["enable_thinking"] = self.enable_thinking

        if realtime_sound_body:
            existing_body = request_kwargs.get("extra_body") or {}
            request_kwargs["extra_body"] = {**existing_body, **realtime_sound_body}

        if request_kwargs:
            log_debug(f"Calling {self.provider} with request parameters: {request_kwargs}", log_level=2)
        return request_kwargs
