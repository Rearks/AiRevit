# -*- coding: utf-8 -*-
# NODE 1A — HTTP Call to OpenRouter (Semantic Intent mode)
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

OUT = "Node 1A: не запущен"

SYSTEM_PROMPT_TEMPLATE = u"""Ты - BIM ассистент для Revit.
Твоя задача - не создавать стены напрямую, а извлекать ИНТЕНТ пользователя в виде строгого JSON.

Верни только строгий JSON-объект без Markdown и без пояснений.

Формат ответа:
{{
  "version": "1.0",
  "project_scope": {{
    "level_keyword": "",
    "units": "mm",
    "layout_type": "single_level_rectangular"
  }},
  "spaces": [
    {{
      "id": "space_1",
      "kind": "office",
      "name": "Кабинет",
      "width_mm": 4000,
      "length_mm": 5000,
      "height_mm": 3000,
      "count": 1
    }}
  ],
  "relationships": [
    {{
      "type": "adjacent_to",
      "from": "space_1",
      "to": "space_2"
    }}
  ],
  "preferences": {{
    "wall_type_keyword": "",
    "floor_type_keyword": ""
  }},
  "constraints": {{
    "orthogonal_only": true,
    "rectangular_spaces_only": true
  }},
  "thought": "Краткое объяснение на русском"
}}

Правила:
1. Возвращай только JSON.
2. Все размеры только в миллиметрах.
3. Если помещение указано как квадратное или задана только одна сторона, то width_mm = length_mm.
4. Если высота не указана, используй 3000.
5. Если уровень не указан, оставляй level_keyword пустым.
6. Если типы стен/полов не указаны, оставляй keywords пустыми.
7. Если пользователь просит несколько одинаковых помещений, можно:
   - либо явно вернуть несколько объектов spaces,
   - либо вернуть один объект с count > 1.
8. На данном этапе поддерживаются только прямоугольные помещения.
9. Используй только такие значения kind:
   - office
   - corridor
   - meeting
   - wc
   - kitchen
   - lobby
   - room
   - storage
10. relationships разрешены только такие:
   - adjacent_to
   - connects_to
   - near
11. Если пользователь не описал связи между помещениями, relationships можно оставить пустым массивом.
12. layout_type всегда "single_level_rectangular".

Каталог текущего Revit-проекта:
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
    user_prompt = _get_str(0, u"Создай кабинет 4 на 5 метров")
    api_key     = _get_str(1, u"")
    model       = _get_str(3, u"nvidia/nemotron-3-super-120b-a12b:free")

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
        req.Headers.Add("X-Title", "AiRevit-Intent")

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
