import os
import tempfile
import math
import streamlit as st

try:
    import ezdxf
except ImportError:
    ezdxf = None


st.set_page_config(
    page_title="Bridge 462 Dynamic CAD Generator",
    page_icon="📐",
    layout="wide",
)

st.title("📐 Bridge 462 Dynamic CAD Generator")
st.caption(
    "Edits the existing master DXF. Barrel length, track count, "
    "attached assemblies, repeated plan/detail views and existing pipe "
    "length are updated together."
)


# ============================================================
# MASTER DRAWING CONSTANTS
# These values come from the supplied master_plan1.dxf.
# ============================================================

MASTER_LEFT = 1817527.993068192
MASTER_RIGHT = 1847667.993068192
MASTER_LENGTH_MM = 30140.0

# Main drawing window. The title block and notes outside this area
# are intentionally protected.
VIEW_X_MIN = 1810000.0
VIEW_X_MAX = 1855500.0
VIEW_Y_MIN = -617500.0
VIEW_Y_MAX = -590500.0

TRACK_BLOCK_NAME = "Prop. Track Structure"

TRACK_SECTION_Y = -593856.4102987697

SECTION_LABEL_Y = -591444.5159887477
PLAN_LABEL_Y = -602922.9663123128

TRACK_NAMES = [
    "℄ OF COMMON LOOP LINE",
    "℄ OF UP MAIN",
    "℄ OF DN MAIN",
    "℄ OF DN LOOP LINE",
]


# ============================================================
# DXF
# ============================================================

def read_dxf(uploaded_file):
    if ezdxf is None:
        raise RuntimeError(
            "ezdxf is not installed. Add ezdxf to requirements.txt."
        )

    raw = uploaded_file.getvalue()

    if not raw:
        raise RuntimeError("The uploaded DXF is empty.")

    path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".dxf",
            delete=False,
        ) as temp:
            temp.write(raw)
            temp.flush()
            path = temp.name

        try:
            return ezdxf.readfile(path)
        except Exception:
            from ezdxf import recover

            doc, auditor = recover.readfile(path)

            if auditor.has_errors:
                st.warning(
                    "DXF recovery mode was used because the source "
                    "contains audit issues."
                )

            return doc

    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


# ============================================================
# POINT / ENTITY TRANSFORMATION
# ============================================================

def p3(point, x=None, y=None):
    return (
        float(point.x if x is None else x),
        float(point.y if y is None else y),
        float(getattr(point, "z", 0.0)),
    )


def transform_x(x, old_left, old_right, new_right):
    """
    Piecewise longitudinal transformation:

      x <= old_left:
          unchanged

      old_left < x < old_right:
          stretched/compressed to the new barrel

      x >= old_right:
          translated by the barrel-length difference

    This is what makes the right wing/return and attached assembly
    move instead of remaining at the old 30140 position.
    """

    if x <= old_left:
        return x

    if x >= old_right:
        return x + (new_right - old_right)

    old_span = old_right - old_left

    if old_span <= 0:
        return x

    ratio = (new_right - old_left) / old_span

    return old_left + (x - old_left) * ratio


def entity_points(e):
    """
    Return representative points for an entity so we can decide
    whether it belongs to the main drawing window.
    """

    t = e.dxftype()

    try:
        if t == "LINE":
            return [e.dxf.start, e.dxf.end]

        if t == "LWPOLYLINE":
            return [
                (p[0], p[1], 0)
                for p in e.get_points()
            ]

        if t == "POLYLINE":
            return [
                v.dxf.location
                for v in e.vertices
            ]

        if t == "INSERT":
            return [e.dxf.insert]

        if t in ("TEXT", "MTEXT"):
            return [e.dxf.insert]

        if t in ("CIRCLE", "ARC", "ELLIPSE"):
            return [e.dxf.center]

        if t == "POINT":
            return [e.dxf.location]

        if t == "DIMENSION":
            points = []

            for name in (
                "defpoint",
                "defpoint2",
                "defpoint3",
                "text_midpoint",
            ):
                if e.dxf.hasattr(name):
                    points.append(getattr(e.dxf, name))

            return points

        if t == "HATCH":
            points = []
            for path in e.paths:
                for v in getattr(path, "vertices", []):
                    points.append((v[0], v[1], 0))
                for edge in getattr(path, "edges", []):
                    for name in ("start", "end", "center"):
                        if hasattr(edge, name):
                            q = getattr(edge, name)
                            points.append((q.x, q.y, getattr(q, "z", 0.0)))
            return points

        if t in ("SOLID", "3DFACE"):
            points = []

            for name in (
                "vtx0",
                "vtx1",
                "vtx2",
                "vtx3",
            ):
                if e.dxf.hasattr(name):
                    points.append(getattr(e.dxf, name))

            return points

    except Exception:
        return []

    return []


