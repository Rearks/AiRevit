# AiRevit Pipeline Architecture

## Текущий пайплайн

- **Node 0** — Revit Catalog (Сбор каталога доступных типов)
- **Node 1A** — Prompt -> semantic intent (LLM запрос)
- **Node 2A** — Parse Intent (Парсинг интента)
- **Node 2B** — Normalize Intent (Нормализация интента)
- **Node 3A** — Build Topology (Построение топологии помещений)
- **Node 4A** — Compile topology -> action plan (Компиляция BIM-плана)
- **Node 5** — Execute action plan in Revit (Исполнение в Revit)

## Какие сценарии поддерживает Node 3A v1

1. `single_room`
   - Если есть только одно помещение.
2. `row_of_rooms`
   - Если несколько помещений и нет коридора.
   - Помещения ставятся в ряд слева направо.
3. `corridor_with_rooms_one_side`
   - Если есть ровно один коридор и хотя бы одно другое помещение.
   - Коридор идёт горизонтально, комнаты ставятся вдоль него сверху.

---

## Целевая архитектура

Развитие архитектуры предполагает включение этапов валидации. Полный ожидаемый пайплайн:

- **Node 0** — Revit Catalog
- **Node 1A** — LLM Semantic Intent Request
- **Node 2A** — Parse Intent
- **Node 2B** — Normalize Intent
- **Node 3A** — Build Topology
- **Node 3B** — Validate Topology ✅
- **Node 4A** — Compile BIM Plan
- **Node 4B** — Validate BIM Plan *(планируется)*
- **Node 5** — Execute BIM Plan

Вот к чему мы хотим прийти концептуально для сложных BIM-сцен:

`Natural language` -> `semantic building intent` -> `topology/layout` -> `deterministic BIM compilation` -> `validation` -> `execution`

---

## Роль RAG в системе

Что реально даст RAG? Он особенно полезен для:

- Выбора правильных семейств и типов.
- Понимания проектного контекста.
- Учёта стандартов компании.
- Подтягивания специфических параметров и ограничений.
- Работы с реальным содержимым текущего BIM-проекта.

То есть, RAG в первую очередь решает задачу умного сопоставления (мэппинга): **“Какой тип стены, пола или семейства выбрать для конкретного запроса?”**
