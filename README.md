# RabbitBot

## Installation

```
uv venv
uv pip install -e .
```

## Folders

- `rabbitbot`: python src package
    - `agents`: qwen agents
    - `robots`: robot control
    - `tools`: qwen tools for function calls provided to agents
- `tests`: unittests
    - `tasks`: end-to-end task tests v1/v2/v3
    - `robots`: test robot controls

## UnitTests

### Running

```
python -m unittest discover tests -v
```

### Writing

Use `patch_vln`, `patch_robot` in case the service and robot are unavailable.

## TODO

- [x] Write unittests
- [x] Modify prompts for better planning
- [x] Refactor prompts `PromptProvider` (not urgent)
- [ ] Setup unittest server
- [ ] Write scripts for 3d/2d camera setup and ros setup
- [ ] Refactor robots to import rclpy/Gst/depthai as optional dependency
  ```
  # E.g., on Jetson locally
  export RABBITBOT_MODEL=Qwen2.5-VL-7B-Instruct
  export RABBITBOT_MODEL_SERVER="http://localhost:8000/v1"
  export RABBITBOT_VLN_URL="http://127.0.0.1:8001"
  ```
