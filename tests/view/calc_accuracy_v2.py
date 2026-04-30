
import pandas as pd
from tabulate import tabulate
import sys

def calculate_metrics(tp, tn, fp, fn):
    """
    计算各项指标
    """
    total = tp + tn + fp + fn

    # 精确率 Precision = TP / (TP + FP)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0

    # 召回率 Recall = TP / (TP + FN)  注意：这里TP是检测为正且实际为正，FN是检测为负但实际为正
    # 对于二分类，Recall = TP / (TP + FN)
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0

    # 准确率 Accuracy = (TP + TN) / Total
    accuracy = (tp + tn) / total if total > 0 else 0

    # 误检率 FPR = FP / (FP + TN)  假阳性率
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

    return {
        'Precision': round(precision, 4),
        'Recall': round(recall, 4),
        'Accuracy': round(accuracy, 4),
        'FPR': round(fpr, 4),
        'TP': tp,
        'TN': tn,
        'FP': fp,
        'FN': fn,
        'Total': total
    }

def analyze_all_categories(input_file, output_file=None):
    """
    分析所有类别的混淆矩阵，每列独立统计

    列结构：
    0: 视频ID, 1: 帧ID, 2: BBOX ID,
    3: 带包(TP/TN/FP/FN),
    4: 携带液体(TP/TN/FP/FN),
    5: 简单交互(TP/TN/FP/FN),
    6: 特殊人群(TP/TN/FP/FN)
    """
    # 读取CSV
    df = pd.read_csv(input_file, dtype=str, keep_default_na=False)

    print(f"数据行数: {len(df)}")
    print(f"列名: {df.columns.tolist()}")

    # 四列混淆矩阵
    category_cols = {
        '携带包类': df.columns[3],
        '携带液体': df.columns[4],
        '简单交互': df.columns[5],
        '特殊人群': df.columns[6]
    }

    print(f"\n分析类别: {list(category_cols.keys())}")

    results = []

    print(f"\n{'='*70}")

    for cat_name, col_name in category_cols.items():
        # 统计该列的混淆矩阵
        tp = len(df[df[col_name] == 'TP'])
        tn = len(df[df[col_name] == 'TN'])
        fp = len(df[df[col_name] == 'FP'])
        fn = len(df[df[col_name] == 'FN'])

        # 检查未标记数据
        total_labeled = tp + tn + fp + fn
        unlabeled = len(df) - total_labeled

        metrics = calculate_metrics(tp, tn, fp, fn)

        print(f"\n【{cat_name}】")
        print(f"  TP={tp}, TN={tn}, FP={fp}, FN={fn}, Total={metrics['Total']}")
        print(f"  Precision={metrics['Precision']}, Recall={metrics['Recall']}")
        print(f"  Accuracy={metrics['Accuracy']}, FPR={metrics['FPR']}")
        if unlabeled > 0:
            print(f"  警告: {unlabeled} 行未标记")

        results.append({
            '类别': cat_name,
            '样本数': metrics['Total'],
            'TP': metrics['TP'],
            'TN': metrics['TN'],
            'FP': metrics['FP'],
            'FN': metrics['FN'],
            #'Precision': metrics['Precision'],
            #'Recall': metrics['Recall'],
            'Accuracy': metrics['Accuracy'],
            'FPR(误检率)': metrics['FPR']
        })

    # 对齐输出 - 使用 col_space 设置列宽
    print("\n" + "="*90)
    print("汇总表格")
    print("="*90)

    # 设置列宽对齐（根据内容调整）
    # 更精细的对齐 - 左对齐或右对齐
    summary_df = pd.DataFrame(results)

    print("\n汇总表格:")
    # 多种格式可选: 'plain', 'simple', 'grid', 'pipe', 'orgtbl', 'rst', 'mediawiki', 'latex'
    print(tabulate(summary_df, headers='keys', tablefmt='grid', showindex=False, stralign='center'))

    # 保存结果
    if output_file is None:
        output_file = input_file[:-4] + '_metrics.csv' if input_file.endswith('.csv') else input_file + '_metrics.csv'

    summary_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n结果已保存至: {output_file}")

    return summary_df

# 使用示例
if __name__ == "__main__":
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else None
        analyze_all_categories(input_path, output_path)
    else:
        input_path = "your_filtered.csv"  # 修改为你的文件路径
        analyze_all_categories(input_path)
