# -*- coding: utf-8 -*-
# NODE 1 — HTTP Call to OpenRouter (JSON-Plan mode)
# IN[0] : str  - User prompt
# IN[1] : str  - API Key
# IN[2] : str/dict/list - Catalog JSON from Node 0
# IN[3] : str  - Model name (optional)
# OUT   : str  - Raw JSON response text from OpenRouter (or error string)

import json
import clr

clr.AddReference("System")
from System.Net import WebRequest, WebException, SecurityProtocolType, ServicePointManager
from System.IO import StreamReader
from System.Text import Encoding

ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12

OUT = "Node 1: не запущен"

SYSTEM_PROMPT_TEMPLATE = u"""Ты - Revit BIM ассистент. Пользователь описывает что нужно построить в BIM-модели.
Ты должен вернуть строгий JSON (без Markdown, без пояснений) с массивом действий.

Формат ответа:
{{
  "thought": "Краткое объяснение на русском",
  "actions": [
    {{
      "action": "имя_действия",
      "params": {{ ... }}
    }}
  ]
}}

Доступные действия:

1. create_wall — одна стена по линии
   params: level_keyword, wall_type_keyword, start_mm (массив [x,y,z]), end_mm (массив [x,y,z]), height_mm

2. create_room_box — замкнутое помещение (4 стены + пол + Room)
   params: level_keyword, wall_type_keyword, floor_type_keyword, origin_mm (массив [x,y,z]), length_mm, width_mm, height_mm, room_number, room_name

3. create_floor — пол по прямоугольнику
   params: level_keyword, floor_type_keyword, origin_mm, length_mm, width_mm

4. create_room — помещение (Room) в точке, если стены уже есть
   params: level_keyword, center_mm (массив [x,y,z]), room_number, room_name

Правила:
- Используй ТОЛЬКО действия из списка выше. Никаких других.
- Все размеры указывай в миллиметрах.
- Если для замкнутого помещения указана только одна длина, считай помещение квадратным: width_mm = length_mm.
- Ключевые слова для типов ищут совпадение в имени типа (подстрока).
- Пустая строка в level_keyword = первый доступный уровень.
- Пустая строка в type keyword = первый доступный тип.
- Для нескольких элементов — несколько объектов в массиве actions.

Каталог доступных типов в текущем проекте Revit:
{catalog}
"""

def _get_str(i, d=""):
    try:
        v = IN[i]
        if v is None:
            return d
        return str(v).strip()
    except:
        return d

try:
    user_prompt = _get_str(0, u"Создай стену 1000 мм")
    api_key     = _get_str(1, u"")
    model       = _get_str(3, u"nvidia/nemotron-3-super-120b-a12b:free")

    # catalog может быть строкой, dict или list
    try:
        raw_catalog = IN[2]
    except:
        raw_catalog = "{}"

    if isinstance(raw_catalog, (dict, list)):
        catalog = json.dumps(raw_catalog, ensure_ascii=False)
    elif raw_catalog is None:
        catalog = "{}"
    else:
        catalog = str(raw_catalog)

    if not api_key:
        OUT = "ERROR: API ключ не передан в IN[1]"
    else:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(catalog=catalog)

        payload = json.dumps({
            "model": model,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ]
        }, ensure_ascii=False)

        byte_array = Encoding.UTF8.GetBytes(payload)

        req = WebRequest.Create("https://openrouter.ai/api/v1/chat/completions")
        req.Method = "POST"
        req.ContentType = "application/json"
        req.Timeout = 90000
        req.ContentLength = byte_array.Length
        req.Headers.Add("Authorization", "Bearer " + api_key)
        req.Headers.Add("HTTP-Referer", "https://github.com/kraer/AiRevit")
        req.Headers.Add("X-Title", "AiRevit")

        stream = req.GetRequestStream()
        stream.Write(byte_array, 0, byte_array.Length)
        stream.Close()

        resp = req.GetResponse()
        reader = StreamReader(resp.GetResponseStream(), Encoding.UTF8)
        text = reader.ReadToEnd()
        reader.Close()
        resp.Close()

        OUT = text

except WebException as e:
    try:
        reader = StreamReader(e.Response.GetResponseStream(), Encoding.UTF8)
        err_body = reader.ReadToEnd()
        reader.Close()
        OUT = "WebException: " + err_body
    except:
        OUT = "WebException: " + str(e)

except Exception:
    import traceback
    OUT = "Exception: " + traceback.format_exc()