#!/usr/bin/env bash
# Запускать на сервере от root: подтягивает последний коммит, обновляет зависимости
# (включая yt-dlp, его нужно обновлять регулярно) и перезапускает бота.
set -euo pipefail

cd /opt/transcribe-it
git pull --ff-only
.venv/bin/pip install --quiet --upgrade -r requirements.txt
systemctl restart transcribe-it
systemctl --no-pager status transcribe-it
