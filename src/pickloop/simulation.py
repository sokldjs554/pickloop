"""Rigid-body SCARA cell. Object truth stays in physics/evaluation, not observations."""
import os
os.environ.setdefault('MUJOCO_GL','egl')
os.environ.setdefault('MESA_SHADER_CACHE_DIR','/tmp/pickloop-mesa')
import time
import uuid
from dataclasses import dataclass
from itertools import product
from xml.sax.saxutils import quoteattr
from pathlib import Path
import cv2
import mujoco
import numpy as np
from .geometry import camera_matrix, estimate_extrinsics, scara_ik, quintic_trajectory, ACCELERATION, JOINT_LOWER, JOINT_UPPER
from .types import Observation, OperationError
from .conditions import copy_condition, in_window

ROOT=Path(__file__).resolve().parents[2]
BIN_CENTER=np.array([.38,.22])
BIN_HALF=np.array([.105,.085])
FIDUCIALS=np.array([[x,y,.062] for y in [.335,-.29] for x in [.06,.33,.60]])


@dataclass(frozen=True)
class BinFixture:
    """Physical scene/evaluator definition. The camera detector never receives it."""
    center_xy_m: tuple[float, float]
    inner_size_m: tuple[float, float]
    yaw_rad: float
    depth_m: float

    def __post_init__(self):
        if len(self.center_xy_m) != 2 or len(self.inner_size_m) != 2:
            raise ValueError('Bin center and opening require two coordinates')
        if not np.isfinite((*self.center_xy_m, *self.inner_size_m, self.yaw_rad, self.depth_m)).all():
            raise ValueError('Bin dimensions and pose must be finite')
        if min(*self.inner_size_m, self.depth_m) <= 0:
            raise ValueError('Bin dimensions must be positive')

    def contains_xy(self, world_xy):
        c, s = np.cos(self.yaw_rad), np.sin(self.yaw_rad)
        local = (np.asarray(world_xy) - self.center_xy_m) @ np.array([[c, -s], [s, c]])
        return bool(np.all(np.abs(local) < np.array(self.inner_size_m) / 2))

    def xml(self, index):
        x, y = self.center_xy_m
        hx, hy = np.asarray(self.inner_size_m) / 2
        hz = (.012 + self.depth_m) / 2
        wall_z = .060 + hz
        t = .004
        walls = [('left', -hx-t, 0, t, hy), ('right', hx+t, 0, t, hy),
                 ('front', 0, -hy-t, hx+2*t, t), ('back', 0, hy+t, hx+2*t, t)]
        pieces = [f'<body name="fixture_{index}" pos="{x} {y} 0" euler="0 0 {self.yaw_rad}">',
                  f'<geom name="fixture_{index}_floor" type="box" pos="0 0 .066" size="{hx} {hy} .006" rgba=".10 .30 .41 1"/>']
        for side, wx, wy, sx, sy in walls:
            pieces.append(f'<geom name="fixture_{index}_{side}" type="box" pos="{wx} {wy} {wall_z}" size="{sx} {sy} {hz}" rgba=".13 .41 .52 1"/>')
        return ''.join(pieces) + '</body>'


