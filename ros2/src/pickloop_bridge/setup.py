from setuptools import setup
setup(name='pickloop_bridge',version='0.1.0',packages=['pickloop_bridge'],
      data_files=[('share/ament_index/resource_index/packages',['resource/pickloop_bridge']),
                  ('share/pickloop_bridge',['package.xml'])],
      install_requires=['setuptools'],zip_safe=True,
      maintainer='PickLoop contributors',maintainer_email='maintainer@example.invalid',
      description='ROS2 task action bridge for PickLoop',license='Apache-2.0',
      entry_points={'console_scripts':['bridge=pickloop_bridge.node:main','pick_client=pickloop_bridge.client:main']})
