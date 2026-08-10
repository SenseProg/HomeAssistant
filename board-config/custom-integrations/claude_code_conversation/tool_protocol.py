"""JSON-протокол виклику інструментів поверх Claude Code CLI.

CLI у режимі `--print` не має нативного function calling, тому інструменти
описуються в системному промті, а модель відповідає або звичайним текстом, або
одним рядком JSON виду:

    {"tool_call": {"name": "HassTurnOn", "arguments": {"name": "Бойлер"}}}

Модуль навмисно тримає лише чисті функції розбору й форматування: виконання
інструментів і всі перевірки безпеки лишаються у conversation.py.
"""

from __future__ import annotations

import json
from typing import Any

# Достатньо, щоб побачити початок JSON-обгортки ще до кінця генерації і не
# показати користувачеві технічний рядок замість відповіді.
SNIFF_PREFIX_CHARS = 24


def looks_like_tool_call(text: str) -> bool:
    """Return True while the streamed text may still be a tool-call JSON."""
    head = text.lstrip()[:SNIFF_PREFIX_CHARS]
    if not head:
        return False
    if not head.startswith("{"):
        return False
    # Дозволяємо частковий префікс: рядок ще генерується.
    candidate = '{"tool_call"'
    return candidate.startswith(head[: len(candidate)]) or head.startswith(candidate)


def parse_tool_call(text: str) -> dict[str, Any] | None:
    """Return {'name': str, 'arguments': dict} when the answer is a tool call."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    # Модель іноді додає пояснення після JSON — беремо перший повний об'єкт.
    decoder = json.JSONDecoder()
    try:
        payload, _end = decoder.raw_decode(stripped)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    call = payload.get("tool_call")
    if not isinstance(call, dict):
        return None
    name = call.get("name")
    if not isinstance(name, str) or not name:
        return None
    arguments = call.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    return {"name": name, "arguments": arguments}


def describe_tools(tools: list[Any]) -> str:
    """Render the tool catalogue for the system prompt."""
    lines: list[str] = []
    for tool in tools:
        description = getattr(tool, "description", "") or ""
        schema_text = ""
        parameters = getattr(tool, "parameters", None)
        if parameters is not None:
            try:
                from voluptuous_openapi import convert

                schema_text = json.dumps(convert(parameters), ensure_ascii=False)
            except Exception:  # noqa: BLE001 - опис не критичний для роботи
                schema_text = ""
        line = f"- {tool.name}: {description}".rstrip(": ")
        if schema_text and len(schema_text) < 700:
            line += f"\n  аргументи: {schema_text}"
        lines.append(line)
    return "\n".join(lines)


def read_tool_instructions(tools: tuple[dict[str, str], ...]) -> str:
    """Return the always-available read-only half of the tool protocol.

    Ці інструменти нічого не змінюють у будинку, тому доступні незалежно від
    того, дозволено керування чи ні. Вони існують саме для того, щоб агент не
    відповідав «не можу сам подивитися історію» і не просив користувача
    повторити питання окремим повідомленням.
    """
    lines = "\n".join(
        f"- {tool['name']}: {tool['description']}\n  аргументи: {tool['arguments']}"
        for tool in tools
    )
    return (
        "\n\nЧИТАННЯ ДАНИХ.\n"
        "Крім готових блоків у запиті, тобі доступні інструменти читання. Вони "
        "нічого не вмикають і не змінюють:\n\n"
        f"{lines}\n\n"
        "Виклик - РІВНО один рядок JSON і нічого більше:\n"
        '{"tool_call": {"name": "НАЗВА", "arguments": {…}}}\n\n'
        "Викликай їх лише тоді, коли наданих блоків справді бракує: інша "
        "сутність, інше вікно часу, потрібні атрибути. Не проси користувача "
        "підтвердити перелік сутностей чи період - обери розумні значення сам "
        "і подивись. Після результату відповідай звичайним текстом українською."
    )


def tool_instructions(tools: list[Any]) -> str:
    """Return the system-prompt section that enables the JSON tool protocol."""
    return (
        "\n\nКЕРУВАННЯ ПРИСТРОЯМИ.\n"
        "Тобі доступні інструменти Home Assistant, перелічені нижче. Вони діють "
        "лише на невеликий список відкритих сутностей; усе інше — тільки читання.\n\n"
        f"{describe_tools(tools)}\n\n"
        "Щоб скористатися інструментом, поверни РІВНО один рядок JSON і нічого "
        "більше — без пояснень, без markdown, без тексту до або після:\n"
        '{"tool_call": {"name": "НАЗВА", "arguments": {…}}}\n\n'
        "Правила: не вигадуй назв інструментів і сутностей поза списком; якщо "
        "запит стосується недоступного пристрою, відповідай звичайним текстом і "
        "поясни, що дію треба виконати з дашборда; якщо для дії бракує даних, "
        "спитай уточнення текстом. Після виконання інструмента тобі повернуть "
        "результат, і тоді ти маєш відповісти користувачеві звичайним текстом "
        "українською, підтвердивши, що саме змінилося."
    )


def format_tool_result(
    name: str, result: Any, error: str | None = None, max_chars: int = 2000
) -> str:
    """Render the tool outcome that is fed back into the next CLI round."""
    if error is not None:
        return (
            f"<tool_result name=\"{name}\" status=\"error\">\n{error}\n</tool_result>"
        )
    if isinstance(result, str):
        # Інструменти читання повертають уже готовий текст: json.dumps перетворив
        # би переноси рядків на \n і зробив журнал нечитабельним.
        rendered = result
    else:
        try:
            rendered = json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            rendered = str(result)
    return (
        f"<tool_result name=\"{name}\" status=\"ok\">\n{rendered[:max_chars]}\n"
        "</tool_result>"
    )
