#!/bin/bash

CUR_DIR=$(pwd)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "${SCRIPT_DIR}/path_env.sh"

SRC_PKG_DIR=/opt/venv/lib/python3.12/site-packages

DST_PKG_DIR="${RABBITBOT_REPO_DIR}/py310/lib/python3.10/site-packages"

cd $DST_PKG_DIR

tar -xzf ${CUR_DIR}/torch_backup.tar.gz
tar -xzf ${CUR_DIR}/torchvision_backup.tar.gz
