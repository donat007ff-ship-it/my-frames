# HyperFrames Project Guidelines & Context

Этот файл читает Antigravity CLI (`agy`) / Gemini CLI при запуске из корня
проекта (директория, где лежит `.git`). Он задаёт границы и контракт, а не
творческие решения — за творческие решения (тайминг, цвет, композиция,
брендинг) отвечают скиллы в `motion-design-skills/skills/` (см. раздел ниже).

---

## Окружение и инфраструктура

- **Среда разработки:** Termux на Android (arm64). Здесь только редактируем
  `index.html` / `compositions/*.html` и работаем с Git через `gh`.
- **Среда рендеринга:** GitHub Actions (`ubuntu-latest`, Node.js 22, FFmpeg).
  Рендер HyperFrames всегда идёт через headless-браузер (Puppeteer/Chrome) +
  FFmpeg — это тяжёлые нативные зависимости.
- **КРИТИЧЕСКОЕ ПРАВИЛО:** никогда не запускать `npx hyperframes init`,
  `npx hyperframes render`, `npx hyperframes lint/validate/preview` или любую
  установку `hyperframes`/native-модулей локально в Termux. Пакет тянет за
  собой нативные зависимости (Puppeteer/Chrome, обработка изображений),
  у которых нет сборок под `android-arm64` — установка гарантированно упадёт.
  Весь жизненный цикл HyperFrames (init/lint/preview/render) — строго в облаке
  GitHub Actions.
- Репозиторий должен быть **публичным** — тогда минуты GitHub Actions
  безлимитны. Если сделаете приватным, упрётесь в месячный лимit минут.

---

## Контракт композиции (`index.html`)

Корневая композиция — это `<div>` прямо в `<body>` (БЕЗ обёртки `<template>` —
`<template>` используется только во вложенных саб-композициях, подключаемых
через `data-composition-src`; на корневом файле она скроет контент и сломает
рендер).

Корневой блок обязан нести **все** эти атрибуты, не только `data-duration`:

```html
<div
  id="scene"
  data-composition-id="main"
  data-start="0"
  data-width="1920"
  data-height="1080"
  data-duration="5"
>
```

Без `data-duration` (и без GSAP-таймлайна, из которого можно вывести длину)
рендер зависает на ~45 сек и падает с ошибкой вида
`[FrameCapture] window.__hf not ready after 45000ms` — по сути это и есть
«нулевая длительность», просто текст ошибки не буквально про duration.
`data-duration` всегда имеет приоритет над длиной GSAP-таймлайна — если они
разъедутся, реальной длиной слота будет `data-duration`.

### GSAP и таймлайны

Таймлайны регистрируются в `window.__timelines` как **объект, ключ — id
композиции**, а не как массив:

```html
<script src="https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js"></script>
<script>
  const tl = gsap.timeline({ paused: true });
  tl.from("#title", { opacity: 0, y: 30, duration: 1 });

  window.__timelines = window.__timelines || {};
  window.__timelines["main"] = tl; // ключ = data-composition-id этого блока
</script>
```

- Запрещены бесконечные циклы (`repeat: -1`, `animation-iteration-count: infinite`)
  — рендеру нужна детерминированная конечная точка.
- Каждый анимированный/таймированный элемент внутри сцены (клип, картинка,
  видео, саб-композиция) должен иметь `class="clip"` и свои `data-start` /
  `data-duration` / `data-track-index` — иначе линтер выдаёт предупреждение.

### Разрешение

- Горизонтальное видео: `1920x1080`.
- Вертикальное (Shorts/Reels): `1080x1920`.
- Указывается и в `data-width`/`data-height` корня, и в CSS `#scene` (ширина/
  высота должны совпадать).

---

## Скиллы motion-design (`motion-design-skills/`)

В проект распакован пак `motion-design-skills` (9 скиллов для агентов). Они
не знают синтаксиса HyperFrames (`data-*`, `window.__timelines`) — этот
контракт задан выше. Их задача — творческие и режиссёрские решения. Перед
тем как писать/переписывать анимацию в `index.html`, открой SKILL.md
подходящего скилла из `motion-design-skills/skills/<name>/SKILL.md`:

