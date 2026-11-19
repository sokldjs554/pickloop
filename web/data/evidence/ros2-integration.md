# ROS2 Jazzy task integration

`ros2/` contains a real ROS2 task action server/client and generated custom interface. The server calls the existing local HTTP job runner; it does not implement robot drivers, MoveIt, Nav2, a ros2_control hardware interface, or a physical safety controller. Core job identity, perception, motion, device protocol, and cancellation remain owned by PickLoop's controller.

## Build and run

The host does not need ROS installed. Docker runs the official ROS Jazzy base on Ubuntu Noble; the Dockerfile pins its registry digest and builds both packages with colcon.

```bash
# From the repository root. The live API must already be running on port 8000.
docker build -t pickloop-ros:jazzy ros2
docker run -d --name pickloop-ros-bridge --network host --ipc host \
  -e ROS_DOMAIN_ID=42 pickloop-ros:jazzy

docker exec pickloop-ros-bridge bash -c 'source /opt/ros/jazzy/setup.bash; source /opt/pickloop_ros/install/setup.bash; ros2 interface show pickloop_interfaces/action/Pick'
docker exec pickloop-ros-bridge bash -c 'source /opt/ros/jazzy/setup.bash; source /opt/pickloop_ros/install/setup.bash; ros2 run pickloop_bridge pick_client --job-id ros-example-1 --seed 7 --sku SKU-RED-A'
docker exec pickloop-ros-bridge bash -c 'source /opt/ros/jazzy/setup.bash; source /opt/pickloop_ros/install/setup.bash; ros2 run pickloop_bridge pick_client --job-id ros-cancel-1 --seed 7 --cancel-after 0.3'
# Release bridge resources after testing.
docker stop pickloop-ros-bridge
```

Use fresh job IDs for distinct intentional jobs. Reusing a job ID submits the same core identity and cannot silently rerun a completed physical task; conflicting core configurations are rejected. If the bridge or HTTP connection fails, reconcile the original job ID with `GET /api/jobs/{job_id}` before issuing another task. The server accepts one active ROS goal at a time and rejects concurrent goals. HTTP runner capacity also applies to jobs launched through the web UI.

For a native Jazzy installation, source `/opt/ros/jazzy/setup.bash`, install `python3-colcon-common-extensions`, `ros-jazzy-rosidl-default-generators`, `ros-jazzy-sensor-msgs`, and `ros-jazzy-rosgraph-msgs`, then run `colcon build` inside `ros2/` and source `install/setup.bash`.

## Action contract

Action `/pickloop/pick`, type `pickloop_interfaces/action/Pick`:

| Direction | Fields |
| --- | --- |
| Goal | `string job_id`, `string sku`, `string fault`, `string policy`, `uint32 seed` |
| Feedback | `string phase`, `string run_id`, `float64 sim_time`, `uint32 attempt` |
| Result | `bool success`, `string status`, `string run_id`, `string reason` |

The action server POSTs the goal to `/api/jobs`, polls `/api/jobs/{job_id}`, and publishes actual observed progress. HTTP failures and bridge deadlines produce an aborted `BRIDGE_UNCERTAIN` result; they never claim the robot stopped or the job failed physically. Each HTTP operation uses a one-second socket timeout by default. The overall job deadline is 120 seconds, with a ten-second cancellation-confirmation budget. Configure ROS parameters `api_url`, `http_timeout`, `job_timeout`, and `cancel_timeout` as needed.

A ROS cancellation request triggers the core cancellation endpoint. The ROS action is marked cancelled only after the core reports terminal `CANCELLED`. A job that finishes successfully before cancellation takes effect reports its actual completion. A failed/unconfirmed cancellation aborts with an uncertainty reason; it does not release suction. The coordinator's controlled-stop behavior and retention of held objects remain in the core.

The current HTTP core accepts seeds through 2^31−1 even though the portable action field is uint32. SKU/fault/policy values must match `/api/health` and the live API schema; examples use `SKU-RED-A`, `normal`, `recovery`.

## Published observations

| Topic | Type | Source and QoS |
| --- | --- | --- |
| `/pickloop/events` | `std_msgs/String` JSON | Current observed job phase/status, reliable transient local depth 1 |
| `/joint_states` | `sensor_msgs/JointState` | Recorded observed frame joints; best effort sensor QoS |
| `/clock` | `rosgraph_msgs/Clock` | Observed frame/event simulation time; best effort sensor QoS |
| `/pickloop/camera/compressed` | `sensor_msgs/CompressedImage` | Actual recorded JPEG bytes fetched from `/runs/{run_id}/frames/...`; best effort sensor QoS |

Joint names are `shoulder`, `elbow`, `vertical`, `wrist`; rotary positions are radians, vertical position is metres. Frames use `base` and `camera_optical`. Camera and joint messages are emitted only when observed frames exist; the bridge does not synthesize them from evaluator truth. It never reads `initial_truth` or `final_truth`. Images are bounded to 10 MB and constrained to the requested run's relative `frames/` path. `/clock` can reset between runs; consumers should handle simulation resets. This bridge does not publish TF or CameraInfo and does not claim a complete calibrated ROS sensor/control stack.

Host helper tests run with `python -m unittest discover -s ros2/tests -v`. The `ros2/scripts/probe_topics.py` tool subscribes over actual DDS and records message counts and representative public telemetry. Integration evidence and precise runtime results are recorded in the build/test report; a successful build alone is not a successful physical-task claim.


## Verified local execution

The Jazzy image was built and the action was exercised over actual DDS against the local MuJoCo API. A normal goal returned `SUCCEEDED` / `COMPLETED` (`normal-7-recovery-a63bfd`); an early cancel returned ROS `CANCELED` after core `CANCELLED` confirmation (`normal-7-recovery-3b11b0`). Resubmitting the completed job ID returned the same run. A simultaneous DDS probe received 74 status messages, 95 clock messages, 72 joint messages, and 72 real compressed camera images. This cancellation test occurred before grasp and does not claim a ROS held-load cancellation test.

Raw logs and the parsed result summary are preserved in [ros2/evidence](../ros2/evidence/). The pinned base digest and built image ID are recorded in `integration-summary.json`. These are local simulation results; no physical robot/control certification is implied.
