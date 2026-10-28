# ClipFlow Qt Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести ClipFlow на PySide6/Qt с общим проверяемым ядром Windows/macOS, рабочими одиночными и пакетными загрузками, обязательной тёмной темой и нативными установщиками.

**Architecture:** Импортируемый пакет `src/clipflow` отделяет domain/application, провайдеры, инфраструктуру и Qt Widgets. Провайдеры синхронны за интерфейсом executor; сеть и FFmpeg исполняются вне GUI-потока, события содержат job/attempt ID. История/очередь хранятся в SQLite, настройки — в версионированном JSON, секреты — в прежнем защищённом хранилище.

**Tech Stack:** Python 3.12, существующие PySide6 6.10.3 / yt-dlp / Instaloader / FFmpeg / Node.js, Qt Widgets model/view, SQLite stdlib, pytest, pytest-qt, pytest-cov, PyInstaller, Inno Setup.

**Spec:** `docs/superpowers/specs/2026-10-27-clipflow-qt-design.md`, утверждена 27 октября 2026. Визуальный ориентир: `docs/superpowers/specs/assets/2026-10-27-clipflow-qt-concept.html` и три PNG рядом.

## Global Constraints

- Прямое уточнение владельца 27 октября: после каждого завершённого этапа — пауза. Сохранить тесты/коммит/память и ждать команды продолжить; автоматический переход к следующей task запрещён. Текущая граница: T8 завершён; пауза перед T9.
- Одна Python-кодовая база; Windows x64 и macOS Apple Silicon, текущий минимум macOS 27; Python 3.12.
- Тёмная тема включена при первом запуске; доступны светлая и системная. Выбор сохраняется.
- Одновременно скачивается одно задание; остальные стоят в очереди. Автозапуск выключен по умолчанию.
- Минимальное окно 880×680, начальный размер около 1180×800; масштабы 100/150/200%, RU/EN.
- Domain/application — 95% строк и 90% ветвей; весь поддерживаемый собственный runtime-код — 85% строк. Сторонний/сгенерированный код и ресурсы исключены; собственные адаптеры/провайдеры не исключать ради порога.
- Работать в `dev`, сохранять посторонние изменения. `main` — только после checks обеих ОС точного коммита и соответствующих пакетных проверок; без force-push.
- DPAPI/Keychain и прежние каталоги/сессии сохраняются. Секреты не попадают в SQLite, Git, логи и фикстуры. Все проверки используют `CLIPFLOW_DATA_DIR`.
- Исторический Google Drive Windows не изменять. `.git`/`.venv` через Drive не синхронизировать. На Mac после проверенной установки одна зарегистрированная копия приложения.
- Ни автоматического обновлятора, ни Spotify-аудио, ни историй Instagram/Intel Mac/новых платных сервисов в этом выпуске.
- Последние N постов определяются по дате, учитывая закрепления; невозможность доказать полноту явно обозначается. HTTP 429 не является успехом.
- Обязательны правила `docs/INSTAGRAM-RATE-LIMITS.md` (дополнение владельца): общий gate Instaloader/yt-dlp/probe; metadata minimum 3s, posts/pages 10–20s как начальные значения; Retry-After/библиотечные задержки имеют приоритет; fallback cooldown 15/30/60 минут, максимум два automatic retries после исходного 429; Instagram fragment concurrency=1, persisted budget/deadline и отменяемые waits. Не заявлять гарантии отсутствия 429.
- Релиз не содержит исполняемый Tk UI и скрытое окно legacy App. Во время переноса старые проверки запускаются отдельными процессами, а не импортируют монолит в Qt.

## Review Focus

1. Поддельные хосты, URL с credentials и tracking/img_index не должны менять сервис/контентную идентичность; pin в T1/T2.
2. Изменение поля, сервиса или параметров во время probe не теряет запрос и не принимает поздний ответ за актуальный; pin в T2/T11.
3. Закрепления, совпадение Reels с лентой, ошибка на второй странице и отмена профиля не создают дублей/ложного успеха; pin в T8.
4. Unicode, Windows device names, длинные пути, разные посты без подписи и ошибка записи/FFmpeg не перезаписывают готовые данные; pin в T4/T7.
5. Выход между записью файла и сохранением состояния, SQLite busy/corruption, дочерний процесс авторизации и повреждённые настройки не теряют сессии и не возобновляют сеть сами; pin в T9/T13/T14.

## Карта файлов и интерфейсов

Новый пакет содержит `domain/{models,urls,events,paths}.py`, `application/{ports,submission,scheduler}.py`, `providers/{base,media,youtube,getcourse,instagram_post,instagram_profile}.py`, `infrastructure/{repository,settings,executor,platform,auth}.py`, `ui/{bootstrap,window,presenter,composer,batch_dialog,queue_model,queue_delegate,themes,i18n,accounts,settings_page,history}.py`, `__main__.py` и `version.py`. Каждый модуль отвечает только за названную область.

Старые `source/{media_names,instagram_media,instagram_profile,youtube_session,instagram_session,embedded_auth,platform_support}.py` — источники проверяемого переноса, не будущая зависимость от App. Ресурсы перемещаются в `assets/` и включаются через пакетный resource resolver. Авторизационный подпакет `infrastructure/auth_process/` сохраняет отдельный Qt-процесс.

Новые тесты: `tests/unit/`, `tests/integration/`, `tests/ui/`, `tests/platform/`, `tests/fixtures/`, общий `tests/conftest.py`. Legacy `tests/test_*.py` временно остаются под `scripts/check.py` в отдельных процессах; `pytest.testpaths` во время переноса указывает только новые подпапки. Так `source/clipflow.py` и новый пакет не конфликтуют в одном процессе. После доказанного паритета legacy удаляется.

### Контракты данных (определяются один раз в T1/T3/T4)

