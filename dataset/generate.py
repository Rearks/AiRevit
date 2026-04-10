import json
import os
import re

base_dir = r"c:\Users\kraer\AiRevit\dataset\annotations"
filepath = os.path.join(base_dir, "office1.json")

# Открываем "чистый" office1.json
with open(filepath, "r", encoding="utf-8") as f:
    text = f.read()

try:
    original_data = json.loads(text)
except Exception as e:
    print("Ошибка парсинга:", e)
    exit(1)

# Создаем 20 копий с нарастающим коэффициентом (например, от 0.5 до 1.45)
for i in range(1, 21):
    # Динамический коэффициент, чтобы все 20 файлов отличались
    # File 1 = 0.5
    # File 2 = 0.55
    # ...
    # File 10 = 0.95
    # File 20 = 1.45
    scale_factor = 0.5 + (i - 1) * 0.05
    
    copy_data = json.loads(text)
    
    # Чтобы сохранить чистоту эксперимента, назовем оригинальный файл как базовый
    copy_data["metadata"]["notes"] = f"Копия {i} (динамический масштаб x{scale_factor:.2f})"
    copy_data["source"]["pdf_file"] = f"Office{i}.pdf"
    copy_data["source"]["image_file"] = f"Office{i}.png"
    
    # Масштабируем комнаты
    for room in copy_data.get("rooms", []):
        room["width_mm"] = round(room.get("width_mm", 0) * scale_factor, 1)
        room["length_mm"] = round(room.get("length_mm", 0) * scale_factor, 1)
        # Площадь пересчитывается: м2 = (ширина * длина) / 1 000 000
        room["area_m2"] = round((room["width_mm"] * room["length_mm"]) / 1000000.0, 2)
        
    # Масштабируем двери
    for door in copy_data.get("doors", []):
        door["width_mm"] = round(door.get("width_mm", 0) * scale_factor, 1)
        
    # Масштабируем общие стены
    for edge in copy_data.get("edges", []):
        if "shared_wall_mm" in edge:
            edge["shared_wall_mm"] = round(edge["shared_wall_mm"] * scale_factor, 1)
            
    # Обновляем статистику
    total_area = sum(r.get("area_m2", 0) for r in copy_data.get("rooms", []))
    copy_data["metadata"]["total_area_m2"] = round(total_area, 2)
    
    min_area = min(r.get("area_m2", 0) for r in copy_data.get("rooms", []))
    if "statistics" in copy_data:
        copy_data["statistics"]["min_room_area_m2"] = round(min_area, 2)
        copy_data["statistics"]["total_area_m2"] = round(total_area, 2)
    
    out_path = os.path.join(base_dir, f"office{i}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(copy_data, f, ensure_ascii=False, indent=2)

print(f"Успешно пересоздано 20 уникальных копий с нарастающим масштабом.")
