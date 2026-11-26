import numpy as np
import pytest

from pickloop.mobile import MobileHold
from pickloop.slam_navigation import SlamNavigationMap


def test_astar_routes_around_a_blocked_sweep_and_preserves_endpoints():
    grid = np.zeros((20, 25), dtype=np.int8)
    grid[4:13, 12:14] = 100
    world = SlamNavigationMap(grid, [-.13, .08], .1, radius=.12, margin=.02)
    start, goal = [.34, .83], [1.92, .76]

    assert not world.segment_clear(start, goal)
    path = world.plan(start, goal)
    assert path[0] == start
    assert path[-1] == goal
    assert len(path) > 2
    assert all(world.segment_clear(a, b) for a, b in zip(path, path[1:]))
    assert world.plan(start, goal) == path


@pytest.mark.parametrize('blocked', [-1, 100])
def test_astar_refuses_to_cross_a_nonfree_barrier_between_free_endpoints(blocked):
    grid = np.zeros((20, 25), dtype=np.int8)
    grid[:, 12] = blocked
    world = SlamNavigationMap(grid, [0., 0.], .1, radius=.12)
    start, goal = [.4, .8], [2., .8]

    assert world.clear(start, .12)
    assert world.clear(goal, .12)
    with pytest.raises(MobileHold, match='NO_PATH'):
        world.plan(start, goal)


def test_sweep_checks_footprint_beside_the_route_and_at_grid_boundary():
    grid = np.zeros((20, 25), dtype=np.int8)
    grid[9, 12] = -1
    world = SlamNavigationMap(grid, [0., 0.], .1, radius=.12, margin=.03)

    assert not world.segment_clear([.4, .77], [2., .77])
    assert world.segment_clear([.4, .55], [2., .55])
    assert not world.segment_clear([.10, .4], [.10, 1.6])
