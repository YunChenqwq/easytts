"""
配置键常量定义（集中管理，避免硬编码）。
"""


class ConfigKeys:
    # Plugin
    PLUGIN_ENABLED = "plugin.enabled"
    PLUGIN_CONFIG_VERSION = "plugin.config_version"

    # General
    GENERAL_DEFAULT_BACKEND = "general.default_backend"
    GENERAL_TIMEOUT = "general.timeout"
    GENERAL_MAX_TEXT_LENGTH = "general.max_text_length"
    GENERAL_USE_REPLYER_REWRITE = "general.use_replyer_rewrite"
    GENERAL_AUDIO_OUTPUT_DIR = "general.audio_output_dir"
    GENERAL_USE_BASE64_AUDIO = "general.use_base64_audio"
    GENERAL_SPLIT_SENTENCES = "general.split_sentences"
    GENERAL_SPLIT_DELAY = "general.split_delay"
    GENERAL_SEND_ERROR_MESSAGES = "general.send_error_messages"

    # Components
    COMPONENTS_ACTION_ENABLED = "components.action_enabled"
    COMPONENTS_COMMAND_ENABLED = "components.command_enabled"

    # Probability
    PROBABILITY_ENABLED = "probability.enabled"
    PROBABILITY_BASE_PROBABILITY = "probability.base_probability"
    PROBABILITY_KEYWORD_FORCE_TRIGGER = "probability.keyword_force_trigger"
    PROBABILITY_FORCE_KEYWORDS = "probability.force_keywords"

    # EasyTTS
    EASYTTS_ENDPOINTS = "easytts.endpoints"
    EASYTTS_DEFAULT_CHARACTER = "easytts.default_character"
    EASYTTS_DEFAULT_PRESET = "easytts.default_preset"
    # “模型/角色”列表与情绪预设映射（用于 UI/LLM 提示与后端情绪选择）
    EASYTTS_CHARACTERS = "easytts.characters"
    EASYTTS_EMOTION_PRESET_MAP = "easytts.emotion_preset_map"
    EASYTTS_REMOTE_SPLIT_SENTENCE = "easytts.remote_split_sentence"
    EASYTTS_PREFER_IDLE_ENDPOINT = "easytts.prefer_idle_endpoint"
    EASYTTS_BUSY_QUEUE_THRESHOLD = "easytts.busy_queue_threshold"
    EASYTTS_STATUS_TIMEOUT = "easytts.status_timeout"
    EASYTTS_JOIN_TIMEOUT = "easytts.join_timeout"
    EASYTTS_SSE_TIMEOUT = "easytts.sse_timeout"
    EASYTTS_DOWNLOAD_TIMEOUT = "easytts.download_timeout"
    EASYTTS_TRUST_ENV = "easytts.trust_env"