def inside_main_view(e):
    points = entity_points(e)

    if not points:
        return False

    for point in points:
        try:
            x = float(point[0] if not hasattr(point, "x") else point.x)
            y = float(point[1] if not hasattr(point, "y") else point.y)

            if (
                VIEW_X_MIN <= x <= VIEW_X_MAX
                and VIEW_Y_MIN <= y <= VIEW_Y_MAX
            ):
                return True

        except Exception:
            continue

    return False


def entity_xy_extents(e):
    """Return (min_x, max_x, min_y, max_y) for common model-space entities."""
    pts = entity_points(e)
    if not pts:
        return None
    xs=[]; ys=[]
    for point in pts:
        try:
            x=float(point.x if hasattr(point, "x") else point[0])
            y=float(point.y if hasattr(point, "y") else point[1])
            xs.append(x); ys.append(y)
        except Exception:
            pass
    if not xs:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def transform_hatch_x(e, transform):
    """Transform HATCH boundary geometry, including earth-cushion hatches."""
    try:
        for path in e.paths:
            if hasattr(path, "vertices"):
                # PolylinePath exposes a mutable vertex list. Mutate each
                # vertex in place; assigning a replacement list is not
                # persisted by all ezdxf versions.
                for i, v in enumerate(list(path.vertices)):
                    x=float(v[0]); y=float(v[1])
                    tail=tuple(v[2:]) if len(v) > 2 else ()
                    path.vertices[i] = (transform(x), y, *tail)
            elif hasattr(path, "edges"):
                for edge in path.edges:
                    if hasattr(edge, "start"):
                        edge.start = edge.start.replace(x=transform(edge.start.x))
                    if hasattr(edge, "end"):
                        edge.end = edge.end.replace(x=transform(edge.end.x))
                    if hasattr(edge, "center"):
                        edge.center = edge.center.replace(x=transform(edge.center.x))
    except Exception:
        # Some complex associative hatches cannot be edited safely by ezdxf.
        # The surrounding linework is still transformed.
        pass


def transform_insert_x(e, old_left, old_right, new_right, dx):
    """Move an INSERT without changing its block definition."""
    try:
        p=e.dxf.insert
        x=p.x
        # Track blocks are handled separately. Other right-side assemblies
        # move as a complete assembly when their insertion point is right of
        # the barrel end.
        if x >= old_right - 2000.0:
            e.dxf.insert = p3(p, x + dx)
        else:
            e.dxf.insert = p3(p, transform_x(x, old_left, old_right, new_right))
    except Exception:
        pass


def transform_main_entity(e, old_left, old_right, new_right, dx):
    """
    Transform the master drawing with two behaviours:

    1) Barrel/earth-cushion geometry between the two barrel ends is stretched.
    2) The complete right-hand wing/return/attached assembly is translated by
       the barrel-length difference, so its shape is NOT distorted.

    This is intentionally based on the actual 462 drawing coordinates.
    """
    ext=entity_xy_extents(e)
    if ext is None:
        return
    xmin,xmax,ymin,ymax=ext

    # Section A-A / upper barrel and plan/detail longitudinal zones.
    section_zone = (
        ymax >= -609500.0 and ymin <= -594000.0
    )
    plan_zone = (
        ymax >= -605500.0 and ymin <= -600500.0
    )

    # Right attached wing/return/earthwork assembly visible at the end of
    # Section A-A. The master geometry begins about 1.3 m before the 30140
    # barrel endpoint, so use a 2.5 m capture zone.
    right_assembly = (
        (section_zone or plan_zone)
        and xmin >= old_right - 2500.0
    )

    # Entities that cross the barrel endpoint and continue into the wing/
    # return are also treated as one attached assembly.
    crossing_right = (
        section_zone
        and xmin < old_right
        and xmax > old_right + 300.0
    )

    # The earth-cushion hatch spans exactly the original barrel and must be
    # stretched with the barrel rather than left at 30140.
    if e.dxftype() == "HATCH":
        if section_zone or plan_zone:
            transform_hatch_x(e, lambda x: transform_x(x, old_left, old_right, new_right))
        return

    if right_assembly or crossing_right:
        # Move the whole attached assembly without distorting its geometry.
        transform_entity_x_translate(e, dx)
        return

    # Normal barrel/plan geometry is stretched piecewise.
    transform_entity_x(
        e,
        old_left,
        old_right,
        new_right,
    )


