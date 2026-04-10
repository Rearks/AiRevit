import os
import glob
from collections import Counter, defaultdict
import json
from graph_loader import load_graph

def generate_report():
    directory = r"c:\Users\kraer\AiRevit\dataset\annotations"
    files = glob.glob(os.path.join(directory, "office*.json"))
    
    total_files = len(files)
    if total_files == 0:
        return "Файлы не найдены!"

    kind_counts = Counter()
    kind_areas = defaultdict(list)
    patterns = Counter()
    flows_counter = Counter()

    for f in files:
        g = load_graph(f)
        
        # собираем паттерны
        patterns[g["pattern"]] += 1
        
        # собираем kind и их площади
        for s in g["data"].get("spaces", []):
            kind = s.get("kind", "unknown")
            kind_counts[kind] += 1
            area = s.get("area_m2")
            if area is not None:
                kind_areas[kind].append(float(area))
                
        # собираем flows
        for flow in g["data"].get("flows", []):
            fname = flow.get("name", "unknown")
            flows_counter[fname] += 1

    lines = []
    lines.append(f"Всего файлов: {total_files}")
    
    lines.append("\n=== Шаблоны графа ===")
    lines.append(f"Найдено уникальных шаблонов: {len(patterns)}")
    most_common_pattern = patterns.most_common(1)
    if most_common_pattern:
        lines.append(f"Самый частый шаблон: {most_common_pattern[0][0]} (встречается {most_common_pattern[0][1]} раз)")
        
    lines.append("\n=== Помещения (kinds) ===")
    for kind, count in kind_counts.most_common():
        lines.append(f"'{kind}' встречается {count} раз")
        
    lines.append("\n=== Средние площади ===")
    for kind in kind_areas.keys():
        areas = kind_areas[kind]
        if areas:
            avg_area = sum(areas) / len(areas)
            lines.append(f"Средняя площадь '{kind}': {avg_area:.2f} m2")
            
    # Дополнительно: среднее отношение office к коридору, если есть
    if "office" in kind_areas and "corridor" in kind_areas:
        avg_office = sum(kind_areas["office"]) / len(kind_areas["office"])
        avg_corridor = sum(kind_areas["corridor"]) / len(kind_areas["corridor"])
        if avg_corridor > 0:
             lines.append(f"\nСреднее отношение офис / коридор = {(avg_office/avg_corridor):.2f}")

    lines.append("\n=== Сценарии Flow ===")
    for flow_name, count in flows_counter.most_common(5):
        lines.append(f"Flow '{flow_name}' встречается {count} раз")

    report_text = "\n".join(lines)
    return report_text

def main():
    report = generate_report()
    print("РАССЧИТАННЫЙ ДАТАСЕТ ОТЧЕТ:")
    print("=" * 40)
    print(report)
    print("=" * 40)
    
    report_path = r"c:\Users\kraer\AiRevit\dataset\report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nОтчет сохранен в {report_path}")

if __name__ == "__main__":
    main()
