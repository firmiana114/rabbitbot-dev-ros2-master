# RabbitBot Autonomy Stack

This document describes the network topology and startup sequence for running SLAM on an NUC, data reception on a Jetson, and loading the Qwen-2.5-8B-Instruct VLM inside Docker, as well as launching the multi-agent control script.

---

## Power

26~29 v

##  Communication Topology

- **NUC ↔ Jetson**  

  Direct wired Ethernet connection.

- **Jetson ↔ Control Device (e.g., laptop)**  
  Over a local Wi-Fi hotspot created by the Jetson.

---

## Step-by-Step Startup

### Step 0: Start SLAM on the NUC

On your **local machine** (or Jetson), open a terminal and SSH into the NUC:

```bash
ssh all@10.1.1.100
bash ~/system_with_domain_bridge.sh
```

passwd: all
jetson passwd: We're#1

### Step 1: Start Data Reception on the Jetson

On the Jetson, open a terminal and run:

```
cd ~/robotcar
bash data_view/data_view.sh
```

**Optional GUI visualization:**

```
bash data_view/data_view_rviz.sh
```

### Step 2: Start the Vision-Language Model (VLM)

In a new terminal on the Jetson, run:

```
docker start suspicious_mcclintoc
docker attach suspicious_mcclintoc
vllm serve /root/models/Qwen2.5-VL-7B-Instruct
```

### Step 3: Launch the Multi-Agent Controller

On the Jetson, activate the Python virtual environment and start the agent script:

```
cd ~/rabbitbot
source .venv/bin/activate
python multi_agents.py
```

To enable the web-based GUI instead, edit `multi_agents.py` and replace the launch call with:

```
app_gui()
```

---

## Additional: Regenerating the Map

1. **Enable PCD saving** (NUC)
    In `src/base_autonomy/visualization_tools/launch/visualization_tools.launch`, set:

   ```
   <param name="savePcd" value="true" />
   ```

2. **Collect data**
    Run the vehicle; you will get `pointcloud_<timestamp>.txt` and a trajectory file in `src/base_autonomy/vehicle_simulator/log/`.

    Close PCD saving

3. Subsample：

   Open  `pointcloud_<timestamp>.txt`  in `CloudCompare` and subsample it with `0.1` parameters.

   Save it with ASCII mode on `~/Desktop` with name: `pointcloud_local.txt`

4. **Prepare for localization**

   - In `src/slam/arise_slam_mid360/config/livox_mid360.yaml`, set:

     ```
     local_mode: true
     init_x:   <your_start_x>
     init_y:   <your_start_y>
     init_z:   <your_start_z>
     init_yaw: <your_start_yaw>
     ```

5. **Restart SLAM**
    Repeat **Step 0**; SLAM will now use the saved point cloud as the fixed map.

6. **Mention: **

   1. **Don’t Forget to set Savepcds to False on running, and set Local_mode to True on Mapping.** 
   2. **Don’t build map with circle looping.**

7. ROS instruction

use ros2 topic list to get all topic
use ros2 topic echo xx to monitor topic. eg: tos2 topic echo /state_estimation to get NUC's location.
use ros2 topic pub to send request. eg : ~/apis/move.py

---

## References

- Autonomy Stack for Mecanum-Wheel Platform (Jazzy branch):
   https://github.com/jizhang-cmu/autonomy_stack_mecanum_wheel_platform/tree/jazzy?tab=readme-ov-file

8. 360 Camera

```
export GST_PLUGIN_PATH=/home/jianyu/robotcar/dependency/360_camera/src/receive_theta/dependency/gstthetauvc/thetauvc
```
