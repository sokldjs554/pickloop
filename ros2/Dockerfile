FROM ros:jazzy-ros-base@sha256:00b8d47a6e6384a2834e3d01fa87ae767876543baa574f2d64a75c04ea33c698
RUN apt-get update && apt-get install -y --no-install-recommends python3-colcon-common-extensions ros-jazzy-rosidl-default-generators ros-jazzy-sensor-msgs ros-jazzy-rosgraph-msgs && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/pickloop_ros
COPY src/ src/
RUN /bin/bash -c 'source /opt/ros/jazzy/setup.bash && colcon build --event-handlers console_direct+'
CMD ["bash", "-c", "source /opt/ros/jazzy/setup.bash && source install/setup.bash && exec python3 -c \"from pickloop_bridge.node import main; main()\""]