- `Service`: `youtube`, `instagram`, `getcourse`; `ContentKind`: `video`, `playlist`, `post`, `profile`, `lesson`, `player`.
- `ParsedLink(service, kind, canonical_id: str, canonical_url: str)` — frozen dataclass.
- `DownloadOptions(folder: Path, format: str='mp4', max_height: int|None=None, media_filter: str='all', author_folder: bool=True, post_folder: bool=True, description: str|None=None, auth_profile: str|None=None)` — frozen. Форматы `mp4/mkv/webm/mp3`, description `None/txt/md`, media_filter `all/video/photo`; auth_profile — безопасная ссылка на защищённый профиль, не секрет.
- `DownloadRequest(link: ParsedLink, options: DownloadOptions, selection: tuple[str,...]|None=None, profile_limit: int|None=None, playlist: PlaylistPosition|None=None)` — frozen. Лимит профиля `10/50/None`, где None означает все; только explicit profile mode/batch preview может создавать profile request. T5 добавил frozen `PlaylistPosition(playlist_id: str, index: int)` для дочернего YouTube video; snapshot участвует в request_key и должен сериализоваться в T9. Исходный номер не выводится из порядка очереди и не теряется после restart/retry.
- `Job(id: str, request: DownloadRequest, state: JobState, attempt_id: str|None, parent_id: str|None=None, result_files: tuple[Path,...]=(), error: str|None=None, pause_reason: str|None=None, next_allowed_at: datetime|None=None)` — изменения через replacement, request не мутирует из UI.
- `BatchPreview(requests: tuple[DownloadRequest,...], invalid: tuple[LineError,...], duplicate_lines: tuple[int,...])`, `SubmissionResult(added: tuple[str,...], existing: tuple[str,...])`; LineError содержит номер строки, безопасный ввод и сообщение.
- `JobState`: queued/probing/downloading/processing/completed/paused/cancelled/failed. `JobEvent(job_id, attempt_id, payload)`; payload — одна из frozen структур `StageChanged`, `ProgressChanged`, `FilesSaved`, `RequestsDiscovered`, `SelectionRequired`, `RateLimitDeferred`, `WorkFinished`, `WorkFailed`, `WorkStopped`. WorkStopped подтверждает освобождение ресурсов после stop/deferral; терминальные worker-события доставляются только после teardown. RateLimitDeferred содержит next_allowed_at/automatic_retry/reason по политике Instagram.
- `CancellationToken.cancel(reason: Literal['pause','cancel','shutdown'])->None`, `raise_if_cancelled()->None`, `wait(timeout: float)->bool`.
- `ExecutionContext(cancel: CancellationToken, emit: Callable[[ProviderEvent],None], auth: AuthGateway, instagram_rate: InstagramRatePolicy|None=None)`. ProviderEvent не содержит UI-объектов; executor добавляет job/attempt IDs. После T8 всем Instagram путям передаётся один policy; None допустим только другим сервисам/ранним unit fixtures.
- `ProbeResult(items: tuple[MediaItem,...], available_heights: tuple[int,...], selection_required: bool=False)`, `MediaItem(id: str, index: int, kind: Literal['photo','video'], title: str, info: Mapping[str,object])`. Raw info/CDN URL живут в памяти, не в истории.
- `DownloadResult(files: tuple[Path,...], discovered_count: int=0)`; профиль может завершить сбор списка без выдачи его за скачанные медиа.

---

### Task 1: Импортируемые модели и единое распознавание URL

**Files:** Create `pyproject.toml`, `requirements-dev.txt`, `src/clipflow/__init__.py`, `src/clipflow/domain/{models,urls}.py`, `tests/conftest.py`, `tests/unit/test_urls.py`; modify `scripts/check.py` для запуска новых тестов после legacy и `.github/workflows/check.yml` для установки test dependencies с первого этапа.

**Interfaces:** Produces `parse_url(text: str)->ParsedLink`, `request_key(request: DownloadRequest)->str`, контракты моделей выше; ошибки — `InvalidLink(ValueError)`. Core не импортирует Qt. Editable package должен устанавливаться Python 3.12 без запуска UI.

- [x] Написать параметризованные red-тесты: music.youtube.com — YouTube; Instagram /p/ABC?img_index=2 и /p/ABC имеют один ID; /username — profile; youtube.com.evil.test, instagram.com.evil.test, user:pass@host, javascript:, пустой ID отклоняются. Разные форматы/папки/auth references дают разные request keys, tracking-параметры — нет.
- [x] `python -m pytest tests/unit/test_urls.py -q`: получить ожидаемый import/behavior failure до реализации; записать причину.
- [x] Реализовать контракты; optional dev dependencies в pyproject включают pytest/pytest-qt/pytest-cov, requirements-dev ссылается на `-e .[dev]` без второго списка версий. В CI обеих ОС установить эти зависимости перед scripts/check.py уже в T1. Проверить доступность совместимых версий перед pin в lock; существующие runtime pins не обновлять попутно.
- [x] `python -m pip install -e '.[dev]'` и `python -m pytest tests/unit/test_urls.py -q`: PASS; `python -c "import clipflow.domain.models; import sys; assert 'PySide6' not in sys.modules"`: exit 0. Старый `scripts/check.py` продолжает проходить в изолированных subprocesses.
- [x] Commit `refactor: introduce typed requests and canonical URL routing` с файлами T1.

### Task 2: Одна команда одиночного и пакетного добавления

**Files:** Create `application/{ports,submission}.py`, `tests/unit/test_submission.py`, `tests/helpers.py`.

**Interfaces:** Produces `JobRepository` Protocol `add(job)->None`, `get(job_id)->Job`, `list()->tuple[Job,...]`, `update(job)->None`; `AuthGateway.options_for(auth_profile: str|None, url: str)->Mapping[str,object]`. `SubmissionService(repository).preview(text: str, presets: Mapping[Service,DownloadOptions], mode: str='batch', profile_limit: int|None=10)->BatchPreview`; `.submit(preview)->SubmissionResult`; `.repeat(job_id)->str`. Modes `single/batch/profile/playlist/lesson`.

