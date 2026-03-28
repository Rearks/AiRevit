# -*- coding: utf-8 -*-
# NODE 2 — Parse & Validate JSON Action Plan from LLM
# IN[0] : str  - Raw response text from Node 1
# OUT   : list - [thought (str), actions (list of dicts), status (str)]

import json
import traceback

# --- КОНСТАНТЫ ---
# Выход по умолчанию, если нода не запустилась
OUT_DEFAULT = ["Node 2: не запущен", [], ""]
# Список разрешённых действий. Set для быстрого поиска.
ALLOWED_ACTIONS = {
    "create_wall",
    "create_room_box",
    "create_floor",
    "create_room",
}

# --- ГЛАВНАЯ ЛОГИКА ---
try:
    # Шаг 1: Получаем сырой текст от Node 1
    raw_text = IN[0] if IN[0] else ""

    # Шаг 2: Проверяем, не вернул ли Node 1 ошибку или пустой ответ
    if not raw_text:
        OUT = ["ERROR", [], "Пустой ответ от Node 1"]
    elif raw_text.startswith("ERROR") or raw_text.startswith("Exception") or raw_text.startswith("WebException"):
        OUT = ["ERROR", [], "Node 1 вернул ошибку: " + str(raw_text)[:500]]
    else:
        # Шаг 3: Парсим JSON-ответ от сервера OpenRouter
        server_json = json.loads(raw_text)

        # Шаг 4: Проверяем на наличие ошибок на уровне API
        if "error" in server_json:
            OUT = ["ERROR", [], "API вернул ошибку: " + str(server_json.get("error"))[:500]]
        else:
            choices = server_json.get("choices", [])
            if not choices:
                OUT = ["ERROR", [], "В ответе API нет поля 'choices'"]
            else:
                # Шаг 5: Извлекаем контент ответа LLM
                message = choices[0].get("message", {})
                content = message.get("content", "")

                # Некоторые модели возвращают контент в виде списка частей
                if isinstance(content, list):
                    content = "".join(str(part.get("text", "")) for part in content)

                t = str(content).strip()

                # Шаг 6: "Очищаем" ответ от Markdown-обёрток и лишнего текста
                # Убираем ```json ... ```
                if t.startswith("```"):
                    first_newline = t.find("\n")
                    if first_newline != -1:
                        t = t[first_newline + 1:]
                    if t.endswith("```"):
                        t = t[:-3]
                    t = t.strip()
                
                # Если LLM добавила текст до JSON, вырезаем JSON-блок
                if not t.startswith("{"):
                    start = t.find("{")
                    end = t.rfind("}")
                    if start != -1 and end > start:
                        t = t[start : end + 1]

                # Шаг 7: Парсим "чистый" JSON от LLM
                llm_json = json.loads(t)
                thought = str(llm_json.get("thought", "Мысль не найдена"))
                actions = llm_json.get("actions", [])

                # Шаг 8: Нормализуем 'actions' (если модель вернула 1 объект вместо списка)
                if isinstance(actions, dict):
                    actions = [actions]

                # Шаг 9: Валидируем каждое действие в списке
                if not isinstance(actions, list) or not actions:
                    OUT = ["ERROR", [], "Массив 'actions' пустой или не является списком. Ответ LLM: " + t[:300]]
                else:
                    validated_actions = []
                    validation_errors = []
                    for i, act in enumerate(actions):
                        # Проверяем, что действие - это словарь
                        if not isinstance(act, dict):
                            validation_errors.append("Действие #{} не является словарём.".format(i + 1))
                            continue
                        
                        action_name = act.get("action")
                        params = act.get("params", {})
                        
                        # Проверяем имя действия
                        if not action_name or action_name not in ALLOWED_ACTIONS:
                            validation_errors.append("Действие #{} ('{}') не разрешено.".format(i + 1, action_name))
                            continue
                        
                        # Проверяем, что параметры - это словарь
                        if not isinstance(params, dict):
                            validation_errors.append("Параметры для действия '{}' не являются словарём.".format(action_name))
                            continue
                        
                        validated_actions.append({"action": action_name, "params": params})

                    # Шаг 10: Формируем финальный результат
                    if not validated_actions:
                        # Если ни одно действие не прошло валидацию
                        errors_str = "; ".join(validation_errors)
                        OUT = ["ERROR", [], "Ни одно действие не прошло валидацию: " + errors_str]
                    else:
                        status = "OK"
                        if validation_errors:
                            status = "OK ({} невалидных действий пропущено)".format(len(validation_errors))
                        
                        OUT = [thought, validated_actions, status]

except Exception:
    # Ловим ВСЕ остальные ошибки (например, невалидный JSON) и выводим их
    OUT = ["ERROR", [], "Критическая ошибка в Node 2: " + traceback.format_exc()]