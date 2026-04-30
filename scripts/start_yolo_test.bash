#!/bin/bash

source py310/bin/activate

export PYTHONPATH=$(pwd):${PYTHONPATH}

python tests/view/test_yolo.py