def scene_xml(seed,condition=None,bin_layout=None,parcel_textures=None):
    rng=np.random.default_rng(seed)
    positions=[(.34+rng.uniform(-.024,.024),-.19+rng.uniform(-.025,.025)),(.49+rng.uniform(-.012,.012),-.16+rng.uniform(-.015,.015)),(.20+rng.uniform(-.015,.015),-.12+rng.uniform(-.012,.012))]
    if condition is not None:
        condition=copy_condition(condition,seed)
        positions=[obj['xy_m'] for obj in condition['objects']]
    textures=[]; materials=[]
    if parcel_textures is not None and len(parcel_textures) != 3:
        raise ValueError('The scene requires three parcel material images')
    for name,file,color in [('a','red_a.png','.7 .12 .10 1'),('b','red_b.png','.7 .12 .10 1'),('u','unknown.png','.1 .65 .25 1')]:
        p=ROOT/'assets'/'textures'/file if parcel_textures is None else Path(parcel_textures[len(materials)]).resolve()
        if parcel_textures is not None and not p.is_file():
            raise FileNotFoundError(p)
        if p.exists():
            textures.append(f'<texture name="tex_{name}" type="2d" file={quoteattr(str(p))}/>')
            materials.append(f'<material name="mat_{name}" texture="tex_{name}" texuniform="false" texrepeat="1 1" reflectance="0" specular="0.1"/>')
        else:
            materials.append(f'<material name="mat_{name}" rgba="{color}"/>')
    objects=[]
    for i,(name,xy) in enumerate(zip(['a','b','u'],positions)):
        yaw=rng.uniform(-.12,.12) if condition is None else condition['objects'][i]['yaw_rad']
        mass=.08 if condition is None else condition['objects'][i]['mass_kg']
        friction=.8 if condition is None else condition['objects'][i]['friction']
        objects.append(f'<body name="parcel_{name}" pos="{xy[0]} {xy[1]} .087" euler="0 0 {yaw}"><freejoint/><geom name="parcel_{name}" type="box" size=".032 .026 .025" mass="{mass}" material="mat_{name}" friction="{friction} .01 .001" condim="4"/></body>')
    fid=''.join(f'<geom name="fid_{i}" type="cylinder" pos="{x} {y} .061" size=".010 .001" rgba=".9 .02 .9 1" contype="0" conaffinity="0"/>' for i,(x,y,z) in enumerate(FIDUCIALS))
    blocker_z=-.5 if condition is None or condition['fault']!='path_blocked' else condition['blocker_top_m']-.14
    weld=''.join(f'<weld name="suction_{n}" body1="tool" body2="parcel_{n}" active="false" solref=".008 1" torquescale=".02"/>' for n in ['a','b','u'])
    bins = '''  <geom name="bin_floor" type="box" pos=".38 .22 .066" size=".105 .085 .006" rgba=".10 .30 .41 1"/>
  <geom name="bin_back" type="box" pos=".38 .309 .095" size=".115 .004 .035" rgba=".13 .41 .52 1"/>
  <geom name="bin_left" type="box" pos=".271 .22 .095" size=".004 .085 .035" rgba=".13 .41 .52 1"/>
  <geom name="bin_right" type="box" pos=".489 .22 .095" size=".004 .085 .035" rgba=".13 .41 .52 1"/>
  <geom name="bin_front" type="box" pos=".38 .131 .095" size=".115 .004 .035" rgba=".13 .41 .52 1"/>
''' if bin_layout is None else ''.join(fixture.xml(i) for i, fixture in enumerate(bin_layout))
    return f'''<mujoco model="pickloop_scara">
 <compiler angle="radian"/>
 <option timestep=".005" gravity="0 0 -9.81" integrator="implicitfast" iterations="60"/>
 <size nconmax="200" njmax="1000"/>
 <visual><global offwidth="800" offheight="600"/><quality shadowsize="2048"/><headlight ambient=".4 .4 .4" diffuse=".55 .55 .55"/></visual>
 <default><joint damping="3" armature=".01"/><geom solref=".012 1" solimp=".95 .99 .001" friction=".8 .01 .001"/></default>
 <asset>{''.join(textures)}{''.join(materials)}<material name="metal" rgba=".68 .73 .77 1" specular=".4"/><material name="teal" rgba=".05 .65 .60 1"/></asset>
 <worldbody>
  <light pos=".2 -.4 1.8" dir="0 .2 -1" diffuse=".75 .75 .75" castshadow="true"/>
  <geom name="floor" type="plane" size="2 2 .02" rgba=".10 .14 .18 1"/>
  <geom name="table" type="box" pos=".33 0 .03" size=".38 .36 .03" rgba=".25 .30 .34 1"/>
  {fid}
  <camera name="rgbd" pos=".33 0 1.35" xyaxes="1 0 0 0 1 0" fovy="45"/>
  {'<camera name="inspection" pos=".33 0 1.35" xyaxes="1 0 0 0 1 0" fovy="4.2"/>' if parcel_textures is not None else ''}
  <camera name="scene" pos="1.1 -1.2 .95" xyaxes=".80 .60 0 -.24 .32 .9165" fovy="46"/>
  <geom name="column" type="cylinder" pos="0 0 .26" size=".055 .21" material="metal"/>
  <body name="shoulder" pos="0 0 .50"><joint name="shoulder" type="hinge" axis="0 0 1" range="-2.9 2.9"/>
   <geom name="link1" type="capsule" fromto="0 0 0 .32 0 0" size=".029" mass=".6" material="teal"/>
   <body name="elbow" pos=".32 0 0"><joint name="elbow" type="hinge" axis="0 0 1" range="-2.8 2.8"/>
    <geom name="link2" type="capsule" fromto="0 0 .005 .28 0 .005" size=".024" mass=".4" material="metal"/>
    <geom name="lift_guide" type="cylinder" pos=".28 0 .105" size=".027 .122" mass=".09" rgba=".12 .38 .40 1"/>
    <body name="slide" pos=".28 0 0" gravcomp="1"><joint name="vertical" type="slide" axis="0 0 1" range="-.39 -.02" damping="8"/>
     <geom name="shaft" type="cylinder" pos="0 0 .099" size=".009 .109" mass=".1" material="metal"/>
     <body name="tool" gravcomp="1"><joint name="wrist" type="hinge" axis="0 0 1" range="-3.14 3.14" damping=".1"/>
      <geom name="cup" type="cylinder" pos="0 0 -.022" size=".012 .018" mass=".035" rgba=".07 .08 .1 1"/>
      <site name="tcp" pos="0 0 -.04" size=".004" rgba="1 .8 .1 1"/>
     </body>
    </body>
    <body name="lift_stage" pos=".28 0 0" gravcomp="1">
     <joint name="stage_travel" type="slide" axis="0 0 1" range="-.20 0" damping=".08" armature=".0001"/>
     <geom name="lift_sleeve" type="cylinder" pos="0 0 .103" size=".015 .113" mass=".035" material="metal"/>
    </body>
   </body>
  </body>
  {bins}
  <geom name="blocker" type="box" pos=".37 .015 {blocker_z}" size=".09 .045 .14" rgba=".80 .50 .12 1"/>
  {''.join(objects)}
 </worldbody>
 <actuator>
  <position joint="shoulder" kp="400" kv="35" forcerange="-60 60"/>
  <position joint="elbow" kp="300" kv="25" forcerange="-40 40"/>
  <position joint="vertical" kp="1800" kv="80" forcerange="-100 100"/>
  <position joint="wrist" kp="70" kv="4" forcerange="-8 8"/>
 </actuator>
 <contact><exclude body1="lift_stage" body2="slide"/><exclude body1="lift_stage" body2="tool"/>
  <exclude body1="tool" body2="parcel_a"/><exclude body1="tool" body2="parcel_b"/><exclude body1="tool" body2="parcel_u"/></contact>
 <equality>{weld}<joint name="sleeve_half_stroke" joint1="stage_travel" joint2="vertical" polycoef="0 .5 0 0 0" solref=".01 1"/></equality>
</mujoco>'''


