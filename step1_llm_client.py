# -*- coding: utf-8 -*-
"""
AiRevit | Agent-as-a-Coder v2
==============================
IN[0] : str  - Текстовый запрос пользователя
IN[1] : str  - OpenRouter API Key
IN[2] : str  - (опционально) Модели через запятую, например: "openai/gpt-4o:free,mistral/..."
IN[3] : str  - (опционально) Кастомный System Prompt (если пусто — используется встроенный)
IN[4] : int  - (опционально) Количество попыток самоисправления (по умолчанию 2)

OUT   : dict - Результат: status, thought, generated_code, llm_output, error
"""

import json
import traceback
import math

import clr
clr.AddReference("System")
from System.Net import (
    WebRequest, WebException,
    SecurityProtocolType, ServicePointManager
)
from System.IO import StreamReader
from System.Text import Encoding

ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

# ─────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ УТИЛИТЫ
# ─────────────────────────────────────────────

try:
    string_types = (basestring,)  # IronPython 2
except NameError:
    string_types = (str,)         # CPython 3


def _to_text(v):
    if v is None:
        return u""
    if isinstance(v, string_types):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return repr(v)


def _clip(text, max_len=4000):
    s = _to_text(text)
    return s if len(s) <= max_len else s[:max_len] + u"...[truncated]"


def _normalize_text(v, default=u""):
    s = _to_text(v).strip()
    return s if s else default


def _get_in(index, default=None):
    try:
        if len(IN) > index and IN[index] is not None:
            return IN[index]
    except Exception:
        pass
    return default


def _parse_models(raw, defaults):
    if raw is None:
        return list(defaults)
    if isinstance(raw, list):
        result = [_normalize_text(m) for m in raw if _normalize_text(m)]
        return result or list(defaults)
    s = _normalize_text(raw)
    if not s:
        return list(defaults)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    return parts if parts else list(defaults)


# ─────────────────────────────────────────────
# КОНФИГУРАЦИЯ
# ─────────────────────────────────────────────

OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_REFERER = "https://github.com/kraer/AiRevit"
OPENROUTER_TITLE   = "AiRevit Dynamo"
HTTP_TIMEOUT       = 90000  # мс

DEFAULT_MODELS = ["openai/gpt-oss-120b:free"]

BUILTIN_SYSTEM_PROMPT = u"""
Ты — Revit BIM разработчик-агент (Agent-as-a-Coder).
Твоя задача — писать исполняемый Python-код для Revit API по текстовому запросу пользователя.

Ты ВСЕГДА возвращаешь строгий JSON без пояснений и Markdown:
{
  "thought": "Краткое объяснение на русском",
  "python_code": "Исполняемый код одной строкой с \\n между инструкциями"
}

Правила для python_code:
1. НЕ импортируй ничего — все уже доступно в среде выполнения.
2. НЕ трогай транзакции — код уже выполняется внутри открытой транзакции.
3. Текущий документ Revit доступен как `doc`.
4. Для перевода мм в футы используй готовую константу `MM_TO_FT`.
5. Все результаты сохраняй в словарь `OUT_DICT`, например: OUT_DICT['id'] = wall.Id.IntegerValue
6. Доступны: doc, MM_TO_FT, OUT_DICT, math, FilteredElementCollector,
   Level, Wall, WallType, Floor, FloorType, Ceiling, XYZ, Line,
   CurveLoop, CurveArray, Arc, ElementId, BuiltInCategory, BuiltInParameter,
   FamilySymbol, FamilyInstance, Options, UnitUtils, ElementTransformUtils.

Пример — стена 1000 мм:
"level = FilteredElementCollector(doc).OfClass(Level).FirstElement()\\nwt = FilteredElementCollector(doc).OfClass(WallType).FirstElement()\\ncurve = Line.CreateBound(XYZ(0,0,0), XYZ(1000*MM_TO_FT,0,0))\\nwall = Wall.Create(doc, curve, wt.Id, level.Id, 3000*MM_TO_FT, 0.0, False, False)\\nOUT_DICT['wall_id'] = wall.Id.IntegerValue"
""".strip()

# ─────────────────────────────────────────────
# ЧТЕНИЕ ВХОДОВ DYNAMO
# ─────────────────────────────────────────────

user_input   = _normalize_text(_get_in(0), u"Смоделируй гипсокартонную стену длиной 1000 мм")
api_key      = _normalize_text(_get_in(1), u"")
models       = _parse_models(_get_in(2), DEFAULT_MODELS)
system_prompt = _normalize_text(_get_in(3), BUILTIN_SYSTEM_PROMPT)
max_retries  = int(_get_in(4, 2))

doc = DocumentManager.Instance.CurrentDBDocument

# ─────────────────────────────────────────────
# РАЗБОР ОТВЕТА LLM
# ─────────────────────────────────────────────

