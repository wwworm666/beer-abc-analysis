#!/usr/bin/env bash
# Установка сервера бота @MCPkulturabot (Амстердам) — один раз, под root.
#
# Команду с ключом выдаёт страница «Доступ агентов» (https://beerkultura.ru/admin/mcp,
# раздел «Бот», «Команда установки»):
#
#   curl -fsSL https://raw.githubusercontent.com/wwworm666/beer-abc-analysis/main/kultura_bot/deploy/install.sh \
#     | KULTURA_BOT_KEY='kmcp_…' bash
#
# Что делает (docs/kultura-bot.md, «Установка»):
#   1. git и curl — если их нет (apt / dnf / yum);
#   2. uv — ставит Python для бота (>= 3.10), не трогая системный;
#   3. системный пользователь kultura-bot — от него работает бот;
#   4. /opt/kultura-bot/repo — папка kultura_bot/ из GitHub (ветка main; частичный клон:
#      других папок репозитория нет, файлы корня git кладёт всегда — бот их не использует);
#   5. /opt/kultura-bot/venv — Python и зависимости (kultura_bot/deploy/requirements.txt);
#   6. /etc/kultura-bot.env — ключ сервера бота и адрес сайта (читает только root);
#   7. службы systemd: kultura-bot (бот) и kultura-bot-update.timer (раз в 2 минуты
#      сверяется с GitHub и обновляется сам — update.sh).
# Повторный запуск безопасен: обновит ключ и код и перезапустит бота.
set -euo pipefail

REPO_URL="${KULTURA_REPO_URL:-https://github.com/wwworm666/beer-abc-analysis.git}"
BRANCH="${KULTURA_REPO_BRANCH:-main}"
SITE_URL="${KULTURA_SITE_URL:-https://beerkultura.ru}"
PREFIX=/opt/kultura-bot
ENV_FILE=/etc/kultura-bot.env
MARK="$PREFIX/deployed"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nОшибка: %s\n' "$*" >&2; exit 1; }

# Всё — внутри main: bash дочитывает скрипт целиком до запуска, и команда, читающая
# stdin, не съест остаток скрипта при «curl … | bash».
main() {
  [ "$(id -u)" -eq 0 ] || die "запустите под root (ssh root@сервер)"
  KEY="${KULTURA_BOT_KEY:-}"
  [[ "$KEY" =~ ^kmcp_[A-Za-z0-9_-]{20,}$ ]] || die "нет ключа сервера бота: скопируйте команду целиком со страницы «Доступ агентов» (кнопка «Команда установки»)"
  command -v systemctl >/dev/null 2>&1 || die "нужен systemd"

  say "Пакеты git и curl"
  if ! command -v git >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git curl ca-certificates
    elif command -v dnf >/dev/null 2>&1; then
      dnf install -y -q git curl ca-certificates
    elif command -v yum >/dev/null 2>&1; then
      yum install -y -q git curl ca-certificates
    else
      die "установите git и curl и запустите команду ещё раз"
    fi
  fi

  say "uv — Python для бота"
  if [ ! -x /usr/local/bin/uv ]; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
  fi
  UV=/usr/local/bin/uv
  export UV_PYTHON_INSTALL_DIR="$PREFIX/python"     # скачанный Python — в /opt, его видит пользователь бота

  say "Пользователь kultura-bot"
  if ! id -u kultura-bot >/dev/null 2>&1; then
    useradd --system --no-create-home --home-dir /var/lib/kultura-bot --shell /usr/sbin/nologin kultura-bot
  fi

  say "Код бота: $REPO_URL ($BRANCH), папка kultura_bot/"
  mkdir -p "$PREFIX"
  if [ -d "$PREFIX/repo/.git" ]; then
    git -C "$PREFIX/repo" fetch --quiet --depth 1 origin "$BRANCH"
    git -C "$PREFIX/repo" reset --quiet --hard FETCH_HEAD
  else
    rm -rf "$PREFIX/repo"
    git clone --quiet --depth 1 --branch "$BRANCH" --filter=blob:none --sparse "$REPO_URL" "$PREFIX/repo"
    git -C "$PREFIX/repo" sparse-checkout set kultura_bot
  fi

  say "Python и зависимости"
  "$UV" venv --quiet --allow-existing --python '>=3.10' "$PREFIX/venv"
  "$UV" pip install --quiet --python "$PREFIX/venv/bin/python" -r "$PREFIX/repo/kultura_bot/deploy/requirements.txt"

  say "Ключ сервера бота — $ENV_FILE (читает только root)"
  (
    umask 077
    printf 'KULTURA_BOT_KEY=%s\nKULTURA_SITE_URL=%s\n' "$KEY" "$SITE_URL" > "$ENV_FILE"
  )
  chmod 600 "$ENV_FILE"

  say "Службы systemd"
  install -m 755 "$PREFIX/repo/kultura_bot/deploy/update.sh" /usr/local/sbin/kultura-bot-update
  for unit in kultura-bot.service kultura-bot-update.service kultura-bot-update.timer; do
    install -m 644 "$PREFIX/repo/kultura_bot/deploy/$unit" "/etc/systemd/system/$unit"
  done
  systemctl daemon-reload
  systemctl enable --quiet kultura-bot.service
  systemctl enable --quiet --now kultura-bot-update.timer
  systemctl restart kultura-bot.service
  git -C "$PREFIX/repo" rev-parse HEAD > "$MARK"

  say "Проверка"
  sleep 8
  if systemctl is-active --quiet kultura-bot.service; then
    echo "Бот запущен."
  else
    echo "Бот не запустился — журнал ниже:"
  fi
  journalctl -u kultura-bot -n 15 --no-pager || true
  echo
  echo "Состояние бота — на странице $SITE_URL/admin/mcp, раздел «Бот @MCPkulturabot»."
  echo "Журнал: journalctl -u kultura-bot -f"
}

main "$@"
