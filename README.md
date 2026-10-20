# transcribe-it

Telegram-бот, который присылает субтитры к видео текстовым файлом.

Пришлите ссылку на видео → бот покажет, на каких языках есть субтитры → выберите язык → получите расшифровку в `.docx`.

Субтитры достаются через [yt-dlp](https://github.com/yt-dlp/yt-dlp) как Python-библиотеку. Ручные субтитры идут первыми, автоматические помечены «· авто». Для YouTube автосубтитры берутся только на языке оригинала видео, без десятков машинных переводов.

Сырой текст субтитров модель Claude превращает в структурированную стенограмму, по образцу документа:

- заголовок и краткое описание, участники и формат;
- разделы «Часть N. …» по смене темы;
- реплики с именем спикера в жирном шрифте.

Спикеров модель определяет по контексту текста, это не диаризация звука. Поэтому имена могут быть угаданы неточно, а для монолога подпись спикера не ставится.

## Локальный запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # впишите BOT_TOKEN и ANTHROPIC_API_KEY
set -a; . ./.env; set +a
.venv/bin/python main.py
```

Для YouTube yt-dlp использует JS-рантайм (`node` или `deno`) — установите один из них.

Структурирование идёт через Claude API, по умолчанию с моделью `claude-opus-5-5`. Другую модель можно задать переменной `TRANSCRIPT_MODEL`.

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
printf 'BOT_TOKEN=%s\nANTHROPIC_API_KEY=%s\n' '<токен бота>' '<ключ Anthropic>' > .env
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
- `subtitles.py` — yt-dlp: список треков, скачивание субтитров, превращение VTT/SRT в текст.
- `transcript.py` — структурирование через Claude (длинный текст режется на фрагменты, участники передаются между ними) и рендер `.docx`.
- `premium_emoji.py` — премиум-эмодзи из пака «Unigram - @SOUICdsgn». У пользователей без Premium вместо них показываются обычные символы.
- `tests/` — юнит-тесты разбора субтитров, выбора треков, фрагментов и рендера `.docx`.
- `deploy/` — systemd-юнит и скрипт обновления.