- [x] Red-тест `test_mixed_batch_ignores_bad_lines_and_preserves_per_service_snapshot`: Instagram пост + профиль + YouTube + плохая строка + повтор дают 3 requests, 1 invalid, 1 duplicate; presets каждого сервиса сохраняются после изменения исходной mapping. `test_single_mode_rejects_profile`, `test_profile_limit_is_explicit`, `test_quality_probe_cannot_block_submission`, `test_completed_job_requires_explicit_repeat`.
- [x] `python -m pytest tests/unit/test_submission.py -q`: ожидаемый FAIL.
- [x] Реализовать preview без сети/создания файлов и submit с дедупликацией queued/active; completed не возобновляется молча, repeat создаёт новую попытку явно. Request с profile всегда имеет post_folder=True. Profile в mixed preview явно показывает выбранный/default 10 лимит.
- [x] Тот же pytest: PASS; добавить проверки отсутствия Qt-импорта и неизменности исходных presets.
- [x] Commit `feat: add unified single and batch submission commands`.

### Task 3: Машина состояний и планировщик без виджетов

**Files:** Create `domain/events.py`, `application/scheduler.py`, `tests/unit/test_scheduler.py`.

**Interfaces:** Consumes JobRepository; produces `Executor.start(job: Job, on_event: Callable[[JobEvent],None])->None`, `.stop(job_id: str, reason: str)->None`; `Scheduler(repository, executor)` methods `start()`, `pause(job_id)`, `resume(job_id)`, `cancel(job_id, include_children=True)`, `retry(job_id)`, `select_items(job_id, ids: tuple[str,...])`, `handle(event)`, `subscribe(callback)->unsubscribe`. Defines CancellationToken/typed events above.

- [x] Red: `test_one_running_job`, `test_old_attempt_cannot_fail_new_attempt`, `test_download_100_is_not_completed_before_processing`, `test_pause_preserves_partial_then_resumes_new_attempt`, `test_profile_cancel_cancels_unstarted_children`, `test_failure_advances_queue`, `test_shutdown_does_not_start_next`.
- [x] `python -m pytest tests/unit/test_scheduler.py -q`: FAIL before implementation.
- [x] Реализовать допустимые переходы, single concurrency, новый attempt ID на retry/resume, дедуп discovered children по request key. SelectionRequired переводит задание в paused с понятной причиной; select_items создаёт новый снимок request с selection и новую попытку. Отмена родителя не удаляет результаты завершённых детей.
- [x] Unit suite: PASS; deterministic fake executor не исполняет реальную сеть и позволяет произвольный порядок поздних событий.
- [x] Commit `feat: add attempt-safe queue state machine`.

### Task 4: Медиаконвейер, пути и атомарные описания

**Files:** Create `domain/paths.py`, `providers/{base,media}.py`, `tests/unit/test_media_paths.py`, `tests/integration/test_media_pipeline.py`; перенос полезных частей `source/{media_names,instagram_media}.py` и `download_options/completed_media_paths/clean_download_sidecars` без App.

**Interfaces:** Produces `Provider` Protocol `.probe(request, context)->ProbeResult`, `.execute(request, context)->DownloadResult`; `MediaPipeline.save(item: MediaItem, request: DownloadRequest, context: ExecutionContext)->tuple[Path,...]`; `output_path(request, item, author: str|None, post: PostIdentity|None)->Path`; `PostIdentity(code: str, title: str|None, published_at: datetime|None)`.

- [x] Red: `test_untitled_posts_cannot_collide`, `test_post_folder_off_includes_post_id`, `test_windows_reserved_unicode_and_long_path`, `test_filtered_items_keep_original_number`, `test_caption_replace_failure_preserves_previous_file`, `test_disk_full_never_reports_success`. Native FFmpeg test: MP4/MKV/WebM/MP3 output has expected streams/container; second run preserves finished file mtime; cancellation retains resumable partials.
- [x] Run `python -m pytest tests/unit/test_media_paths.py tests/integration/test_media_pipeline.py -q`: FAIL for missing pipeline.
- [x] Реализовать безопасные пути, оригинальную нумерацию, atomic descriptions и общий FFmpeg/YoutubeDL pipeline. WebM: remux совместимых потоков, VP9/Opus conversion для несовместимых; не менять разрешение молча. Для фото сохранить оригинальное расширение/байты. Учитывать postprocessed final extension при повторе.
- [x] Тот же pytest с настоящим FFmpeg/FFprobe и локальным HTTP-сервером: PASS; ошибки инструмента/записи дают typed failure, не completed.
- [x] Commit `refactor: extract safe media pipeline and output layout`.

T4 verified on Windows 11 x64 / Python 3.12.10 / FFmpeg 9.0.2: 47 new tests, 126 total pytest tests, full scripts/check.py. `MediaItem.info` carries transient source metadata; Instagram adapters normalize `author`, `post_code`, `post_title`, `published_at` (datetime), `description`, `ext`, `http_headers` when required by the extractor. Mixed/lowercase post codes include a deterministic case marker to avoid collisions on case-insensitive volumes. No new packaged Qt release or live provider check is implied.

### Task 5: YouTube и YouTube Music через общий провайдер

**Files:** Create `providers/youtube.py`, `tests/unit/test_youtube_provider.py`, `tests/integration/test_youtube_worker.py`.

**Interfaces:** Produces `YouTubeProvider(pipeline: MediaPipeline)` implementing Provider. Consumes request link/format and ephemeral AuthGateway options; emits typed stage/progress/files/discovered events.