def transform_entity_x_translate(e, dx):
    """Translate a complete entity in X, preserving its shape."""
    t=e.dxftype()
    try:
        if t == "LINE":
            e.dxf.start = p3(e.dxf.start, e.dxf.start.x + dx)
            e.dxf.end = p3(e.dxf.end, e.dxf.end.x + dx)
        elif t == "LWPOLYLINE":
            pts=[]
            for item in e.get_points():
                pts.append((item[0]+dx,item[1],item[2],item[3],item[4]))
            e.set_points(pts)
        elif t == "POLYLINE":
            for v in e.vertices:
                q=v.dxf.location
                v.dxf.location=p3(q,q.x+dx)
        elif t == "INSERT":
            q=e.dxf.insert
            e.dxf.insert=p3(q,q.x+dx)
        elif t in ("TEXT","MTEXT"):
            q=e.dxf.insert
            e.dxf.insert=p3(q,q.x+dx)
        elif t in ("CIRCLE","ARC","ELLIPSE"):
            q=e.dxf.center
            e.dxf.center=p3(q,q.x+dx)
        elif t == "POINT":
            q=e.dxf.location
            e.dxf.location=p3(q,q.x+dx)
        elif t == "DIMENSION":
            for name in ("defpoint","defpoint2","defpoint3","text_midpoint"):
                if e.dxf.hasattr(name):
                    q=getattr(e.dxf,name)
                    setattr(e.dxf,name,p3(q,q.x+dx))
            try: e.render()
            except Exception: pass
        elif t in ("SOLID","3DFACE"):
            for name in ("vtx0","vtx1","vtx2","vtx3"):
                if e.dxf.hasattr(name):
                    q=getattr(e.dxf,name)
                    setattr(e.dxf,name,p3(q,q.x+dx))
    except Exception:
        pass


def transform_entity_x(
    e,
    old_left,
    old_right,
    new_right,
):
    """
    Transform the existing entity itself.
    """

    t = e.dxftype()

    try:

        if t == "LINE":
            a = e.dxf.start
            b = e.dxf.end

            e.dxf.start = p3(
                a,
                transform_x(a.x, old_left, old_right, new_right),
            )

            e.dxf.end = p3(
                b,
                transform_x(b.x, old_left, old_right, new_right),
            )

        elif t == "LWPOLYLINE":
            new_points = []

            for item in e.get_points():
                new_points.append(
                    (
                        transform_x(
                            item[0],
                            old_left,
                            old_right,
                            new_right,
                        ),
                        item[1],
                        item[2],
                        item[3],
                        item[4],
                    )
                )

            e.set_points(new_points)

        elif t == "POLYLINE":
            for vertex in e.vertices:
                point = vertex.dxf.location

                vertex.dxf.location = p3(
                    point,
                    transform_x(
                        point.x,
                        old_left,
                        old_right,
                        new_right,
                    ),
                )

        elif t == "INSERT":
            point = e.dxf.insert

            e.dxf.insert = p3(
                point,
                transform_x(
                    point.x,
                    old_left,
                    old_right,
                    new_right,
                ),
            )

        elif t in ("TEXT", "MTEXT"):
            point = e.dxf.insert

            e.dxf.insert = p3(
                point,
                transform_x(
                    point.x,
                    old_left,
                    old_right,
                    new_right,
                ),
            )

        elif t in ("CIRCLE", "ARC", "ELLIPSE"):
            point = e.dxf.center

            e.dxf.center = p3(
                point,
                transform_x(
                    point.x,
                    old_left,
                    old_right,
                    new_right,
                ),
            )

        elif t == "POINT":
            point = e.dxf.location

            e.dxf.location = p3(
                point,
                transform_x(
                    point.x,
                    old_left,
                    old_right,
                    new_right,
                ),
            )

        elif t == "DIMENSION":
            for name in (
                "defpoint",
                "defpoint2",
                "defpoint3",
                "text_midpoint",
            ):
                if e.dxf.hasattr(name):
                    point = getattr(e.dxf, name)

                    setattr(
                        e.dxf,
                        name,
                        p3(
                            point,
                            transform_x(
                                point.x,
                                old_left,
                                old_right,
                                new_right,
                            ),
                        ),
                    )

            try:
                e.render()
            except Exception:
                pass

        elif t in ("SOLID", "3DFACE"):
            for name in (
                "vtx0",
                "vtx1",
                "vtx2",
                "vtx3",
            ):
                if e.dxf.hasattr(name):
                    point = getattr(e.dxf, name)

                    setattr(
                        e.dxf,
                        name,
                        p3(
                            point,
                            transform_x(
                                point.x,
                                old_left,
                                old_right,
                                new_right,
                            ),
                        ),
                    )

    except Exception:
        # Do not stop the whole drawing because one unusual entity
        # cannot be transformed.
        pass


