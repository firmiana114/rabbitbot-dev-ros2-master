#!/bin/bash

CUR_DIR=$(pwd)

SRC_PKG_DIR=/opt/venv/lib/python3.12/site-packages

DST_PKG_DIR=/datanvme/fuchengjia/projects/rabbitbot-dev-ros2/py310/lib/python3.10/site-packages

cd $DST_PKG_DIR

tar -xzf ${CUR_DIR}/torch_backup.tar.gz
tar -xzf ${CUR_DIR}/torchvision_backup.tar.gz