- [x] Red: `test_single_video`, `test_music_track_audio_mode`, `test_music_playlist`, `test_playlist_order_and_unavailable_entry`, `test_auth_options_are_not_in_result_or_logs`, `test_audio_quality_not_misrepresented_as_lossless` with recorded synthetic metadata. Progress burst 3000 callbacks/3s yields ≤7 UI telemetry updates and cannot skip processing.
- [x] `python -m pytest tests/unit/test_youtube_provider.py tests/integration/test_youtube_worker.py -q`: FAIL.
- [x] Перенести yt-dlp options/auth/hooks из legacy worker в provider; плейлист выдаёт стабильные задания/нумерацию, недоступный элемент не уничтожает остальные. Никакого обращения к Qt/App.
- [x] Tests: PASS with local media URLs; живые YouTube/Music проверки отложены в T16 и не подменяются этими тестами.
- [x] Commit `feat: port YouTube and Music provider to shared pipeline`.

T5: 27 tests (24 unit + 3 real HTTP/FFmpeg integration), 153 total pytest + full scripts/check.py passed locally on Windows. Playlist discovery retains valid private IDs as independent jobs, skips entries without IDs without closing numbering gaps, emits batches ≤25. Lazy yt-dlp entries are consumed within the downloader lifetime and safe error/cancellation boundary. Children use a stable per-playlist ID directory (portable case marker) and original 001 positions; T9 must persist PlaylistPosition. Native sessions/live YouTube/Music remain unverified until their later stages/T16.

### Task 6: GetCourse: урок, плеер, выбор материалов

**Files:** Create `providers/getcourse.py`, `tests/unit/test_getcourse_provider.py`, `tests/fixtures/getcourse/`.

**Interfaces:** Produces `GetCourseProvider(pipeline)` implementing Provider. ProbeResult содержит стабильные media IDs/названия; для выбора selection_required=True, execute проверяет request.selection против актуальных доступных IDs.

- [x] Red: `test_direct_player`, `test_lesson_all_items`, `test_selection_required_and_selected_ids`, `test_school_login_error_not_instagram_hint`, `test_source_cookie_export_is_not_overwritten`, `test_metadata_change_rejects_missing_selection`.
- [x] `python -m pytest tests/unit/test_getcourse_provider.py -q`: FAIL.
- [x] Перенести GetCourse extractor/title parsing и доступ: protected account reference, browser cookies, email/password, Netscape export, no-login. Сетевой доступ к школе идёт через AuthGateway; чтение экспорта не записывает его обратно.
- [x] Tests: PASS; скрытые credentials редактируются в диагностике, ошибка одного материала не удаляет остальные.
- [x] Commit `feat: preserve GetCourse access and lesson selection`.

T6: 30 cases in test_getcourse_provider.py (including two actual local HTTP/FFmpeg transfers), 183 total pytest + full scripts/check.py passed on Windows. Scoped subclasses replace legacy global monkey patches. Regional vhcdn/gceuproxy /sign-player routes are supported; lookalikes rejected. Stable IDs come from video_hash/actual player IDs; missing/changed selection is rejected. Multiple chosen IDs become independent lesson child requests with singleton selection. Shared providers/access.py reads Netscape exports into memory without rewriting them, rejects malformed rows before yt-dlp can log raw cookie contents, and accepts ephemeral _cookiejar for the authenticated media transfer. AuthGateway protected storage/browser UI adapters remain T13; live school access remains T16. GetCourse outputs use stable lesson/player subdirectories to prevent same-title collisions; new paths do not move existing files.

### Task 7: Instagram: отдельный пост, Reel и карусель

**Files:** Create `providers/instagram_post.py`, `tests/unit/test_instagram_post.py`, `tests/integration/test_instagram_files.py`.

**Interfaces:** Produces `InstagramPostProvider(pipeline)` implementing Provider; наследует проверенное извлечение фото/метаданных из `source/instagram_media.py`, не из App.worker.

- [x] Red: `test_single_post_does_not_discover_profile`, `test_carousel_img_index_does_not_truncate`, `test_mixed_photo_video_numbering_and_paired_txt_md`, `test_author_and_post_folder_options_independent`, `test_caption_missing_or_disabled`, `test_second_untitled_post_same_author_safe`.
- [x] `python -m pytest tests/unit/test_instagram_post.py tests/integration/test_instagram_files.py -q`: FAIL.
- [x] Реализовать post/Reel probe/execute с исходным порядком, безопасным author/post ID, парными описаниями и фильтрами. При HTTP/FS failure завершённые элементы сохраняются, failed item имеет отдельную диагностику.
- [x] Tests: PASS with actual local image/video downloads; нет лишних TXT для caption=None, нет перезаписи соседнего поста при выключенной папке поста.
- [x] Commit `feat: port individual Instagram posts and carousels`.

T7: 36 cases (20 unit + 16 local HTTP/FFmpeg integration), 219 total pytest + full scripts/check.py passed locally on Windows. Profiles are rejected before networking; img_index is removed by canonical routing. Scoped extractor preserves the photo adaptation; original carousel positions, author/post options, caption pairs and completed-file reuse use T4. First failed item stops the post with InstagramMediaFailure(media_id,index,reason); prior FilesSaved remain, later items are not claimed complete. Shared SessionAuth carries refreshed metadata cookies into transfers without credentials in results/history. No policy in context fails closed before requests; automatic yt-dlp retries are disabled for Instagram. Actual shared HTTP pacing/cooldown/Retry-After remains T8, including the upstream homepage initialization request. Final tests stub that initialization and enforce loopback-only urlopen; the first pre-isolation run accidentally allowed the initialization homepage fetch and is not offline or live-content acceptance evidence.

### Task 8: Instagram-профили: точный лимит, частичные результаты и отмена

