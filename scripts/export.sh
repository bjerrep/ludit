#!/bin/bash

# A quick way to update the ludit server and clients directly via rsync (and not though git).
# All remotes will just get a full rsync of all ludit python files.

if [ ! -d "src" ] 
then
    echo "this script should be run from project root, now terminating" 
    exit 1
fi

source ./scripts/remote_server_and_clients.txt

USER=${SERVER%@*}

echo
echo "********* Updating server ${SERVER} *************"
echo

rsync --include "*/" --include="*.py" --exclude="*" --prune-empty-dirs -zarv -e ssh src ${SERVER}:/home/${USER}/ludit


for client in $CLIENTS; do
    echo
    echo "********* Updating client ${client} *************"
    echo
    USER=${client%@*}
    rsync --include "*/" --include="*.py" --exclude="*" --prune-empty-dirs -zarv -e ssh src ${client}:/home/${USER}/ludit
done
