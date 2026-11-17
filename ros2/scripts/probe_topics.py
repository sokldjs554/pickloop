"""Record real DDS telemetry counts during an independently requested action."""
import json
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy, ReliabilityPolicy
from std_msgs.msg import String
from sensor_msgs.msg import JointState, CompressedImage
from rosgraph_msgs.msg import Clock

rclpy.init();node=Node('pickloop_topic_probe');counts={};samples={};subscriptions=[]

def receive(name):
    def callback(message):
        counts[name]=counts.get(name,0)+1
        if name=='events':samples[name]=json.loads(message.data)
        elif name=='joints':samples[name]={'names':list(message.name),'position':list(message.position)}
        elif name=='camera':samples[name]={'format':message.format,'bytes':len(message.data)}
        else:samples[name]={'sec':message.clock.sec,'nanosec':message.clock.nanosec}
    return callback

status=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
for name,kind,topic,qos in [('events',String,'/pickloop/events',status),('joints',JointState,'/joint_states',qos_profile_sensor_data),('camera',CompressedImage,'/pickloop/camera/compressed',qos_profile_sensor_data),('clock',Clock,'/clock',qos_profile_sensor_data)]:
    subscriptions.append(node.create_subscription(kind,topic,receive(name),qos))
started=time.monotonic()
try:
    while time.monotonic()-started<30:rclpy.spin_once(node,timeout_sec=.1)
    print(json.dumps({'counts':counts,'samples':samples}),flush=True)
finally:node.destroy_node();rclpy.shutdown()