T7 follow-through for the existing shared-policy requirement: also wire providers/instagram_post.py and providers/access.py as needed. The coarse metadata/post acquire calls in T7 are not full HTTP pacing: cover yt-dlp initialization/homepage, API/probes and CDN transfers with the same real policy, propagate Retry-After/RateLimitDeferred, keep implicit library retries disabled, and test every path without making live requests to a blocked account.

**Files:** Create `providers/instagram_profile.py`, `tests/unit/test_profile_discovery.py`, `tests/integration/test_profile_queue.py`.

**Interfaces:** Produces `InstagramProfileProvider(page_source: ProfilePageSource)` implementing Provider. `ProfilePageSource.pages(request, context)->Iterator[ProfilePage]`; `ProfilePage(posts: tuple[PostRef,...], next_cursor: str|None, order_guaranteed: bool, pinned_ids: frozenset[str])`; `PostRef(code: str, published_at: datetime, author: str)`. execute emits RequestsDiscovered batches ≤25, DownloadResult.discovered_count; JobRepository dedup in T3.

Также create `application/instagram_rate_policy.py`, `infrastructure/rate_limit_store.py`, `tests/unit/test_instagram_rate_policy.py`, `tests/integration/test_rate_limit_store.py`; modify `domain/events.py`, `application/scheduler.py`, `providers/media.py` для RateLimitDeferred/gate. Contract `InstagramRatePolicy.acquire(kind: str, cancel: CancellationToken)->None`, `.record_429(retry_after: str|None)->RateLimitDecision`, `.record_completed_post()->None`; decision: next_allowed_at UTC, automatic_retry bool, reason. `RateLimitStore.reserve(kind, now_utc, minimum_gap)->datetime`, `.save_cooldown(deadline, strikes)->None`, `.load()->RateLimitState`. Clock/random инъецируемые, отдельный versioned `instagram-rate.sqlite3` store/lease защищает разные процессы и не зависит от будущей queue DB T9. Передать один policy в context всем Instagram providers и probes; UI wiring — T10/T11.

- [x] Red: `test_latest_10_with_old_pinned_posts`, `test_latest_50_merges_reels_without_duplicates`, `test_all_paginates_until_exhausted`, `test_cancellation_interrupts_backoff`, `test_429_second_page_keeps_discovered_jobs_but_not_success`, `test_private_profile_requires_access`, `test_unknown_order_does_not_claim_latest_n`.
- [x] `python -m pytest tests/unit/test_profile_discovery.py tests/integration/test_profile_queue.py -q`: FAIL.
- [x] Обернуть Instaloader источником страниц. У profile probe только валидация ссылки, execute выполняет реальное перечисление один раз; не собирать профиль дважды из-за общей цепочки probe/execute. Передать cookie session в памяти; ставить bounded timeout/retry и отменяемый wait. Не считать первую порцию N гарантированно последними N: учитывать закрепления/порядок и при необходимости продолжать до доказуемой границы, при неизвестном порядке — до исчерпания либо явного ограничения. UI сообщит неполноту, не выдаст её за точный результат.
- [x] Tests: PASS; 5000 synthetic posts не исполняются в GUI-потоке, порции ограничены, повторные страницы не удваивают очередь. Живой rate-limited профиль остаётся непроверенным до T16.
- [x] Дополнительный red/green cycle policy: `test_shared_budget_across_instaloader_ytdlp_probe`, `test_metadata_minimum_3_seconds`, `test_page_post_gap_10_to_20`, `test_retry_after_seconds_and_http_date`, `test_invalid_retry_after_falls_back`, `test_library_wait_wins`, `test_429_backoff_900_1800_3600_then_manual`, `test_cooldown_survives_restart_and_clock_rollback`, `test_cross_process_reservation`, `test_cancel_interrupts_wait`, `test_instagram_cooldown_releases_youtube_worker`, `test_cdn_not_throttled_per_chunk`. Сначала увидеть FAIL; реализовать policy/deadline событие и paused reason в scheduler из T3, затем `python -m pytest tests/unit/test_instagram_rate_policy.py tests/integration/test_rate_limit_store.py -q`: PASS. Profile cursor/checkpoint и completed IDs сохраняются безопасно, expired cursor вызывает dedup re-enumeration без ложной полноты.
- [x] Commit `feat: add cancellable profile discovery with explicit completeness`.

T8: 38 new cases, 257 total pytest; exact completeness is conservative: latest N enumerates feed/Reels to exhaustion, all mode emits batches ≤25 incrementally. Fresh enumeration/dedup is used for expired or nonportable cursors; checkpoints are hints, never queue acknowledgements. Separate versioned SQLite stores budget, cooldown/strikes, lease, safe IDs/checkpoints; no session or signed URL persistence. Every new-core Instagram HTTP path uses a scoped transport, including yt-dlp initialization/redirects/CDN and Instaloader cloned sessions; no chunk sleeps. Scheduler tick is owner-thread driven, manual/user pause cannot automatically retry. UI/policy singleton wiring and shutdown close remain T10/T13. T9 must serialize Job.automatic_retry and recover it as false (no network on restart), as well as PlaylistPosition. Live Instagram remains T16; no release/install/main changes.

### Task 9: Постоянная очередь, история и настройки с миграцией

**Files:** Create `infrastructure/{repository,settings}.py`, `tests/integration/test_repository.py`, `tests/unit/test_settings_migration.py`.

**Interfaces:** Produces `SqliteJobRepository(path: Path)` implementing JobRepository plus `.history()->tuple[Job,...]`, `.recover()->tuple[Job,...]`, `.clear_history()->None`, `.close()->None`; `SettingsStore(directory: Path).load()->AppSettings`, `.save(settings: AppSettings)->None`. AppSettings fields: schema_version=2, theme='dark', language='ru', auto_start=False, presets per Service, recent_folders, profile_limit=10.

