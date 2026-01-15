"""
统一 TTS 语音合成插件（EasyttsPugin）

目标：除“语音合成后端”替换为 easytts 之外，尽量保持 xuqian13/tts_voice_plugin 的功能与行为一致：
- Action：关键词触发，生成/润色回复文本后转语音发送
- Command：/tts /voice /gsv2p /gptsovits /doubao /cosyvoice 等命令兼容（均路由到 easytts）
- 概率控制 / 强制关键词 / 分段发送 / SPLIT 标记 / 失败降级为文字
"""

import sys
sys.dont_write_bytecode = True

import asyncio
import random
from typing import List, Tuple, Type

from src.common.logger import get_logger
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.apis.plugin_register_api import register_plugin
from src.plugin_system.base.base_action import BaseAction, ActionActivationType
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.base.component_types import ComponentInfo, ChatMode
from src.plugin_system.base.config_types import ConfigField
from src.plugin_system.apis import generator_api

from .backends import TTSBackendRegistry, TTSResult
from .config_keys import ConfigKeys
from .utils.text import TTSTextUtils

logger = get_logger("EasyttsPugin")

VALID_BACKENDS = ["easytts"]


class TTSExecutorMixin:
    def _create_backend(self, backend_name: str):
        backend = TTSBackendRegistry.create(backend_name, self.get_config, self.log_prefix)
        if backend and hasattr(backend, "set_send_custom"):
            backend.set_send_custom(self.send_custom)
        return backend

    async def _execute_backend(self, backend_name: str, text: str, voice: str = "", emotion: str = "") -> TTSResult:
        backend = self._create_backend(backend_name)
        if not backend:
            return TTSResult(success=False, message=f"未知的 TTS 后端: {backend_name}")
        return await backend.execute(text, voice, emotion=emotion)

    def _get_default_backend(self) -> str:
        backend = self.get_config(ConfigKeys.GENERAL_DEFAULT_BACKEND, "easytts")
        if backend not in VALID_BACKENDS:
            return "easytts"
        return backend

    async def _send_error(self, message: str) -> None:
        if self.get_config(ConfigKeys.GENERAL_SEND_ERROR_MESSAGES, True):
            await self.send_text(message)


