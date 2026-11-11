"""可插拔 LLM 客户端（v1.1）。

封装对任意 OpenAI 兼容接口的调用，用于「大模型软判断（第二审）」与
「存量批量蒸馏」。设计约束（design D4 / write-approval）：

- LLM 只产出「软判断报告」与「候选」，绝不直接落库、绝不自行拍板要不要人；
- key 只从环境变量或私有数据目录读取，公开仓库不发布任何真实 key；
- 未配置或调用失败时抛出 :class:`LLMUnavailable`，由上层走降级路径。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

ENV_LLM_KEY = "LMR_LLM_KEY"


class LLMUnavailable(RuntimeError):
    """LLM 未配置或调用失败。上层据此走降级路径。"""


class LLMClient:
    """极简 OpenAI 兼容聊天客户端，零第三方依赖（仅标准库）。"""

    def __init__(self, base_url, model, api_key, timeout=60):
        if not base_url or not model or not api_key:
            raise LLMUnavailable("LLM 未完整配置（base_url/model/api_key 缺一不可）")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def chat(self, messages, temperature=0.0, max_tokens=2048, response_format=None):
        """发一轮对话，返回助手文本内容（忽略 reasoning_content）。

        response_format 可选：传 {"type": "json_object"} 强制 JSON 输出；
        传 {"type": "json_schema", "json_schema": {...}} 强制符合给定 schema。
        某些网关可能不支持，失败时由上层降级（正则兜底解析）。
        """
        url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            raise LLMUnavailable("LLM 调用失败：%s" % exc) from exc
        except ValueError as exc:
            raise LLMUnavailable("LLM 返回非 JSON：%s" % exc) from exc

        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailable("LLM 返回结构异常：%s" % exc) from exc

        # 只取 content，丢弃 reasoning_content（省 token、避免污染下游）。
        content = msg.get("content") or ""
        if not content:
            raise LLMUnavailable("LLM 返回空内容")
        return content


def resolve_api_key(settings, data_config):
    """解析 api_key：环境变量 > 数据目录 config > 用户级 config。"""
    for source in (os.environ.get(ENV_LLM_KEY), data_config.get("llm_key"), settings.get("llm_key")):
        if source:
            return source
    return ""


def make_client(settings, data_config):
    """按配置构造 LLMClient；未启用或未配置则抛 LLMUnavailable。"""
    if not settings.get("llm_enabled", False):
        raise LLMUnavailable("LLM 未启用（llm_enabled=false）")
    key = resolve_api_key(settings, data_config)
    return LLMClient(
        base_url=settings.get("llm_base_url", ""),
        model=settings.get("llm_model", ""),
        api_key=key,
    )