- [ ] Red: `test_restart_recovers_active_as_paused`, `test_completed_history_preserved`, `test_unknown_schema_never_overwrites`, `test_busy_db_reports_failure`, `test_corrupt_database_is_preserved_and_reported`, `test_readonly_data_directory_reports_actionable_error`, `test_corrupt_settings_backup_and_defaults`, `test_legacy_settings_migrate_without_touching_sessions`, `test_no_credentials_or_signed_cdn_urls_persisted`.
- [ ] `python -m pytest tests/integration/test_repository.py tests/unit/test_settings_migration.py -q`: FAIL.
- [ ] Создать schema-versioned SQLite (`queue.sqlite3`) и JSON `settings-v2.json` рядом с прежним settings.json. Migration читает whitelist старых параметров, делает backup, не изменяет старые protected files. Запись атомарна; транзакции ограничены. Original lesson/post URL можно хранить только без секретных query-параметров; auth-required request хранит безопасный protected-profile reference, не credential value. Если ссылка без секрета невосстановима — при восстановлении запросить ввод снова, не записывать секрет в историю.
- [ ] Tests: PASS with temporary disk DB, simulated power-loss point после готового файла и до commit. Recover не создаёт сетевой запрос сам и согласует найденный файл через pipeline при явном resume.
- [ ] Commit `feat: persist queue and history with safe settings migration`.

### Task 10: Qt-оболочка с настоящим вертикальным сценарием

**Files:** Create `infrastructure/executor.py`, `ui/{bootstrap,window,presenter,queue_model,queue_delegate}.py`, `__main__.py`, `tests/ui/test_workbench.py`; modify `run.py` для временного `--qt-preview` без изменения legacy default до T16.

**Interfaces:** Produces `ThreadExecutor(provider_registry, auth_gateway)` implementing Executor; `WorkbenchPresenter(submission, scheduler, settings, repository)` Qt signals `jobs_changed`, `input_accepted`, `error_raised`; `MainWindow(presenter)`; `create_application(argv: list[str], data_dir: Path|None=None)->tuple[QApplication,MainWindow]`; `JobListModel(QAbstractListModel)` roles job_id/title/state/progress/files/source. GUI обновляется только queued signals.

- [ ] Red qtbot: `test_real_url_command_creates_model_row`, `test_worker_events_update_correct_attempt`, `test_local_media_download_reaches_real_completed_file`, `test_window_minimum_880x680`, `test_large_queue_uses_model_not_child_widgets`, `test_blocking_provider_does_not_block_gui_timer`.
- [ ] `python -m pytest tests/ui/test_workbench.py -q`: FAIL.
- [ ] Создать базовый workbench по макету: sidebar, composer placeholder подключённый к SubmissionService, очередь model/delegate, настоящие действия. Подключить registry T5–T8 и T9, базовую dark palette с первого запуска. Темп UI progress ≤2 Hz; critical state/errors проходят сразу.
- [ ] Tests: PASS including local media provider → saved file → persisted history; никакого hidden legacy App и fake completed timer. `python run.py --qt-preview` открывает новый workbench только явно.
- [ ] Commit `feat: add Qt workbench with real asynchronous download flow`.

### Task 11: Одиночная/пакетная форма и явные режимы сервисов

**Files:** Create `ui/{composer,batch_dialog}.py`, `tests/ui/test_submission_dialogs.py`; modify `ui/window.py`, `ui/presenter.py`.

**Interfaces:** Produces `Composer` signals `submit_requested(text, mode, profile_limit)`, `probe_requested(text, request_id)`; `BatchDialog(submission, presets).preview()->BatchPreview`, accepted только после явной кнопки. Presenter использует SubmissionService из T2, не переключает чужие поля для добавления.

- [ ] Red qtbot: `test_batch_button_always_visible`, `test_mixed_batch_adds_three_services_and_profile`, `test_bad_line_does_not_block_valid_lines`, `test_single_profile_requires_explicit_mode`, `test_profile_10_50_all`, `test_input_changed_during_probe_not_cleared`, `test_quality_pending_does_not_drop_batch`, `test_cancel_dialog_adds_nothing`, `test_getcourse_media_selection`.
- [ ] `python -m pytest tests/ui/test_submission_dialogs.py -q`: FAIL.
- [ ] Реализовать видимые режимы и раскрываемые параметры, per-service draft/presets, batch preview с лимитами/ошибками/дублями, асинхронный probe с request ID. Accepted input очищается только если всё ещё относится к принятому запросу. SelectionRequired открывает Qt-выбор материалов без blocking GUI worker.
- [ ] Qt suite: PASS; проверять клик/Enter на настоящих виджетах до JobRepository, а не только прямой вызов presenter.
- [ ] Commit `feat: expose reliable single batch and Instagram profile modes`.

### Task 12: Полные темы, RU/EN и системная клавиатура

**Files:** Create `ui/{themes,i18n}.py`, `tests/ui/test_themes.py`, `tests/platform/test_qt_clipboard.py`; modify все Qt формы для общих tokens/translations.

**Interfaces:** Produces `ThemeManager(app, settings).set_mode(mode: Literal['dark','light','system'])->None`, `.resolved_mode()->str`, `.tokens()->Mapping[str,str]`; `Translator(language).text(key: str, **args)->str`. Набор токенов покрывает backgrounds/text/disabled/border/accent/success/error/selection/focus/menu/dialog.

