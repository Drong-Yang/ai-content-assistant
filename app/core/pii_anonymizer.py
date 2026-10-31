"""
PII 脱敏模块
检测和处理敏感个人信息（邮箱、信用卡、API Key、手机号等）

支持多种脱敏策略：
- redact: 完全替换为 [REDACTED_xxx]
- mask: 部分隐藏，如 ****1234
- hash: 替换为哈希值
"""
import re
import hashlib
from typing import Callable, Literal, Optional
from dataclasses import dataclass, field


# ============== PII 类型定义 ==============

@dataclass
class PIIPattern:
    """PII 检测模式"""
    name: str
    pattern: re.Pattern
    mask_func: Optional[Callable[[str], str]] = None  # 自定义 mask 函数


# 内置 PII 检测模式
BUILTIN_PII_PATTERNS: dict[str, PIIPattern] = {
    # 邮箱
    "email": PIIPattern(
        name="email",
        pattern=re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        mask_func=lambda x: x.split('@')[0][:2] + '***@' + x.split('@')[1] if '@' in x else x
    ),
    
    # 信用卡（支持空格/横线分隔）
    "credit_card": PIIPattern(
        name="credit_card",
        pattern=re.compile(r'\b(?:\d{4}[- ]?){3}\d{4}\b'),
        mask_func=lambda x: re.sub(r'\d', '*', x[:-4]) + x[-4:]
    ),
    
    # API Key（常见格式）
    "api_key": PIIPattern(
        name="api_key",
        pattern=re.compile(
            r'\b('
            r'sk-[a-zA-Z0-9]{20,}|'           # OpenAI
            r'sk-proj-[a-zA-Z0-9_-]{20,}|'    # OpenAI Project
            r'lsv2_pt_[a-zA-Z0-9_]{20,}|'     # LangSmith
            r'ak-[a-zA-Z0-9]{20,}|'           # 通用 ak-
            r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'  # UUID 格式的 key
            r')\b'
        ),
        mask_func=lambda x: x[:8] + '***' + x[-4:] if len(x) > 12 else '***'
    ),
    
    # 中国手机号
    "phone_cn": PIIPattern(
        name="phone",
        pattern=re.compile(r'\b1[3-9]\d{9}\b'),
        mask_func=lambda x: x[:3] + '****' + x[-4:]
    ),
    
    # IP 地址
    "ip": PIIPattern(
        name="ip",
        pattern=re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        mask_func=lambda x: '.'.join(x.split('.')[:2]) + '.***.***'
    ),
    
    # 身份证号（中国 18 位）
    "id_card_cn": PIIPattern(
        name="id_card",
        pattern=re.compile(r'\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'),
        mask_func=lambda x: x[:6] + '********' + x[-4:]
    ),
}


# ============== PII 脱敏器 ==============

Strategy = Literal["redact", "mask", "hash", "block"]


@dataclass
class PIIMatch:
    """PII 匹配结果"""
    text: str
    start: int
    end: int
    pii_type: str


