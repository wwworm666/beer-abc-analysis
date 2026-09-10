#!/usr/bin/env bash
# Installed root-owned at /usr/local/sbin/beer-deploy. SSH key is forced here.
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077

readonly REPO=/opt/beer
readonly STATE=/var/lib/beer-deploy
readonly LOCK=/run/lock/beer-deploy.lock
readonly IMAGE=beer-abc-analysis:latest
readonly PREVIOUS_IMAGE=beer-abc-analysis:previous

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
git_repo() { runuser -u deploy -- git -C "$REPO" "$@"; }
compose() { docker compose --project-directory "$REPO" -f "$REPO/docker-compose.yml" "$@"; }

[[ $EUID -eq 0 ]] || die 'Run as root (the dedicated SSH key only permits this script).'
if [[ $# -eq 0 ]]; then
    command_text=${SSH_ORIGINAL_COMMAND:-}
elif [[ $# -eq 2 ]]; then
    command_text="$1 $2"
else
    die 'Expected: deploy <40-character commit SHA>'
fi
[[ "$command_text" =~ ^deploy\ ([0-9a-f]{40})$ ]] || die 'Only deploy <40-character commit SHA> is permitted.'
readonly TARGET=${BASH_REMATCH[1]}

mkdir -p "$STATE"
exec 9>"$LOCK"
flock -n 9 || die 'Another deployment is already running.'
[[ $(git_repo symbolic-ref --short HEAD) == main ]] || die 'Server checkout must be on main.'
[[ -z $(git_repo status --porcelain) ]] || die 'Server checkout has local changes; inspect git status before retrying.'
[[ -f "$REPO/.env" ]] || die 'Server .env is missing.'

git_repo fetch --no-tags origin main
remote_sha=$(git_repo rev-parse FETCH_HEAD)
[[ "$remote_sha" == "$TARGET" ]] || die 'This run is outdated: main has moved. Run the latest workflow.'
before_sha=$(git_repo rev-parse HEAD)
git_repo merge-base --is-ancestor "$before_sha" "$TARGET" || die 'Update is not a fast-forward.'

old_image=$(docker inspect --format '{{.Image}}' beer-app)
# Compare against the running image when it has a release label; the first
# installation predates labels and falls back to the server checkout.
running_sha=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$old_image")
if [[ ! "$running_sha" =~ ^[0-9a-f]{40}$ ]]; then running_sha=$before_sha; fi
changed_data=$(git_repo diff --name-only "$running_sha" "$TARGET" -- data/)
[[ -z "$changed_data" ]] || die 'Release changes data/. Mounted production data needs a separate manual update; see docs/guides/deploy.md.'

release_dir=$(mktemp -d "$STATE/release-${TARGET:0:12}.XXXXXX")
printf '%s\n' "$before_sha" > "$release_dir/source-before.txt"
printf '%s\n' "$old_image" > "$release_dir/image-before.txt"
printf '%s\n' "$TARGET" > "$release_dir/target.txt"
# After a failed release, HEAD may be newer than the image still serving users.
# Always restore the Compose configuration that belongs to that running image.
git_repo show "$running_sha:docker-compose.yml" > "$release_dir/compose-before.yml"
docker image tag "$old_image" "$PREVIOUS_IMAGE"
switching=0

healthy() {
    local expected=$1 current state local_code tls_code attempt streak=0
    # Require several successful responses from the intended container.
    for ((attempt=0; attempt<30; attempt++)); do
        current=$(docker inspect --format '{{.Image}}' beer-app 2>/dev/null) || current=''
        state=$(docker inspect --format '{{.State.Running}} {{.State.Restarting}}' beer-app 2>/dev/null) || state=''
        local_code=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:10000/login 2>/dev/null) || local_code=''
        tls_code=$(curl -sS --max-time 5 --resolve beerkultura.ru:443:127.0.0.1 -o /dev/null -w '%{http_code}' https://beerkultura.ru/login 2>/dev/null) || tls_code=''
        if [[ "$current" == "$expected" && "$state" == 'true false' && "$local_code" == 200 && "$tls_code" == 200 ]]; then
            streak=$((streak + 1))
            if [[ $streak -ge 3 ]]; then return 0; fi
        else
            streak=0
        fi
        sleep 2
    done
    return 1
}

on_failure() {
    local status=$1 rollback_status=0
    trap - EXIT INT TERM HUP
    set +e
    # Application logs may contain business data; retain them only on the VPS.
    docker logs --tail=100 beer-app > "$release_dir/app-failure.log" 2>&1
    printf 'Deployment failed. Server diagnostics: %s\n' "$release_dir" >&2
    docker image tag "$old_image" "$IMAGE" || rollback_status=1
    if [[ $switching -eq 1 && $rollback_status -eq 0 ]]; then
        docker compose --project-directory "$REPO" -f "$release_dir/compose-before.yml" \
            up -d --no-build --no-deps --force-recreate app || rollback_status=1
        if [[ $rollback_status -eq 0 ]]; then
            healthy "$old_image" || rollback_status=1
        fi
        if [[ $rollback_status -eq 0 ]]; then
            printf 'Previous application image restored and responding. Release was NOT deployed.\n' >&2
        else
            printf 'ERROR: rollback did not restore a healthy application; inspect the VPS immediately.\n' >&2
        fi
    elif [[ $switching -eq 0 ]]; then
        printf 'Application container was not replaced.\n' >&2
    fi
    # Keep main fast-forwarded; never reset work or change mounted data.
    exit "$status"
}
# EXIT also catches explicit validation failures (exit in die), not only ERR.
trap 'status=$?; if [[ $status -ne 0 ]]; then on_failure "$status"; fi' EXIT
trap 'on_failure 130' INT
trap 'on_failure 143' TERM
trap 'on_failure 129' HUP

git_repo merge --ff-only "$TARGET"
printf 'Building tested commit %s; current container stays running.\n' "$TARGET"
timeout 1200 docker compose --project-directory "$REPO" -f "$REPO/docker-compose.yml" \
    build --build-arg "BEER_COMMIT=$TARGET" app
new_image=$(docker image inspect --format '{{.Id}}' "$IMAGE")
new_revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$new_image")
[[ "$new_revision" == "$TARGET" ]] || die 'Built image does not have the requested commit label.'
docker image tag "$new_image" "beer-abc-analysis:release-$TARGET"

switching=1
compose up -d --no-build --no-deps app
healthy "$new_image"
printf '%s\n' "$TARGET" > "$STATE/deployed-revision.tmp"
mv "$STATE/deployed-revision.tmp" "$STATE/deployed-revision"
printf '%s\n' "$release_dir" > "$STATE/last-release"
trap - EXIT INT TERM HUP
printf 'DEPLOYED %s: container image verified; application and HTTPS return 200.\n' "$TARGET"
