from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

import phonenumbers
from detect_secrets.plugins.base import RegexBasedDetector
from detect_secrets.settings import get_plugins, transient_settings

EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
CPF_PATTERN = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
SECRET_PLUGINS = (
    "AWSKeyDetector",
    "AzureStorageKeyDetector",
    "BasicAuthDetector",
    "DiscordBotTokenDetector",
    "GitHubTokenDetector",
    "GitLabTokenDetector",
    "IbmCloudIamDetector",
    "IbmCosHmacDetector",
    "JwtTokenDetector",
    "MailchimpDetector",
    "NpmDetector",
    "OpenAIDetector",
    "PrivateKeyDetector",
    "PypiTokenDetector",
    "SendGridDetector",
    "SlackDetector",
    "SquareOAuthDetector",
    "StripeDetector",
    "TelegramBotTokenDetector",
    "TwilioKeyDetector",
)
CAPTURE_ONLY_DETECTORS = {
    "AWSKeyDetector",
    "BasicAuthDetector",
    "IbmCloudIamDetector",
    "IbmCosHmacDetector",
}
NPM_TOKEN_PATTERN = re.compile(r"(?:npm_[A-Za-z0-9]{36}|[A-Fa-f0-9-]{36})")
REDACTED_FIELD_LABELS = frozenset(
    {"and", "cpf", "e", "email", "mail", "or", "ou", "phone", "telefone", "tel"}
)


class RedactionKind(Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    CPF = "CPF"
    CREDENTIAL = "SECRET"


@dataclass(frozen=True)
class RedactionSpan:
    start: int
    end: int
    kind: RedactionKind


@dataclass(frozen=True)
class DetectSecretsScanner:
    plugins: tuple[RegexBasedDetector, ...]

    @classmethod
    def with_default_plugins(cls) -> DetectSecretsScanner:
        config = {"plugins_used": [{"name": name} for name in SECRET_PLUGINS]}
        with transient_settings(config):
            configured = tuple(get_plugins())
        plugins = tuple(plugin for plugin in configured if isinstance(plugin, RegexBasedDetector))
        if len(plugins) != len(configured):
            raise RuntimeError("configured secret detector is not regex based")
        return cls(plugins=plugins)

    def spans(self, text: str) -> tuple[RedactionSpan, ...]:
        spans: list[RedactionSpan] = []
        offset = 0
        for line in text.splitlines(keepends=True) or [text]:
            for plugin in self.plugins:
                for pattern in plugin.denylist:
                    spans.extend(
                        RedactionSpan(
                            offset + start,
                            offset + end,
                            RedactionKind.CREDENTIAL,
                        )
                        for match in pattern.finditer(line)
                        for start, end in secret_match_spans(type(plugin).__name__, match)
                    )
            offset += len(line)
        return tuple(spans)


def secret_match_spans(detector_name: str, match: re.Match[str]) -> tuple[tuple[int, int], ...]:
    if detector_name in CAPTURE_ONLY_DETECTORS:
        captured = next(
            (
                match.span(index)
                for index in range(1, len(match.groups()) + 1)
                if match.group(index)
            ),
            match.span(),
        )
        return (captured,)
    if detector_name == "NpmDetector":
        value, start = next(
            (match.group(index), match.start(index))
            for index in range(1, len(match.groups()) + 1)
            if match.group(index)
        )
        token = NPM_TOKEN_PATTERN.match(value)
        return ((start + token.start(), start + token.end()),) if token else (match.span(),)
    return (match.span(),)


@dataclass(frozen=True)
class TextCleaner:
    secret_scanner: DetectSecretsScanner

    @classmethod
    def with_default_secret_scanner(cls) -> TextCleaner:
        return cls(secret_scanner=DetectSecretsScanner.with_default_plugins())

    def clean(self, text: str) -> str | None:
        spans = [
            *(
                RedactionSpan(match.start(), match.end(), RedactionKind.EMAIL)
                for match in EMAIL_PATTERN.finditer(text)
            ),
            *(
                RedactionSpan(match.start(), match.end(), RedactionKind.CPF)
                for match in CPF_PATTERN.finditer(text)
                if is_valid_cpf(match.group())
            ),
            *phone_spans(text),
            *self.secret_scanner.spans(text),
        ]
        cleaned = replace_spans(text, merge_spans(spans))
        return cleaned if has_meaningful_text(cleaned) else None


def phone_spans(text: str) -> tuple[RedactionSpan, ...]:
    return tuple(
        RedactionSpan(match.start, match.end, RedactionKind.PHONE)
        for match in phonenumbers.PhoneNumberMatcher(text, "BR")
        if phonenumbers.is_valid_number(match.number)
    )


def is_valid_cpf(value: str) -> bool:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for index in (9, 10):
        total = sum(int(digits[position]) * (index + 1 - position) for position in range(index))
        check = (total * 10 % 11) % 10
        if check != int(digits[index]):
            return False
    return True


def merge_spans(spans: list[RedactionSpan]) -> tuple[RedactionSpan, ...]:
    priority = {
        RedactionKind.CREDENTIAL: 4,
        RedactionKind.CPF: 3,
        RedactionKind.EMAIL: 2,
        RedactionKind.PHONE: 1,
    }
    ordered = sorted(spans, key=lambda span: (span.start, -span.end, -priority[span.kind]))
    merged: list[RedactionSpan] = []
    for span in ordered:
        if span.start >= span.end:
            continue
        if not merged or span.start >= merged[-1].end:
            merged.append(span)
            continue
        previous = merged[-1]
        winner = span if priority[span.kind] > priority[previous.kind] else previous
        merged[-1] = RedactionSpan(
            min(previous.start, span.start), max(previous.end, span.end), winner.kind
        )
    return tuple(merged)


def replace_spans(text: str, spans: tuple[RedactionSpan, ...]) -> str:
    for span in reversed(spans):
        text = f"{text[: span.start]}[{span.kind.value}]{text[span.end :]}"
    return text


def has_meaningful_text(text: str) -> bool:
    without_markers = re.sub(r"\[(?:EMAIL|PHONE|CPF|SECRET)\]", "", text)
    words = re.findall(r"\w+", without_markers.casefold(), flags=re.UNICODE)
    return any(
        word not in REDACTED_FIELD_LABELS
        and any(unicodedata.category(character)[0] in {"L", "N"} for character in word)
        for word in words
    )
