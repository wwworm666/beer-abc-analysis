#!/usr/bin/env bash
# Самообновление сервера бота @MCPkulturabot (Амстердам). Ставит install.sh как
# /usr/local/sbin/kultura-bot-update; запускает kultura-bot-update.timer раз в 2 минуты.
#
# Сверяет ветку main на GitHub с выложенной версией (/opt/kultura-bot/deployed):
# - то же — ничего не делает;
# - в kultura_bot/ ничего не менялось — только запоминает новую версию;
# - менялось — обновляет код (только папку kultura_bot/), зависимости, свои службы и
#   этот скрипт и перезапускает бота. Начатые ответы бот доводит до конца (до 90 с),
#   ждавшие очереди получают «повторите вопрос».
# Версия запоминается только после успешного перезапуска: сбой посередине — повтор через
# 2 минуты.
set -euo pipefail

PREFIX=/opt/kultura-bot
REPO="$PREFIX/repo"
BRANCH="${KULTURA_REPO_BRANCH:-main}"
MARK="$PREFIX/deployed"
UV=/usr/local/bin/uv
export UV_PYTHON_INSTALL_DIR="$PREFIX/python"

git -C "$REPO" fetch --quiet --depth 1 origin "$BRANCH"
new=$(git -C "$REPO" rev-parse FETCH_HEAD)
deployed=$(cat "$MARK" 2>/dev/null || true)
[ "$new" = "$deployed" ] && exit 0

head=$(git -C "$REPO" rev-parse HEAD)
if [ -n "$deployed" ] && [ "$head" = "$deployed" ]; then
  changed=$(git -C "$REPO" diff --name-only --no-renames "$head" "$new" -- kultura_bot)
else
  changed="(неизвестно, что выложено — обновляю всё)"
fi
git -C "$REPO" reset --quiet --hard FETCH_HEAD

if [ -z "$changed" ]; then
  echo "kultura-bot: main $new — в kultura_bot/ изменений нет"
  echo "$new" > "$MARK"
  exit 0
fi

echo "kultura-bot: обновление ${deployed:-?} -> $new"
"$UV" pip install --quiet --python "$PREFIX/venv/bin/python" -r "$REPO/kultura_bot/deploy/requirements.txt"
install -m 755 "$REPO/kultura_bot/deploy/update.sh" /usr/local/sbin/kultura-bot-update
for unit in kultura-bot.service kultura-bot-update.service kultura-bot-update.timer; do
  install -m 644 "$REPO/kultura_bot/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl restart kultura-bot.service
echo "$new" > "$MARK"
echo "kultura-bot: выложено $new"