| Скилл | Когда открывать |
| --- | --- |
| `animation-principles` | Движение выглядит «дёрганым»/«роботизированным», нужно подобрать easing, длительность, 12 принципов анимации |
| `color-motion` | Палитра, градиенты, перцептивная интерполяция (OKLCH/Lab), цветокоррекция сцены |
| `shot-composition` | Сетка кадра, safe area, фокус, 2D/3D-камера, адаптация под 16:9 / 9:16 |
| `motion-art-direction` | Общий язык движения, темп, иерархия, что анимировать и что — нет |
| `beat-sync-editing` | Сцена синхронизируется с музыкой/битом, спид-рампы, монтажный ритм |
| `logo-animation` | Реveal логотипа, стингер, сплэш-экран, лоадер |
| `motion-background` | Меш-градиенты, шейдерный/частичный фон сцены |
| `after-effects` | Только если часть пайплайна реально идёт через After Effects, а не напрямую в HyperFrames |
| `remotion-video` | Только для портирования готовой Remotion/React-композиции в HyperFrames-HTML — это другой движок, не сам HyperFrames |

Технические скрипты из `motion-design-skills/scripts/` (verify-loop):
`seek-shot.sh` и `contact-sheet.sh` требуют Playwright Chromium — тоже не
запускать в Termux, только в CI или на десктопе. А вот `probe-mp4.sh`
использует только `ffprobe`, который в Termux ставится нормально
(`pkg install ffmpeg`, это обычный бинарник, а не Node-модуль) — им можно
проверять уже скачанный на телефон MP4:

```bash
pkg install ffmpeg -y
motion-design-skills/scripts/probe-mp4.sh ~/storage/downloads/ahyperframes/*.mp4 1920x1080 30
```

---

## Команды пайплайна

**1. Отправка изменений на рендер и озвучку**
```bash
git add index.html voiceover.json && git commit -m "Update video scene & voiceover" && git push
```

**2. Мониторинг сборки**
```bash
gh run watch
```
Если недавних ранов несколько, `gh` спросит, какой смотреть/качать. Чтобы
всегда брать именно последний ран рендер-воркфлоу без интерактивного выбора
(удобно для скриптов):
```bash
gh run download \
  "$(gh run list --workflow=render.yml --limit 1 --json databaseId --jq '.[0].databaseId')" \
  -n rendered-video -D ~/storage/downloads/ahyperframes/
```

**3. Скачивание готового озвученного MP4 на телефон**
```bash
gh run download -n rendered-video -D ~/storage/downloads/ahyperframes/
```
Флаг `-D` (заглавный) — обязателен, задаёт каталог назначения.
Скачанный MP4 уже сведён с дикторским голосом!

---

## `.github/workflows/render.yml`

Пайплайн в GitHub Actions полностью автоматизирован:
1. Запускает рендер кадров HyperFrames (`npx hyperframes render`).
2. Запускает `scripts/generate_voiceover.py` с секретом `GEMINI_API_KEY`.
3. Читает `voiceover.json`, генерирует озвучку сегментов через **Gemini 3.8 Flash TTS**.
4. Через FFmpeg (`adelay` + `amix`) собирает мастер-аудиодорожку и сводит с видео (`-c:v copy -c:a aac`).
5. Загружает финальный MP4 в артефакт `rendered-video`.

---

## Озвучка и голос (Gemini Flash TTS в GitHub Actions)

- **СТРОЖАЙШЕЕ ПРАВИЛО:** Для генерации закадрового голоса и озвучки видео ВСЕГДА использовать именно **Gemini 3.8 Flash TTS** (`models/gemini-3.8-flash-tts`).
- **Конфигурация реплик:** Все реплики диктора, таймкоды (`start_sec`) и голоса хранятся в [`voiceover.json`](file:///data/data/com.termux/files/home/storage/downloads/ahyperframes/voiceover.json).
- **Скрипт генератора:** [`scripts/generate_voiceover.py`](file:///data/data/com.termux/files/home/storage/downloads/ahyperframes/scripts/generate_voiceover.py) выполняется в CI/CD на GitHub Actions.
- **Тембр по умолчанию:** `Charon` (глубокий, авторитетный документальный голос Vox) или `Fenrir` (энергичный).
- **Синхронизация:** Озвучка генерируется по актам/сегментам сценария с точной временной привязкой по миллисекундам (`adelay` в FFmpeg), исключая наплывы звука на чужие сцены.
- **Сведение:** Сведение дорожки с видео выполняется в облаке GitHub Actions без перекодирования видеопотока (`-c:v copy -c:a aac -b:a 192k -shortest`). На телефон через `gh run download` скачивается уже готовый ролик с диктором.
- **Секрет:** `GEMINI_API_KEY` настроен в GitHub Secrets репозитория и автоматически передаётся в workflow.

