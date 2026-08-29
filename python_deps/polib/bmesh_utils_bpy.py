# copyright (c) 2018- polygoniq xyz s.r.o.

import bmesh
import enum
import typing


class ElementCollection(enum.StrEnum):
    VERTS = "verts"
    EDGES = "edges"
    FACES = "faces"
    LOOPS = "loops"


class LayerType(enum.StrEnum):
    BOOL = "bool"
    COLOR = "color"
    FLOAT = "float"
    FLOAT_COLOR = "float_color"
    FLOAT_VECTOR = "float_vector"
    INT = "int"
    STRING = "string"


BM_COLLECTION_TO_BM_TYPE_MAP = {
    ElementCollection.VERTS: bmesh.types.BMVert,
    ElementCollection.EDGES: bmesh.types.BMEdge,
    ElementCollection.FACES: bmesh.types.BMFace,
    ElementCollection.LOOPS: bmesh.types.BMLoop,
}

BMElement: typing.TypeAlias = (
    bmesh.types.BMVert | bmesh.types.BMEdge | bmesh.types.BMFace | bmesh.types.BMLoop
)

BMElementCollection: typing.TypeAlias = (
    bmesh.types.BMVertSeq | bmesh.types.BMEdgeSeq | bmesh.types.BMFaceSeq | bmesh.types.BMLoopSeq
)


@typing.overload
def get_active_element(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.VERTS],
) -> bmesh.types.BMVert | None: ...


@typing.overload
def get_active_element(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.EDGES],
) -> bmesh.types.BMEdge | None: ...


@typing.overload
def get_active_element(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.FACES],
) -> bmesh.types.BMFace | None: ...


@typing.overload
def get_active_element(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.LOOPS],
) -> bmesh.types.BMLoop | None: ...


@typing.overload
def get_active_element(
    bm: bmesh.types.BMesh,
    element_type: ElementCollection,
) -> BMElement | None: ...


def get_active_element(bm: bmesh.types.BMesh, element_type: ElementCollection) -> BMElement | None:
    """Get currently active vertex | edge | face | loop

    For loops, the active element is inferred from the active edge in select history:
    the selected loop whose edge is the active edge and whose link_loop_prev.edge is also selected.
    Returns `None` in case there is currently no active element of the selected type.
    """
    if bm.select_history.active is None:
        return None

    if element_type == ElementCollection.LOOPS:
        active_element = bm.select_history.active

        if isinstance(active_element, bmesh.types.BMEdge):
            for loop in active_element.link_loops:
                if loop.link_loop_prev.edge.select:
                    return loop

            for loop in active_element.link_loops:
                if loop.link_loop_next.edge.select:
                    return loop.link_loop_next

    if isinstance(bm.select_history.active, BM_COLLECTION_TO_BM_TYPE_MAP[element_type]):
        return bm.select_history.active
    return None


@typing.overload
def get_selected_elements(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.VERTS],
) -> typing.Iterator[bmesh.types.BMVert]: ...


@typing.overload
def get_selected_elements(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.EDGES],
) -> typing.Iterator[bmesh.types.BMEdge]: ...


@typing.overload
def get_selected_elements(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.FACES],
) -> typing.Iterator[bmesh.types.BMFace]: ...


@typing.overload
def get_selected_elements(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.LOOPS],
) -> typing.Iterator[bmesh.types.BMLoop]: ...


@typing.overload
def get_selected_elements(
    bm: bmesh.types.BMesh,
    element_type: ElementCollection,
) -> typing.Iterator[BMElement]: ...


def get_selected_elements(
    bm: bmesh.types.BMesh,
    element_type: ElementCollection,
) -> typing.Iterator[BMElement]:
    """Get currently selected vertices | edges | faces | loops from the provided bmesh element collection"""
    if element_type == ElementCollection.LOOPS:
        # BMLoopSeq is not directly iterable, we yield loops based on selected edges.
        # In bmesh, each loop belongs to exactly one face, and each face has exactly one loop per edge.
        # The if loop.link_loop_prev.edge.select ensures only one loop is considered selected when user
        # selects a corner by selecting the two edges that form the corner.
        return (
            loop
            for edge in bm.edges
            if edge.select
            for loop in edge.link_loops
            if loop.link_loop_prev.edge.select
        )
    collection = getattr(bm, element_type)
    return (elem for elem in collection if elem.select)


