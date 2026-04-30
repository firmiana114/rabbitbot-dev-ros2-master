#!/usr/bin/env python3
"""
行人包与衣服颜色区分增强工具
通过边缘检测、颜色空间转换和局部对比度增强来提高相似颜色的区分度
"""

import cv2
import numpy as np
from pathlib import Path


def enhance_bag_separation(image_path, output_path=None,
                          edge_strength=1.5,
                          color_boost=1.3,
                          contrast_clip=3.0):
    """
    增强图像中包与衣服的颜色区分度

    参数:
        image_path: 输入PNG图像路径
        output_path: 输出路径(可选)
        edge_strength: 边缘增强强度(默认1.5)
        color_boost: 颜色饱和度提升(默认1.3)
        contrast_clip: CLAHE对比度限制(默认3.0)
    """

    # 读取图像(保留Alpha通道)
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"无法读取图像: {image_path}")

    # 分离Alpha通道(如果有)
    if img.shape[2] == 4:
        bgr = img[:, :, :3]
        alpha = img[:, :, 3]
    else:
        bgr = img
        alpha = None

    # 1. 转换到LAB颜色空间(更符合人眼感知)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # 2. 对L通道应用CLAHE(自适应直方图均衡)增强局部对比度
    clahe = cv2.createCLAHE(clipLimit=contrast_clip, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l)

    # 3. 合并回LAB并转回BGR
    lab_enhanced = cv2.merge([l_enhanced, a, b])
    bgr_enhanced = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    # 4. 使用双边滤波保留边缘的同时平滑颜色
    # 这有助于分离相似颜色的区域
    smooth = cv2.bilateralFilter(bgr_enhanced, 9, 75, 75)

    # 5. 边缘检测和增强
    # 转换到灰度进行边缘检测
    gray = cv2.cvtColor(smooth, cv2.COLOR_BGR2GRAY)

    # 使用Scharr算子获得更好的边缘响应
    scharr_x = cv2.Scharr(gray, cv2.CV_64F, 1, 0)
    scharr_y = cv2.Scharr(gray, cv2.CV_64F, 0, 1)
    edges = cv2.magnitude(scharr_x, scharr_y)

    # 归一化边缘图
    edges = cv2.normalize(edges, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    # 6. 创建边缘掩码，在边缘处增强对比度
    _, edge_mask = cv2.threshold(edges, 30, 255, cv2.THRESH_BINARY)
    edge_mask = cv2.dilate(edge_mask, np.ones((3, 3), np.uint8), iterations=1)
    edge_mask = edge_mask.astype(np.float32) / 255.0

    # 7. 高频增强(类似锐化但更好)
    # 使用拉普拉斯算子提取高频细节
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    laplacian = np.abs(laplacian)
    laplacian = cv2.normalize(laplacian, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

    # 将拉普拉斯细节添加到原图
    laplacian_colored = cv2.cvtColor(laplacian, cv2.COLOR_GRAY2BGR)
    sharpened = cv2.addWeighted(bgr_enhanced, 1.0, laplacian_colored, edge_strength * 0.01, 0)

    # 8. 颜色饱和度调整(HSV空间)
    hsv = cv2.cvtColor(sharpened, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * color_boost, 0, 255)
    hsv = hsv.astype(np.uint8)
    color_enhanced = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    # 9. 在边缘区域应用额外的对比度增强
    edge_mask_3ch = np.stack([edge_mask] * 3, axis=-1)
    result = color_enhanced * (1 + edge_mask_3ch * 0.2) + sharpened * (1 - edge_mask_3ch * 0.2)
    result = np.clip(result, 0, 255).astype(np.uint8)

    # 10. 可选：添加轻微的去雾效果(暗通道先验的简化版)来增强深度感
    # 这有助于区分前景(包)和背景(衣服)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    dark_channel = cv2.erode(np.min(result, axis=2), kernel)
    atmospheric = cv2.dilate(dark_channel, kernel)
    atmospheric = np.stack([atmospheric] * 3, axis=-1).astype(np.float32) / 255.0

    # 根据亮度轻微调整色调
    result_float = result.astype(np.float32)
    dehazed = result_float / (1 - atmospheric * 0.1 + 1e-6)
    result = np.clip(dehazed, 0, 255).astype(np.uint8)

    # 合并Alpha通道(如果存在)
    if alpha is not None:
        result = cv2.cvtColor(result, cv2.COLOR_BGR2BGRA)
        result[:, :, 3] = alpha

    # 保存结果
    if output_path is None:
        input_path = Path(image_path)
        output_path = input_path.parent / f"{input_path.stem}_enhanced{input_path.suffix}"

    cv2.imwrite(str(output_path), result)
    print(f"已保存增强图像: {output_path}")

    return result


def advanced_edge_sharpen(image_path, output_path=None):
    """
    更激进的边缘锐化方案，专门用于区分相似颜色物体
    使用高频提升滤波
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"无法读取图像: {image_path}")

    # 处理Alpha通道
    has_alpha = img.shape[2] == 4
    if has_alpha:
        bgr = img[:, :, :3]
        alpha = img[:, :, 3]
    else:
        bgr = img

    # 高频提升滤波核
    # 中心权重高，周围负权重，增强边缘对比
    kernel = np.array([
        [-1, -1, -1],
        [-1,  9, -1],
        [-1, -1, -1]
    ], dtype=np.float32)

    # 应用滤波
    sharpened = cv2.filter2D(bgr, -1, kernel)

    # 限制范围
    sharpened = np.clip(sharpened, 0, 255).astype(np.uint8)

    # 在YUV空间增强色度通道
    yuv = cv2.cvtColor(sharpened, cv2.COLOR_BGR2YUV)
    # 增强U和V通道(色度)
    yuv[:, :, 1] = np.clip(yuv[:, :, 1].astype(int) * 1.2, 0, 255).astype(np.uint8)
    yuv[:, :, 2] = np.clip(yuv[:, :, 2].astype(int) * 1.2, 0, 255).astype(np.uint8)
    result = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)

    # 合并Alpha
    if has_alpha:
        result = cv2.cvtColor(result, cv2.COLOR_BGR2BGRA)
        result[:, :, 3] = alpha

    if output_path is None:
        input_path = Path(image_path)
        output_path = input_path.parent / f"{input_path.stem}_sharp{input_path.suffix}"

    cv2.imwrite(str(output_path), result)
    return result


def texture_based_separation(image_path, output_path=None):
    """
    基于纹理的分离方法
    包和衣服通常有不同的纹理特征，即使颜色相似
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"无法读取图像: {image_path}")

    has_alpha = img.shape[2] == 4
    if has_alpha:
        bgr = img[:, :, :3]
        alpha = img[:, :, 3]
    else:
        bgr = img

    # 1. 计算局部二值模式(LBP)风格的纹理特征
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 2. 使用Gabor滤波器提取纹理
    kernels = []
    for theta in np.arange(0, np.pi, np.pi / 4):
        for freq in [0.1, 0.2]:
            kernel = cv2.getGaborKernel((21, 21), 5.0, theta, 10.0, freq, 0, ktype=cv2.CV_32F)
            kernels.append(kernel)

    # 应用Gabor滤波并累加响应
    texture_response = np.zeros_like(gray, dtype=np.float32)
    for kernel in kernels:
        filtered = cv2.filter2D(gray, cv2.CV_32F, kernel)
        texture_response += np.abs(filtered)

    # 归一化纹理响应
    texture_response = cv2.normalize(texture_response, None, 0, 255, cv2.NORM_MINMAX)
    texture_mask = texture_response.astype(np.uint8)

    # 3. 根据纹理强度调整原图对比度
    texture_mask_3ch = cv2.cvtColor(texture_mask, cv2.COLOR_GRAY2BGR).astype(np.float32) / 255.0

    # 在纹理丰富区域(可能是包或衣服边界)增加对比度
    enhanced = bgr.astype(np.float32) * (1 + texture_mask_3ch * 0.3)
    enhanced = np.clip(enhanced, 0, 255).astype(np.uint8)

    # 4. 再次应用锐化
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    result = cv2.filter2D(enhanced, -1, kernel)

    if has_alpha:
        result = cv2.cvtColor(result, cv2.COLOR_BGR2BGRA)
        result[:, :, 3] = alpha

    if output_path is None:
        input_path = Path(image_path)
        output_path = input_path.parent / f"{input_path.stem}_texture{input_path.suffix}"

    cv2.imwrite(str(output_path), result)
    return result


def simple_adjust(image_path, brightness=0, saturation=1.0, output_path=None):
    """
    简单调整亮度和饱和度
    brightness: -100 到 100 (正值变亮)
    saturation: 0.0 到 3.0 (1.0为原图，>1增加饱和度)
    """
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("无法读取图像")

    # 分离Alpha通道
    has_alpha = img.shape[2] == 4
    if has_alpha:
        bgr = img[:, :, :3]
        alpha = img[:, :, 3]
    else:
        bgr = img

    # 转换到HSV
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)

    # 调整亮度 (V通道)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] + brightness, 0, 255)

    # 调整饱和度 (S通道)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturation, 0, 255)

    # 转回BGR
    result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 合并Alpha
    if has_alpha:
        result = cv2.cvtColor(result, cv2.COLOR_BGR2BGRA)
        result[:, :, 3] = alpha

    if output_path:
        cv2.imwrite(output_path, result)

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='增强行人包与衣服的颜色区分度')
    parser.add_argument('input', help='输入PNG图像路径')
    parser.add_argument('-o', '--output', help='输出路径(可选)')
    parser.add_argument('-m', '--method', choices=['standard', 'sharp', 'texture', 'all'],
                       default='standard', help='处理方法')
    parser.add_argument('--edge', type=float, default=1.5, help='边缘增强强度')
    parser.add_argument('--color', type=float, default=1.3, help='颜色增强强度')

    args = parser.parse_args()

    if args.method == 'standard' or args.method == 'all':
        print("应用标准增强...")
        enhance_bag_separation(args.input, args.output, args.edge, args.color)

    if args.method == 'sharp' or args.method == 'all':
        print("应用锐化增强...")
        advanced_edge_sharpen(args.input, args.output.replace('.png', '_sharp.png') if args.output else None)

    if args.method == 'texture' or args.method == 'all':
        print("应用纹理分离...")
        texture_based_separation(args.input, args.output.replace('.png', '_texture.png') if args.output else None)

    print("完成!")
