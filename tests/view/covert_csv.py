import csv
import os
import re
from pathlib import Path

def parse_bbox_file(txt_path):
    """
    解析bbox文件，返回bbox列表 [(x1,y1,x2,y2), ...]
    """
    bboxes = []
    if not os.path.exists(txt_path):
        return bboxes

    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('bbox:'):
                # 提取坐标
                match = re.search(r'bbox:\s*\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)', line)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    bboxes.append((x1, y1, x2, y2))
    return bboxes

def convert_label(value):
    """
    将TP/FN/FP/TN转换为Y/N
    TP/FN = 带包/携带液体/简单交互/特殊人群 = Y (正样本)
    FP/TN = 不带包/不携带 = N (负样本)
    空值保持空
    """
    if not value or value.strip() == '':
        return ''
    value = value.strip().upper()
    if value in ['TP', 'FN']:
        return 'Y'
    elif value in ['FP', 'TN']:
        return 'N'
    return value

def process_csv(input_csv, output_csv, bbox_dir):
    """
    主处理函数
    """
    rows = []

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)

        current_video_id = None

        for row in reader:
            if len(row) < 7:
                continue

            # 提取数据
            video_id_str = row[0].strip()
            frame_id_str = row[1].strip()
            box_id_str = row[2].strip()
            bag = row[3].strip()
            liquid = row[4].strip()
            interaction = row[5].strip()
            special = row[6].strip()

            # 更新当前视频ID（如果提供了）
            if video_id_str:
                current_video_id = video_id_str

            # 跳过没有帧ID的行（这些行只有框ID，bbox在上一行同一帧）
            # 实际上这些行需要处理，但bbox在同一帧的txt文件中
            if not frame_id_str and not box_id_str:
                continue

            # 如果没有帧ID，但有框ID，说明是同帧不同框
            # 需要从rows中找到同视频同帧的最后一行获取帧ID
            frame_id = None
            if frame_id_str:
                frame_id = int(frame_id_str)
            else:
                # 向上查找同视频的最新帧ID
                for prev_row in reversed(rows):
                    if prev_row[0] == current_video_id and prev_row[1] != '':
                        frame_id = int(prev_row[1])
                        break

            if frame_id is None:
                continue

            box_id = int(box_id_str) if box_id_str else 0

            # 构建bbox文件路径
            # video_{video_id}/h265_output_{frame_id}.txt
            txt_filename = f"h265_output_{frame_id}.txt"
            video_folder = f"video_{current_video_id}"
            txt_path = os.path.join(bbox_dir, video_folder, txt_filename)

            # 解析bbox
            bboxes = parse_bbox_file(txt_path)

            # 获取对应box_id的bbox
            if box_id < len(bboxes):
                x1, y1, x2, y2 = bboxes[box_id]
            else:
                # bbox文件不存在或box_id超出范围
                x1, y1, x2, y2 = '', '', '', ''

            # 转换标签
            bag_yn = convert_label(bag)
            liquid_yn = convert_label(liquid)
            interaction_yn = convert_label(interaction)
            special_yn = convert_label(special)

            rows.append([
                current_video_id,
                frame_id,
                box_id,
                x1, y1, x2, y2,
                bag_yn,
                liquid_yn,
                interaction_yn,
                special_yn
            ])

    # 写入输出CSV
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # 写入表头
        writer.writerow([
            '视频ID', '帧ID', '框ID',
            'x1', 'y1', 'x2', 'y2',
            '是否带包', '是否携带液体', '是否简单交互', '是否是特殊人群'
        ])
        writer.writerows(rows)

    print(f"处理完成！输出文件: {output_csv}")
    print(f"共处理 {len(rows)} 条记录")

if __name__ == "__main__":
    # 配置路径
    # 输入CSV
    INPUT_CSV = "workspace/tools/vision_tools/h265_multi_frames_detect_t0_v3/src_csv.csv"
    # 输出CSV
    OUTPUT_CSV = "workspace/tools/vision_tools/h265_multi_frames_detect_t0_v3/label_csv.csv"
    # bbox文件根目录（包含video_0等文件夹）
    BBOX_DIR = "workspace/tools/vision_tools/h265_multi_frames_detect_t0_v3/"

    process_csv(INPUT_CSV, OUTPUT_CSV, BBOX_DIR)
