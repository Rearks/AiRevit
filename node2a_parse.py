# -*- coding: utf-8 -*-
# NODE 2A — Parse & Validate Semantic Intent
# IN[0] : str - Raw response from Node 1A
# OUT   : list - [thought (str), intent (dict), status (str)]

import json
import traceback

OUT_DEFAULT = ["Node 2A: не запущен", {}, ""]
ALLOWED_KINDS = {
    "office",
    "corridor",
    "meeting",
    "wc",
    "kitchen",
    "lobby",
    "room",
    "storage"
}
ALLOWED_REL_TYPES = {
    "adjacent_to",
    "connects_to",
    "near"
}

def _is_num(v):
    try:
        float(v)
        return True
    except:
        return False

def _clean_json_text(t):
    t = str(t).strip()

    if t.startswith("```"):
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1:]
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()

    if not t.startswith("{"):
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end > start:
            t = t[start:end+1]

    return t

try:
    raw_text = IN[0] if IN[0] else ""

    if not raw_text:
        OUT = ["ERROR", {}, "Пустой ответ от Node 1A"]

    elif str(raw_text).startswith("ERROR") or str(raw_text).startswith("Exception") or str(raw_text).startswith("WebException"):
        OUT = ["ERROR", {}, "Node 1A вернул ошибку: " + str(raw_text)[:500]]

    else:
        server_json = json.loads(raw_text)

        if "error" in server_json:
            OUT = ["ERROR", {}, "API вернул ошибку: " + str(server_json.get("error"))[:500]]

        else:
            choices = server_json.get("choices", [])
            if not choices:
                OUT = ["ERROR", {}, "В ответе API нет поля 'choices'"]
            else:
                message = choices[0].get("message", {})
                content = message.get("content", "")

                if isinstance(content, list):
                    content = "".join(str(part.get("text", "")) for part in content)

                t = _clean_json_text(content)
                intent_json = json.loads(t)

                errors = []
                warnings = []

                version = str(intent_json.get("version", "")).strip()
                if not version:
                    errors.append("Отсутствует поле 'version'")

                project_scope = intent_json.get("project_scope", {})
                if not isinstance(project_scope, dict):
                    errors.append("'project_scope' должен быть объектом")

                spaces = intent_json.get("spaces", [])
                if not isinstance(spaces, list) or not spaces:
                    errors.append("'spaces' должен быть непустым массивом")

                relationships = intent_json.get("relationships", [])
                if not isinstance(relationships, list):
                    errors.append("'relationships' должен быть массивом")

                preferences = intent_json.get("preferences", {})
                if preferences and not isinstance(preferences, dict):
                    errors.append("'preferences' должен быть объектом")

                constraints = intent_json.get("constraints", {})
                if constraints and not isinstance(constraints, dict):
                    errors.append("'constraints' должен быть объектом")

                thought = str(intent_json.get("thought", "Мысль не найдена"))

                # Проверка spaces
                space_ids = set()
                if isinstance(spaces, list):
                    for i, sp in enumerate(spaces):
                        if not isinstance(sp, dict):
                            errors.append("Space #{} не является объектом".format(i + 1))
                            continue

                        sid = str(sp.get("id", "")).strip()
                        if not sid:
                            errors.append("Space #{} не содержит 'id'".format(i + 1))
                        elif sid in space_ids:
                            errors.append("Дублирующийся space id: '{}'".format(sid))
                        else:
                            space_ids.add(sid)

                        kind = str(sp.get("kind", "")).strip().lower()
                        if kind not in ALLOWED_KINDS:
                            errors.append("Space '{}' имеет недопустимый kind '{}'".format(sid or i + 1, kind))

                        name = str(sp.get("name", "")).strip()
                        if not name:
                            warnings.append("Space '{}' не имеет name".format(sid or i + 1))

                        if "width_mm" in sp and not _is_num(sp.get("width_mm")):
                            errors.append("Space '{}' имеет нечисловой width_mm".format(sid))
                        if "length_mm" in sp and not _is_num(sp.get("length_mm")):
                            errors.append("Space '{}' имеет нечисловой length_mm".format(sid))
                        if "height_mm" in sp and not _is_num(sp.get("height_mm")):
                            errors.append("Space '{}' имеет нечисловой height_mm".format(sid))
                        if "count" in sp and not _is_num(sp.get("count")):
                            errors.append("Space '{}' имеет нечисловой count".format(sid))

                # Проверка relationships
                if isinstance(relationships, list):
                    for i, rel in enumerate(relationships):
                        if not isinstance(rel, dict):
                            errors.append("Relationship #{} не является объектом".format(i + 1))
                            continue

                        rtype = str(rel.get("type", "")).strip().lower()
                        rf = str(rel.get("from", "")).strip()
                        rt = str(rel.get("to", "")).strip()

                        if rtype not in ALLOWED_REL_TYPES:
                            errors.append("Relationship #{} имеет недопустимый type '{}'".format(i + 1, rtype))
                        if not rf or not rt:
                            errors.append("Relationship #{} должен содержать 'from' и 'to'".format(i + 1))
                        else:
                            if rf not in space_ids:
                                errors.append("Relationship #{} ссылается на неизвестный from '{}'".format(i + 1, rf))
                            if rt not in space_ids:
                                errors.append("Relationship #{} ссылается на неизвестный to '{}'".format(i + 1, rt))

                if errors:
                    OUT = ["ERROR", {}, "Ошибки в semantic intent: " + "; ".join(errors[:20])]
                else:
                    intent_json["_warnings"] = warnings
                    OUT = [thought, intent_json, "OK"]

except Exception:
    OUT = ["ERROR", {}, "Критическая ошибка в Node 2A: " + traceback.format_exc()]
