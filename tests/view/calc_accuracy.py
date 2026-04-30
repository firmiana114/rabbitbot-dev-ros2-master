
import csv
import os
import re
from collections import defaultdict

def parse_bbox_and_detect(txt_path):
    """
    解析一帧的txt文件，返回bbox列表和detect结果列表
    每个bbox对应一个detect块（8行：4组判断）
    只返回前num_boxes个结果
    """
    if not os.path.exists(txt_path):
        return [], []

    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    bboxes = []
    detects = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # 解析bbox行
        if line.startswith('bbox:'):
            match = re.search(r'bbox:\s*\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)', line)
            if match:
                x1, y1, x2, y2 = map(int, match.groups())
                bboxes.append((x1, y1, x2, y2))

                # 查找对应的detect块（在bbox之后的行）
                detect_result = {
                    'bag': False,
                    'liquid': False,
                    'interaction': False,
                    'special': False
                }

                # 移动到detect行
                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith('bbox:'):
                    if lines[j].strip().startswith('detect:'):
                        # 找到detect行，后面8行是4个判断
                        # 格式：0/1行、描述行、0/1行、描述行...
                        # 第1/3/5/7行（索引j+1, j+3, j+5, j+7）是描述行

                        desc_indices = [j+2, j+4, j+6, j+8]  # 4个描述行的索引
                        categories = ['bag', 'liquid', 'interaction', 'special']

                        for idx, cat in zip(desc_indices, categories):
                            if idx < len(lines):
                                desc_line = lines[idx].strip()
                                if desc_line != '无':
                                    if ('【包】' in desc_line or '【背包】' in desc_line or '【手提袋】' in desc_line):
                                        detect_result['bag'] = True
                                    elif ('【饮料】' in desc_line or '【液体】' in desc_line):
                                        detect_result['liquid'] = True
                                    elif '【交互】' in desc_line:
                                        detect_result['interaction'] = True
                                    elif '【特殊人群】' in desc_line:
                                        detect_result['special'] = True

                        break  # 处理完这个bbox的detect就退出
                    j += 1

                detects.append(detect_result)

            i += 1
        else:
            i += 1

    # 只返回需要的数量
    return bboxes, detects

def calculate_iou(box1, box2):
    """
    计算两个bbox的IOU（交并比）
    box格式: (x1, y1, x2, y2)
    """
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    # 计算交集
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)

    if x2_i <= x1_i or y2_i <= y1_i:
        return 0.0

    intersection = (x2_i - x1_i) * (y2_i - y1_i)

    # 计算并集
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection

    if union <= 0:
        return 0.0

    return intersection / union

def match_boxes(csv_boxes, txt_bboxes, txt_detects, iou_threshold=0.9):
    """
    基于IOU匹配CSV框和txt框
    返回: list of (csv_box, matched_detect) 或 (csv_box, None)
    """
    matched_results = []
    used_txt_indices = set()

    for csv_box in csv_boxes:
        csv_bbox = csv_box['bbox']
        best_iou = 0
        best_idx = -1

        # 在txt中找到最佳匹配的框
        for i, txt_bbox in enumerate(txt_bboxes):
            if i in used_txt_indices:
                continue

            iou = calculate_iou(csv_bbox, txt_bbox)
            if iou > best_iou:
                best_iou = iou
                best_idx = i

        # 如果最佳匹配IOU超过阈值，则匹配成功
        if best_iou >= iou_threshold and best_idx != -1:
            matched_results.append((csv_box, txt_detects[best_idx]))
            used_txt_indices.add(best_idx)
        else:
            # 未找到匹配
            #matched_results.append((csv_box, None))
            pass

    return matched_results

def calculate_metrics(tp, fp, fn, tn):
    """计算各项指标"""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0

    return {
        'precision': precision,
        'recall': recall,
        'fpr': fpr,
        'accuracy': accuracy,
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn
    }