class Cell:
    def __init__(self,seed=0,fault='normal',run_id=None,condition=None,bin_layout=None,parcel_textures=None):
        self.seed=seed; self.fault=fault; self.run_id=run_id or uuid.uuid4().hex[:12]
        self.condition=None if condition is None else copy_condition(condition,seed,fault)
        self.bin_layout = None if bin_layout is None else tuple(bin_layout)
        self.model=mujoco.MjModel.from_xml_string(scene_xml(seed,self.condition,self.bin_layout,parcel_textures)); self.data=mujoco.MjData(self.model)
        self.data.qpos[:4]=scara_ik([.19,-.32,.34]); self.data.ctrl[:]=self.data.qpos[:4]
        # The concentric intermediate sleeve travels half as far as the driven spindle.
        self.stage_qpos = self.model.joint('stage_travel').qposadr.item()
        self.data.qpos[self.stage_qpos] = self.data.qpos[2] / 2
        self.tcp_id=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_SITE,'tcp')
        self.tool_id=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,'tool')
        self.cup_id=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_GEOM,'cup')
        self.object_bodies=[mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,'parcel_'+n) for n in ['a','b','u']]
        self.robot_geoms={mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_GEOM,n) for n in ['link1','link2','lift_guide','lift_sleeve','shaft','cup']}
        self.attempt=1; self.valve=False; self.attached=None; self.pressure_kpa=0.; self.attach_time=0.
        self.drop_count=0; self.collision_count=0; self._drop_used=False; self._obs_count=0
        self.on_step=None; self.output_source=None; self.cancel=None; self.closed=False; self._command_velocity=np.zeros(4); self._stopping=False; self._active_contacts=set()
        self.renderer=mujoco.Renderer(self.model,height=480,width=480)
        self.scene_renderer=mujoco.Renderer(self.model,height=480,width=640)
        self.K=camera_matrix(480,480,45)
        self.step_for(.5)
        rgb,_=self._render_sensor()
        mask=((rgb[:,:,0]>140)&(rgb[:,:,2]>140)&(rgb[:,:,1]<110)).astype(np.uint8)
        n,lab,stats,cent=cv2.connectedComponentsWithStats(mask)
        centers=[c for c,s in zip(cent[1:],stats[1:]) if 20<s[4]<250]
        centers=sorted(centers,key=lambda p:(round(p[1]/20),p[0]))
        if len(centers)!=6:
            self.close()
            raise OperationError('CALIBRATION_MARKERS_MISSING',{'count':len(centers)})
        self.T_base_camera,self.calibration_rms_px=estimate_extrinsics(FIDUCIALS,np.array(centers),self.K)
        self.calibration_id='pnp-six-dots-v1'
        self.calibration={'kind':'fixed_camera_extrinsic_PnP','rms_px':self.calibration_rms_px,'K':self.K.tolist(),'T_base_camera':self.T_base_camera.tolist(),'image_points':np.array(centers).tolist(),'base_points':FIDUCIALS.tolist()}
        if fault=='path_blocked':
            idx=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_GEOM,'blocker')
            self.model.geom_pos[idx,2]=.20 if self.condition is None else self.condition['blocker_top_m']-.14
            mujoco.mj_forward(self.model,self.data)

    def __enter__(self): return self
    def __exit__(self,*_): self.close()
    def close(self):
        if not self.closed:
            self.renderer.close(); self.scene_renderer.close(); self.closed=True
    @property
    def sim_time(self): return float(self.data.time)
    @property
    def tcp(self): return self.data.site_xpos[self.tcp_id].copy()
    @property
    def joints(self): return self.data.qpos[:4].copy()

    def _render_sensor(self):
        self.renderer.update_scene(self.data,camera='rgbd')
        rgb=self.renderer.render().copy()
        self.renderer.enable_depth_rendering()
        depth=self.renderer.render().copy()
        self.renderer.disable_depth_rendering()
        return rgb,depth

    def observe(self):
        self._obs_count+=1
        rgb,depth=self._render_sensor()
        T=self.T_base_camera.copy()
        obs_time=self.sim_time
        if self.condition is None:
            # Legacy replay path; explicit experiment conditions below do not use attempts.
            if self.attempt==1:
                if self.fault=='occlusion':
                    rgb[260:385,175:275]=75; depth[260:385,175:275]=1.11
                if self.fault=='depth_missing':depth[260:385,175:275]=np.nan
                if self.fault=='calibration_error':T[0,3]+=.028
                if self.fault=='stale_observation':obs_time-=.8
        else:
            sensor=self.condition['sensor']
            T[:3,3]+=np.asarray(sensor['persistent_bias_xyz_m'])
            tick=int(np.floor((self.sim_time+1e-9)/sensor['noise_quantum_s']))
            rng=np.random.default_rng(np.random.SeedSequence([sensor['noise_seed'],tick]))
            depth+=rng.normal(0.,sensor['depth_noise_std_m'],depth.shape).astype(depth.dtype)
            if in_window(self.sim_time,[0.,sensor['release_s']]):
                x0,y0,x1,y1=sensor['region_xyxy_px']
                if self.fault=='occlusion':
                    rgb[y0:y1,x0:x1]=75; depth[y0:y1,x0:x1]=1.11
                if self.fault=='depth_missing':depth[y0:y1,x0:x1]=np.nan
                if self.fault=='calibration_error':T[:3,3]+=np.asarray(sensor['transient_bias_xyz_m'])
                if self.fault=='stale_observation':obs_time-=sensor['stale_age_s']
        return Observation(self.run_id,f'{self.run_id}-obs-{self._obs_count:04}',obs_time,time.monotonic_ns(),rgb,depth,self.K.copy(),T,self.calibration_id)

    def inspect_point(self, xyz, fovy=4.2):
        """Pan a virtual overhead zoom camera toward a base-frame RGB-D measurement."""
        cam = self.model.camera('inspection')
        cam.fovy[0] = fovy
        # This rotation is a camera command derived from the requested point. No
        # scene bodies or object coordinates enter the inspection observation.
        pos = cam.pos.copy()
        look = np.asarray(xyz) - pos
        look /= np.linalg.norm(look)
        right = np.cross(look, [0., 1., 0.])
        right /= np.linalg.norm(right)
        up = np.cross(right, look)
        rotation = np.column_stack((right, up, -look))
        quaternion = np.empty(4)
        mujoco.mju_mat2Quat(quaternion, rotation.ravel())
        cam.quat[:] = quaternion
        mujoco.mj_forward(self.model, self.data)
        self.renderer.update_scene(self.data, camera='inspection')
        rgb = self.renderer.render().copy()
        self.renderer.enable_depth_rendering()
        depth = self.renderer.render().copy()
        self.renderer.disable_depth_rendering()
        transform = np.eye(4)
        transform[:3, :3] = np.column_stack((right, -up, look))
        transform[:3, 3] = pos
        self._obs_count += 1
        return Observation(self.run_id, f'{self.run_id}-zoom-{self._obs_count:04}', self.sim_time,
                           time.monotonic_ns(), rgb, depth, camera_matrix(480, 480, fovy), transform,
                           'virtual-zoom-command-v1')

    def render_scene(self):
        self.scene_renderer.update_scene(self.data,camera='scene')
        return self.scene_renderer.render().copy()

    def command_suction(self,on):
        self.valve=bool(on)
        if not on: self._release()

    def _release(self,drop=False):
        if self.attached is not None:
            p=self.data.xpos[self.object_bodies[self.attached]]
            if self.bin_layout is None:
                over_floor = np.all(np.abs(p[:2]-BIN_CENTER)<BIN_HALF)
            else:
                over_floor = any(fixture.contains_xy(p[:2]) for fixture in self.bin_layout)
            support = .072 if over_floor else .060
            unsupported_clearance=float(p[2]-.025-support)
            self.data.eq_active[self.attached]=False
            self.attached=None
            if drop or unsupported_clearance>.040:self.drop_count+=1
        self.pressure_kpa=0.

    def _vacuum_physics(self):
        if not self.valve:
            self.pressure_kpa=0.; return
        suction=None if self.condition is None else self.condition['suction']
        supply_outage=suction is not None and (suction['permanent_outage'] or any(in_window(self.sim_time,w) for w in suction['outage_windows_s']))
        if self.attached is not None:
            if supply_outage:
                self._release(drop=True); self.pressure_kpa=-6.; return
            if self.condition is None and self.fault=='drop' and not self._drop_used and self.tcp[2]>.25 and self.tcp[1]>-.08:
                self._drop_used=True; self._release(drop=True); return
            # 55 kPa, 12 mm cup -> ~24.9 N; explicit wrench limit.
            eq_index=np.where(self.data.efc_type==mujoco.mjtConstraint.mjCNSTR_EQUALITY)[0]
            if len(eq_index) and np.max(np.abs(self.data.efc_force[eq_index]))>(26 if suction is None else suction['wrench_limit_n']):
                self._release(drop=True); return
            self.pressure_kpa=-55. if suction is None else suction['sealed_pressure_kpa']; return
        self.pressure_kpa=-6.
        if supply_outage:return
        if self.condition is None:
            if self.fault=='suction_permanent' or (self.fault=='suction_once' and self.attempt==1): return
            if self._drop_used and self.attempt==1: return
        seal_halfwidth=[.020,.014] if suction is None else suction['seal_halfwidth_m']
        seal_z=.0045 if suction is None else suction['seal_z_tolerance_m']
        tcp=self.tcp
        for index,body in enumerate(self.object_bodies):
            R=self.data.xmat[body].reshape(3,3)
            local=R.T@(tcp-self.data.xpos[body])
            # seal entirely inside flat top and normal aligned within 12 degrees
            if abs(local[0])<seal_halfwidth[0] and abs(local[1])<seal_halfwidth[1] and abs(local[2]-.025)<seal_z and R[2,2]>.978:
                invq=np.empty(4); mujoco.mju_negQuat(invq,self.data.xquat[self.tool_id])
                pos=np.empty(3); quat=np.empty(4)
                mujoco.mju_rotVecQuat(pos,self.data.xpos[body]-self.data.xpos[self.tool_id],invq)
                mujoco.mju_mulQuat(quat,invq,self.data.xquat[body])
                self.model.eq_data[index,3:6]=pos; self.model.eq_data[index,6:10]=quat
                self.data.eq_active[index]=True; self.attached=index; self.attach_time=self.sim_time; self.pressure_kpa=-55. if suction is None else suction['sealed_pressure_kpa']
                break

    def step(self):
        if not self._stopping and self.cancel is not None and self.cancel():
            self.data.ctrl[:]=self.data.qpos[:4]
            raise OperationError('CANCELLED')
        if self.output_source is not None:self.command_suction(self.output_source())
        self._vacuum_physics()
        # Catalog payload mass feed-forward, enabled only by pressure feedback.
        self.data.qfrc_applied[2]=.08*9.81 if self.pressure_kpa < -35 else 0.
        mujoco.mj_step(self.model,self.data)
        contacts=self._prohibited_contacts(self.data)
        self.collision_count+=len(contacts-self._active_contacts)
        self._active_contacts=contacts
        if contacts and not self._stopping: raise OperationError('COLLISION',{'pairs':sorted(contacts)})
        if self.on_step: self.on_step(self)

    def step_for(self,seconds):
        for _ in range(int(np.ceil(seconds/self.model.opt.timestep))): self.step()

    def _prohibited_contacts(self,data,payload_name=None):
        prohibited=set()
        adjacent={frozenset(p) for p in [('link1','link2'),('link2','shaft'),('shaft','cup'),('column','link1')]}
        held=payload_name or ('parcel_'+['a','b','u'][self.attached] if self.attached is not None else None)
        for c in data.contact:
            if c.dist>=-.001:continue
            g1,g2=int(c.geom1),int(c.geom2)
            n1=mujoco.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_GEOM,g1) or ''
            n2=mujoco.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_GEOM,g2) or ''
            names=frozenset((n1,n2))
            if names in adjacent:continue
            if (g1 in self.robot_geoms or g2 in self.robot_geoms) or (held and held in names):
                if 'cup' in names and any(n.startswith('parcel_') for n in names):continue
                prohibited.add('|'.join(sorted(names)))
        return prohibited

    def _collision_at(self,q,allow_contact):
        # The planner has the surveyed cell map and the configured box envelope.
        # Dynamic object's true poses/IDs are deliberately erased from its probe.
        probe=mujoco.MjData(self.model); probe.qpos[:]=self.data.qpos; probe.qpos[:4]=q
        for body in self.object_bodies:
            adr=self.model.jnt_qposadr[self.model.body_jntadr[body]]
            probe.qpos[adr:adr+3]=[0,0,-5];probe.qpos[adr+3:adr+7]=[1,0,0,0]
        probe.qpos[self.stage_qpos] = q[2] / 2
        for name in ('suction_a', 'suction_b', 'suction_u'):
            probe.eq_active[self.model.equality(name).id] = False
        mujoco.mj_forward(self.model,probe)
        payload=None
        if self.pressure_kpa < -35:
            # A generic catalog box beneath TCP, independent of the simulator object ID.
            body=self.object_bodies[0];adr=self.model.jnt_qposadr[self.model.body_jntadr[body]]
            probe.qpos[adr:adr+3]=probe.site_xpos[self.tcp_id]+np.array([0,0,-.025])
            probe.qpos[adr+3:adr+7]=probe.xquat[self.tool_id]
            payload='parcel_a';mujoco.mj_forward(self.model,probe)
        contacts=self._prohibited_contacts(probe,payload)
        return sorted(contacts)[0] if contacts else None

    def stop_motion(self):
        # Continue from the last command with continuous position/velocity, bounded deceleration.
        q0=self.data.ctrl.copy();v0=self._command_velocity.copy()
        duration=max(.10,float(np.max(np.abs(v0)/ACCELERATION))*np.pi/2)
        n=int(np.ceil(duration/self.model.opt.timestep));duration=n*self.model.opt.timestep
        target=q0+v0*duration/2
        distance_limited=bool(np.any(target<JOINT_LOWER) or np.any(target>JOINT_UPPER))
        if distance_limited or self._active_contacts:
            q0=self.joints;v0=np.zeros(4);self.data.ctrl[:]=q0
        self._stopping=True
        try:
            for i in range(1,n+1):
                t=i*self.model.opt.timestep
                self.data.ctrl[:]=q0+v0*(t/2+duration*np.sin(np.pi*t/duration)/(2*np.pi))
                self.step()
                if self._active_contacts:
                    self.data.ctrl[:]=self.joints
                    break
            self._command_velocity[:]=0
            for _ in range(70):self.step()
        finally:self._stopping=False
        return {'motion_settled':bool(np.max(np.abs(self.data.qvel[:4]))<.02),'distance_limited':distance_limited,'contact_pairs':sorted(self._active_contacts),'valve_retained':self.valve}

    def move_to(self,xyz,allow_contact=True):
        try: target=scara_ik(np.array(xyz))
        except ValueError as e: raise OperationError(str(e)) from e
        t,traj=quintic_trajectory(self.data.ctrl.copy(),target,dt=self.model.opt.timestep)
        # Dense sampling (<=25ms) is conservative for static obstacles but is not continuous collision proof.
        for q in traj[::max(1,int(.025/self.model.opt.timestep))]:
            obstacle=self._collision_at(q,allow_contact)
            if obstacle: raise OperationError('PATH_BLOCKED',{'obstacle':obstacle})
        for q in traj[1:]:
            self._command_velocity=(q-self.data.ctrl)/self.model.opt.timestep
            self.data.ctrl[:]=q; self.step()
        self.data.ctrl[:]=target;self._command_velocity[:]=0
        for _ in range(160):
            self.step()
            if np.max(np.abs(self.data.qpos[:4]-target))<.001 and np.max(np.abs(self.data.qvel[:4]))<.005: break
        else: raise OperationError('TRACKING_TIMEOUT',{'error':(self.data.qpos[:4]-target).tolist()})
        return {'sim_duration_s':float(t[-1]),'target':target.tolist(),'actual':self.joints.tolist()}

    def truth_summary(self):
        # ONLY evaluator/test/physics diagnostics may call this; never used for control goals.
        result=[]
        for n,b in zip(['SKU-RED-A','SKU-RED-B','SKU-UNKNOWN'],self.object_bodies):
            qadr=self.model.jnt_qposadr[self.model.body_jntadr[b]]
            dadr=self.model.jnt_dofadr[self.model.body_jntadr[b]]
            if self.bin_layout is None:
                inside = np.all(np.abs(self.data.xpos[b,:2]-BIN_CENTER)<BIN_HALF-np.array([.032,.026])) and .085<self.data.xpos[b,2]<.14
            else:
                # All eight world corners must project inside the actual rotated opening
                # and the lowest point must have settled onto its physical floor.
                offsets = np.array(list(product((-1, 1), repeat=3))) * np.array([.032, .026, .025])
                corners = self.data.xpos[b] + offsets @ self.data.xmat[b].reshape(3, 3).T
                inside = (abs(corners[:, 2].min() - .072) < .004
                          and any(fixture.contains_xy(corners[:, :2]) for fixture in self.bin_layout))
            result.append({'sku':n,'position':self.data.xpos[b].tolist(),'speed_m_s':float(np.linalg.norm(self.data.qvel[dadr:dadr+3])),'in_bin':bool(inside)})
        return {'objects':result,'attached':self.attached,'drop_count':self.drop_count,'collision_count':self.collision_count}
