"""宿主适配器的统一接口（host-integration/spec.md 落地）。

核心引擎（lmr）不感知宿主差异；每个宿主通过一个薄适配器接入，
把各自的会话边界事件（SessionStart/SessionEnd 或等价物）转换成对
引擎的统一调用：
  - on_session_start()：会话开始，注入记忆索引到上下文（读）。
  - on_session_end(transcript)：会话结束，后台异步蒸馏（写）。

适配器只负责「事件 → 引擎调用」的转换与 hook 脚本生成，不做记忆
逻辑本身；记忆逻辑全部在引擎里。
"""

from __future__ import annotations

import abc


class HostAdapter(abc.ABC):
    """宿主适配器抽象基类。"""

    #: 宿主名（用于 --host 参数与注册表查找）。
    name = "base"

    @abc.abstractmethod
    def on_session_start(self) -> str:
        """会话开始：返回注入命令/内容（读路径，零模型零网络）。"""

    @abc.abstractmethod
    def on_session_end(self, transcript_path: str) -> str:
        """会话结束：返回后台蒸馏命令（写路径，异步执行）。"""

    @abc.abstractmethod
    def install(self, paths) -> dict:
        """生成 hook 脚本并注册到宿主的事件配置，幂等。

        返回安装结果（如生成的脚本路径、注册的 hook 条目数）。
        """
