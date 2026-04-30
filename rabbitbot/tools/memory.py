from qwen_agent.tools.base import BaseToolWithFileAccess, register_tool
import cv2
from rabbitbot.robots.constants import MoveType
from rabbitbot.robots import get_robot
from rabbitbot.provider import get_vlm_openai
from rabbitbot.prompts import get_prompt_provider
from rabbitbot.provider import get_memory_layer, get_memory_agent

from typing import Union, List, Optional, Dict
import os
import re
import time
import numpy as np
import math
import asyncio
from datetime import datetime
import uuid


# TODO: refactoring
@register_tool('memorymap')
class MemoryMap(BaseToolWithFileAccess):
    _pp = get_prompt_provider('memorymap')
    description = _pp.description
    parameters = [
    ]

    def __init__(self, cfg: Optional[Dict] = None):
        super().__init__(cfg)
        self.vlm = get_vlm_openai(prompt=self._pp.system_message, bbox_prompt=self._pp.system_message_bbox)
        self.frame_size = self.cfg.get('frame_size', (1024, 784))
        self.rotate_step = self.cfg.get('rotate_step', 90)
        self.robot_type = self.cfg.get('robot_type', 'cmu')
        self.robot_height = 1.55

    def get_image_and_location(self, image, depth_image, entities, robot_rot_angle=0, robot_location=(0,0)):
        print(f"MemoryMap: Get image and location")
        images = []
        locations = []
        entity_names = re.findall(r'"Entity_name":\s*"([^"]+)"', entities)
        entity_bbox = re.findall(r'"Entity_bbox":\s*\[(.*?)\]', entities)
        entity_bbox = [list(map(int, bbox.split(','))) for bbox in entity_bbox]

        camera = get_robot(self.robot_type).get_depth_camera()

        for idx, name in enumerate(entity_names):
            bbox = entity_bbox[idx]
            if len(bbox) == 0:
                continue
            x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
            image_entity = image[y1:y2, x1:x2]
            x_scale = depth_image.shape[1] / image.shape[1]
            y_scale = depth_image.shape[0] / image.shape[0]
            x1, y1, x2, y2 = int(x1 * x_scale), int(y1 * y_scale), int(x2 * x_scale), int(y2 * y_scale)
            depth = get_object_distance_final(depth_image, bbox)
            depth = camera.get_real_depth(depth)
            depth = math.sqrt(depth**2 - self.robot_height**2)
            if depth > 0.5:
                depth -= 0.5
            bbox_center_x = (x1 + x2) / 2
            image_center_x = depth_image.shape[1] / 2
            angle_per_pixel = camera.hfov / depth_image.shape[1]
            horizontal_offset_angle = -((bbox_center_x - image_center_x) * angle_per_pixel) * (math.pi / 180)
            rot_angle = (horizontal_offset_angle + robot_rot_angle) % (2 * math.pi)
            x_relative = depth * math.cos(rot_angle)
            y_relative = depth * math.sin(rot_angle)
            # loc0前向, loc1左
            location = (round(robot_location[0] + x_relative, 1), round(robot_location[1] + y_relative, 1), rot_angle)
            locations.append(location)

            image_path = os.path.join(self.work_dir, f'{name}_{location}.png')
            cv2.imwrite(image_path, image_entity)
            images.append(image_path)

        return images, locations

    def call(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        print(f"MemoryMap: Call (patrams={params})")
        os.makedirs(self.work_dir, exist_ok=True)

        robot = get_robot(self.robot_type)
        update_data = {}
        images, depths, robot_rot_angles = zip(*self.generate_360_images())
        images = list(images)
        depths = list(depths)

        for idx, (image, depth, robot_rot_angle) in enumerate(zip(images, depths, robot_rot_angles)):
            print(f"MemoryMap: Process image (idx={idx})")
            image_message, video_kwargs = self.vlm.prepare_video_message_for_vllm([image])
            json_content = self.vlm.get_chat_response(
                messages=image_message,
                extra_body={
                    "mm_processor_kwargs": video_kwargs
                }
            )
            print(f"MemoryMap: Get chat response (idx={idx})")
            print(json_content)
            json_content = json_content.strip('```json\n').strip('```')
            print(f"MemoryMap: Ready to get image and location (idx={idx})")
            image_paths, locations = self.get_image_and_location(image, depth, json_content, robot_rot_angle=robot_rot_angle, robot_location=robot.get_point()[:2])
            entity_names = re.findall(r'"Entity_name":\s*"([^"]+)"', json_content)
            entity_descriptions = re.findall(r'"Entity_description":\s*"([^"]+)"', json_content)
            update_data.update({name: (description, image_path, location) for name, description, image_path, location in zip(entity_names, entity_descriptions, image_paths, locations)})

        print(f"MemoryMap: Get entity data")
        print(update_data)

        #get_memory_layer().update_sync(update_data)
        get_memory_agent().update_sync(update_data)
        return self._pp.return_message

    def generate_360_images(self):
        print(f"MemoryMap: Genearte 360 images")
        for i in range(0, 90, self.rotate_step):
            robot = get_robot(self.robot_type)
            # Get the image and depth frame
            time.sleep(2)
            image = robot.view_2d(output_size=self.frame_size)
            camera = robot.get_depth_camera()
            depth = camera.get_depth_frame()
            depth = cv2.resize(depth, self.frame_size)
            image_path = os.path.join(self.work_dir, f'temp_test_{i}.png')
            print(f"MemoryMap: Write frame (path={image_path})")
            cv2.imwrite(image_path, image)

            depth_path = os.path.join(self.work_dir, f'temp_test_depth_{i}.png')
            print(f"MemoryMap: Write depth frame (path={depth_path})")
            cv2.imwrite(depth_path, depth)

            pose = robot.get_pose()
            while pose is None:
                time.sleep(1)
                pose = robot.get_pose()

            print(f"MemoryMap: pose {pose}")
            robot_rot_angle = robot.get_pose()[3] + camera.yaw_offset
            #import pdb;pdb.set_trace();
            yield (image, depth, robot_rot_angle)

            for _ in range(0, self.rotate_step, robot.rotate_step):
                if self.robot_type == 'cmu':
                    robot.move_with_joystick(MoveType.RIGHT, blocking=True)
                elif self.robot_type == 'kuavo':
                    #robot.jazzy_control_sync(MoveType.RIGHT)
                    pass
            # For the stability of the camera focus
            time.sleep(1)

def get_object_distance_final(depth_image, bbox, min_dist_mm=1000, max_dist_mm=10000):
    """
    通过范围过滤和K-Means聚类，精确计算物体距离。

    Args:
        depth_image (np.ndarray): 深度图像，单位为毫米。
        bbox (tuple): 对象的边界框，格式为 (x_min, y_min, x_max, y_max)。
        min_dist_mm (int): 可接受的最小深度值（毫米）。
        max_dist_mm (int): 可接受的最大深度值（毫米）。
        visualize (bool): 是否显示分割结果的可视化图像。

    Returns:
        float: 估算出的物体距离（毫米）。如果无法计算，则返回-1。
    """
    x_min, y_min, x_max, y_max = map(int, bbox)
    depth_roi = depth_image[y_min:y_max, x_min:x_max]

    # 1. 关键步骤：应用深度范围过滤，同时去除无效值(0)
    valid_mask = (depth_roi > min_dist_mm) & (depth_roi < max_dist_mm)
    valid_depths = depth_roi[valid_mask]
    #import pdb; pdb.set_trace()
    if valid_depths.size < 20: # 聚类需要足够的数据点
        if valid_depths.size > 0:
            print(f"警告: 有效深度点过少({valid_depths.size}个)，将直接使用中位数。")
            return np.median(valid_depths)
        else:
            print(f"警告: 在指定范围 [{min_dist_mm}, {max_dist_mm}] mm 内没有找到任何有效深度点。")
            return -1.0
            
    # 2. 准备数据进行K-Means聚类
    pixels = valid_depths.reshape(-1, 1).astype(np.float32)

    # 3. 应用K-Means聚类
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    K = 2
    try:
        # 当数据点本身已经很集中时，可能只需要1个簇
        # 但我们强制用K=2来分离主体和近处背景
        compactness, labels, centers = cv2.kmeans(pixels, K, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
    except cv2.error:
        print("警告: K-Means聚类失败。将退回使用中位数。")
        return np.median(valid_depths)

    # 4. 识别主体簇（像素最多的那个）
    label_counts = np.bincount(labels.ravel(), minlength=K)
    fg_label = int(np.argmax(label_counts))
    fg_center_value = float(centers[fg_label][0])
    
    # 5. 计算最终距离
    foreground_pixels = pixels[labels.ravel() == fg_label]
    distance_final = np.mean(foreground_pixels)
    
    print(f"--- 最终距离估算 ---")
    print(f"有效深度范围: [{min_dist_mm}, {max_dist_mm}] mm")
    print(f"聚类中心: {centers.flatten()[0]:.2f} mm, {centers.flatten()[1]:.2f} mm")
    print(f"识别出的主体中心深度: {fg_center_value:.2f} mm")
    print(f"最终估算距离: {distance_final:.2f} mm")

    return distance_final