#!/usr/bin/python3
# copyright (c) 2018- polygoniq xyz s.r.o.

import bpy
import itertools
import mathutils
import math
import typing
import abc


class BoundingBox(abc.ABC):
    """Bounding box base class"""

    def __init__(
        self,
        min: typing.Optional[mathutils.Vector] = None,
        max: typing.Optional[mathutils.Vector] = None,
    ):
        self.min = min if min is not None else mathutils.Vector((math.inf,) * 3)
        self.max = max if max is not None else mathutils.Vector((-math.inf,) * 3)

    def is_valid(self) -> bool:
        """Checks whether this bounding box is valid

        Bounding box is valid if and only if its volume is non-negative,
        any bounding box becomes valid if it was extended by at least one point or any other object.
        """
        for min_field, max_field in zip(self.min, self.max):
            if min_field > max_field:
                return False
        return True

    def get_eccentricity(self) -> mathutils.Vector:
        """Returns relative eccentricity in each axis."""
        assert self.is_valid(), "Bounding box is not valid"
        return (self.max - self.min) / 2.0

    def get_center(self) -> mathutils.Vector:
        assert self.is_valid(), "Bounding box is not valid"
        return (self.min + self.max) / 2.0

    def get_size(self) -> mathutils.Vector:
        assert self.is_valid(), "Bounding box is not valid"
        return self.max - self.min

    def get_corners(self) -> typing.Iterable[mathutils.Vector]:
        assert self.is_valid(), "Bounding box is not valid"
        for i, j, k in itertools.product([self.min, self.max], repeat=3):
            yield mathutils.Vector((i.x, j.y, k.z))

    def extend_by_point(self, point: mathutils.Vector) -> None:
        """Extends this bounding box by given infinitesimal point

        Point must be in the same space as the bounding box.

        This makes sure the resulting bounding box contains everything it contained before, plus
        the given point.
        """
        self.min.x = min(self.min.x, point.x)
        self.min.y = min(self.min.y, point.y)
        self.min.z = min(self.min.z, point.z)

        self.max.x = max(self.max.x, point.x)
        self.max.y = max(self.max.y, point.y)
        self.max.z = max(self.max.z, point.z)

    @abc.abstractmethod
    def extend_by_object(self, obj: bpy.types.Object) -> None:
        raise NotImplementedError


class AlignedBox(BoundingBox):
    """Axis-aligned bounding box"""

    def extend_by_point(self, point: mathutils.Vector) -> None:
        """Extends this bounding box by given infinitesimal point

        Point must be in world space.

        This makes sure the resulting bounding box contains everything it contained before, plus
        the given point.
        """
        super().extend_by_point(point)

    def extend_by_object(
        self,
        obj: bpy.types.Object,
        parent_collection_matrix: mathutils.Matrix = mathutils.Matrix.Identity(4),
    ) -> None:
        """Extend the bounding box to cover given object

        If the AlignedBox is extended by object then min_x, max_x,... values are in world space,
        not object local space. When object moves after initialization of the AlignedBox,
        coordinate properties are not recomputed to match new object's position - this class does
        not store any reference to initialization objects.
        AlignedBox computes boundaries even for instanced collection objects, that's its main
        difference compared to the bound_box property of bpy.types.Object.

        Note: Other methods of this class are space-neutral but this method only makes sense if
        the bounding box is considered a world-space bounding box.
        """
        # matrix_world is matrix relative to object's blend.
        # Thus collection objects have offset inside collection defined by their matrix_world.
        # We need to multiply parent_collection_matrix by obj.matrix_world in recursion
        # to get matrix relevant to top-most collection world space.
        obj_matrix = parent_collection_matrix @ obj.matrix_world
        # if object is a collection, it has bounding box ((0,0,0), (0,0,0), ...)
        # we need to manually traverse objects from collections and extend main bounding box
        # to contain all objects
        if obj.instance_type == 'COLLECTION':
            collection = obj.instance_collection
            if collection is not None:  # if this happens we assume no objects
                for collection_obj in collection.objects:
                    self.extend_by_object(collection_obj, obj_matrix)
        else:
            for corner in obj.bound_box:
                self.extend_by_point(obj_matrix @ mathutils.Vector(corner))

    def __str__(self):
        return (
            f"Aligned Box\n"
            f"X = ({self.min.x}, {self.max.x})\n"
            f"Y = ({self.min.y}, {self.max.y})\n"
            f"Z = ({self.min.z}, {self.max.z})"
        )


class OrientedBox(BoundingBox):
    """Oriented bounding box"""

    def __init__(
        self,
        matrix_world: mathutils.Matrix,
        min: typing.Optional[mathutils.Vector] = None,
        max: typing.Optional[mathutils.Vector] = None,
    ):
        """Constructs oriented bounding box with given world matrix

        Optionally, min and max corners (in bbox local space) can be provided.
        """
        super().__init__(min, max)
        self.matrix_world = matrix_world
        self.inverse_matrix_world = matrix_world.inverted()

    def extend_by_point(self, point: mathutils.Vector) -> None:
        """Extends this bounding box by given infinitesimal point

        Point must be in the local space of the bounding box.

        This makes sure the resulting bounding box contains everything it contained before, plus
        the given point.
        """
        return super().extend_by_point(point)

    def extend_by_object(
        self,
        obj: bpy.types.Object,
        recursive: bool = False,
        transform_matrix: mathutils.Matrix = mathutils.Matrix.Identity(4),
    ) -> None:
        """Extend the bounding box to cover given object

        If recursive is True, the function will traverse the object's children and extend the bbox
        to cover all of them. (Ignored for collections, as they behave like a single object)

        When object moves after initialization of the OrientedBox, coordinate properties
        are not recomputed to match new object's position - this class does not store
        any reference to initialization objects. OrientedBox computes boundaries
        even for instanced collection objects, that's its main difference compared
        to the bound_box property of bpy.types.Object.
        """
        # if object is a collection, it has bounding box ((0,0,0), (0,0,0), ...)
        # we need to manually traverse objects from collections and extend main bounding box
        # to contain all objects
        if obj.instance_type == 'COLLECTION':
            collection = obj.instance_collection
            if collection is not None:  # if this happens we assume no objects
                for collection_obj in collection.objects:
                    self.extend_by_object(
                        collection_obj, True, transform_matrix @ collection_obj.matrix_local
                    )
        else:
            for corner in obj.bound_box:
                self.extend_by_point(transform_matrix @ mathutils.Vector(corner))
            if recursive:
                for child in obj.children:
                    self.extend_by_object(child, recursive, transform_matrix @ child.matrix_local)

    def __str__(self) -> str:
        return (
            f"Oriented Box\n"
            f"Matrix = {self.matrix_world}\n"
            f"X = ({self.min.x}, {self.max.x})\n"
            f"Y = ({self.min.y}, {self.max.y})\n"
            f"Z = ({self.min.z}, {self.max.z})"
        )
