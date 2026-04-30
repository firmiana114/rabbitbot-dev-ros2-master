
# test_cuda_torch.py
import torch

print("CUDA available :", torch.cuda.is_available())
print("Current device :", torch.cuda.current_device())
print("Device name    :", torch.cuda.get_device_name())
print("Device count   :", torch.cuda.device_count())
print("Arch list      :", torch.cuda.get_arch_list())

# 真正跑一点计算
a = torch.randn(1000, 1000, device="cuda")
b = torch.randn(1000, 1000, device="cuda")
c = torch.mm(a, b)          # 矩阵乘法
print("GEMM 结果前 5×5:\n", c[:5, :5])