# ============================================================
# FIND THE EXISTING BARREL DIMENSIONS
# ============================================================

def find_barrel_dimensions(doc):
    found = []

    # Exact handles in the supplied master.
    for handle in (
        "309E29D",
        "309E4EA",
    ):
        entity = doc.entitydb.get(handle)

        if (
            entity is not None
            and entity.dxftype() == "DIMENSION"
        ):
            found.append(entity)

    if len(found) >= 2:
        return found[:2]

    # Fallback: locate all 30140 dimensions.
    for entity in doc.modelspace():

        if entity.dxftype() != "DIMENSION":
            continue

        try:
            measurement = float(
                entity.dxf.actual_measurement
            )

            if abs(measurement - MASTER_LENGTH_MM) <= 10:
                found.append(entity)

        except Exception:
            pass

    return found


# ============================================================
# TRACKS
# ============================================================

def find_track_inserts(doc):
    tracks = []

    for entity in doc.modelspace():

        if entity.dxftype() != "INSERT":
            continue

        name = str(
            entity.dxf.get("name", "")
        ).upper()

        if name == TRACK_BLOCK_NAME.upper():
            tracks.append(entity)

    return sorted(
        tracks,
        key=lambda e: e.dxf.insert.x,
    )


def delete_existing_tracks(doc):
    for entity in find_track_inserts(doc):
        doc.modelspace().delete_entity(entity)


def add_tracks(
    doc,
    number_of_tracks,
    spacing_m,
    new_left,
    new_right,
):
    """
    Rebuild the track structures using the actual master block.

    Track count is independent of barrel length.

    The tracks are centred within the bridge/barrel width and use
    the user-specified track spacing.
    """

    if TRACK_BLOCK_NAME not in doc.blocks:
        raise RuntimeError(
            "The master DXF does not contain the "
            "'Prop. Track Structure' block."
        )

    delete_existing_tracks(doc)

    count = int(number_of_tracks)

    spacing_mm = max(
        float(spacing_m) * 1000.0,
        100.0,
    )

    centre = (
        new_left + new_right
    ) / 2.0

    total = (
        count - 1
    ) * spacing_mm

    first = centre - total / 2.0

    positions = [
        first + i * spacing_mm
        for i in range(count)
    ]

    for x in positions:

        insert = doc.modelspace().add_blockref(
            TRACK_BLOCK_NAME,
            (
                x,
                TRACK_SECTION_Y,
            ),
        )

        insert.dxf.rotation = 0
        insert.dxf.xscale = 1
        insert.dxf.yscale = 1
        insert.dxf.zscale = 1

    return positions


