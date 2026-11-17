"""Real ROS2 Jazzy action transport to the existing HTTP job controller."""
import json
import threading
import time

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor, ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import JointState, CompressedImage
from std_msgs.msg import String
from pickloop_interfaces.action import Pick
from .core import HttpCore, TERMINAL, camera_path, progress


class Bridge(Node):
    def __init__(self):
        super().__init__('pickloop_bridge')
        self.declare_parameter('api_url','http://127.0.0.1:8000')
        self.declare_parameter('http_timeout',1.)
        self.declare_parameter('job_timeout',120.)
        self.declare_parameter('cancel_timeout',10.)
        self.core=HttpCore(self.get_parameter('api_url').value,self.get_parameter('http_timeout').value)
        self.lock=threading.Lock();self.busy=False;self.last_frame=None;self.last_event=None
        status_qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.events=self.create_publisher(String,'/pickloop/events',status_qos)
        self.joints=self.create_publisher(JointState,'/joint_states',qos_profile_sensor_data)
        self.clock=self.create_publisher(Clock,'/clock',qos_profile_sensor_data)
        self.camera=self.create_publisher(CompressedImage,'/pickloop/camera/compressed',qos_profile_sensor_data)
        self.action=ActionServer(self,Pick,'/pickloop/pick',self.execute,
            goal_callback=self.goal,cancel_callback=lambda _:CancelResponse.ACCEPT,
            callback_group=ReentrantCallbackGroup())
        self.get_logger().info('Pick action HTTP bridge ready: '+self.core.base_url)

    def goal(self,request):
        if not request.job_id or len(request.job_id)>128 or not request.sku or request.policy not in ('baseline','recovery'):
            return GoalResponse.REJECT
        with self.lock:
            if self.busy:return GoalResponse.REJECT
            self.busy=True
        return GoalResponse.ACCEPT

    def publish_observation(self,snapshot):
        phase,run_id,sim_time,attempt=progress(snapshot)
        message=String();message.data=json.dumps({'job_id':snapshot.get('job_id'),'run_id':run_id,
            'status':snapshot.get('status'),'phase':phase,'sim_time':sim_time,'attempt':attempt})
        if message.data!=self.last_event:self.events.publish(message);self.last_event=message.data
        seconds=int(sim_time);nanos=int((sim_time-seconds)*1e9)
        stamp=Clock();stamp.clock.sec=seconds;stamp.clock.nanosec=nanos;self.clock.publish(stamp)
        frames=snapshot.get('frames') or []
        if frames:
            frame=frames[-1];identity=(run_id,frame.get('frame_id'))
            if identity!=self.last_frame:
                self.last_frame=identity
                if 'joints' in frame:
                    joints=JointState();joints.header.stamp=stamp.clock;joints.header.frame_id='base'
                    joints.name=['shoulder','elbow','vertical','wrist'];joints.position=[float(v) for v in frame['joints']]
                    self.joints.publish(joints)
                if frame.get('camera'):
                    try:
                        image=CompressedImage();image.header.stamp=stamp.clock;image.header.frame_id='camera_optical'
                        image.format='jpeg';image.data=self.core.image(camera_path(run_id,frame['camera']))
                        self.camera.publish(image)
                    except Exception as error:self.get_logger().warning('camera fetch failed: '+str(error))
        return phase,run_id,sim_time,attempt

    def execute(self,handle):
        result=Pick.Result();job_id=handle.request.job_id;cancel_sent=False;cancel_at=None
        deadline=time.monotonic()+float(self.get_parameter('job_timeout').value)
        try:
            snapshot=self.core.submit(handle.request)
            while rclpy.ok():
                if handle.is_cancel_requested and not cancel_sent:
                    self.core.cancel(job_id);cancel_sent=True;cancel_at=time.monotonic()
                snapshot=self.core.status(job_id)
                phase,run_id,sim_time,attempt=self.publish_observation(snapshot)
                feedback=Pick.Feedback();feedback.phase=phase;feedback.run_id=run_id
                feedback.sim_time=sim_time;feedback.attempt=attempt;handle.publish_feedback(feedback)
                status=snapshot.get('status',snapshot.get('state','QUEUED'))
                if status in TERMINAL:
                    result.success=bool(snapshot.get('success',False));result.status=status
                    result.run_id=run_id;result.reason=str(snapshot.get('reason') or '')
                    if status=='CANCELLED' and handle.is_cancel_requested:handle.canceled()
                    elif result.success:handle.succeed()
                    else:handle.abort()
                    return result
                if cancel_sent and time.monotonic()-cancel_at>float(self.get_parameter('cancel_timeout').value):
                    raise TimeoutError('core cancellation not confirmed; job requires reconciliation')
                if time.monotonic()>deadline:raise TimeoutError('bridge job deadline expired; job requires reconciliation')
                time.sleep(.1)
            raise RuntimeError('ROS shutdown before confirmed core result')
        except Exception as error:
            result.success=False;result.status='BRIDGE_UNCERTAIN';result.reason=str(error)
            result.run_id=str(snapshot.get('run_id','')) if 'snapshot' in locals() else ''
            handle.abort();return result
        finally:
            with self.lock:self.busy=False


def main(args=None):
    rclpy.init(args=args);node=Bridge();executor=MultiThreadedExecutor(num_threads=4);executor.add_node(node)
    try:executor.spin()
    except (KeyboardInterrupt,ExternalShutdownException):pass
    finally:
        executor.shutdown();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
