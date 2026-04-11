import clr
import json

clr.AddReference("System")
from System.Net import WebRequest, WebException, SecurityProtocolType, ServicePointManager
from System.IO import StreamReader
from System.Text import Encoding

# Принудительно используем TLS 1.2
ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12

# IN[0] - Ваш API ключ (подайте строку из Code Block)
api_key = IN[0] if IN else ""

if not api_key:
    OUT = "ОШИБКА: Пожалуйста, подключите API ключ ко входу IN[0]"
else:
    try:
        # Самый простой тестовый запрос к моделям OpenRouter
        # Мы не тратим токены на генерацию, просто просим поздороваться
        payload = json.dumps({
            "model": "nvidia/nemotron-3-super-120b-a12b:free", 
            "messages": [
                {"role": "user", "content": "Say 'API is working'"}
            ]
        })
        
        byte_array = Encoding.UTF8.GetBytes(payload)

        req = WebRequest.Create("https://openrouter.ai/api/v1/chat/completions")
        req.Method = "POST"
        req.ContentType = "application/json"
        req.Headers.Add("Authorization", "Bearer " + str(api_key))
        req.ContentLength = byte_array.Length

        stream = req.GetRequestStream()
        stream.Write(byte_array, 0, byte_array.Length)
        stream.Close()

        resp = req.GetResponse()
        reader = StreamReader(resp.GetResponseStream(), Encoding.UTF8)
        text = reader.ReadToEnd()
        
        reader.Close()
        resp.Close()
        
        response_data = json.loads(text)
        message = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        OUT = "УСПЕХ! Ответ сервера: " + message

    except WebException as e:
        try:
            reader = StreamReader(e.Response.GetResponseStream(), Encoding.UTF8)
            err_body = reader.ReadToEnd()
            reader.Close()
            OUT = "WebException (Сервер вернул ошибку): \n" + err_body
        except:
            OUT = "WebException: " + str(e)
    except Exception as e:
        import traceback
        OUT = "Exception: " + traceback.format_exc()