def delete_track_labels(doc):
    """
    Remove only the four original track labels in the two track
    label rows. Other notes remain untouched.
    """

    for entity in list(doc.modelspace()):

        if entity.dxftype() not in (
            "TEXT",
            "MTEXT",
        ):
            continue

        text = str(
            entity.dxf.get("text", "")
        ).upper()

        if not any(
            name.upper().replace("℄ ", "")
            in text.replace("℄ ", "")
            for name in TRACK_NAMES
        ):
            continue

        y = entity.dxf.insert.y

        if (
            abs(y - SECTION_LABEL_Y) < 100
            or abs(y - PLAN_LABEL_Y) < 100
        ):
            doc.modelspace().delete_entity(entity)


def add_track_labels(
    doc,
    track_positions,
):
    """
    Add labels for both the upper section row and the plan row.
    """

    delete_track_labels(doc)

    for row_y in (
        SECTION_LABEL_Y,
        PLAN_LABEL_Y,
    ):

        for i, x in enumerate(track_positions):

            if i < len(TRACK_NAMES):
                label = TRACK_NAMES[i]
            else:
                label = f"℄ OF TRACK {i + 1}"

            text = doc.modelspace().add_mtext(
                label,
                dxfattribs={
                    "layer": "Exist. Dimensions",
                    "char_height": 300.0,
                    "color": 242,
                },
            )

            text.dxf.insert = (
                x,
                row_y,
                0,
            )


# ============================================================
# PIPE LENGTH
# ============================================================

def update_pipe_length_dimensions(
    doc,
    new_length_mm,
):
    """
    The master contains two 30140 dimensions.

    Both are changed automatically.

    Any other 30140 dimension found after transformation is also
    updated, so the second drawing/detail does not retain 30140.
    """

    changed = 0

    for entity in doc.modelspace():

        if entity.dxftype() != "DIMENSION":
            continue

        try:
            measurement = float(
                entity.dxf.actual_measurement
            )

            if abs(
                measurement - MASTER_LENGTH_MM
            ) <= 10:

                entity.dxf.actual_measurement = (
                    float(new_length_mm)
                )

                try:
                    entity.render()
                except Exception:
                    pass

                changed += 1

        except Exception:
            pass

    return changed


# ============================================================
# TEXTUAL 30140 CLEANUP
# ============================================================

def replace_30140_text(
    doc,
    old_mm,
    new_mm,
):
    """
    If a drawing contains static text "30140", change it too.

    This is deliberately limited to the main drawing window so
    title-block revision/history text is not modified.
    """

    old_texts = {
        "30140",
        "30140.0",
        "30140.00",
    }

    new_text = (
        f"{new_mm:.0f}"
    )

    changed = 0

    for entity in doc.modelspace():

        if entity.dxftype() not in (
            "TEXT",
            "MTEXT",
        ):
            continue

        if not inside_main_view(entity):
            continue

        text = str(
            entity.dxf.get("text", "")
        )

        if text.strip() in old_texts:
            entity.dxf.text = new_text
            changed += 1

    return changed


# ============================================================
# LEVELS
# ============================================================

def update_existing_level_text(
    doc,
    keyword,
    new_value,
):
    """
    Update existing MTEXT such as:
        BED LEVEL: 93.070

    The label stays; only the number changes.
    """

    changed = 0

    for entity in doc.modelspace():

        if entity.dxftype() not in (
            "TEXT",
            "MTEXT",
        ):
            continue

        text = str(
            entity.dxf.get("text", "")
        )

        if keyword.upper() not in text.upper():
            continue

        if not inside_main_view(entity):
            continue

        if keyword.upper() == "BED LEVEL":

            if ":" in text:
                prefix = text.split(":")[0]
                entity.dxf.text = (
                    f"{prefix}: {new_value:.3f}"
                )
            else:
                entity.dxf.text = (
                    f"BED LEVEL: {new_value:.3f}"
                )

            changed += 1

    return changed


# ============================================================
# MAIN EDIT
# ============================================================

