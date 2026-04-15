# Dynamo Pipeline Architecture

Эта документация описывает новую структуру нодов для генерации BIM-модели в Revit через Dynamo.

## Node 1: User Prompt
- **Тип**: String
- **Назначение**: Ввод текстового промпта от пользователя.
- **Пример**: `Design an office with two offices, total area 200 m², one twice as large, corridor, toilet`

## Node 2: Directory Path
- **Тип**: Directory Path
- **Назначение**: Путь к папке, куда был скачан репозиторий (содержит python скрипты, такие как `prompt_to_program_graph.py` и `layout_generator_v2.py`).

## Node 3: Python Script (Prompt to Program Graph)
- **Входы**:
  - `IN[0]`: Node 2 (Directory Path)
  - `IN[1]`: Node 1 (User Prompt)
- **Выход (`OUT`)**: Подключается к Watch, затем к Node 4
- **Скрипт**: См. `dynamo_node3_prompt_to_graph.py`

## Node 4: Python Script (Program Graph to Layout)
- **Входы**:
  - `IN[0]`: Node 2 (Directory Path)
  - `IN[1]`: Node 3 (Program Graph Path)
- **Выход (`OUT`)**: Подключается к Watch, затем к Node 5
- **Скрипт**: См. `dynamo_node4_graph_to_layout.py`

## Node 5: Python Script (Create Revit Elements)
- **Входы**:
  - `IN[0]`: Node 4 (Layout JSON Path)
- **Выход (`OUT`)**: Отчет о создании элементов в Revit (Подключается к Watch)
- **Скрипт**: См. `dynamo_node5_build_revit.py`
