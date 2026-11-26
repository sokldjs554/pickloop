"""Plan in a reconstructed LiDAR grid without a surveyed map or landmarks."""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree

from .mobile import MobileHold, MobileMap


def _xy(point):
    point = np.asarray(point, dtype=float)
    if point.shape != (2,) or not np.isfinite(point).all():
        raise ValueError('expected a finite XY point')
    return point


class SlamNavigationMap:
    """A* on a ray-carved grid, with every non-free cell treated as blocked.

    Coordinates are metres in the first-scan frame. ``origin`` locates the
    lower left cell corner, and the A* lattice is at cell centres.
    """

    def __init__(self, occupancy, origin, resolution, *, radius, margin=0.):
        grid = np.asarray(occupancy)
        if grid.ndim != 2 or not grid.size or not np.isin(grid, [-1, 0, 100]).all():
            raise ValueError('expected a nonempty grid of unknown (-1), free (0) or occupied (100) cells')
        if not all(map(math.isfinite, (resolution, radius, margin))) or resolution <= 0 or min(radius, margin) < 0:
            raise ValueError('expected positive grid resolution and nonnegative footprint and margin')
        self.origin = _xy(origin).copy()
        self.resolution = resolution
        self.radius = radius
        self.margin = margin
        self._upper = self.origin + resolution * np.asarray(grid.shape[::-1])
        self._half_diagonal = resolution / math.sqrt(2.)
        rows, cols = np.nonzero(grid != 0)
        self._blocked = cKDTree(self.origin + resolution * (np.column_stack((cols, rows)) + .5))

    def _point_clearance(self, points):
        boundary = np.minimum(points - self.origin, self._upper - points).min(axis=-1)
        distance, _ = self._blocked.query(points)
        # The square cell fits inside a disc of this radius around its centre.
        return np.minimum(boundary, distance - self._half_diagonal)

    def clear(self, point, radius):
        return bool(self._point_clearance(_xy(point)) > radius)

    def segment_clearance(self, start, end):
        """Conservative lower bound on centreline clearance over a segment."""
        start, end = _xy(start), _xy(end)
        endpoints = np.vstack((start, end))
        if np.any(endpoints < self.origin) or np.any(endpoints > self._upper):
            return -math.inf
        distance = math.dist(start, end)
        intervals = max(1, math.ceil(distance / (.5 * self.resolution)))
        samples = np.linspace(start, end, intervals + 1)
        # Any unsampled point is within half a step of one of the samples.
        return float(self._point_clearance(samples).min() - distance / (2 * intervals))

    def segment_clear(self, start, end):
        return self.segment_clearance(start, end) > self.radius + self.margin

    def plan(self, start, goal):
        """Return a footprint-checked path in metres or raise ``NO_PATH``."""
        start, goal = _xy(start), _xy(goal)
        if self.segment_clear(start, goal):
            return [start.tolist(), goal.tolist()]
        lattice = _GridLattice(self)
        route = [np.asarray(point) + lattice.offset
                 for point in lattice.plan(start - lattice.offset, goal - lattice.offset)]
        route[0], route[-1] = start, goal
        if not all(self.segment_clear(a, b) for a, b in zip(route, route[1:])):
            raise MobileHold('NO_PATH')
        return [point.tolist() for point in route]


class _GridLattice(MobileMap):
    """Present the SLAM grid geometry to the existing A* implementation."""

    def __init__(self, grid):
        self.grid = grid
        self.resolution, self.radius, self.margin = grid.resolution, grid.radius, grid.margin
        self.offset = grid.origin + self.resolution / 2
        # A point between adjacent nodes is at most half an edge from either
        # end. Reserve that distance and the sweep audit's sample allowance.
        self.edge_allowance = self.resolution / math.sqrt(2.) + self.resolution / 4

    def clear(self, point, radius):
        return self.grid.clear(point + self.offset, radius + self.edge_allowance)

    def segment_clear(self, start, end):
        return self.grid.segment_clear(start + self.offset, end + self.offset)