def edit_master(
    uploaded_file,
    barrel_length_m,
    pipe_length_m,
    number_of_tracks,
    track_spacing_m,
    gl_rl,
    bed_rl,
):
    doc = read_dxf(uploaded_file)

    barrel_dims = find_barrel_dimensions(doc)

    if not barrel_dims:
        raise RuntimeError(
            "The existing 30140 mm barrel dimensions "
            "could not be found in the master DXF."
        )

    old_left = MASTER_LEFT
    old_right = MASTER_RIGHT

    # Prefer actual dimension endpoints from the master.
    try:
        p2 = barrel_dims[0].dxf.defpoint2
        p3 = barrel_dims[0].dxf.defpoint3

        old_left = min(
            p2.x,
            p3.x,
        )

        old_right = max(
            p2.x,
            p3.x,
        )

    except Exception:
        pass

    new_length_mm = (
        float(barrel_length_m) * 1000.0
    )

    new_right = (
        old_left + new_length_mm
    )

    # --------------------------------------------------------
    # 1. Transform ALL existing main drawing entities.
    # --------------------------------------------------------

    transformed = 0

    for entity in list(doc.modelspace()):

        # Track structures are rebuilt separately.
        if (
            entity.dxftype() == "INSERT"
            and str(
                entity.dxf.get("name", "")
            ).upper()
            == TRACK_BLOCK_NAME.upper()
        ):
            continue

        # Use the actual drawing zones instead of a simple viewport test.
        # This catches hatches/earth cushion and the right-hand wing/return
        # assembly that were missed by earlier versions.
        ext = entity_xy_extents(entity)
        if ext is None:
            continue

        xmin, xmax, ymin, ymax = ext
        relevant = (
            (ymax >= -609500.0 and ymin <= -594000.0)
            or (ymax >= -605500.0 and ymin <= -600500.0)
        )

        # Also include the lower existing/dismantling detail if it lies in
        # the master drawing area.
        if not relevant:
            relevant = (
                xmin >= 1815000.0 and xmax <= 1865000.0
                and ymax >= -618000.0 and ymin <= -611000.0
            )

        if not relevant:
            continue

        transform_main_entity(
            entity,
            old_left,
            old_right,
            new_right,
            new_right - old_right,
        )

        transformed += 1

    # --------------------------------------------------------
    # 1B. Move the existing green dismantling/pipe/detail geometry.
    # The supplied drawing marks dismantling work in green. These entities
    # are often outside the Section A-A barrel window, so move them with the
    # same longitudinal datum instead of leaving them behind.
    # --------------------------------------------------------
    for entity in list(doc.modelspace()):
        try:
            if entity.dxftype() == "INSERT" and str(entity.dxf.get("name", "")).upper() == TRACK_BLOCK_NAME.upper():
                continue
            c = entity.dxf.get("color", 0)
            if c != 3:
                continue
            ext = entity_xy_extents(entity)
            if ext is None:
                continue
            xmin, xmax, ymin, ymax = ext
            if (ymax >= -618000.0 and ymin <= -611000.0) and xmax >= 1815000.0:
                transform_entity_x_translate(entity, new_right - old_right)
        except Exception:
            pass

    # --------------------------------------------------------
    # 2. Change both 30140 barrel dimensions.
    # --------------------------------------------------------

    dimension_changes = (
        update_pipe_length_dimensions(
            doc,
            new_length_mm,
        )
    )

    # --------------------------------------------------------
    # 3. Change static 30140 text if any exists.
    # --------------------------------------------------------

    text_changes = replace_30140_text(
        doc,
        MASTER_LENGTH_MM,
        new_length_mm,
    )

    # --------------------------------------------------------
    # 4. Update BED LEVEL text.
    # --------------------------------------------------------

    bed_changes = update_existing_level_text(
        doc,
        "BED LEVEL",
        float(bed_rl),
    )

    # --------------------------------------------------------
    # 5. Rebuild the actual track structures.
    # --------------------------------------------------------

    track_positions = add_tracks(
        doc,
        number_of_tracks,
        track_spacing_m,
        old_left,
        new_right,
    )

    # --------------------------------------------------------
    # 6. Rebuild track labels in both views.
    # --------------------------------------------------------

    add_track_labels(
        doc,
        track_positions,
    )

    # --------------------------------------------------------
    # 7. Save output.
    # --------------------------------------------------------

    output_path = None

    try:

        with tempfile.NamedTemporaryFile(
            suffix=".dxf",
            delete=False,
        ) as temp:

            output_path = temp.name

        doc.saveas(
            output_path
        )

        with open(
            output_path,
            "rb",
        ) as file:

            output_bytes = file.read()

    finally:

        if output_path:

            try:
                os.remove(output_path)
            except OSError:
                pass

    return {
        "bytes": output_bytes,
        "old_length_m": (
            old_right - old_left
        ) / 1000.0,
        "new_length_m": barrel_length_m,
        "transformed_entities": transformed,
        "barrel_dimensions_changed": dimension_changes,
        "static_text_changed": text_changes,
        "bed_level_changed": bed_changes,
        "tracks": len(track_positions),
        "track_positions": track_positions,
    }


