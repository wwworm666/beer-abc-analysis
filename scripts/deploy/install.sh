#!/usr/bin/env bash
# One-time installation, run in the existing authenticated root SSH session.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run this installer as root.' >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for tool in docker git runuser curl flock timeout ssh-keygen; do
    command -v "$tool" >/dev/null || { echo "Missing command: $tool" >&2; exit 1; }
done
docker compose version >/dev/null
[[ -f /opt/beer/.env ]] || { echo 'Missing /opt/beer/.env' >&2; exit 1; }
[[ $(runuser -u deploy -- git -C /opt/beer symbolic-ref --short HEAD) == main ]]

install -d -m 700 /var/lib/beer-deploy /root/.ssh
install -o root -g root -m 755 "$script_dir/beer-deploy.sh" /usr/local/sbin/beer-deploy
key_file=/root/.ssh/beer_github_actions
if [[ ! -f "$key_file" ]]; then
    ssh-keygen -q -t ed25519 -N '' -C beer-github-actions -f "$key_file"
fi
chmod 600 "$key_file"
public_key=$(ssh-keygen -y -f "$key_file")
authorized=/root/.ssh/authorized_keys
touch "$authorized"
chmod 600 "$authorized"
key_line="restrict,command=\"/usr/local/sbin/beer-deploy\" $public_key beer-github-actions"
if ! grep -Fxq "$key_line" "$authorized"; then
    if grep -Fq "$public_key" "$authorized"; then
        echo 'This key already exists with different options. Inspect authorized_keys manually.' >&2
        exit 1
    fi
    printf '%s\n' "$key_line" >> "$authorized"
fi

# Get the host key from the authenticated server, never via an unverified scan.
[[ -f /etc/ssh/ssh_host_ed25519_key.pub ]]
read -r key_type key_value _ < /etc/ssh/ssh_host_ed25519_key.pub
printf '139.100.200.92 %s %s\n' "$key_type" "$key_value" > /var/lib/beer-deploy/known_hosts
printf '%s\n' \
    'Installed. Existing application containers were not restarted.' \
    'Add two repository secrets in GitHub Settings > Secrets and variables > Actions:' \
    'BEER_DEPLOY_SSH_KEY: contents of /root/.ssh/beer_github_actions' \
    'BEER_DEPLOY_KNOWN_HOSTS: contents of /var/lib/beer-deploy/known_hosts' \
    'Copy the private key directly to GitHub, never to a chat or repository.' \
    'Then run Actions > Deploy production > Run workflow (branch main).'