def process_data_box_id(input_csv, bbox_dir):
    """
    主处理函数
    """
    # 读取CSV并按video_id -> frame_id分组
    video_frames = defaultdict(lambda: defaultdict(list))

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            video_id = row['视频ID']
            frame_id = row['帧ID']

            # 读取四类标签
            labels = {
                'bag': row['是否带包'].strip().upper(),
                'liquid': row['是否携带液体'].strip().upper(),
                'interaction': row['是否简单交互'].strip().upper(),
                'special': row['是否是特殊人群'].strip().upper()
            }

            # 只保留至少有一个有效标签的框
            has_valid = any(l in ['Y', 'N'] for l in labels.values())
            if not has_valid:
                continue

            video_frames[video_id][frame_id].append({
                'box_id': row['框ID'],
                'labels': labels
            })

    # 初始化统计
    stats = {
        'bag': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0},
        'liquid': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0},
        'interaction': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0},
        'special': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0}
    }

    category_names = {
        'bag': '带包检测',
        'liquid': '携带液体',
        'interaction': '简单交互',
        'special': '特殊人群'
    }

    total_boxes = 0

    # 处理每个视频-帧
    for video_id, frames in video_frames.items():
        if int(video_id) != 3:
          continue
        for frame_id, boxes in frames.items():
            num_boxes = len(boxes)
            total_boxes += num_boxes

            # 构建文件路径
            txt_path = os.path.join(bbox_dir, f"video_{video_id}", f"h265_output_{frame_id}.txt")

            # 解析该帧的bbox和detect（只取前num_boxes个）
            _, detects = parse_frame_file(txt_path)

            # 按顺序匹配：CSV第i个框 <-> txt第i个detect
            for i, box in enumerate(boxes):
                if i >= len(detects):
                    continue  # txt中结果不足

                box_id = int(box['box_id'])

                detect = detects[box_id]
                labels = box['labels']

                #print(f"{video_id}, {frame_id}, {box_id}, {detect}, {labels}")

                # 统计四类
                for cat in ['bag', 'liquid', 'interaction', 'special']:
                    label = labels[cat]
                    if label not in ['Y', 'N']:
                        continue

                    actual = (label == 'Y')
                    pred = detect[cat]

                    if pred and actual:
                        stats[cat]['tp'] += 1
                    elif pred and not actual:
                        stats[cat]['fp'] += 1
                    elif not pred and actual:
                        stats[cat]['fn'] += 1
                    else:
                        stats[cat]['tn'] += 1

        #break

    # 输出结果
    print("=" * 70)
    print("检测结果评估报告")
    print("=" * 70)
    print(f"总评估框数: {total_boxes}")
    print()

    all_metrics = {}

    for cat_key, cat_name in category_names.items():
        s = stats[cat_key]
        total = s['tp'] + s['fp'] + s['fn'] + s['tn']

        if total == 0:
            print(f"【{cat_name}】无有效样本")
            continue

        metrics = calculate_metrics(s['tp'], s['fp'], s['fn'], s['tn'])
        all_metrics[cat_key] = metrics

        print(f"【{cat_name}】样本数: {total}")
        print(f"  混淆矩阵: TP={s['tp']}, FP={s['fp']}, FN={s['fn']}, TN={s['tn']}")
        print(f"  精确度 (Precision): {metrics['precision']:.4f} ({metrics['precision']*100:.2f}%)")
        print(f"  召回率 (Recall):    {metrics['recall']:.4f} ({metrics['recall']*100:.2f}%)")
        print(f"  误检率 (FPR):       {metrics['fpr']:.4f} ({metrics['fpr']*100:.2f}%)")
        print(f"  准确度 (Accuracy):  {metrics['accuracy']:.4f} ({metrics['accuracy']*100:.2f}%)")
        print()

    # 总体指标
    print("=" * 70)
    print("总体指标（宏平均）")
    print("=" * 70)

    valid_cats = [c for c in all_metrics if all_metrics[c]['tp'] + all_metrics[c]['fp'] + all_metrics[c]['fn'] + all_metrics[c]['tn'] > 0]

    if valid_cats:
        avg_precision = sum(all_metrics[c]['precision'] for c in valid_cats) / len(valid_cats)
        avg_recall = sum(all_metrics[c]['recall'] for c in valid_cats) / len(valid_cats)
        avg_fpr = sum(all_metrics[c]['fpr'] for c in valid_cats) / len(valid_cats)

        total_tp = sum(stats[c]['tp'] for c in stats)
        total_fp = sum(stats[c]['fp'] for c in stats)
        total_fn = sum(stats[c]['fn'] for c in stats)
        total_tn = sum(stats[c]['tn'] for c in stats)
        overall_accuracy = (total_tp + total_tn) / (total_tp + total_fp + total_fn + total_tn) if (total_tp + total_fp + total_fn + total_tn) > 0 else 0

        print(f"平均精确度 (Precision): {avg_precision:.4f} ({avg_precision*100:.2f}%)")
        print(f"平均召回率 (Recall):    {avg_recall:.4f} ({avg_recall*100:.2f}%)")
        print(f"平均误检率 (FPR):       {avg_fpr:.4f} ({avg_fpr*100:.2f}%)")
        print(f"总体准确度 (Accuracy):  {overall_accuracy:.4f} ({overall_accuracy*100:.2f}%)")

    # 保存报告
    save_report(stats, all_metrics, category_names, total_boxes, valid_cats)

