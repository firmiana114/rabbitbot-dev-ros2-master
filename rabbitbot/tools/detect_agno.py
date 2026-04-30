import cv2
from rabbitbot.robots.constants import MoveType
from rabbitbot.prompts.register import get_prompt_provider
from rabbitbot.tools.base_agno import BaseToolkit

from typing import Union, List, Optional, Dict, Any
import re
import numpy as np
import math
from textwrap import dedent
import time
import json

detect_agno_configs = {"is_robot_agent": True}

class DetectToolkit(BaseToolkit):
    _pp = get_prompt_provider('memorymap')
    description = _pp.description
    parameters = [
    ]

    def __init__(
        self,
        ctx: Any,
        do_async: bool = True,
        frame_size: tuple = (960, 540),
        crop_ratio: float = 0.95,
        kuavo: bool = False,
        **kwargs
    ):
        self.do_async = do_async
        self.frame_size = frame_size
        self.crop_ratio = crop_ratio
        self.kuavo = kuavo
        tools = [self.detect_location]
        requires_confirmation_tools = ["detect_location"]
        super().__init__(ctx, name='detect_tools', tools=tools, requires_confirmation_tools=requires_confirmation_tools, **kwargs)
        #self.frame_size = (504, 364)
        self.frame_size = (1280, 720)
        self.room = []
        self.camera_height = 1.5
        self.desk_height = 1
        self.debug = True

    def _get_point_cloud_center(self, point_cloud_patch: np.ndarray) -> Optional[np.ndarray]:
        """
        Calculates the center of a point cloud patch after basic filtering.

        Args:
            point_cloud_patch (np.ndarray): A numpy array representing the point cloud patch,
                                            with shape (height, width, 3), where each element
                                            is an [x, y, z] coordinate.

        Returns:
            Optional[np.ndarray]: The center of the filtered point cloud as a numpy array,
                                  or None if no valid points are found.
        """
        if point_cloud_patch.size == 0:
            return None
        if len(point_cloud_patch.shape) == 3:
            # Reshape the patch into a list of points
            points = point_cloud_patch.reshape(-1, 3)
        else:
            points = point_cloud_patch
        # Filter out invalid points (e.g., [0, 0, 0] where depth is missing)
        valid_points = points[np.any(points != 0, axis=1)]

        if valid_points.shape[0] < 10:  # Not enough points to process
            return np.mean(valid_points, axis=0) if valid_points.shape[0] > 0 else None

        # Use percentile-based filtering to remove outliers.
        # This is more robust for points that are not normally distributed.
        distances = np.linalg.norm(valid_points, axis=1)
        lower_bound = np.percentile(distances, 30)
        upper_bound = np.percentile(distances, 70)

        # Keep points within the 10th and 90th percentile of distances
        main_object_points = valid_points[(distances >= lower_bound) & (distances <= upper_bound)]

        if main_object_points.shape[0] == 0:
            # Fallback to all valid points if filtering removes everything
            main_object_points = valid_points

        # Calculate the center of the main object points
        center = np.mean(main_object_points, axis=0)
        print(center)
        return center

    def get_red_area(self, image):
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower_red = np.array([0, 80, 100])
        upper_red = np.array([10, 255, 255])
        mask = cv2.inRange(hsv, lower_red, upper_red)
        
        # # 查找轮廓并保留最大的红色区域
        # contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # if contours:
        #     # 找到面积最大的轮廓
        #     largest_contour = max(contours, key=cv2.contourArea)
        #     # 创建新的mask，只保留最大的红色区域
        #     mask = np.zeros_like(mask)
        #     cv2.fillPoly(mask, [largest_contour], 255)
        if self.debug:
            cv2.imwrite('red_area.jpg', mask)
        return mask

    def get_location(self, image, entity):
        # 兼容多种格式
        entity_bbox_str = re.findall(r'"Entity_bbox":\s*"\[([^\]]+)\]"', entity)
        entity_bbox_array = re.findall(r'"Entity_bbox":\s*\[\s*\[([^\]]+)\]\s*\]', entity)
        # 支持新格式：{"bbox_2d": [0, 34, 581, 496], "label": "描述"}
        entity_bbox_dict = re.findall(r'"bbox_2d":\s*\[([^\]]+)\]', entity)
        # 兼容格式："Entity_bbox": [198,173,330,456]
        entity_bbox_direct = re.findall(r'"Entity_bbox":\s*\[([^\]]+)\]', entity)
        # 兼容JSON数组格式：["[154,160,178,193]"]
        entity_bbox_json_array = re.findall(r'"\[([^\]]+)\]"', entity)
        
        if entity_bbox_str:
            entity_bbox = entity_bbox_str
        elif entity_bbox_array:
            entity_bbox = entity_bbox_array
        elif entity_bbox_dict:
            entity_bbox = entity_bbox_dict
        elif entity_bbox_direct:
            entity_bbox = entity_bbox_direct
        elif entity_bbox_json_array:
            entity_bbox = entity_bbox_json_array
        else:
            entity_bbox = []
        
        # 判断bbox数目
        if len(entity_bbox) == 0:
            return (0, 0, 0)
        elif len(entity_bbox) > 1:
            return (-1, -1, -1)
        
        bbox = list(map(int, entity_bbox[0].split(',')))
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
        # 在图像上可视化边界框
        new_image = image.copy()
        cv2.rectangle(new_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(new_image, f'Entity', (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.imwrite(f'entity.jpg', new_image)
        if not detect_agno_configs['is_robot_agent']:
            location = self.ctx.robot.get_depth_camera().get_location((x1, y1, x2, y2))
        else:
            location = self.ctx.robot.get_camera_info("get_location", {'bbox': (x1, y1, x2, y2)})
        # import pdb; pdb.set_trace()
        # depth_object = depth_image[y1:y2, x1:x2]
        # print(depth_object.shape)
        # center = self._get_point_cloud_center(depth_object)
        # x_offset = center[2] /1000.0
        # y_offset = center[0] /1000.0
        # z_offset = center[1] /1000.0
        # location = (x_offset, y_offset, z_offset)
        return location

    def get_location_old(self, image, depth_image, entity):
        # 兼容多种格式
        entity_bbox_str = re.findall(r'"Entity_bbox":\s*"\[([^\]]+)\]"', entity)
        entity_bbox_array = re.findall(r'"Entity_bbox":\s*\[\s*\[([^\]]+)\]\s*\]', entity)
        # 支持新格式：{"bbox_2d": [0, 34, 581, 496], "label": "描述"}
        entity_bbox_dict = re.findall(r'"bbox_2d":\s*\[([^\]]+)\]', entity)
        # 兼容格式："Entity_bbox": [198,173,330,456]
        entity_bbox_direct = re.findall(r'"Entity_bbox":\s*\[([^\]]+)\]', entity)
        # 兼容JSON数组格式：["[154,160,178,193]"]
        entity_bbox_json_array = re.findall(r'"\[([^\]]+)\]"', entity)
        # 兼容不完整JSON数组格式：["[300,519,476,561"]
        entity_bbox_incomplete_json = re.findall(r'"\[([^\]"]+)"', entity)
        
        if entity_bbox_str:
            entity_bbox = entity_bbox_str
        elif entity_bbox_array:
            entity_bbox = entity_bbox_array
        elif entity_bbox_dict:
            entity_bbox = entity_bbox_dict
        elif entity_bbox_direct:
            entity_bbox = entity_bbox_direct
        elif entity_bbox_json_array:
            entity_bbox = entity_bbox_json_array
        elif entity_bbox_incomplete_json:
            entity_bbox = entity_bbox_incomplete_json
        else:
            entity_bbox = []
                # 判断bbox数目
        if len(entity_bbox) == 0:
            return (0, 0, 0)
        elif len(entity_bbox) > 1:
            return (-1, -1, -1)
        bbox = list(map(int, entity_bbox[0].split(',')))
        if not detect_agno_configs['is_robot_agent']:
            camera = self.ctx.robot.get_depth_camera()
        if len(bbox) == 0:
            return None
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
        if self.debug:
            # 在图像上可视化边界框
            new_image = image.copy()
            cv2.rectangle(new_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(new_image, f'Entity', (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imwrite(f'entity.jpg', new_image)
        x_scale = depth_image.shape[1] / image.shape[1]
        y_scale = depth_image.shape[0] / image.shape[0]
        x1, y1, x2, y2 = int(x1 * x_scale), int(y1 * y_scale), int(x2 * x_scale), int(y2 * y_scale)
        # import pdb; pdb.set_trace()
        depth = self.get_object_distance_final(depth_image, bbox)
        if not detect_agno_configs['is_robot_agent']:
            depth = camera.get_real_depth(depth)
        else:
            depth = self.ctx.robot.get_camera_info("real_depth", {'depth': depth})
            #depth = depth / 1000.0
        print(f"depth: {depth}")
        projection_depth = math.sqrt(depth ** 2 - (self.camera_height - self.desk_height) ** 2)
        # Calculate the center of the bounding box
        bbox_center_x = (x1 + x2) / 2
        image_center_x = depth_image.shape[1] / 2

        # More accurate angle calculation using perspective projection model (atan)
        hfov = 90.0
        hfov_rad = math.radians(hfov)
        print(f"hfov_rad: {hfov_rad}")
        focal_length_x = (depth_image.shape[1] / 2) / math.tan(hfov_rad / 2)
        print(f"focal_length_x: {focal_length_x}")
        pixel_offset = bbox_center_x - image_center_x
        print(f"pixel_offset: {pixel_offset}")
        horizontal_offset_angle = -math.atan(pixel_offset / focal_length_x)
        print(f"pixel_offset: {pixel_offset}")
        print(f"horizontal_offset_angle: {horizontal_offset_angle}")

        # if horizontal_offset_angle > 0:
        #     self.robot.turn_right(-horizontal_offset_angle)
        # 根据projection_depth和horizontal_offset_angle计算三角形的其他两边长度
        # 假设projection_depth为斜边，horizontal_offset_angle为与x轴的夹角
        x_offset = projection_depth * math.cos(horizontal_offset_angle)
        y_offset = projection_depth * math.sin(horizontal_offset_angle)
        if y_offset < 0:
            y_offset -= 0.05
        else:
            y_offset += 0.05
        #z_offset = self.desk_height-self.camera_height
        z_offset = -0.25
        location = (x_offset, y_offset, z_offset)
        return location

    def get_key_points(self, image, depth_image, entity):
        """
        处理关键点格式并将关键点打印到图片上
        """
        import json
        camera = self.ctx.robot.get_depth_camera()
        # 解析关键点数据
        try:
            # 尝试解析JSON格式的关键点数据
            if isinstance(entity, str):
                # 如果是字符串，尝试解析JSON
                key_points_data = json.loads(entity)
            else:
                key_points_data = entity
            
            # 创建图像副本用于绘制
            new_image = image.copy()
            # 获取2D坐标点
            if isinstance(key_points_data, list) and len(key_points_data) > 0:
                # 处理数组格式：[{"point_2d": [501, 364], "label": "红色把手的中心点"}]
                point_2d = key_points_data[0]["point_2d"]
            else:
                # 处理直接对象格式：{"point_2d": [501, 364], "label": "红色把手的中心点"}
                point_2d = key_points_data["point_2d"]
                
            # 获取深度图上相邻10x10区域的深度信息并去除噪音
            x, y = int(point_2d[0]), int(point_2d[1])
            # 计算深度图坐标
            x_scale = depth_image.shape[1] / image.shape[1]
            y_scale = depth_image.shape[0] / image.shape[0]
            depth_x = int(x * x_scale)
            depth_y = int(y * y_scale)
            
            # 获取10x10区域的深度值
            half_size = 3
            y_start = max(0, depth_y - half_size)
            y_end = min(depth_image.shape[0], depth_y + half_size + 1)
            x_start = max(0, depth_x - half_size)
            x_end = min(depth_image.shape[1], depth_x + half_size + 1)
            depth_region = depth_image[y_start:y_end, x_start:x_end]
            
            # 去除噪音：过滤掉0值和异常值
            valid_depths = depth_region[depth_region > 0]
            if len(valid_depths) > 0:
                # 使用中位数去除异常值
                median_depth = np.median(valid_depths)
                std_depth = np.std(valid_depths)
                # 过滤掉超过2个标准差的异常值
                filtered_depths = valid_depths[np.abs(valid_depths - median_depth) <= 2 * std_depth]
                
                if len(filtered_depths) > 0:
                    avg_depth = np.mean(filtered_depths)
                    print(f"  平均深度: {avg_depth:.2f}mm")
            else:
                print(f"关键点({x}, {y})周围区域: 无有效深度数据")
            # 在RGB图像上绘制关键点
            cv2.circle(new_image, (int(point_2d[0]), int(point_2d[1])), 5, (0, 255, 0), -1)
            
            # 添加标签文本
            if isinstance(key_points_data, list) and len(key_points_data) > 0:
                label = key_points_data[0].get("label", "关键点")
            else:
                label = key_points_data.get("label", "关键点")
            
            cv2.putText(new_image, label, (int(point_2d[0]) + 10, int(point_2d[1]) - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            # 保存可视化图像
            cv2.imwrite('key_point.jpg', new_image)
            print(f"关键点可视化图像已保存为 key_point.jpg")
            # return avg_depth
            depth = camera.get_real_depth(avg_depth)
            projection_depth = math.sqrt(depth ** 2 - (self.camera_height - self.basket_height) ** 2)
            # Calculate the center of the bounding box
            bbox_center_x = depth_x
            image_center_x = depth_image.shape[1] / 2

            # More accurate angle calculation using perspective projection model (atan)
            hfov_rad = math.radians(camera.hfov)
            focal_length_x = (depth_image.shape[1] / 2) / math.tan(hfov_rad / 2)
            pixel_offset = bbox_center_x - image_center_x
            horizontal_offset_angle = -math.atan(pixel_offset / focal_length_x)
            # import pdb; pdb.set_trace()
            print(f"horizontal_offset_angle: {horizontal_offset_angle}")

            # if horizontal_offset_angle > 0:
            #     self.robot.turn_right(-horizontal_offset_angle)
            # 根据projection_depth和horizontal_offset_angle计算三角形的其他两边长度
            # 假设projection_depth为斜边，horizontal_offset_angle为与x轴的夹角
            x_offset = projection_depth * math.cos(horizontal_offset_angle)
            y_offset = projection_depth * math.sin(horizontal_offset_angle)
            # 转换头部坐标系
            x_offset = x_offset / math.cos(0.4886922)
            location = (x_offset, y_offset, self.basket_height-self.camera_height-0.05)
            print(location)
            return location
    
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"解析关键点数据时出错: {e}")
            return None

    def detect_location(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        description = params['task']
        if not detect_agno_configs['is_robot_agent']:
            locations = self.ctx.robot.get_depth_camera().get_location(description)
        else:
            locations = self.ctx.robot.get_camera_info("get_location", {'text': description})
        return locations

    def detect_hand_location(self, files: List[str] = None, **kwargs):
        if not detect_agno_configs['is_robot_agent']:
            locations = self.ctx.robot.get_depth_camera().detect_hand_location()
        else:
            locations = self.ctx.robot.get_camera_info("detect_hand_location")
        return locations

    def detect_key_point_pixel(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        if not detect_agno_configs['is_robot_agent']:
            locations = self.ctx.robot.get_depth_camera().detect_key_point_pixel()
        else:
            locations = self.ctx.robot.get_camera_info("detect_key_point_pixel")
        return locations

    def generate_image(self):
        robot = self.ctx.robot
        if not detect_agno_configs['is_robot_agent']:
            camera = robot.get_depth_camera()
            image = camera.view_2d(output_size=self.frame_size)
            # depth = camera.get_depth_frame()
        else:
            start_time = time.time()
            image = robot.get_camera_info('view_2d', {'frame_size': self.frame_size})
            end_time = time.time()
            print(f"RGB Image generation Time taken: {end_time - start_time} seconds")
        #     depth = robot.get_camera_info('depth_frame')
        #     end_time = time.time()
        #     print(f"Depth generation Time taken: {end_time - start_time} seconds")
        # depth = cv2.resize(depth, self.frame_size)
        return image


    def get_object_distance_final(self, depth_image, bbox, min_dist_mm=300, max_dist_mm=5000):
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

        # 4. 识别前景簇（深度值较小的那个）
        fg_center_value = min(centers)[0]
        fg_label = np.argmin(centers)
        
        # 5. 计算最终距离
        foreground_pixels = pixels[labels.ravel() == fg_label]
        distance_final = np.mean(foreground_pixels)
        
        print(f"--- 最终距离估算 ---")
        print(f"有效深度范围: [{min_dist_mm}, {max_dist_mm}] mm")
        print(f"聚类中心: {centers.flatten()[0]:.2f} mm, {centers.flatten()[1]:.2f} mm")
        print(f"识别出的前景中心深度: {fg_center_value:.2f} mm")
        print(f"最终估算距离: {distance_final:.2f} mm")

        return distance_final