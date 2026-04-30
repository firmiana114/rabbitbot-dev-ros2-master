
import cv2
import pyrealsense2 as rs
import numpy as np


def test_rgb():
    p = rs.pipeline()
    c = rs.config()
    c.enable_stream(rs.stream.color, 1280, 720, rs.format.rgb8, 30)
    p.start(c)
    f = p.wait_for_frames()
    img = np.asanyarray(f.get_color_frame().get_data())
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    cv2.imwrite('d455.jpg', img)
    print('已保存 -> d455.jpg')
    p.stop()


def test_depth():
    p = rs.pipeline()
    c = rs.config()
    c.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 30)
    p.start(c)
    f = p.wait_for_frames()
    img = np.asanyarray(f.get_color_frame().get_data())
    depth_colormap = cv2.applyColorMap(
        cv2.convertScaleAbs(img, alpha=0.08),
        cv2.COLORMAP_JET
    )
    cv2.imwrite('d455_depth.jpg', depth_colormap)
    print('已保存 -> d455_depth.jpg')
    p.stop()


def test_rgb_depth():
    # 1. 创建 pipeline 和 config
    pipeline = rs.pipeline()
    config = rs.config()

    # 2. 启用两个流
    width = 640
    height = 480
    fps = 5
    config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
    config.enable_stream(rs.stream.color, width, height, rs.format.rgb8, fps)

    # 3. 启动流
    profile = pipeline.start(config)

    # 4. 创建对齐对象：深度→彩色
    align = rs.align(rs.stream.color)

    try:
        while True:
            # 5. 等待帧集
            frames = pipeline.wait_for_frames()

            # 6. 对齐
            aligned_frames = align.process(frames)

            # 7. 取对齐后的帧
            aligned_depth = aligned_frames.get_depth_frame()
            color_frame = aligned_frames.get_color_frame()

            if not aligned_depth or not color_frame:
                continue

            # 8. 转成 numpy
            depth_image = np.asanyarray(aligned_depth.get_data())   # uint16, 单位 mm
            color_image = np.asanyarray(color_frame.get_data())     # uint8 RGB

            # 9. 可选：彩色可视化深度
            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_image, alpha=0.08),
                cv2.COLORMAP_JET
            )

            # 10. 显示
            cv2.imwrite('d455_color.jpg', cv2.cvtColor(color_image, cv2.COLOR_RGB2BGR))
            cv2.imwrite('d455_depth.jpg', depth_colormap)

            if cv2.waitKey(1) & 0xFF == 27:   # ESC 退出
                break
            input("Press ENTER to continue")
    finally:
        pipeline.stop()


if __name__ == "__main__":
    #test_rgb()
    test_depth()
    #test_rgb_depth()
