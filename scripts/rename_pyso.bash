#!/bin/bash

# 用法：./rename_so.sh [目录路径]
# 如果不传参数，则默认为当前目录。

DIR="${1:-.}"

# 查找所有 *.so 文件，名字里带 -38-
find "$DIR" -type f -name '*-38-*.so' | while read -r src; do
    # 生成目标文件名：把 -38- 换成 -310-
    dst="${src//-38-/-310-}"
    echo "Copying:"
    echo "  $src"
    echo "  → $dst"
    cp "$src" "$dst"
done
