#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import itertools
import mathutils
import math
import collections.abc


class BoundingBox:
    """Bounding box for enclosing multiple objects

    This class can represent both axis-aligned and oriented bounding boxes.
    Use `matrix` property to determine the orientation and position of the bounding box.

    Note that bounding box is a static snapshot of the objects at the time they were added.
    Moving or transforming the objects after they were added does not affect the bounding box.
    """

    def __init__(
        self,
        matrix: mathutils.Matrix = mathutils.Matrix.Identity(4),
        min: mathutils.Vector | None = None,
        max: mathutils.Vector | None = None,
    ):
        """Constructs bounding box with given local-to-world matrix.

        For oriented bounding boxes, the matrix is the world matrix of the bounding box.
        For axis-aligned bounding boxes, the matrix is always identity matrix. (default value)
        """
        self._matrix = matrix.copy()
        self._inverse_matrix = self._matrix.inverted()
        # Min and max corners in bounding box local space
        self._min = mathutils.Vector((math.inf,) * 3) if min is None else min.copy()
        self._max = mathutils.Vector((-math.inf,) * 3) if max is None else max.copy()

    def is_valid(self) -> bool:
        """Checks whether this bounding box is valid.

        Bounding box is valid if and only if its volume is non-negative.
        Any bounding box becomes valid if it was extended by at least one point or any object.
        """
        for min_field, max_field in zip(self._min, self._max):  # type: ignore
            if min_field > max_field:
                return False
        return True

    def get_min(self, world: bool = False) -> mathutils.Vector:
        """Returns min corner in local or world space."""
        assert self.is_valid(), "Bounding box is not valid"
        if world:
            return self._matrix @ self._min
        return self._min.copy()

    def get_max(self, world: bool = False) -> mathutils.Vector:
        """Returns max corner in local or world space."""
        assert self.is_valid(), "Bounding box is not valid"
        if world:
            return self._matrix @ self._max
        return self._max.copy()

    def get_eccentricity(self) -> mathutils.Vector:
        """Returns relative eccentricity in each axis.

        Note that eccentricity respects the orientation and scale of the bounding box.
        """
        assert self.is_valid(), "Bounding box is not valid"
        return (self._max - self._min) / 2.0

    def get_center(self, world: bool = False) -> mathutils.Vector:
        """Returns center of the bounding box in local or world space."""
        assert self.is_valid(), "Bounding box is not valid"
        center = (self._min + self._max) / 2.0
        if world:
            return self._matrix @ center
        return center

    def get_size(self, world: bool = False) -> mathutils.Vector:
        """Returns size of the bounding box in each axis.

        Note that size is always computed along the bounding box's local axes.
        If `world` is set to False (default), size is in local space.
        If `world` is set to True, size will be recomputed to match world space distances.
        """
        assert self.is_valid(), "Bounding box is not valid"
        size = self._max - self._min
        if world:
            scale = self._matrix.to_scale()
            size.x *= abs(scale.x)
            size.y *= abs(scale.y)
            size.z *= abs(scale.z)
        return size

    def get_corners(self, world: bool = False) -> collections.abc.Iterable[mathutils.Vector]:
        """Yields all 8 corners of the bounding box in local or world space."""
        assert self.is_valid(), "Bounding box is not valid"
        for i, j, k in itertools.product([self._min, self._max], repeat=3):
            corner = mathutils.Vector((i.x, j.y, k.z))
            if world:
                corner = self._matrix @ corner
            yield corner

    def extend_by_local_point(self, point: mathutils.Vector) -> None:
        """Extends this bounding box by given infinitesimal point

        Point must be in the local space of the bounding box.

        This makes sure the resulting bounding box contains everything it contained before, plus
        the given point.
        """
        self._min.x = min(self._min.x, point.x)
        self._min.y = min(self._min.y, point.y)
        self._min.z = min(self._min.z, point.z)

        self._max.x = max(self._max.x, point.x)
        self._max.y = max(self._max.y, point.y)
        self._max.z = max(self._max.z, point.z)

    def extend_by_world_point(self, point: mathutils.Vector) -> None:
        """Extends this bounding box by given infinitesimal point.

        Point must be in world space.

        This makes sure the resulting bounding box contains everything it contained before, plus
        the given point.
        """
        self.extend_by_local_point(self._inverse_matrix @ point)

    def extend_by_object(
        self,
        obj: bpy.types.Object,
        recursive: bool = False,
        object_filter: collections.abc.Callable[[bpy.types.Object], bool] = lambda o: True,
        parent_collection_matrix: mathutils.Matrix = mathutils.Matrix.Identity(4),
    ) -> None:
        """Extend the bounding box to cover given object.

        Note: Coordinate properties are recomputed only when extending by the object.
        This class does not store any reference to initialization objects and won't update
        the bounding box when objects move.

        Warning: Method uses obj.bound_box for speed-up. This may result in bounding box
        that is not tight.

        Arguments:
            - obj: Object to cover. Can be also a collection instance (e.g. linked asset).
            - recursive: If True, traverse the object's children and extend the bbox to cover all of
                them. (Ignored for collections, as they behave like a single object)
            - object_filter: A callable that takes an object and returns True if the object
                should be included in the bounding box, False otherwise. (default: include all)
            - parent_collection_matrix: Matrix transforming objects from their collection space to
                world space. This is needed as obj.matrix_world of objects inside the instanced
                collection is relative to the instance.
        """
        # Special handling of collection instances
        if obj.instance_type == 'COLLECTION':
            collection = obj.instance_collection
            if collection is not None:  # if this happens we assume no objects
                for collection_obj in collection.objects:
                    self.extend_by_object(
                        collection_obj,
                        True,
                        object_filter,
                        parent_collection_matrix @ obj.matrix_world,
                    )
            return
        # Other instance types are not supported. Only the underlying object is considered.

        # Extend bbox
        if object_filter(obj):
            # We use bounding box of bounding boxes approximation.
            # This might lead to non-tight bounding box if objects are oriented differently
            # than the bounding box itself.
            # TODO: this could be improved for some object types - meshes, curves, etc.
            obj_local_2_bbox_local = (
                self._inverse_matrix @ parent_collection_matrix @ obj.matrix_world
            )
            vertices_local = (
                obj_local_2_bbox_local @ mathutils.Vector(corner) for corner in obj.bound_box
            )
            for v in vertices_local:
                self.extend_by_local_point(v)

        # Extend by children
        if recursive:
            for child in obj.children:
                self.extend_by_object(child, recursive, object_filter, parent_collection_matrix)

    def __str__(self):
        return (
            f"Bounding Box\n"
            f"Matrix = {self._matrix}\n"
            f"X = ({self._min.x}, {self._max.x})\n"
            f"Y = ({self._min.y}, {self._max.y})\n"
            f"Z = ({self._min.z}, {self._max.z})"
        )
