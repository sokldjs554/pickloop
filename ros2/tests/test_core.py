import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'src/pickloop_bridge'))

class CoreContractTests(unittest.TestCase):
    def test_progress_uses_observed_frames_or_events_without_truth(self):
        from pickloop_bridge.core import progress
        sample={'run_id':'r1','state':'SEAL','events':[{'sim_time':1.25,'attempt':2}],
                'final_truth':{'sim_time':999, 'joints':[9]*4}}
        self.assertEqual(progress(sample), ('SEAL','r1',1.25,2))

    def test_camera_path_stays_inside_run_directory(self):
        from pickloop_bridge.core import camera_path
        self.assertEqual(camera_path('r1','frames/001-camera.jpg'), '/runs/r1/frames/001-camera.jpg')
        for bad in ('../secret','https://evil/a','/etc/passwd','frames/../../secret'):
            with self.assertRaises(ValueError):camera_path('r1',bad)

if __name__ == '__main__':unittest.main()