def _strip_json_fence(text):
    """Убирает ```json ... ``` или ``` ... ``` вокруг JSON."""
    t = text.strip()
    if t.startswith("```"):
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _extract_json_block(text):
    """Ищет первый полный JSON-объект в тексте."""
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return None


def _parse_llm_response(raw_text):
    """
    Пытается вытащить dict с ключами 'thought' и 'python_code'.
    Поддерживает: чистый JSON, JSON в ```-блоке, вырезание фрагмента {...}.
    """
    t = _to_text(raw_text).strip()
    if not t:
        return None, u"Пустой ответ"

    # Убираем markdown-обёртку
    cleaned = _strip_json_fence(t)

    for candidate in [cleaned, _extract_json_block(t), _extract_json_block(cleaned)]:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                # нормализуем ключи
                if "code" in parsed and "python_code" not in parsed:
                    parsed["python_code"] = parsed.pop("code")
                if "python_code" in parsed:
                    parsed.setdefault("thought", u"")
                    return parsed, None
        except Exception:
            pass

    return None, u"Не удалось распарсить JSON из ответа: " + _clip(t, 300)


# ─────────────────────────────────────────────
# HTTP-ЗАПРОС К OPENROUTER
# ─────────────────────────────────────────────

def _call_openrouter(api_key, messages, model):
    """
    Отправляет запрос и возвращает (parsed_dict | None, debug_str).
    """
    debug_lines = [u"Model: " + model]
    try:
        req = WebRequest.Create(OPENROUTER_URL)
        req.Method      = "POST"
        req.ContentType = "application/json"
        req.Timeout     = HTTP_TIMEOUT

        req.Headers.Add("Authorization", "Bearer " + api_key)
        req.Headers.Add("X-Title",       OPENROUTER_TITLE)
        req.Headers.Add("HTTP-Referer",  OPENROUTER_REFERER)

        payload   = json.dumps({"model": model, "messages": messages, "temperature": 0.0})
        body_bytes = Encoding.UTF8.GetBytes(payload)
        req.ContentLength = body_bytes.Length

        stream = req.GetRequestStream()
        stream.Write(body_bytes, 0, body_bytes.Length)
        stream.Close()

        resp       = req.GetResponse()
        reader     = StreamReader(resp.GetResponseStream(), Encoding.UTF8)
        resp_text  = reader.ReadToEnd()
        reader.Close()
        resp.Close()

        debug_lines.append(u"HTTP OK, len=" + str(len(resp_text)))

        resp_json = json.loads(resp_text)

        if "error" in resp_json:
            debug_lines.append(u"API error: " + _clip(resp_json["error"]))
            return None, u"\n".join(debug_lines)

        choices = resp_json.get("choices") or []
        if not choices:
            debug_lines.append(u"No choices in response")
            return None, u"\n".join(debug_lines)

        content_raw = choices[0].get("message", {}).get("content", u"")
        debug_lines.append(u"content_len=" + str(len(_to_text(content_raw))))

        parsed, err = _parse_llm_response(content_raw)
        if parsed is None:
            debug_lines.append(u"Parse error: " + (err or u"unknown"))
            debug_lines.append(u"Raw content: " + _clip(content_raw, 500))

        return parsed, u"\n".join(debug_lines)

    except WebException as e:
        try:
            err_reader = StreamReader(e.Response.GetResponseStream(), Encoding.UTF8)
            err_body   = err_reader.ReadToEnd()
            err_reader.Close()
            debug_lines.append(u"WebException: " + _clip(err_body))
        except Exception:
            debug_lines.append(u"WebException: " + _clip(str(e)))
        return None, u"\n".join(debug_lines)

    except Exception as e:
        debug_lines.append(u"Exception: " + _clip(traceback.format_exc()))
        return None, u"\n".join(debug_lines)


# ─────────────────────────────────────────────
# БЕЗОПАСНАЯ СРЕДА ВЫПОЛНЕНИЯ
# ─────────────────────────────────────────────

SAFE_BUILTINS = {
    "len": len, "range": range, "min": min, "max": max,
    "sum": sum, "abs": abs, "round": round,
    "str": str, "int": int, "float": float, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "enumerate": enumerate, "zip": zip, "sorted": sorted,
    "any": any, "all": all, "print": print,
    "isinstance": isinstance, "hasattr": hasattr,
    "getattr": getattr, "setattr": setattr,
    "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "RuntimeError": RuntimeError,
}

# Опциональные классы (могут отсутствовать в некоторых версиях Revit)
def _safe_get(name):
    try:
        return globals().get(name)
    except Exception:
        return None