class UnifiedTTSAction(BaseAction, TTSExecutorMixin):
    """LLM 自动触发（关键词）"""

    action_name = "unified_tts_action"
    action_description = "用语音回复（easytts 云端仓库池）"
    activation_type = ActionActivationType.KEYWORD
    mode_enable = ChatMode.ALL
    parallel_action = False

    activation_keywords = [
        "语音", "说话", "朗读", "念一个", "读出来",
        "voice", "speak", "tts", "语音回复", "用语音说", "播报",
    ]
    keyword_case_sensitive = False

    action_parameters = {
        "text": "要转换为语音的文本内容（必填）",
        "voice": "可选：角色/预设。推荐格式 `角色:预设`，例如 `mika:普通`",
        "backend": "可选：TTS 后端（仅支持 easytts，可省略）",
        "emotion": "可选：情绪（用于自动选择 preset，映射见 config.toml 的 [easytts.emotion_preset_map]）",
    }

    action_require = [
        "当用户要求用语音回复时使用",
        "注意：过长内容会降级为文字回复",
    ]

    associated_types = ["text", "command"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = int(self.get_config(ConfigKeys.GENERAL_TIMEOUT, 60) or 60)
        self.max_text_length = int(self.get_config(ConfigKeys.GENERAL_MAX_TEXT_LENGTH, 200) or 200)

    def _check_force_trigger(self, text: str) -> bool:
        if not self.get_config(ConfigKeys.PROBABILITY_KEYWORD_FORCE_TRIGGER, True):
            return False
        force_keywords = self.get_config(ConfigKeys.PROBABILITY_FORCE_KEYWORDS, ["一定要用语音", "必须语音", "语音回复"])
        return any(kw in text for kw in force_keywords)

    def _probability_check(self, text: str) -> bool:
        # 与参考插件保持一致：若没有该配置，默认视为开启
        if not self.get_config(ConfigKeys.PROBABILITY_ENABLED, True):
            return True
        base_prob = float(self.get_config(ConfigKeys.PROBABILITY_BASE_PROBABILITY, 1.0) or 1.0)
        base_prob = max(0.0, min(1.0, base_prob))
        result = random.random() < base_prob
        logger.info(f"{self.log_prefix} 概率检查 {base_prob:.2f}, 结果={'通过' if result else '未通过'}")
        return result

    async def _get_final_text(self, raw_text: str, reason: str, use_replyer: bool) -> Tuple[bool, str]:
        """
        生成最终要转语音的文本。
        参考插件使用 generator_api.generate_reply（用于触发 POST_LLM 等事件与日程注入）。
        """
        max_text_length = int(self.get_config(ConfigKeys.GENERAL_MAX_TEXT_LENGTH, 200) or 200)

        if not use_replyer:
            if not raw_text:
                return False, ""
            return True, raw_text

        try:
            extra_info_parts = []
            if raw_text:
                extra_info_parts.append(f"期望的回复内容：{raw_text}")
            extra_info_parts.append(
                f"【重要】你的回复必须控制在{max_text_length}字以内，这是硬性要求。"
                f"超过此长度将无法转换为语音。请直接回复核心内容，不要啰嗦。"
            )

            success, llm_response = await generator_api.generate_reply(
                chat_stream=self.chat_stream,
                reply_message=self.action_message,
                reply_reason=reason,
                extra_info="\n".join(extra_info_parts),
                request_type="easytts_pugin",
                from_plugin=False,
            )
            if success and llm_response and getattr(llm_response, "content", None):
                logger.info(f"{self.log_prefix} 语音内容生成成功")
                return True, llm_response.content.strip()

            if raw_text:
                logger.warning(f"{self.log_prefix} 内容生成失败，使用原始文本")
                return True, raw_text

            return False, ""
        except Exception as e:
            logger.error(f"{self.log_prefix} 调用 replyer 出错: {e}")
            return bool(raw_text), raw_text

    async def execute(self) -> Tuple[bool, str]:
        async def send_message_single_sentences() -> Tuple[bool, str]:
            result = await self._execute_backend(backend, clean_text, voice, emotion)
            if result.success:
                text_preview = clean_text[:80] + "..." if len(clean_text) > 80 else clean_text
                await self.store_action_info(
                    action_build_into_prompt=True,
                    action_prompt_display=f"已用语音回复：{text_preview}",
                    action_done=True,
                )
            else:
                await self._send_error(f"语音合成失败: {result.message}")
            return result.success, result.message

        async def send_message_with_splited_sentences() -> Tuple[bool, str]:
            if len(sentences) > 1:
                logger.info(f"{self.log_prefix} 分段发送：共 {len(sentences)} 句")
                success_count = 0
                all_sentences_text: List[str] = []

                for i, sentence in enumerate(sentences):
                    if not sentence.strip():
                        continue

                    result = await self._execute_backend(backend, sentence, voice, emotion)
                    if result.success:
                        success_count += 1
                        all_sentences_text.append(sentence)
                    else:
                        logger.warning(f"{self.log_prefix} 第 {i + 1} 句失败: {result.message}")

                    if i < len(sentences) - 1 and split_delay > 0:
                        await asyncio.sleep(split_delay)

                if success_count > 0:
                    display_text = "".join(all_sentences_text)
                    text_preview = display_text[:80] + "..." if len(display_text) > 80 else display_text
                    await self.store_action_info(
                        action_build_into_prompt=True,
                        action_prompt_display=f"已用语音回复（{success_count}段）：{text_preview}",
                        action_done=True,
                    )
                    return True, f"成功发送 {success_count}/{len(sentences)} 条语音"

                await self._send_error("语音合成失败")
                return False, "all failed"

            return await send_message_single_sentences()

        try:
            raw_text = (self.action_data.get("text") or "").strip()
            voice = (self.action_data.get("voice") or "").strip()
            emotion = (self.action_data.get("emotion") or "").strip()
            reason = (self.action_data.get("reason") or "").strip()
            user_backend = (self.action_data.get("backend") or "").strip()

            use_replyer = self.get_config(ConfigKeys.GENERAL_USE_REPLYER_REWRITE, True)

            # 获取最终文本
            success, final_text = await self._get_final_text(raw_text, reason, use_replyer)
            if not success or not final_text:
                await self._send_error("无法生成语音内容")
                return False, "text empty"

            # 概率检查
            force_trigger = self._check_force_trigger(final_text)
            if not force_trigger and not self._probability_check(final_text):
                logger.info(f"{self.log_prefix} 概率未通过，降级为文字回复")
                await self.send_text(final_text)
                text_preview = final_text[:80] + "..." if len(final_text) > 80 else final_text
                await self.store_action_info(
                    action_build_into_prompt=True,
                    action_prompt_display=f"已用文字回复（概率未触发）：{text_preview}",
                    action_done=True,
                )
                return True, "probability skipped"

            # 清理文本（不做硬截断）
            clean_text = TTSTextUtils.clean_text(final_text, self.max_text_length)
            if not clean_text:
                await self._send_error("文本处理后为空")
                return False, "clean text empty"

            # 长度限制：超长降级为文字
            if len(clean_text) > self.max_text_length:
                logger.warning(
                    f"{self.log_prefix} 内容过长({len(clean_text)}>{self.max_text_length})，降级为文字回复"
                )
                await self.send_text(clean_text)
                text_preview = clean_text[:80] + "..." if len(clean_text) > 80 else clean_text
                await self.store_action_info(
                    action_build_into_prompt=True,
                    action_prompt_display=f"已用文字回复（内容过长）：{text_preview}",
                    action_done=True,
                )
                return True, "too long, fallback to text"

            # 后端（仅 easytts）
            backend = user_backend if user_backend in VALID_BACKENDS else self._get_default_backend()
            logger.info(f"{self.log_prefix} 使用后端: {backend}, voice={voice}")

            # 分段发送
            split_sentences = self.get_config(ConfigKeys.GENERAL_SPLIT_SENTENCES, True)
            split_delay = float(self.get_config(ConfigKeys.GENERAL_SPLIT_DELAY, 0.3) or 0.3)

            sentences: List[str] = []
            if "|||SPLIT|||" in clean_text:
                logger.info(f"{self.log_prefix} 使用 SPLIT 标记分段")
                sentences = [s.strip() for s in clean_text.split("|||SPLIT|||") if s.strip()]
                return await send_message_with_splited_sentences()
            if split_sentences:
                sentences = TTSTextUtils.split_sentences(clean_text)
                return await send_message_with_splited_sentences()
            return await send_message_single_sentences()

        except Exception as e:
            logger.error(f"{self.log_prefix} TTS 语音合成出错: {e}")
            await self._send_error(f"语音合成出错: {e}")
            return False, str(e)


class UnifiedTTSCommand(BaseCommand, TTSExecutorMixin):
    """手动命令触发"""

    command_name = "unified_tts_command"
    command_description = "将文本转换为语音（easytts 云端仓库池）"
    command_pattern = r"^/eztts\s+(?P<text>.+?)(?:\s+-v\s+(?P<voice>\S+))?(?:\s+-e\s+(?P<emotion>\S+))?$"
    command_help = "用法：/eztts <文本> [-v 角色:预设] [-e 情绪]"
    command_examples = [
        "/eztts 你好世界",
        "/eztts 今天天气不错 -v mika:普通",
        "/eztts 我有点难过 -v mika -e 伤心",
    ]
    intercept_message = True

    async def _send_help(self):
        default_backend = self._get_default_backend()
        help_text = (
            "【TTS 语音合成帮助】\n\n"
            "基本语法：\n"
            "/eztts <文本> [-v <角色:预设>] [-e <情绪>]\n\n"
            "示例：\n"
            "/eztts 你好世界\n"
            "/eztts 今天天气不错 -v mika:普通\n"
            "/eztts 我有点难过 -v mika -e 伤心\n\n"
            f"当前默认后端：{default_backend}\n"
        )
        await self.send_text(help_text)

    def _determine_backend(self, user_backend: str) -> str:
        raw_text = self.message.raw_message if self.message.raw_message else self.message.processed_plain_text
        if raw_text and raw_text.startswith("/eztts"):
            return "easytts"
        return self._get_default_backend()

    async def execute(self) -> Tuple[bool, str, bool]:
        try:
            text = (self.matched_groups.get("text") or "").strip()
            voice = (self.matched_groups.get("voice") or "").strip()
            emotion = (self.matched_groups.get("emotion") or "").strip()

            if text.lower() == "help":
                await self._send_help()
                return True, "help", True

            if not text:
                await self._send_error("请输入要转换为语音的文本")
                return False, "missing text", True

            max_length = int(self.get_config(ConfigKeys.GENERAL_MAX_TEXT_LENGTH, 200) or 200)
            clean_text = TTSTextUtils.clean_text(text, max_length)
            if not clean_text:
                await self._send_error("文本处理后为空")
                return False, "clean text empty", True
            if len(clean_text) > max_length:
                await self.send_text(clean_text)
                return True, "too long, fallback to text", True

            backend = self._determine_backend("")
            result = await self._execute_backend(backend, clean_text, voice, emotion)
            if not result.success:
                await self._send_error(f"语音合成失败: {result.message}")
            return result.success, result.message, True
        except Exception as e:
            await self._send_error(f"语音合成出错: {e}")
            return False, str(e), True


@register_plugin
class EasyttsPuginPlugin(BasePlugin):
    plugin_name = "EasyttsPugin"
    plugin_description = "easytts 语音合成插件（云端仓库池自动切换）"
    plugin_version = "0.1.0"
    plugin_author = "yunchenqwq"
    enable_plugin = True
    config_file_name = "config.toml"
    dependencies = []
    python_dependencies = ["aiohttp"]

    config_section_descriptions = {
        "plugin": "插件基本配置",
        "general": "通用设置",
        "components": "组件启用控制",
        "probability": "概率控制",
        "easytts": "EasyTTS（ModelScope Studio / Gradio）与云端仓库池",
    }

    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="0.1.0", description="配置版本"),
        },
        "general": {
            "default_backend": ConfigField(type=str, default="easytts", description="默认后端（仅 easytts）"),
            "timeout": ConfigField(type=int, default=60, description="请求超时（秒）"),
            "max_text_length": ConfigField(type=int, default=200, description="最大文本长度（超出则降级为文字）"),
            "use_replyer_rewrite": ConfigField(type=bool, default=True, description="是否使用 replyer 润色语音内容"),
            "audio_output_dir": ConfigField(type=str, default="", description="音频输出目录（留空使用项目根目录）"),
            "use_base64_audio": ConfigField(type=bool, default=True, description="是否使用 base64 方式发送音频"),
            "split_sentences": ConfigField(type=bool, default=True, description="是否按标点分句发送"),
            "split_delay": ConfigField(type=float, default=0.3, description="分句发送间隔（秒）"),
            "send_error_messages": ConfigField(type=bool, default=True, description="失败时是否发送错误提示"),
        },
        "components": {
            "action_enabled": ConfigField(type=bool, default=True, description="是否启用 Action（自动触发）"),
            "command_enabled": ConfigField(type=bool, default=True, description="是否启用 Command（手动命令）"),
        },
        "probability": {
            "enabled": ConfigField(type=bool, default=False, description="是否启用概率控制"),
            "base_probability": ConfigField(type=float, default=1.0, description="触发概率（0~1）"),
            "keyword_force_trigger": ConfigField(type=bool, default=True, description="关键词强制触发"),
            "force_keywords": ConfigField(type=list, default=["一定要用语音", "必须语音", "语音回复"], description="强制触发关键词"),
        },
        "easytts": {
            "default_character": ConfigField(type=str, default="mika", description="默认角色（character）"),
            "default_preset": ConfigField(type=str, default="普通", description="默认预设（preset）"),
            "characters": ConfigField(
                type=list,
                default=[{"name": "mika", "presets": ["普通", "开心", "伤心", "生气"]}],
                description="角色模型列表（可选，用于提示/校验）",
                item_type="object",
                item_fields={
                    "name": {"type": "string", "label": "角色名", "required": True},
                    "presets": {"type": "array", "label": "预设列表", "required": False},
                    # 可选：角色级别的情绪映射（优先级高于全局 emotion_preset_map）
                    "emotion_preset_map": {"type": "object", "label": "情绪->预设映射", "required": False},
                },
            ),
            "emotion_preset_map": ConfigField(
                type=dict,
                default={"普通": "普通", "开心": "开心", "伤心": "伤心", "生气": "生气"},
                description="全局情绪->预设映射（Action/Command 传 emotion 时使用）",
            ),
            "remote_split_sentence": ConfigField(type=bool, default=True, description="是否让远端也进行分句合成"),
            "prefer_idle_endpoint": ConfigField(type=bool, default=True, description="优先选择空闲仓库（queue_size 低）"),
            "busy_queue_threshold": ConfigField(type=int, default=0, description="队列繁忙阈值（>此值视为忙）"),
            "status_timeout": ConfigField(type=int, default=3, description="queue/status 超时（秒）"),
            "join_timeout": ConfigField(type=int, default=30, description="queue/join 超时（秒）"),
            "sse_timeout": ConfigField(type=int, default=300, description="queue/data SSE 超时（秒）"),
            "download_timeout": ConfigField(type=int, default=120, description="音频下载超时（秒）"),
            "trust_env": ConfigField(type=bool, default=False, description="aiohttp 是否继承系统代理"),
            "endpoints": ConfigField(
                type=list,
                default=[{"name": "default", "base_url": "", "studio_token": "", "fn_index": 3, "trigger_id": 19}],
                description="云端仓库池（多个 endpoints 自动切换）",
                item_type="object",
                item_fields={
                    "name": {"type": "string", "label": "名称", "required": True},
                    "base_url": {"type": "string", "label": "Gradio 基地址", "required": True},
                    "studio_token": {"type": "string", "label": "studio_token", "required": True},
                    "fn_index": {"type": "number", "label": "fn_index", "default": 3},
                    "trigger_id": {"type": "number", "label": "trigger_id", "default": 19},
                },
            ),
        },
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        components: List[Tuple[ComponentInfo, Type]] = []
        try:
            action_enabled = self.get_config(ConfigKeys.COMPONENTS_ACTION_ENABLED, True)
            command_enabled = self.get_config(ConfigKeys.COMPONENTS_COMMAND_ENABLED, True)
        except AttributeError:
            action_enabled = True
            command_enabled = True
        if action_enabled:
            components.append((UnifiedTTSAction.get_action_info(), UnifiedTTSAction))
        if command_enabled:
            components.append((UnifiedTTSCommand.get_command_info(), UnifiedTTSCommand))
        return components