@typing.overload
def iter_bm_elements(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.VERTS],
) -> typing.Iterator[bmesh.types.BMVert]: ...


@typing.overload
def iter_bm_elements(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.EDGES],
) -> typing.Iterator[bmesh.types.BMEdge]: ...


@typing.overload
def iter_bm_elements(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.FACES],
) -> typing.Iterator[bmesh.types.BMFace]: ...


@typing.overload
def iter_bm_elements(
    bm: bmesh.types.BMesh,
    element_type: typing.Literal[ElementCollection.LOOPS],
) -> typing.Iterator[bmesh.types.BMLoop]: ...


@typing.overload
def iter_bm_elements(
    bm: bmesh.types.BMesh,
    element_type: ElementCollection,
) -> typing.Iterator[BMElement]: ...


def iter_bm_elements(
    bm: bmesh.types.BMesh, element_type: ElementCollection
) -> typing.Iterator[BMElement]:
    """Iterate all elements of the given bmesh collection by name.

    Unlike `getattr(bm, element_collection_name)`, this works correctly for 'loops'
    which is not directly iterable in Blender's API.
    """
    if element_type == ElementCollection.LOOPS:
        return (loop for face in bm.faces for loop in face.loops)
    return iter(getattr(bm, element_type))


def is_element_selected(
    element: BMElement,
) -> bool:
    """Check if the provided vertex | edge | face | loop is selected

    For loops, selection is inferred from the loop's edge and the previous loop's edge being selected.
    """
    if isinstance(element, bmesh.types.BMLoop):
        return element.edge.select and element.link_loop_prev.edge.select
    return element.select


_LAST_SELECTED_INDEX_CACHE: dict[type, int | None] = {
    bmesh.types.BMVertSeq: None,
    bmesh.types.BMEdgeSeq: None,
    bmesh.types.BMFaceSeq: None,
}


def is_any_element_selected(
    bm: bmesh.types.BMesh,
    element_type: ElementCollection,
) -> bool:
    """Check if there is any selected vertex | edge | face | loop in the provided bmesh element collection

    Uses caching of the last selected index to speed up the check in case the same element is still
    selected. The cache is primarily designed to work with one mesh, switching between meshes will
    usually result in cache invalidation.
    """
    # Loops are not directly selectable. Last selected edge is cached instead and we check for selected loops on that edge
    is_loop = element_type == ElementCollection.LOOPS
    if is_loop:
        element_collection = bm.edges
        collection_type = bmesh.types.BMEdgeSeq
    else:
        element_collection = getattr(bm, element_type)
        collection_type = type(element_collection)

    last_index = _LAST_SELECTED_INDEX_CACHE[collection_type]
    element_collection.ensure_lookup_table()
    if (
        last_index is not None
        and last_index < len(element_collection)
        and element_collection[last_index].select
        and (
            not is_loop
            or any(
                loop.link_loop_prev.edge.select
                for loop in element_collection[last_index].link_loops
            )
        )
    ):
        return True

    for element in element_collection:
        if element.select and (
            not is_loop or any(loop.link_loop_prev.edge.select for loop in element.link_loops)
        ):
            _LAST_SELECTED_INDEX_CACHE[collection_type] = element.index
            return True

    _LAST_SELECTED_INDEX_CACHE[collection_type] = None
    return False


def get_layer(
    element_collection: BMElementCollection,
    layer_type: LayerType,
    layer_name: str,
) -> bmesh.types.BMLayerItem | None:
    """Get bmesh layer with the provided name and type from the provided element collection

    Returns `None` in case there is no layer with the provided name and type.
    """
    return getattr(element_collection.layers, layer_type.value, {}).get(layer_name, None)


def has_edge_neighbor(edge: bmesh.types.BMEdge) -> bool:
    """Check if the provided edge has any neighboring edge (i.e. edge sharing a vertex with the provided edge)"""
    return any(edge_neighbors(edge))


def edge_neighbors(edge: bmesh.types.BMEdge) -> typing.Iterator[bmesh.types.BMEdge]:
    """Get neighboring edges of the provided edge (i.e. edges sharing a vertex with the provided edge)"""
    yield from (
        neighbor_edge for neighbor_edge in edge.verts[0].link_edges if neighbor_edge != edge
    )
    yield from (
        neighbor_edge for neighbor_edge in edge.verts[1].link_edges if neighbor_edge != edge
    )