def _build_exec_scope():
    scope = {
        "__builtins__": SAFE_BUILTINS,
        "doc":     doc,
        "MM_TO_FT": 1.0 / 304.8,
        "math":    math,
        "OUT_DICT": {},

        # Collectors & basics
        "FilteredElementCollector": FilteredElementCollector,
        "BuiltInCategory":    BuiltInCategory,
        "BuiltInParameter":   BuiltInParameter,
        "ElementId":          ElementId,
        "Element":            Element,

        # Architectural
        "Level":      Level,
        "Wall":       Wall,
        "WallType":   WallType,
        "Floor":      Floor,
        "FloorType":  FloorType,

        # Geometry
        "XYZ":        XYZ,
        "Line":       Line,
        "Arc":        Arc,
        "CurveLoop":  CurveLoop,
        "CurveArray": CurveArray,
        "UV":         UV,

        # Families
        "FamilySymbol":   FamilySymbol,
        "FamilyInstance": FamilyInstance,

        # Utilities
        "Options":                Options,
        "UnitUtils":              UnitUtils,
        "ElementTransformUtils":  ElementTransformUtils,
    }

    # Необязательные классы
    for name in ["Ceiling", "RoofBase", "Plane", "SketchPlane",
                 "Solid", "SolidUtils", "GeometryInstance", "Parameter"]:
        obj = _safe_get(name)
        if obj is not None:
            scope[name] = obj

    return scope


FORBIDDEN_TOKENS = [
    "__import__", "import os", "import sys", "import clr",
    "from os", "from sys", "open(", "eval(", "execfile(",
    "subprocess", "socket", "webrequest",
    "transactionmanager", "transaction(",
    "forceclosetransaction", "ensureintransaction",
]


def _validate_code(code):
    lowered = code.lower()
    for token in FORBIDDEN_TOKENS:
        if token in lowered:
            return False, u"Запрещённый токен: " + token
    return True, u""


# ─────────────────────────────────────────────
# ВЫПОЛНЕНИЕ КОДА ЧЕРЕЗ exec()
# ─────────────────────────────────────────────

def _execute_code(code, exec_scope):
    """
    Запускает сгенерированный код внутри Revit Transaction.
    Возвращает (success: bool, out_dict: dict, error_text: str).
    """
    ok, reason = _validate_code(code)
    if not ok:
        return False, {}, u"Валидация отклонена: " + reason

    tx = Transaction(doc, "AiRevit LLM Code")
    try:
        status = tx.Start()
        if str(status) != "Started":
            return False, {}, u"Transaction.Start() вернул: " + str(status)

        exec(code, {}, exec_scope)   # изолированный глобальный контекст

        tx.Commit()
        return True, exec_scope.get("OUT_DICT", {}), u""

    except Exception as e:
        try:
            tx.RollbackToSavepoint if False else tx.RollBack()
        except Exception:
            pass
        return False, {}, traceback.format_exc()


# ─────────────────────────────────────────────
# ГЛАВНЫЙ ЦИКЛ: запрос → exec → самоисправление
# ─────────────────────────────────────────────

if not api_key:
    OUT = {"status": "error", "message": u"API-ключ не передан в IN[1]"}
else:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_input},
    ]

    final_out = {"status": "error", "message": u"Превышено число попыток"}
    all_debug  = []

    for attempt in range(max_retries):

        # --- Запрашиваем LLM ---
        parsed = None
        for model in models:
            p, dbg = _call_openrouter(api_key, messages, model)
            all_debug.append(dbg)
            if p:
                parsed = p
                break

        if not parsed:
            final_out = {
                "status": "error",
                "message": u"LLM не вернула валидный ответ",
                "debug":   all_debug,
            }
            break

        # --- Исполняем сгенерированный код ---
        code = _to_text(parsed.get("python_code", u""))
        if not code.strip():
            final_out = {
                "status":  "error",
                "message": u"python_code пустой",
                "thought": _to_text(parsed.get("thought")),
            }
            break

        exec_scope = _build_exec_scope()
        success, out_dict, error_text = _execute_code(code, exec_scope)

        if success:
            final_out = {
                "status":         "success",
                "message":        u"Код выполнен успешно!",
                "thought":        _to_text(parsed.get("thought")),
                "generated_code": code,
                "llm_output":     out_dict,
                "attempts":       attempt + 1,
                "debug":          all_debug,
            }
            break
        else:
            # --- Самоисправление: отправляем ошибку обратно в LLM ---
            if attempt < max_retries - 1:
                messages.append({
                    "role":    "assistant",
                    "content": json.dumps(parsed, ensure_ascii=False),
                })
                messages.append({
                    "role":    "user",
                    "content": (
                        u"Твой код вызвал ошибку при выполнении в Revit API.\n"
                        u"Ошибка:\n" + _clip(error_text, 1500) + u"\n\n"
                        u"Исправь python_code и верни новый JSON."
                    ),
                })
            else:
                final_out = {
                    "status":         "error",
                    "message":        u"Ошибка выполнения кода",
                    "thought":        _to_text(parsed.get("thought")),
                    "generated_code": code,
                    "error_detail":   _clip(error_text, 3000),
                    "attempts":       attempt + 1,
                    "debug":          all_debug,
                }

    OUT = final_out