- [ ] Red: `test_dark_first_launch_and_persistence`, `test_system_palette_change`, `test_every_dialog_has_readable_dark_controls`, `test_all_text_pairs_contrast_4_5`, `test_ru_en_880px_no_clipping`, `test_ctrl_command_v_button_context_menu_all_services`, `test_russian_keyboard_edit_shortcuts`, `test_batch_shortcut_ctrl_command_n`.
- [ ] `python -m pytest tests/ui/test_themes.py tests/platform/test_qt_clipboard.py -q`: FAIL (native clipboard marker в настоящей GUI-сессии отдельно).
- [ ] Реализовать единые palettes/styles и tokens, стандартные Qt menus/input с platform shortcuts, каталог переводов вместо замен произвольного текста. Смена сервиса меняет только accent/иконку, не глобальную палитру. Масштаб определяется Qt DPI; пользовательский zoom не применяется дважды.
- [ ] Tests: PASS for light/dark/system, RU/EN, 100/150/200% отдельными GUI-процессами; native clipboard тест сохраняет и восстанавливает прежний clipboard. Не заменять native результат offscreen-проходом.
- [ ] Commit `feat: add persistent dark light system themes and native input`.

### Task 13: Аккаунты, защита и перенос авторизационных процессов

**Files:** Create `infrastructure/{platform,auth}.py`, `infrastructure/auth_process/{__main__,window,sessions}.py`, `ui/{accounts,settings_page}.py`, `tests/platform/test_auth_compatibility.py`, `tests/ui/test_accounts.py`; источник поведения — прежние platform/session/embedded_auth модули.

**Interfaces:** Produces `NativeAuthGateway(data_dir)` implementing AuthGateway; `.sign_in(service: Service, language: str)->AuthProcessHandle`, `.logout(auth_profile: str)->None`, `.status(service)->AuthStatus`; `AuthProcessHandle.poll()->AuthStatus`, `.close()->None`; `PlatformServices.reveal(path: Path)->None`, `.choose_folder(parent, initial: Path)->Path|None`, `.protect(data: bytes, decrypt: bool=False)->bytes`.

- [ ] Red: `test_old_encrypted_session_readable`, `test_youtube_instagram_isolation`, `test_logout_only_selected_service`, `test_auth_process_single_instance`, `test_close_parent_handles_child`, `test_no_secret_in_errors_db_or_support_export`, `test_windows_icon_retained_after_delayed_startup`, `test_macos_data_and_keychain_namespace_unchanged`.
- [ ] `python -m pytest tests/platform/test_auth_compatibility.py tests/ui/test_accounts.py -q`: FAIL.
- [ ] Перенести защиту и отдельный QtWebEngine auth process без смены key namespace/формата snapshot. Bootstrap распознаёт прежние `--youtube-login`, `--instagram-login`, `--auth-self-test`, `--instagram-auth-self-test` до создания основного окна. GetCourse auth references дают доступ к проверенной школе, не наследуют другой аккаунт.
- [ ] Tests: PASS in isolated profiles. На каждой реальной ОС DPAPI/Keychain round-trip и запуски auth self-test; не читать/печать реальные secrets. Отсутствующий доступ пользователя фиксируется отдельно.
- [ ] Commit `refactor: preserve native security and authentication in Qt`.

### Task 14: История, операции с файлами и безопасный жизненный цикл

**Files:** Create `ui/history.py`, `tests/ui/test_history_actions.py`, `tests/integration/test_shutdown_recovery.py`; modify `ui/presenter.py`, `ui/window.py`, repository/executor по их контрактам.

**Interfaces:** Produces Presenter commands `.clear_queue()`, `.clear_history()`, `.delete_files(job_ids: tuple[str,...], confirmed: bool)`, `.shutdown()->None`, `.open_result(job_id)->None`. Повторы идут через SubmissionService.repeat/Scheduler.retry, не через текст URL поля.

- [ ] Red: `test_clear_keeps_files`, `test_delete_requires_confirmation_and_containment`, `test_open_uses_resolved_post_folder`, `test_restart_does_not_autostart`, `test_close_during_network_processing_or_auth`, `test_recovery_after_file_written_before_db_commit`, `test_deleted_file_history_is_honest`.
- [ ] `python -m pytest tests/ui/test_history_actions.py tests/integration/test_shutdown_recovery.py -q`: FAIL.
- [ ] Реализовать реальную историю/папки/подтверждения и bounded shutdown: отменяемое ожидание сетевого timeout, join worker/process, транзакционное сохранение. Очистка списка и удаление файлов имеют разные команды. Незавершённые jobs после restart paused; исходные файлы не стираются.
- [ ] Tests: PASS with actual temp files/processes. Активный FFmpeg не остаётся сиротой после закрытия; teardown не вызывает Qt slots после уничтожения окна.
- [ ] Commit `feat: add history file actions and safe queue recovery`.

### Task 15: Покрытие, CI и нативные пакеты обеих ОС

**Files:** Create `scripts/{check_coverage,package_smoke}.py`, `src/clipflow/ui/self_test.py`, `packaging/windows/ClipFlow.spec`; modify `pyproject.toml`, `scripts/{check,build}.py`, `packaging/macos/ClipFlow.spec`, `.github/workflows/{check,build}.yml`, `tests/integration/test_packaging_config.py`.

**Interfaces:** Produces CLI `python scripts/check.py --qt` (new unit/integration/Qt suite), `python scripts/check_coverage.py` (threshold gate), `python scripts/build.py` (native release), `python scripts/package_smoke.py --executable PATH --data-dir TEMP` (real package/self-test/auth/embedded tools/resources). Qt bootstrap supports `--ui-self-test` in a built binary.