class PIIAnonymizer:
    """
    PII 脱敏器
    
    使用示例:
        anonymizer = PIIAnonymizer()
        anonymizer.add_pattern("email", strategy="mask")
        anonymizer.add_pattern("phone_cn", strategy="redact")
        
        result = anonymizer.anonymize("联系邮箱: test@example.com, 电话: 13812345678")
        # 输出: "联系邮箱: te***@example.com, 电话: [REDACTED_PHONE]"
    """
    
    def __init__(self):
        self._patterns: list[tuple[PIIPattern, Strategy]] = []
    
    def add_pattern(
        self,
        pii_type: str,
        strategy: Strategy = "redact",
        detector: Optional[str | re.Pattern | Callable] = None,
    ) -> "PIIAnonymizer":
        """
        添加 PII 检测模式
        
        Args:
            pii_type: PII 类型名称（内置: email, credit_card, api_key, phone_cn, ip, id_card_cn）
            strategy: 脱敏策略 (redact, mask, hash, block)
            detector: 自定义检测器（正则字符串、编译后的正则、或检测函数）
        
        Returns:
            self（支持链式调用）
        """
        if detector is not None:
            # 自定义检测器
            if isinstance(detector, str):
                pattern = PIIPattern(name=pii_type, pattern=re.compile(detector))
            elif isinstance(detector, re.Pattern):
                pattern = PIIPattern(name=pii_type, pattern=detector)
            else:
                # 函数检测器暂不支持，使用正则
                raise ValueError("Currently only regex detectors are supported")
        else:
            # 使用内置模式
            if pii_type not in BUILTIN_PII_PATTERNS:
                raise ValueError(f"Unknown PII type: {pii_type}. Available: {list(BUILTIN_PII_PATTERNS.keys())}")
            pattern = BUILTIN_PII_PATTERNS[pii_type]
        
        self._patterns.append((pattern, strategy))
        return self
    
    def detect(self, content: str) -> list[PIIMatch]:
        """
        检测内容中的 PII
        
        Args:
            content: 要检测的文本
            
        Returns:
            检测到的 PII 列表
        """
        matches = []
        for pattern, _ in self._patterns:
            for match in pattern.pattern.finditer(content):
                matches.append(PIIMatch(
                    text=match.group(),
                    start=match.start(),
                    end=match.end(),
                    pii_type=pattern.name
                ))
        return matches
    
    def anonymize(self, content: str) -> str:
        """
        对内容进行脱敏处理
        
        Args:
            content: 要脱敏的文本
            
        Returns:
            脱敏后的文本
        """
        if not content or not isinstance(content, str):
            return content
        
        result = content
        
        # 按照添加顺序处理每个模式
        for pattern, strategy in self._patterns:
            result = self._apply_strategy(result, pattern, strategy)
        
        return result
    
    def _apply_strategy(self, content: str, pattern: PIIPattern, strategy: Strategy) -> str:
        """应用脱敏策略"""
        
        def replace_func(match: re.Match) -> str:
            text = match.group()
            
            if strategy == "redact":
                return f"[REDACTED_{pattern.name.upper()}]"
            
            elif strategy == "mask":
                if pattern.mask_func:
                    return pattern.mask_func(text)
                # 默认 mask：保留首尾，中间用 *
                if len(text) <= 4:
                    return '*' * len(text)
                return text[:2] + '*' * (len(text) - 4) + text[-2:]
            
            elif strategy == "hash":
                hash_value = hashlib.sha256(text.encode()).hexdigest()[:8]
                return f"[HASH_{pattern.name.upper()}_{hash_value}]"
            
            elif strategy == "block":
                raise PIIDetectedError(f"PII detected: {pattern.name}")
            
            return text
        
        return pattern.pattern.sub(replace_func, content)
    
    def anonymize_dict(self, data: dict, recursive: bool = True) -> dict:
        """
        对字典中的所有字符串值进行脱敏
        
        Args:
            data: 要脱敏的字典
            recursive: 是否递归处理嵌套字典
            
        Returns:
            脱敏后的字典
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.anonymize(value)
            elif isinstance(value, dict) and recursive:
                result[key] = self.anonymize_dict(value, recursive)
            elif isinstance(value, list):
                result[key] = [
                    self.anonymize(item) if isinstance(item, str) 
                    else self.anonymize_dict(item, recursive) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result


class PIIDetectedError(Exception):
    """检测到 PII 时抛出的异常（用于 block 策略）"""
    pass


# ============== 预配置的脱敏器实例 ==============

def create_default_anonymizer() -> PIIAnonymizer:
    """
    创建默认配置的脱敏器
    
    包含：邮箱、信用卡、API Key、手机号
    """
    return (
        PIIAnonymizer()
        .add_pattern("email", strategy="mask")
        .add_pattern("credit_card", strategy="mask")
        .add_pattern("api_key", strategy="redact")
        .add_pattern("phone_cn", strategy="mask")
    )


# 全局默认脱敏器实例
default_anonymizer = create_default_anonymizer()


# ============== structlog Processor ==============

def pii_anonymize_processor(logger, method_name: str, event_dict: dict) -> dict:
    """
    structlog 处理器：对日志内容进行 PII 脱敏
    
    用法：在 structlog 配置中添加此处理器
    """
    return default_anonymizer.anonymize_dict(event_dict)