# ============================================================
# USER INTERFACE
# ============================================================

with st.sidebar:

    st.header("MASTER CAD")

    master = st.file_uploader(
        "Upload master_plan1.dxf",
        type=["dxf"],
    )

    if master:
        st.success(
            f"Loaded: {master.name}"
        )

    st.divider()

    st.write(
        "Variable drawing data:"
    )

    st.write(
        "• Barrel / pipe length"
    )
    st.write(
        "• Number of tracks"
    )
    st.write(
        "• Track spacing"
    )
    st.write(
        "• Ground / bed levels"
    )

    st.divider()

    st.warning(
        "Do not upload the generated DXF as the master. "
        "Always start from the original master_plan1.dxf."
    )


# ------------------------------------------------------------
# Bridge Data
# ------------------------------------------------------------

st.subheader("Bridge Data")

b1, b2, b3, b4, b5 = st.columns(5)

with b1:
    drawing_no = st.text_input(
        "Drawing No.",
        "462",
    )

with b2:
    chainage = st.text_input(
        "Chainage",
        "274/60.10",
    )

with b3:
    barrel_length_m = st.number_input(
        "Barrel Length (m)",
        min_value=0.100,
        value=30.140,
        step=0.001,
        format="%.3f",
    )

with b4:
    span_m = st.number_input(
        "Span (m)",
        min_value=0.100,
        value=2.400,
        step=0.001,
        format="%.3f",
    )

with b5:
    number_of_tracks = st.number_input(
        "NO. OF TRACKS",
        min_value=1,
        max_value=20,
        value=4,
        step=1,
        help="The master has 4 tracks. Change this to 3, 5, 6, etc.",
    )


# ------------------------------------------------------------
# Track / Pipe Data
# ------------------------------------------------------------

st.subheader("Track / Pipe Data")

p1, p2, p3, p4 = st.columns(4)

with p1:
    track_spacing_m = st.number_input(
        "Track Spacing (m)",
        min_value=0.100,
        value=4.800,
        step=0.001,
        format="%.3f",
    )

with p2:
    pipe_od = st.number_input(
        "Pipe OD (mm)",
        min_value=1.0,
        value=1200.0,
        step=1.0,
    )

with p3:
    st.metric(
        "Dismantling / Existing Pipe Length (m)",
        f"{barrel_length_m:.3f}",
    )
    st.caption(
        "This follows Barrel Length automatically."
    )

with p4:
    pipe_slope = st.number_input(
        "Pipe Slope (%)",
        value=0.500,
        step=0.001,
        format="%.3f",
    )

# The existing/dismantling pipe in the master drawing is tied to
# the 30140 barrel length. Therefore it follows the same variable.
pipe_length_m = barrel_length_m


# ------------------------------------------------------------
# Level Data
# ------------------------------------------------------------

st.subheader("Level Data")

l1, l2, l3, l4 = st.columns(4)

with l1:
    gl_rl = st.number_input(
        "G.L. RL (m)",
        value=97.300,
        step=0.001,
        format="%.3f",
    )

with l2:
    bed_rl = st.number_input(
        "Bed Level RL (m)",
        value=96.271,
        step=0.001,
        format="%.3f",
    )

with l3:
    pipe_invert_rl = st.number_input(
        "Pipe Invert RL (m)",
        value=95.000,
        step=0.001,
        format="%.3f",
    )

with l4:
    pipe_top_rl = (
        pipe_invert_rl
        + pipe_od / 1000.0
    )

    st.metric(
        "Pipe Top RL",
        f"{pipe_top_rl:.3f}",
    )

    st.metric(
        "G.L. Clearance",
        f"{gl_rl - pipe_top_rl:.3f} m",
    )


