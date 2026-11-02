"""Requirements and validated evaluator output; no provider dependencies."""
import re
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ContentBrief(BaseModel):
    audience: str = Field(default="", max_length=200)
    tone: str = Field(default="", max_length=200)
    min_chars: int = Field(default=800, ge=0, le=3000)
    max_chars: int = Field(default=1200, ge=50, le=4000)
    required_sections: list[str] = Field(default_factory=list, max_length=8)
    preserve_phrases: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_limits(self):
        if self.min_chars > self.max_chars:
            raise ValueError("最小长度不能大于最大长度")
        if any(not s.strip() or len(s) > 100 for s in self.required_sections + self.preserve_phrases):
            raise ValueError("栏目/保留文本须为1—100字符")
        return self


class QualityItem(BaseModel):
    criterion: str = Field(min_length=1, max_length=100)
    passed: bool
    issue: str = Field(default="", max_length=500)
    evidence: str = Field(default="", max_length=500)
    evidence_id: int = Field(default=0, ge=0)
    suggestion: str = Field(default="", max_length=500)
    kind: Literal["semantic", "rule"] = "semantic"
    evidence_normalized_whitespace: bool = False


class SemanticReview(BaseModel):
    checks: list[QualityItem] = Field(min_length=3, max_length=6)


def count_chars(content: str) -> int:
    """Non-whitespace characters, including punctuation/Markdown symbols."""
    return len(re.sub(r"\s", "", content))


def article_segments(content: str) -> list[str]:
    return [part.strip() for part in re.split(r'(?<=[。！？!?])|\n+', content) if part.strip()]


def rule_checks(content: str, brief: dict) -> list[dict]:
    size = count_chars(content)
    lo, hi = brief.get("min_chars", 800), brief.get("max_chars", 1200)
    checks = [QualityItem(criterion="正文长度", passed=lo <= size <= hi, kind="rule",
        evidence=f"非空白字符数={size}，范围={lo}—{hi}",
        issue="" if lo <= size <= hi else "正文长度不符合要求",
        suggestion=f"将正文控制在{lo}—{hi}个非空白字符").model_dump()]
    for field, label in [("required_sections", "必含栏目"), ("preserve_phrases", "保留文本")]:
        for phrase in brief.get(field, []):
            checks.append(QualityItem(criterion=label, passed=phrase in content, kind="rule",
                evidence=phrase if phrase in content else "",
                issue="" if phrase in content else f"缺少：{phrase}",
                suggestion=f"原样保留或加入：{phrase}").model_dump())
    return checks


def remaining_tokens(state: dict) -> int:
    return max(0, state.get("quality_policy", {}).get("token_budget", 30000)
               - state.get("quality_tokens_used", 0))


def input_estimate(text: str) -> int:
    # Conservative admission estimate, not provider billing data.
    return len(text) * 2 + 256
