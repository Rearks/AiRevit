import json
import glob
import os

def validate_file(filepath):
    errors = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return [f"Не читается JSON: {e}"]
        
    if data.get("version") != "2.0":
        errors.append("Версия не 2.0")
        
    if "spaces" not in data:
        errors.append("Отсутствует ключ 'spaces'")
    if "connections" not in data:
        errors.append("Отсутствует ключ 'connections'")
        
    if errors:
        # Если нет базовых ключей, дальнейшая проверка невозможна
        if "spaces" in [e for e in errors if "Отсутствует ключ" in e]:
            return errors

    spaces = data.get("spaces", [])
    space_ids = set()
    for i, s in enumerate(spaces):
        sid = s.get("id")
        if not sid:
            errors.append(f"У помещения индекс {i} нет id")
        else:
            if sid in space_ids:
                errors.append(f"Дублирующийся id помещения: {sid}")
            space_ids.add(sid)
            
        kind = s.get("kind")
        if not kind or str(kind).strip() == "":
            errors.append(f"Пустой 'kind' у помещения {sid}")
            
        area = s.get("area_m2")
        if area is not None:
            if not isinstance(area, (int, float)) or area < 0:
                errors.append(f"Некорректная площадь (area_m2 < 0) у {sid}")

    connections = data.get("connections", [])
    for i, c in enumerate(connections):
        src = c.get("source")
        tgt = c.get("target")
        if src not in space_ids:
            errors.append(f"Связь {c.get('id', i)}: source '{src}' не существует")
        if tgt not in space_ids:
            errors.append(f"Связь {c.get('id', i)}: target '{tgt}' не существует")

    flows = data.get("flows", [])
    for i, f in enumerate(flows):
        path = f.get("path", [])
        for pid in path:
            if pid not in space_ids:
                errors.append(f"Flow '{f.get('id', i)}' содержит неизвестный id в path: {pid}")

    constraints = data.get("constraints", [])
    for i, c in enumerate(constraints):
        for key in ["space_a", "space_b", "via"]:
            if key in c:
                ref = c[key]
                if ref not in space_ids:
                    errors.append(f"Constraint '{c.get('id', i)}' ссылается на неизвестное помещение {ref} в поле {key}")

    return errors

def main():
    directory = r"c:\Users\kraer\AiRevit\dataset\annotations"
    files = glob.glob(os.path.join(directory, "office*.json"))
    
    if not files:
        print(f"Файлы не найдены в {directory}")
        return

    print(f"Найдено файлов для проверки: {len(files)}")
    all_valid = True
    
    for f in files:
        errs = validate_file(f)
        if errs:
            all_valid = False
            print(f"[ОШИБКА] {os.path.basename(f)}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"[ОК] {os.path.basename(f)}")
            
    print("\nИТОГ:")
    if all_valid:
        print("Все файлы успешно прошли валидацию!")
    else:
        print("Есть ошибки в датасете, проверьте логи выше.")

if __name__ == "__main__":
    main()
