
import torch
import os
import shutil

# 找到 torch 安装目录
torch_path = os.path.dirname(torch.__file__)
base_path = os.path.dirname(torch_path)
package_name = os.path.basename(torch_path)

print(f'Found torch at: {torch_path}')
print(f'Base path: {base_path}')

# 创建 tar 包
shutil.make_archive('torch_backup', 'gztar', root_dir=base_path, base_dir='torch')
print('Created torch_backup.tar.gz')
