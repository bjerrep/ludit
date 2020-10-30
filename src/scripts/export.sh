
KeyFile=/tmp/exclude.rsync
(
cat <<'ADD'
pycache
.git
doc
venv
__pycache__
.idea
*.cfg
ludit_local.js
ADD
) > $KeyFile


DIR="$(dirname $(readlink -f $0))"

source $DIR/remote_server_and_clients.txt

rsync --exclude-from=/tmp/exclude.rsync -av -e ssh .. $SERVER

for s in $CLIENTS; do
    rsync --exclude-from=/tmp/exclude.rsync -av -e ssh .. $s
done
