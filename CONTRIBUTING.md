# Работа над ClipFlow

Исходники: src/clipflow. Настройка: docs/DEVELOPMENT.md. Python3.12, `python scripts/check.py` (сначала ruff format/check, затем тесты и пороги покрытия), native package checks перед выдачей. Стиль — docs/DEVELOPMENT.md, раздел «Стиль кода». Изменения в dev; main только после необходимых exact-SHA gates. Не force-push и не стирать чужие изменения.

Проверять фактическое поведение regression tests; сетевые mock данные не доказывают upstream доступ. Секреты, cookies, профили и машинные пути не коммитить. Все тесты с CLIPFLOW_DATA_DIR; отмена/закрытие ждут worker teardown. Instagram использует общую rate policy, включая probes.

Нативные Windows и Mac проверки различать. Незавершённая Mac приёмка описана в docs/MAC-T16A.md. Лицензию собственного кода не менять; зависимости сохраняют свои лицензии.
