#!/bin/bash
cd ~/kabanaty/sandbox
source dev_env.sh
pydm slacwire/slacwire/ws_gui.py "$@"
