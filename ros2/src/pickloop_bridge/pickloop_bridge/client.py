"""CLI action client used for real DDS smoke/integration evidence."""
import argparse
import json
import time
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from pickloop_interfaces.action import Pick


def main(args=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--job-id',required=True);parser.add_argument('--sku',default='SKU-RED-A')
    parser.add_argument('--seed',type=int,default=1);parser.add_argument('--fault',default='normal')
    parser.add_argument('--policy',default='recovery')
    cancel = parser.add_mutually_exclusive_group()
    cancel.add_argument('--cancel-after',type=float)
    cancel.add_argument('--cancel-at-phase',choices=('LIFT', 'TRANSPORT'),
                        help='request cancellation when the action first reports this phase')
    options,ros_args=parser.parse_known_args(args)
    rclpy.init(args=ros_args);node=Node('pickloop_action_client');client=ActionClient(node,Pick,'/pickloop/pick')
    try:
        if not client.wait_for_server(timeout_sec=10):raise RuntimeError('action server unavailable')
        goal=Pick.Goal()
        for key in ('job_id','sku','seed','fault','policy'):setattr(goal,key,getattr(options,key))
        cancel_feedback = None
        def feedback(message):
            nonlocal cancel_feedback
            f=message.feedback
            observed = {'phase':f.phase,'run_id':f.run_id,'sim_time':f.sim_time,'attempt':f.attempt}
            print(json.dumps({'feedback':observed}),flush=True)
            if f.phase == options.cancel_at_phase and cancel_feedback is None:
                cancel_feedback = observed
        future=client.send_goal_async(goal,feedback_callback=feedback);rclpy.spin_until_future_complete(node,future,timeout_sec=10)
        if not future.done() or not future.result().accepted:raise RuntimeError('goal not accepted')
        handle=future.result();result=handle.get_result_async();started=time.monotonic();cancelled=False
        while rclpy.ok() and not result.done() and time.monotonic()-started<150:
            rclpy.spin_once(node,timeout_sec=.05)
            timer_due = options.cancel_after is not None and time.monotonic()-started>=options.cancel_after
            if not result.done() and not cancelled and (timer_due or cancel_feedback is not None):
                handle.cancel_goal_async()
                cancelled = True
                request = {'cancel_requested':True}
                if cancel_feedback is not None:
                    request['trigger'] = cancel_feedback
                print(json.dumps(request),flush=True)
        if not result.done():raise RuntimeError('action result deadline expired')
        response=result.result();value=response.result
        print(json.dumps({'result':{'action_status':response.status,'success':value.success,'status':value.status,'run_id':value.run_id,'reason':value.reason}}),flush=True)
    finally:node.destroy_node();rclpy.shutdown()

if __name__=='__main__':main()