- [ ] Red: `test_both_specs_use_same_qt_entry_version_and_resources`, `test_no_tk_or_legacy_app_in_release`, `test_coverage_threshold_gate_fails_below_each_limit`, `test_windows_build_path_excludes_foreign_dlls`, `test_auth_flags_work_when_frozen`.
- [ ] Run these tests: FAIL against old specs; сначала зафиксировать падение новых тестов, не собирать старый продукт под новым номером.
- [ ] Перенести единственный version source в `src/clipflow/version.py`; build entry — новый `__main__.py`, данные/Qt plugins/auth resources/FFmpeg/Node/licenses включены. Сохранить Windows AppId и macOS bundle ID, исправление из 1.8.7 по DLL PATH сохранить. Native workflow matrix — Windows/macOS; test matrix продолжает работать на каждую PR/push, package workflow — manual/release candidate.
- [ ] `python scripts/check.py --qt`, `python scripts/check_coverage.py`: PASS с coverage JSON по каждому порогу. После `.venv`-free запуска собранного приложения package smoke: PASS. macOS runner, который старше minimum 27, может собирать/проверять Python, но не доказывает поддержку запуска App через Launch Services: этот шаг обязателен на имеющемся Mac 27.0.1 либо совместимом runner. Windows GUI smoke — в native session. Точный OS/CPU записать в отчёт.
- [ ] Commit `build: verify Qt coverage and native Windows macOS packages`.

### Task 16: Паритет, удаление legacy, документация и выпуск

**Files:** Modify `run.py`, `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `docs/{DEVELOPMENT,BUILDING,MIGRATION,WINDOWS-CODEX-HANDOFF,CHANGELOG}.md`, `THIRD-PARTY-NOTICES.md`; create `docs/{ARCHITECTURE,TESTING,ROADMAP}.md`, обновить реальные screenshots; удалить superseded legacy runtime/tests только после соответствующего parity test.

**Interfaces:** `python run.py` и `python -m clipflow` запускают единственный Qt UI. Documentation соответствует существующим командам/пакетам. Один стабильный release entry, не пара независимых UI.

- [ ] Составить parity assertions для всех 11 legacy regression scripts и auth flags, каждому назначить новый pytest test; `test_default_entrypoint_is_qt`, `test_no_ast_test_extraction`, `test_no_tk_import_in_supported_runtime`. Написать/увидеть FAIL до переключения default entry.
- [ ] Удалить старый UI/default path и временный `--qt-preview`; перевести полезные custom extractor fixes в package, затем убрать неиспользуемый `_internal/customtkinter`. Сохранять узнаваемый запуск через run.py и существующую Windows data migration command.
- [ ] Полный suite/coverage, обе CI ОС на точном SHA и обе нативные package checks: PASS. Запросить whole-branch review согласно выбранному способу исполнения, устранить существенные замечания до слияния.
- [ ] Выполнить живые разрешённые проверки: публичные YouTube video/playlist/Music track/Music playlist, Instagram Reel + карусель DeR11OUkobq (если доступна) + profile 10/50/all с отменой; GetCourse с доступным материалом владельца. Не делать массовую загрузку чужого большого профиля только ради smoke: metadata discovery + маленькая выбранная выборка, полный сценарий на собственном/разрешённом профиле. Если внешняя блокировка/нет сессии — явно перечислить непроверенные случаи, оставить соответствующий статус experimental; не выдавать suite mocks за network success.
- [ ] Обновить README на актуальные форматы/режимы/ограничения, реальные Qt light/dark screenshots, инструкции, архитектуру, тесты и backlog. Spec markup не использовать как screenshot готового приложения. В ROADMAP отделить shipped/experimental/future; Spotify — metadata-only idea, не прямой audio download.
- [ ] Commit final parity/docs; дождаться checks обеих ОС финального кандидата, собрать/перепроверить при изменениях runtime. Только затем PR `dev` → `main` (attach PR), merge и возврат к `dev`; при недоступном PR UI разрешено обычное безопасное слияние по текущим правилам проекта, не bypass failed checks.
- [ ] Сохранить EXE/portable/DMG/APP ZIP, SHA256SUMS и verification report с source SHA в `outputs` и Google Drive `Kas-common/ClipFlow/Releases/2.0.0` (либо подтверждённый номер). Mac обновить после проверки сохранности профиля; временные APP unregister/remove, одна установленная копия. Старые backups/Windows baseline сохранить. Выпуск на GitHub не подразумевает автоматическое обновление пользовательских приложений.

## Самопроверка плана

- Spec §§1–4: цель/approach/global constraints и T1/T3/T9/T10/T12/T15/T16.
- Spec §5: single/batch T1/T2/T11; Instagram T4/T7/T8; YouTube/Music T5; GetCourse T6.
- Spec §§6–8: UI/state T3/T10–T14; architecture T1–T9; security/migration T9/T13/T14.
- Spec §§9–11: каждый компонент имеет red/green cycle; coverage/CI/packages T15, native/live parity и docs T16.
- Review Focus 1→T1/T2, 2→T2/T11, 3→T8, 4→T4/T7, 5→T9/T13/T14. Контракты между tasks используют одни имена/типы.
- Число строк coverage не является критерием реального доступа к площадке. Критические skips, неподтверждённые native/live cases и ошибки внешних сервисов записываются отдельно.

## Исполнение и отметки

- План составлен после утверждения спецификации; 27 октября владелец выполнил review и выбрал Native: исполнитель проходит этапы сам, независимый whole-branch review в конце.
- Рекомендуется Native: один исполнитель проходит тесно связанные интерфейсы по порядку в этой сессии, затем независимый whole-branch review; это уменьшает расходы на повторную передачу большого контекста.
- Альтернатива — свежий исполнитель и reviewer на каждую task; дороже по контексту, проверки независимы на каждом этапе.
- Текущий baseline на Mac: `python scripts/check.py`, macOS 27.0.1 arm64, успешно 27 октября; лог `work/qt-migration-baseline-macos.log`. Существующие third-party ResourceWarning о file handler фиксируются как известное наблюдение, не маскируются. Это не новый тест Windows и не проверка новой Qt-версии.
- На момент составления плана T1–T16 не были начаты. После утверждения начат T1; текущий статус и команды проверок хранятся в журнале исполнения и копируются в Agents/ClipFlow.
- После T2 владелец указал останавливаться после каждого этапа. Continuous execution из executing-plans отменён этим указанием; Native и независимый финальный review сохраняются.