def process_data(input_csv, bbox_dir, iou_threshold=0.9):
    """
    主处理函数：基于IOU匹配bbox
    """
    # 读取CSV并按video_id -> frame_id分组
    video_frames = defaultdict(lambda: defaultdict(list))

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            video_id = row['视频ID']
            frame_id = row['帧ID']

            # 解析bbox坐标
            try:
                x1 = int(row['x1']) if row['x1'] else 0
                y1 = int(row['y1']) if row['y1'] else 0
                x2 = int(row['x2']) if row['x2'] else 0
                y2 = int(row['y2']) if row['y2'] else 0
            except (ValueError, KeyError):
                continue

            # 读取四类标签
            labels = {
                'bag': row['是否带包'].strip().upper(),
                'liquid': row['是否携带液体'].strip().upper(),
                'interaction': row['是否简单交互'].strip().upper(),
                'special': row['是否是特殊人群'].strip().upper()
            }

            # 只保留至少有一个有效标签的框
            has_valid = any(l in ['Y', 'N'] for l in labels.values())
            if not has_valid:
                continue

            video_frames[video_id][frame_id].append({
                'box_id': row['框ID'],
                'bbox': (x1, y1, x2, y2),
                'labels': labels
            })

    # 初始化统计
    stats = {
        'bag': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'unmatched': 0},
        'liquid': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'unmatched': 0},
        'interaction': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'unmatched': 0},
        'special': {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'unmatched': 0}
    }

    category_names = {
        'bag': '带包检测',
        'liquid': '携带液体',
        'interaction': '简单交互',
        'special': '特殊人群'
    }

    total_boxes = 0
    matched_boxes = 0
    unmatched_boxes = 0

    # 处理每个视频-帧
    for video_id, frames in video_frames.items():
        # if int(video_id) != 3:
        #   continue
        for frame_id, csv_boxes in frames.items():
            total_boxes += len(csv_boxes)

            # 构建文件路径
            txt_path = os.path.join(bbox_dir, f"video_{video_id}", f"h265_output_{frame_id}.txt")

            # 解析该帧的所有bbox和detect
            txt_bboxes, txt_detects = parse_bbox_and_detect(txt_path)

            # 基于IOU匹配
            matched_results = match_boxes(csv_boxes, txt_bboxes, txt_detects, iou_threshold)

            # 统计匹配结果
            for csv_box, detect in matched_results:
                if detect is None:
                    unmatched_boxes += 1
                    labels = csv_box['labels']
                    # 未匹配的框，根据标签统计为漏检或正确拒绝
                    for cat in ['bag', 'liquid', 'interaction', 'special']:
                        label = labels[cat]
                        if label not in ['Y', 'N']:
                            continue
                        stats[cat]['unmatched'] += 1
                        # 未匹配视为检测为负，所以Y是FN，N是TN
                        #if label == 'Y':
                        #    stats[cat]['fn'] += 1  # 漏检
                        #else:
                        #    stats[cat]['tn'] += 1  # 正确拒绝
                else:
                    matched_boxes += 1
                    labels = csv_box['labels']

                    # 统计四类
                    for cat in ['bag', 'liquid', 'interaction', 'special']:
                        label = labels[cat]
                        if label not in ['Y', 'N']:
                            continue

                        actual = (label == 'Y')
                        pred = detect[cat]

                        if pred and actual:
                            stats[cat]['tp'] += 1
                        elif pred and not actual:
                            stats[cat]['fp'] += 1
                            if cat == 'liquid':
                                print(f"{video_id}, {frame_id}, {csv_box['bbox'][0]}, fp, {detect}, {labels}")
                        elif not pred and actual:
                            stats[cat]['fn'] += 1
                            if cat == 'liquid':
                                print(f"{video_id}, {frame_id}, {csv_box['bbox'][0]}, fn, {detect}, {labels}")
                        else:
                            stats[cat]['tn'] += 1

    # 输出结果
    print("=" * 70)
    print("检测结果评估报告（基于IOU匹配）")
    print("=" * 70)
    print(f"总评估框数: {total_boxes}")
    print(f"成功匹配: {matched_boxes} (IOU >= {iou_threshold})")
    print(f"未匹配: {unmatched_boxes}")
    print()

    all_metrics = {}

    for cat_key, cat_name in category_names.items():
        s = stats[cat_key]
        total = s['tp'] + s['fp'] + s['fn'] + s['tn']

        if total == 0:
            print(f"【{cat_name}】无有效样本")
            continue

        metrics = calculate_metrics(s['tp'], s['fp'], s['fn'], s['tn'])
        all_metrics[cat_key] = metrics

        print(f"【{cat_name}】样本数: {total} (未匹配: {s['unmatched']})")
        print(f"  混淆矩阵: TP={s['tp']}, FP={s['fp']}, FN={s['fn']}, TN={s['tn']}")
        print(f"  精确度 (Precision): {metrics['precision']:.4f} ({metrics['precision']*100:.2f}%)")
        print(f"  召回率 (Recall):    {metrics['recall']:.4f} ({metrics['recall']*100:.2f}%)")
        print(f"  误检率 (FPR):       {metrics['fpr']:.4f} ({metrics['fpr']*100:.2f}%)")
        print(f"  准确度 (Accuracy):  {metrics['accuracy']:.4f} ({metrics['accuracy']*100:.2f}%)")
        print()

    # 总体指标
    print("=" * 70)
    print("总体指标（宏平均）")
    print("=" * 70)

    valid_cats = [c for c in all_metrics if all_metrics[c]['tp'] + all_metrics[c]['fp'] + all_metrics[c]['fn'] + all_metrics[c]['tn'] > 0]

    if valid_cats:
        avg_precision = sum(all_metrics[c]['precision'] for c in valid_cats) / len(valid_cats)
        avg_recall = sum(all_metrics[c]['recall'] for c in valid_cats) / len(valid_cats)
        avg_fpr = sum(all_metrics[c]['fpr'] for c in valid_cats) / len(valid_cats)

        total_tp = sum(stats[c]['tp'] for c in stats)
        total_fp = sum(stats[c]['fp'] for c in stats)
        total_fn = sum(stats[c]['fn'] for c in stats)
        total_tn = sum(stats[c]['tn'] for c in stats)
        overall_accuracy = (total_tp + total_tn) / (total_tp + total_fp + total_fn + total_tn) if (total_tp + total_fp + total_fn + total_tn) > 0 else 0

        print(f"IOU阈值: {iou_threshold}")
        print(f"平均精确度 (Precision): {avg_precision:.4f} ({avg_precision*100:.2f}%)")
        print(f"平均召回率 (Recall):    {avg_recall:.4f} ({avg_recall*100:.2f}%)")
        print(f"平均误检率 (FPR):       {avg_fpr:.4f} ({avg_fpr*100:.2f}%)")
        print(f"总体准确度 (Accuracy):  {overall_accuracy:.4f} ({overall_accuracy*100:.2f}%)")

    # 保存报告
    save_report(stats, all_metrics, category_names, total_boxes, matched_boxes, unmatched_boxes, valid_cats, iou_threshold)

