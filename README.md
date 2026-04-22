# NetAuto MVP

`NetAuto MVP` — минимально жизнеспособная информационная система для автоматизации настройки сетевого оборудования.

Проект построен на `FastAPI` и `Nornir`, стартует в безопасном `mock-first` режиме и уже подготовлен к работе с `NetBox` и `Netmiko`.

## Что умеет система
- хранить инвентарь устройств через подключаемый backend (`mock` по умолчанию, также поддержан `netbox`);
- генерировать базовую CLI-конфигурацию по API-запросу или по типовому профилю;
- валидировать hostname, IPv4-адреса, CIDR, а также дубли интерфейсов и batch-элементов до запуска автоматизации;
- защищать automation `POST`-эндпоинты через `X-API-Key`, если задан `NAA_API_KEY`;
- добавлять `X-Request-ID` в каждый ответ и сохранять его в журнал операций;
- хранить mock running-state, snapshots и журнал операций в JSON-файлах без отдельной БД;
- выполнять `preview`, `dry_run`, `apply`, `rollback`, `compliance/drift` и выдавать результаты через HTTP API;
- поддерживать одиночные, batch- и selector-based сценарии по фильтрам `site`, `role`, `status`, `vendor`;
- возвращать `summary`-сводки по массовым операциям;
- выполнять `preflight` перед запуском автоматизации;
- выполнять активную `diagnostics`-проверку для внешних интеграций;
- собирать demo/smoke/stand-validation артефакты для демонстрационного стенда и защиты.

## Режимы работы
- `mock + mock` — самый безопасный режим для разработки и демонстрации без реального оборудования;
- `netbox + mock` — инвентарь берётся из `NetBox`, применение конфигурации остаётся симулированным;
- `netbox + netmiko` — инвентарь берётся из `NetBox`, команды отправляются на реальное или виртуальное устройство.

## Локальный запуск
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

После запуска:
- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health-check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

## Запуск через Docker
В mock-режиме сервис можно поднять даже без `.env`, так как в `docker-compose.yml` уже заданы безопасные значения по умолчанию.

```bash
docker compose up --build
```

Если нужно включить `netbox`, `netmiko` или защиту через API key:
```bash
copy .env.example .env
docker compose up --build
```

После запуска:
- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Документация: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Переменные окружения
```env
NAA_INVENTORY_BACKEND=mock
NAA_EXECUTION_BACKEND=mock
NAA_API_KEY=
NAA_MOCK_STATE_PATH=data/mock_device_state.json
NAA_OPERATION_JOURNAL_PATH=data/operation_journal.json
NAA_NETBOX_URL=
NAA_NETBOX_TOKEN=
NAA_DEVICE_USERNAME=
NAA_DEVICE_PASSWORD=
NAA_DEVICE_SECRET=
NAA_DEVICE_PORT=22
NAA_RUNNING_CONFIG_COMMAND=show running-config
```

Пояснения:
- если `NAA_API_KEY` пустой, аутентификация отключена;
- если `NAA_API_KEY` задан, все automation `POST`-эндпоинты требуют заголовок `X-API-Key`;
- в каждом ответе возвращается `X-Request-ID`; можно передать свой `X-Request-ID`, и он сохранится в журнале операций;
- по умолчанию mock-state и журнал операций сохраняются в каталоге `data/`.

## Примеры API-вызовов

Получить список профилей:
```bash
curl "http://127.0.0.1:8000/api/automation/profiles"
```

Отфильтровать устройства из инвентаря:
```bash
curl "http://127.0.0.1:8000/api/devices?site=msk-lab&status=reachable"
```

