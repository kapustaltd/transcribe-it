# transcribe-it

Telegram-бот: присылает расшифровку видео по субтитрам в `.md` или `.txt`.

Пришлите ссылку на видео → бот покажет, на каких языках есть субтитры → выберите язык → выберите формат → получите файл.

Всё делается локально, без внешних LLM. Субтитры достаёт [yt-dlp](https://github.com/yt-dlp/yt-dlp) как Python-библиотеку. Ручные субтитры идут первыми, автоматические помечены «· авто». Для YouTube автосубтитры берутся только на языке оригинала видео, без десятков машинных переводов.

## Что в документе

- заголовок (название видео) и ссылка на видео;
- абзацы с таймкодом в начале. Абзац начинается после паузы в субтитрах или через 45 секунд.

Служебных строк (канал, язык, длительность) и заголовков разделов в файле нет.

Формат выбирается после языка:

- **Markdown (`.md`)** — абзацы с таймкодами в жирном;
- **Текст (`.txt`)** — абзацы с таймкодом в квадратных скобках, без жирного шрифта и экранирования.

Спикеров бот не определяет: субтитры не содержат разметки голосов. Поэтому реплики идут абзацами без имён.

## Локальный запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # впишите BOT_TOKEN от @BotFather
set -a; . ./.env; set +a
.venv/bin/python main.py
```

Для YouTube yt-dlp использует JS-рантайм (`node` или `deno`) — установите один из них.

Один токен можно опрашивать только в одном месте: не запускайте бота локально, пока он работает на сервере.

## Тесты

```bash
.venv/bin/python -m unittest
```

## Деплой

Бот работает на сервере в режиме long polling: входящих портов не нужно.

Один раз на сервере (от root):

```bash
useradd --system --create-home --home-dir /var/lib/transcribe-it --shell /usr/sbin/nologin transcribe-it
git clone https://github.com/kapustaltd/transcribe-it.git /opt/transcribe-it
cd /opt/transcribe-it
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# токен кладётся только на сервер, в git его нет
printf 'BOT_TOKEN=%s\n' '<токен бота>' > .env
chown root:transcribe-it .env && chmod 640 .env

cp deploy/transcribe-it.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now transcribe-it
```

Обновление после пуша в репозиторий:

```bash
/opt/transcribe-it/deploy/update.sh
```

Логи: `journalctl -u transcribe-it -f`.

Если YouTube начал отдавать ошибки, в первую очередь обновите yt-dlp — `update.sh` делает это при каждом запуске.

## Структура

- `main.py` — Telegram-бот (aiogram): обработчики команд, ссылок и выбора языка.
- `subtitles.py` — yt-dlp: треки, главы, скачивание субтитров и разбор VTT/SRT в реплики с таймкодами.
- `transcript.py` — сборка документа: разделы, абзацы, рендер Markdown.
- `premium_emoji.py` — премиум-эмодзи из пака «Unigram - @SOUICdsgn». У пользователей без Premium вместо них показываются обычные символы.
- `tests/` — юнит-тесты разбора субтитров, глав, абзацев и рендера Markdown.
- `deploy/` — systemd-юнит и скрипт обновления.