def shared_vertex(
    edge1: bmesh.types.BMEdge, edge2: bmesh.types.BMEdge
) -> bmesh.types.BMVert | None:
    """Get shared vertex of the provided edges, if it exists"""
    if edge1.verts[0] == edge2.verts[0] or edge1.verts[0] == edge2.verts[1]:
        return edge1.verts[0]
    if edge1.verts[1] == edge2.verts[0] or edge1.verts[1] == edge2.verts[1]:
        return edge1.verts[1]
    return None


def edge_verts_ordered_by_index(
    edge: bmesh.types.BMEdge,
) -> tuple[bmesh.types.BMVert, bmesh.types.BMVert]:
    """Get vertices of the provided edge ordered by their indices"""
    v1, v2 = edge.verts
    if v1.index < v2.index:
        return v1, v2
    else:
        return v2, v1


FaceTriangulation: typing.TypeAlias = dict[
    bmesh.types.BMFace, list[tuple[bmesh.types.BMVert, bmesh.types.BMVert, bmesh.types.BMVert]]
]


def compute_face_triangulation(bm: bmesh.types.BMesh) -> FaceTriangulation:
    """Build a `face -> triangles` map matching n-gon tessellation.

    The result maps each bmesh face to the list of triangles produced by n-gon tessellation
    (`bm.calc_loop_triangles()`). Each triangle is a 3-tuple of `BMVert`. Faces that produce no
    triangles (degenerate) are absent from the dict, so call sites should use `.get(face)` and treat
    `None` as "no triangulation available".

    The result depends on the bmesh's current topology AND
    vertex positions: ear-clipping on concave n-gons can change when verts move,
    so callers caching the result must invalidate on any geometry edit.

    The returned `BMVert` references stay valid only while `bm` is alive; do not
    persist the dict across edit-mode toggles or other bmesh invalidations.
    """
    face_to_tris: FaceTriangulation = {}
    for tri in bm.calc_loop_triangles():
        # `tri` is a 3-tuple of `BMLoop` describing a triangle in the tessellation of `tri[0].face`.
        face_to_tris.setdefault(tri[0].face, []).append(tuple(l.vert for l in tri))
    return face_to_tris


def get_corner_split_verts(
    loop: bmesh.types.BMLoop,
    face_tris: list[tuple[bmesh.types.BMVert, bmesh.types.BMVert, bmesh.types.BMVert]] | None,
) -> list[bmesh.types.BMVert]:
    """Return diagonal-target verts for `loop`'s corner, ordered around the face.

    A diagonal target is a face vertex connected to `loop.vert` by an internal
    triangulation edge generated by n-gon tessellation. The result is ordered as encountered
    when walking `face.loops` from `loop.link_loop_next` toward `loop.link_loop_prev`.

    Args:
        loop: Corner whose diagonals are being queried; the corner vertex is `loop.vert`
            and the bounding edges are `loop.edge` and `loop.link_loop_prev.edge`.
        face_tris: Triangulation of `loop.face` as produced by `compute_face_triangulation`
            (the value of `FaceTriangulation[loop.face]`). `None` or an empty list means
            no triangulation is available for this face and the result is an empty list.
    """
    if face_tris is None or len(face_tris) == 0:
        return []
    v = loop.vert
    next_v = loop.link_loop_next.vert
    prev_v = loop.link_loop_prev.vert
    # Collect all face vertices connected to `v` by a triangulation edge
    diag_neighbors: set[bmesh.types.BMVert] = set()
    for tri in face_tris:
        if v in tri:
            for w in tri:
                if w is not v and w is not next_v and w is not prev_v:
                    diag_neighbors.add(w)
    if len(diag_neighbors) == 0:
        return []
    # Walk the face loops from `next_v` to `prev_v` and collect the diagonal neighbors in order
    ordered: list[bmesh.types.BMVert] = []
    walker = loop.link_loop_next.link_loop_next  # first loop strictly between next_v and prev_v
    while walker is not loop.link_loop_prev:
        if walker.vert in diag_neighbors:
            ordered.append(walker.vert)
        walker = walker.link_loop_next
    return ordered