# ------------------------------------------------------------
# Preview of what will change
# ------------------------------------------------------------

st.divider()

st.subheader("Change Preview")

q1, q2, q3, q4 = st.columns(4)

with q1:
    st.metric(
        "Master Barrel",
        "30.140 m",
    )

with q2:
    st.metric(
        "New Barrel",
        f"{barrel_length_m:.3f} m",
    )

with q3:
    st.metric(
        "Master Tracks",
        "4",
    )

with q4:
    st.metric(
        "New Tracks",
        str(int(number_of_tracks)),
    )

st.caption(
    "When Barrel Length changes, the centre barrel stretches/compresses "
    "and the right-hand wing/return and attached assemblies translate "
    "by the same length difference. The lower plan/detail and the "
    "existing green/dismantling geometry are transformed in the same "
    "longitudinal operation."
)


# ============================================================
# GENERATE
# ============================================================

st.divider()

if st.button(
    "GENERATE EDITED DRAWING",
    type="primary",
    use_container_width=True,
):

    if master is None:
        st.error(
            "Please upload the original master_plan1.dxf."
        )
        st.stop()

    if ezdxf is None:
        st.error(
            "ezdxf is missing. Put 'ezdxf' in requirements.txt "
            "and redeploy."
        )
        st.stop()

    try:

        with st.spinner(
            "Editing the actual master CAD entities..."
        ):

            result = edit_master(
                master,
                barrel_length_m,
                pipe_length_m,
                int(number_of_tracks),
                track_spacing_m,
                gl_rl,
                bed_rl,
            )

        st.success(
            "Master drawing edited successfully."
        )

        st.write(
            f"Barrel: "
            f"{result['old_length_m']:.3f} m → "
            f"{result['new_length_m']:.3f} m"
        )

        st.write(
            f"Track count: "
            f"{result['tracks']}"
        )

        st.write(
            f"Existing CAD entities transformed: "
            f"{result['transformed_entities']:,}"
        )

        st.write(
            f"30140 dimensions changed: "
            f"{result['barrel_dimensions_changed']}"
        )

        st.write(
            f"Static 30140 text changed: "
            f"{result['static_text_changed']}"
        )

        st.write(
            f"Bed level text changed: "
            f"{result['bed_level_changed']}"
        )

        filename = (
            f"Bridge_{drawing_no}_"
            f"{barrel_length_m:.3f}m_"
            f"{int(number_of_tracks)}Tracks.dxf"
        )

        st.download_button(
            "⬇ DOWNLOAD EDITED DXF",
            data=result["bytes"],
            file_name=filename,
            mime="application/dxf",
            use_container_width=True,
        )

        st.success(
            "The output contains the edited master drawing, "
            "not a newly drawn replacement."
        )

    except Exception as error:

        st.error(
            "Drawing editing failed."
        )

        st.code(
            str(error),
            language="text",
        )


# ============================================================
# DIAGNOSTICS
# ============================================================

with st.expander(
    "DXF diagnostics / master mapping"
):

    if master is None:
        st.write(
            "Upload the original master DXF."
        )

    elif ezdxf is None:
        st.error(
            "ezdxf is not installed."
        )

    else:

        try:

            diagnostic = read_dxf(
                master
            )

            st.write(
                "DXF version:",
                diagnostic.dxfversion,
            )

            st.write(
                "Model-space entities:",
                len(diagnostic.modelspace()),
            )

            st.write(
                "Layers:",
                len(diagnostic.layers),
            )

            st.write(
                "Blocks:",
                len(diagnostic.blocks),
            )

            dims = find_barrel_dimensions(
                diagnostic
            )

            tracks_found = find_track_inserts(
                diagnostic
            )

            st.write(
                "30140 barrel dimensions found:",
                len(dims),
            )

            st.write(
                "Existing track blocks found:",
                len(tracks_found),
            )

            if dims:

                st.write(
                    "Current master barrel:",
                    f"{float(dims[0].dxf.actual_measurement) / 1000.0:.3f} m",
                )

            st.write(
                "Existing track block X positions:",
                [
                    round(
                        t.dxf.insert.x,
                        1,
                    )
                    for t in tracks_found
                ],
            )

        except Exception as error:

            st.error(
                str(error)
            )