def save_report(stats, all_metrics, category_names, total_boxes, matched_boxes, unmatched_boxes, valid_cats, iou_threshold):
    """保存报告到文件"""
    output_file = "evaluation_report_iou.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("检测结果评估报告（基于IOU匹配）\n")
        f.write("=" * 70 + "\n")
        f.write(f"总评估框数: {total_boxes}\n")
        f.write(f"成功匹配: {matched_boxes} (IOU >= {iou_threshold})\n")
        f.write(f"未匹配: {unmatched_boxes}\n\n")

        for cat_key, cat_name in category_names.items():
            s = stats[cat_key]
            total = s['tp'] + s['fp'] + s['fn'] + s['tn']

            if total == 0:
                f.write(f"【{cat_name}】无有效样本\n\n")
                continue

            m = all_metrics[cat_key]
            f.write(f"【{cat_name}】样本数: {total} (未匹配: {s['unmatched']})\n")
            f.write(f"  混淆矩阵: TP={s['tp']}, FP={s['fp']}, FN={s['fn']}, TN={s['tn']}\n")
            f.write(f"  精确度 (Precision): {m['precision']:.4f}\n")
            f.write(f"  召回率 (Recall):    {m['recall']:.4f}\n")
            f.write(f"  误检率 (FPR):       {m['fpr']:.4f}\n")
            f.write(f"  准确度 (Accuracy):  {m['accuracy']:.4f}\n\n")

        if valid_cats:
            avg_precision = sum(all_metrics[c]['precision'] for c in valid_cats) / len(valid_cats)
            avg_recall = sum(all_metrics[c]['recall'] for c in valid_cats) / len(valid_cats)
            avg_fpr = sum(all_metrics[c]['fpr'] for c in valid_cats) / len(valid_cats)

            total_tp = sum(stats[c]['tp'] for c in stats)
            total_fp = sum(stats[c]['fp'] for c in stats)
            total_fn = sum(stats[c]['fn'] for c in stats)
            total_tn = sum(stats[c]['tn'] for c in stats)
            overall_accuracy = (total_tp + total_tn) / (total_tp + total_fp + total_fn + total_tn) if (total_tp + total_fp + total_fn + total_tn) > 0 else 0

            f.write("=" * 70 + "\n")
            f.write("总体指标（宏平均）\n")
            f.write("=" * 70 + "\n")
            f.write(f"IOU阈值: {iou_threshold}\n")
            f.write(f"平均精确度 (Precision): {avg_precision:.4f}\n")
            f.write(f"平均召回率 (Recall):    {avg_recall:.4f}\n")
            f.write(f"平均误检率 (FPR):       {avg_fpr:.4f}\n")
            f.write(f"总体准确度 (Accuracy):  {overall_accuracy:.4f}\n")

    print(f"\n详细报告已保存至: {output_file}")

if __name__ == "__main__":
    # 配置路径
    # 输入的带标签CSV
    CSV_PATH = "workspace/tools/vision_tools/h265_multi_frames_detect_t0_v3/label_csv.csv"
    # bbox和detect文件根目录
    BBOX_DIR = "workspace/tools/vision_tools/h265_multi_frames_detect_t0_v3_1/"
    #BBOX_DIR = "workspace/tools/vision_tools/"

    process_data(CSV_PATH, BBOX_DIR, iou_threshold=0.8)
