"""宿主适配器的统一接口（host-integration/spec.md 落地）。

核心引擎（lmr）不感知宿主差异；每个宿主通过一个薄适配器接入。
抽象层只规定记忆系统的两个动作，不绑定具体的宿主事件名——
「挂到哪个事件」由各宿主适配器自己决定：

  - on_recall()：读路径——召回并注入相关记忆到宿主上下文（零模型零网络）。
    宿主自己决定挂哪个事件（WorkBuddy 用 UserPromptSubmit，其他宿主
    用各自的等价事件，例如 DSH 的会话开始/提问事件）。
  - on_capture(transcript_path)：写路径——捕获一段会话记录，后台异步蒸馏。

适配器只负责「事件 → 引擎调用」的转换与 hook 脚本生成，不做记忆逻辑
本身；记忆逻辑全部在引擎里。

多宿主扩展约定：新增一个平台时，只需继承 HostAdapter 实现 name /
on_recall / on_capture / install 四个成员，并在 lmr/host/__init__.py 的
注册表里登记，无需改动引擎或其他宿主。
"""

from __future__ import annotations

import abc


class HostAdapter(abc.ABC):
    """宿主适配器抽象基类。"""

    #: 宿主名（用于 --host 参数与注册表查找）。
    name = "base"

    @abc.abstractmethod
    def on_recall(self) -> str:
        """读路径：返回召回/注入记忆的命令或内容（零模型零网络）。"""

    @abc.abstractmethod
    def on_capture(self, transcript_path: str) -> str:
        """写路径：返回后台异步蒸馏命令，入参为会话记录文件路径。"""

    @abc.abstractmethod
    def install(self, paths) -> dict:
        """生成 hook 脚本并注册到宿主的事件配置，幂等。

        返回安装结果（如生成的脚本路径、注册的 hook 条目数）。
        """
