
import torchvision
import os
import shutil
torchvision_path = os.path.dirname(torchvision.__file__)
base_path = os.path.dirname(torchvision_path)
shutil.make_archive('torchvision_backup', 'gztar', root_dir=base_path, base_dir='torchvision')
print('Created torchvision_backup.tar.gz')
