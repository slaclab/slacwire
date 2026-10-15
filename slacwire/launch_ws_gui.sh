#!/bin/bash
source $PACKAGE_TOP/anaconda/envs/rhel7_devel/bin/activate

# Pre-select beampath/area/wire/detector by appending CLI arguments:
#   pydm ws_gui.py --beampath SC_HXR --area COL1 --wire WSC106 --detector PMT29150
pydm /usr/local/lcls/tools/python/hla/slacwire/slacwire/ws_gui.py "$@" &