Разрешить selector в список устройств:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/selection/resolve" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -d "{\"site\":\"msk-lab\",\"status\":\"reachable\"}"
```

Сделать `preview` базовой конфигурации по профилю:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/devices/lab-r1/base-config/profiles/branch-edge/preview" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-preview-001" ^
  -d "{\"hostname\":\"EDGE-R1\",\"banner_motd\":\"Managed by profile override\"}"
```

Selector-based `preview` для всех reachable-устройств на площадке:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/selection/base-config/preview" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-selector-preview-001" ^
  -d "{\"selector\":{\"site\":\"msk-lab\",\"status\":\"reachable\"},\"request\":{\"hostname\":\"EDGE-R1\"}}"
```

Batch `preview` для нескольких устройств:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/batch/base-config/preview" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-batch-preview-001" ^
  -d "{\"items\":[{\"device_name\":\"lab-r1\",\"request\":{\"hostname\":\"EDGE-R1\"}},{\"device_name\":\"lab-r99\",\"request\":{\"hostname\":\"MISSING-R99\"}}]}"
```

`dry_run` применение конфигурации:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/devices/lab-r1/base-config/apply?dry_run=true" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-dry-run-001" ^
  -d "{\"hostname\":\"EDGE-R1\",\"domain_name\":\"branch.lab\",\"banner_motd\":\"Preview only\"}"
```

Проверка compliance перед применением:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/devices/lab-r1/base-config/profiles/branch-edge/compliance" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-compliance-001" ^
  -d "{\"hostname\":\"EDGE-R1\"}"
```

Применение конфигурации по профилю:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/devices/lab-r1/base-config/profiles/branch-edge/apply" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-apply-001" ^
  -d "{\"hostname\":\"EDGE-R1\"}"
```

`preflight` перед реальным применением:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/preflight" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -d "{\"site\":\"msk-lab\",\"status\":\"reachable\"}"
```

`diagnostics` перед переходом к `NetBox` или `Netmiko`:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/diagnostics" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -d "{\"site\":\"msk-lab\",\"status\":\"reachable\"}"
```

Batch compliance:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/batch/base-config/compliance" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-batch-compliance-001" ^
  -d "{\"items\":[{\"device_name\":\"lab-r1\",\"request\":{\"hostname\":\"EDGE-R1\"}},{\"device_name\":\"lab-r99\",\"request\":{\"hostname\":\"MISSING-R99\"}}]}"
```

Selector-based compliance:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/selection/base-config/compliance" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-selector-compliance-001" ^
  -d "{\"selector\":{\"site\":\"msk-lab\",\"status\":\"reachable\"},\"request\":{\"hostname\":\"EDGE-R1\"}}"
```

Selector-based `apply` по профилю:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/selection/base-config/profiles/branch-edge/apply?dry_run=true" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-selector-apply-001" ^
  -d "{\"selector\":{\"site\":\"msk-lab\",\"status\":\"reachable\"},\"overrides\":{\"hostname\":\"EDGE-R1\"}}"
```

Список snapshots:
```bash
curl "http://127.0.0.1:8000/api/automation/devices/lab-r1/snapshots"
```

Rollback к snapshot:
```bash
curl -X POST "http://127.0.0.1:8000/api/automation/devices/lab-r1/rollback/{snapshot_id}" ^
  -H "X-API-Key: demo-secret" ^
  -H "X-Request-ID: demo-rollback-001"
```

Текущий running-config:
```bash
curl "http://127.0.0.1:8000/api/automation/devices/lab-r1/running-config"
```

Фильтрованный журнал операций:
```bash
curl "http://127.0.0.1:8000/api/automation/operations?device_name=lab-r1&status=success&limit=5"
```

Сводка по операциям:
```bash
curl "http://127.0.0.1:8000/api/automation/operations/summary?device_name=lab-r1"
```

## Сервисные скрипты для стенда

Smoke-проверка живого API:
```bash
.\.venv\Scripts\python scripts\demo_smoke.py --base-url http://127.0.0.1:8000 --api-key demo-secret
```

Валидация стенда:
```bash
.\.venv\Scripts\python scripts\stand_validate.py --base-url http://127.0.0.1:8000 --api-key demo-secret --site msk-lab --status reachable --output tmp\stand-report.json
```

Экспорт OpenAPI-контракта:
```bash
.\.venv\Scripts\python scripts\export_openapi.py --output tmp\openapi.json
```

Сборка полного demo bundle:
```bash
.\.venv\Scripts\python scripts\build_demo_bundle.py --base-url http://127.0.0.1:8000 --api-key demo-secret --site msk-lab --status reachable --output-dir tmp\demo-bundle
```

Сброс mock demo-state перед повторным показом:
```bash
.\.venv\Scripts\python scripts\reset_demo_state.py --base-url http://127.0.0.1:8000 --api-key demo-secret
```

## Тесты
```bash
.\.venv\Scripts\python -m pytest
```

## Рекомендуемый сценарий демонстрации на защите
1. Запустить сервис в режиме `mock + mock` и открыть Swagger UI.
2. Показать инвентарь устройств и каталог профилей.
3. Включить `NAA_API_KEY`, отправить запрос без `X-API-Key` и показать `401`.
4. Повторить тот же запрос с корректным ключом.
5. Отправить запрос с `X-Request-ID` и показать, что он возвращается в ответе и попадает в журнал.
6. Показать selector-based выбор устройств без ручного перечисления узлов.
7. Выполнить profile-based `preview` и пояснить merge профиля с overrides.
8. Отправить намеренно некорректный payload и показать `422` до запуска автоматизации.
9. Выполнить batch `preview` и показать partial success / partial failure.
10. Показать фильтрацию инвентаря по площадке или роли.
11. Запустить `preflight` перед применением конфигурации.
12. Запустить `diagnostics` перед переходом к живому стенду.
13. Выполнить `stand_validate.py` и сохранить `stand-report.json`.
14. Экспортировать `openapi.json` как зафиксированный API-контракт.
15. Собрать `demo-bundle` и показать `summary.md`, `stand-validation.json`, `openapi.json`.
16. Выполнить `reset_demo_state.py` и показать возврат стенда к baseline.
17. Выполнить selector-based `preview`.
18. Выполнить `dry_run` и показать, что running-config не меняется.
19. Выполнить compliance-проверку и показать drift-report.
20. Выполнить batch compliance.
21. Выполнить selector-based compliance.
22. Выполнить selector-based `apply` в `dry_run` режиме.
23. Выполнить реальный `apply` в mock-контуре и показать `snapshot_id`.
24. Повторно выполнить compliance и показать, что устройство стало compliant.
25. Перезапустить сервис и показать, что состояние и журнал сохранились в JSON.
26. Выполнить rollback.
27. Показать фильтрованный журнал операций.
28. Показать aggregate summary по операциям.
29. Пояснить, что тот же API-контур можно переключить на `netbox` и `netmiko` через переменные окружения.
