# Load .env without overriding variables already set in the environment.
# Portable to macOS's bash 3.2. Values are taken literally (no quotes/expansion).
if [ -f .env ]; then
  while IFS='=' read -r key value || [ -n "$key" ]; do
    case "$key" in ''|\#*) continue ;; esac
    case "$key" in *[!A-Za-z0-9_]*) continue ;; esac
    printenv "$key" >/dev/null || export "$key=$value"
  done < .env
fi
