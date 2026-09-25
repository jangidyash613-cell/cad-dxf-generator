import math
import os
import tempfile
from pathlib import Path

import streamlit as st

try:
    import ezdxf
except ImportError:
    ezdxf = None


st.set_page_config(
    page_title="Bridge 462 CAD Drawing Generator",
    page_icon="📐",
    layout="wide",
)

st.title("📐 Bridge 462 CAD Drawing Generator")
st.caption(
    "This version edits the existing master drawing instead of adding a separate drawing."
)


# ============================================================
# BASIC HELPERS
# ============================================================

def f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_dimension_text(doc, dim):
    """
    Read visible dimension text from the DIMENSION entity.
    """
    return str(dim.dxf.get("text", "") or "")


def set_vec_x(vec, x):
    return (x, vec.y, vec.z)


def set_vec_y(vec, y):
    return (vec.x, y, vec.z)


# ============================================================
# DXF READING
# ============================================================

def read_dxf(uploaded_file):
    if ezdxf is None:
        raise RuntimeError(
            "ezdxf is not installed. Put 'ezdxf' in requirements.txt."
        )

    if uploaded_file is None:
        raise RuntimeError("Please upload the master DXF.")

    raw = uploaded_file.getvalue()

    if not raw:
        raise RuntimeError("The uploaded DXF file is empty.")

    temp_name = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".dxf",
            delete=False,
        ) as tmp:
            tmp.write(raw)
            tmp.flush()
            temp_name = tmp.name

        try:
            return ezdxf.readfile(temp_name)
        except Exception:
            from ezdxf import recover

            doc, auditor = recover.readfile(temp_name)

            if auditor.has_errors:
                st.warning(
                    "The DXF required ezdxf recovery mode. "
                    "The drawing was opened, but the source contains "
                    "some DXF audit issues."
                )

            return doc

    finally:
        if temp_name:
            try:
                os.remove(temp_name)
            except OSError:
                pass


# ============================================================
# FIND THE ACTUAL EXISTING 462 DIMENSIONS
# ============================================================

def find_section_length_dimensions(doc):
    """
    In the supplied 462 master DXF, Section A-A has two existing
    horizontal 30140 dimensions.

    Their handles in the supplied master are:
        309E29D
        309E4EA

    We first try the handles. If handles changed after a CAD save,
    we fall back to finding horizontal DIMENSION entities whose
    measured length is approximately 30140 mm.
    """

    found = []

    for handle in ("309E29D", "309E4EA"):
        entity = doc.entitydb.get(handle)
        if entity is not None and entity.dxftype() == "DIMENSION":
            found.append(entity)

    if len(found) >= 2:
        return found[:2]

    candidates = []

    for entity in doc.modelspace():
        if entity.dxftype() != "DIMENSION":
            continue

        try:
            measurement = float(entity.dxf.actual_measurement)
            p2 = entity.dxf.defpoint2
            p3 = entity.dxf.defpoint3

            horizontal = abs(p2.y - p3.y) < 5.0
            close_to_original = abs(measurement - 30140.0) < 5.0

            if horizontal and close_to_original:
                candidates.append(entity)

        except Exception:
            continue

    return candidates[:2]


def find_gl_dimensions(doc):
    """
    Find the two existing G.L. dimensions in Section A-A.
    """

    result = []

    for handle in ("309E2F4", "309E2FD"):
        entity = doc.entitydb.get(handle)
        if entity is not None and entity.dxftype() == "DIMENSION":
            result.append(entity)

    if len(result) >= 2:
        return result[:2]

    for entity in doc.modelspace():
        if entity.dxftype() != "DIMENSION":
            continue

        text = get_dimension_text(doc, entity).upper()

        if "G.L." in text or "G.L" in text:
            result.append(entity)

    return result[:2]


def find_bed_level_dimensions(doc):
    """
    Find the existing BED LEVEL dimensions around Section A-A.
    """

    result = []

    for entity in doc.modelspace():
        if entity.dxftype() != "DIMENSION":
            continue

        text = get_dimension_text(doc, entity).upper()

        if "BED LEVEL" in text:
            result.append(entity)

    return result


# ============================================================
# UPDATE SECTION A-A LENGTH
# ============================================================

def update_length_dimension(dim, new_length_mm):
    """
    Change the existing dimension itself.

    The original drawing is in millimetres:
        30140 = 30.140 m

    The left endpoint is retained.
    The right endpoint is moved to:
        left + new_length
    """

    left_x = dim.dxf.defpoint2.x
    new_right_x = left_x + new_length_mm

    dim.dxf.defpoint = set_vec_x(
        dim.dxf.defpoint,
        new_right_x,
    )

    dim.dxf.defpoint3 = set_vec_x(
        dim.dxf.defpoint3,
        new_right_x,
    )

    dim.dxf.text_midpoint = set_vec_x(
        dim.dxf.text_midpoint,
        left_x + new_length_mm / 2.0,
    )

    dim.dxf.actual_measurement = float(new_length_mm)

    # Let ezdxf rebuild the graphical dimension block.
    dim.render()


def stretch_section_geometry(
    doc,
    old_left,
    old_right,
    new_right,
):
    """
    Stretch the actual Section A-A geometry horizontally.

    This is the important difference from the previous code.

    We do NOT simply add a new pipe at 0,0.

    Existing lines/polylines/text in the Section A-A drawing
    are stretched between the existing left and right barrel
    boundaries.

    Y coordinates and text heights are preserved.
    """

    if abs(old_right - old_left) < 1:
        return

    scale = (new_right - old_left) / (old_right - old_left)

    xmin = old_left - 400.0
    xmax = old_right + 400.0

    # Section A-A vertical range in the supplied master.
    ymin = -599200.0
    ymax = -594000.0

    def sx(x):
        return old_left + (x - old_left) * scale

    for entity in list(doc.modelspace()):

        typ = entity.dxftype()

        # ----------------------------------------------------
        # LINE
        # ----------------------------------------------------
        if typ == "LINE":
            p1 = entity.dxf.start
            p2 = entity.dxf.end

            if (
                ymin <= p1.y <= ymax
                and ymin <= p2.y <= ymax
                and xmin <= p1.x <= xmax
                and xmin <= p2.x <= xmax
            ):
                entity.dxf.start = (sx(p1.x), p1.y, p1.z)
                entity.dxf.end = (sx(p2.x), p2.y, p2.z)

        # ----------------------------------------------------
        # LWPOLYLINE
        # ----------------------------------------------------
        elif typ == "LWPOLYLINE":
            points = list(entity.get_points())

            if not points:
                continue

            if all(
                ymin <= p[1] <= ymax
                and xmin <= p[0] <= xmax
                for p in points
            ):
                new_points = []

                for p in points:
                    new_points.append(
                        (
                            sx(p[0]),
                            p[1],
                            p[2],
                            p[3],
                            p[4],
                        )
                    )

                entity.set_points(new_points)

        # ----------------------------------------------------
        # TEXT
        # ----------------------------------------------------
        elif typ == "TEXT":
            p = entity.dxf.insert

            if (
                ymin <= p.y <= ymax
                and xmin <= p.x <= xmax
            ):
                entity.dxf.insert = (sx(p.x), p.y, p.z)

        # ----------------------------------------------------
        # MTEXT
        # ----------------------------------------------------
        elif typ == "MTEXT":
            p = entity.dxf.insert

            if (
                ymin <= p.y <= ymax
                and xmin <= p.x <= xmax
            ):
                entity.dxf.insert = (sx(p.x), p.y, p.z)

        # ----------------------------------------------------
        # DIMENSIONS
        # ----------------------------------------------------
        elif typ == "DIMENSION":
            try:
                pts = [
                    entity.dxf.defpoint,
                    entity.dxf.defpoint2,
                    entity.dxf.defpoint3,
                    entity.dxf.text_midpoint,
                ]

                if all(
                    ymin <= p.y <= ymax
                    and xmin <= p.x <= xmax
                    for p in pts
                ):
                    entity.dxf.defpoint = (
                        sx(entity.dxf.defpoint.x),
                        entity.dxf.defpoint.y,
                        entity.dxf.defpoint.z,
                    )

                    entity.dxf.defpoint2 = (
                        sx(entity.dxf.defpoint2.x),
                        entity.dxf.defpoint2.y,
                        entity.dxf.defpoint2.z,
                    )

                    entity.dxf.defpoint3 = (
                        sx(entity.dxf.defpoint3.x),
                        entity.dxf.defpoint3.y,
                        entity.dxf.defpoint3.z,
                    )

                    entity.dxf.text_midpoint = (
                        sx(entity.dxf.text_midpoint.x),
                        entity.dxf.text_midpoint.y,
                        entity.dxf.text_midpoint.z,
                    )

                    entity.render()

            except Exception:
                pass


# ============================================================
# UPDATE G.L. LEVEL
# ============================================================

def update_gl_dimension(dim, new_rl):
    """
    Existing G.L. dimensions use drawing units in mm.

    Example:
        97.300 m = 97300 mm above the dimension base point.
    """

    base_y = dim.dxf.defpoint.y

    new_y = base_y + float(new_rl) * 1000.0

    dim.dxf.defpoint2 = set_vec_y(
        dim.dxf.defpoint2,
        new_y,
    )

    dim.dxf.defpoint3 = set_vec_y(
        dim.dxf.defpoint3,
        new_y,
    )

    # Keep the normal dimension text position slightly below the level line.
    dim.dxf.text_midpoint = set_vec_y(
        dim.dxf.text_midpoint,
        new_y - 206.0,
    )

    dim.dxf.actual_measurement = float(new_rl)
    dim.dxf.text = f"G.L.  {float(new_rl):.3f}"

    dim.render()


# ============================================================
# UPDATE BED LEVEL
# ============================================================

def update_bed_dimension(dim, new_rl):
    """
    Update an existing BED LEVEL dimension.
    """

    base_y = dim.dxf.defpoint.y
    new_y = base_y + float(new_rl) * 1000.0

    dim.dxf.defpoint2 = set_vec_y(
        dim.dxf.defpoint2,
        new_y,
    )

    dim.dxf.defpoint3 = set_vec_y(
        dim.dxf.defpoint3,
        new_y,
    )

    dim.dxf.text_midpoint = set_vec_y(
        dim.dxf.text_midpoint,
        new_y - 206.0,
    )

    dim.dxf.actual_measurement = float(new_rl)

    # Preserve the original formatting/color controls while replacing
    # only the displayed level.
    old_text = get_dimension_text(None, dim)

    if "{\\C" in old_text:
        dim.dxf.text = "{\\C0;BED LEVEL %.3f}" % float(new_rl)
    else:
        dim.dxf.text = "BED LEVEL %.3f" % float(new_rl)

    dim.render()


# ============================================================
# MODIFY THE EXISTING MASTER DRAWING
# ============================================================

def modify_master(
    uploaded_file,
    section_length_mm,
    gl_rl,
    bed_rl,
):
    doc = read_dxf(uploaded_file)

    length_dims = find_section_length_dimensions(doc)

    if not length_dims:
        raise RuntimeError(
            "Could not locate the existing 30140 Section A-A "
            "dimension in this master drawing."
        )

    gl_dims = find_gl_dimensions(doc)

    if not gl_dims:
        raise RuntimeError(
            "Could not locate the existing G.L. 97.300 "
            "dimensions in Section A-A."
        )

    old_length = float(
        length_dims[0].dxf.actual_measurement
    )

    old_left = length_dims[0].dxf.defpoint2.x
    old_right = length_dims[0].dxf.defpoint3.x

    # Stretch actual Section A-A geometry first.
    stretch_section_geometry(
        doc,
        old_left,
        old_right,
        old_left + section_length_mm,
    )

    # Update both existing barrel-length dimensions.
    for dim in length_dims:
        update_length_dimension(
            dim,
            section_length_mm,
        )

    # Update both existing G.L. dimensions.
    for dim in gl_dims:
        update_gl_dimension(
            dim,
            gl_rl,
        )

    # Update existing bed-level dimensions if requested.
    bed_dims = find_bed_level_dimensions(doc)

    for dim in bed_dims:
        update_bed_dimension(
            dim,
            bed_rl,
        )

    # Save to a temporary DXF.
    with tempfile.NamedTemporaryFile(
        suffix=".dxf",
        delete=False,
    ) as tmp:
        output_path = tmp.name

    try:
        doc.saveas(output_path)

        with open(output_path, "rb") as file:
            output_bytes = file.read()

    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass

    return output_bytes, doc, old_length


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("Master CAD")

    master_file = st.file_uploader(
        "Upload master DXF",
        type=["dxf"],
        help="Upload master_plan1.dxf or your equivalent master DXF.",
    )

    if master_file:
        st.success(
            f"Loaded: {master_file.name}"
        )

    st.divider()

    st.write(
        "This version edits the existing Section A-A dimensions "
        "inside the master CAD."
    )


# ============================================================
# USER INPUTS
# ============================================================

st.subheader("Bridge Data")

c1, c2, c3, c4 = st.columns(4)

with c1:
    drawing_no = st.text_input(
        "Bridge / Drawing No.",
        value="462",
    )

with c2:
    chainage = st.text_input(
        "Chainage",
        value="274/60.10",
    )

with c3:
    section_length_m = st.number_input(
        "Section A-A Length (m)",
        min_value=0.001,
        value=30.140,
        step=0.001,
        format="%.3f",
        help="Existing master value is 30140 mm = 30.140 m.",
    )

with c4:
    bridge_width = st.number_input(
        "Bridge Width (m)",
        value=8.000,
        step=0.001,
        format="%.3f",
    )


st.subheader("Pipe Data")

p1, p2, p3, p4 = st.columns(4)

with p1:
    pipe_od = st.number_input(
        "Pipe OD (mm)",
        min_value=1.0,
        value=1200.0,
        step=1.0,
    )

with p2:
    pipe_id = st.number_input(
        "Pipe ID (mm)",
        min_value=0.0,
        value=1000.0,
        step=1.0,
    )

with p3:
    number_of_pipes = st.number_input(
        "Number of Pipes",
        min_value=1,
        value=1,
        step=1,
    )

with p4:
    pipe_slope = st.number_input(
        "Pipe Slope (%)",
        value=0.500,
        step=0.001,
        format="%.3f",
    )


st.subheader("Level Data")

l1, l2, l3, l4 = st.columns(4)

with l1:
    gl_rl = st.number_input(
        "G.L. RL (m)",
        value=97.300,
        step=0.001,
        format="%.3f",
        help="Existing master value is 97.300.",
    )

with l2:
    bed_rl = st.number_input(
        "Bed Level RL (m)",
        value=96.271,
        step=0.001,
        format="%.3f",
        help="Existing master value is 96.271.",
    )

with l3:
    pipe_invert_rl = st.number_input(
        "Pipe Invert RL (m)",
        value=95.000,
        step=0.001,
        format="%.3f",
    )

with l4:
    required_clearance = st.number_input(
        "Required Clearance (m)",
        value=0.600,
        step=0.001,
        format="%.3f",
    )


# ============================================================
# CALCULATED PIPE LEVELS
# ============================================================

pipe_od_m = pipe_od / 1000.0

pipe_center_rl = pipe_invert_rl + pipe_od_m / 2.0
pipe_top_rl = pipe_invert_rl + pipe_od_m

available_clearance = gl_rl - pipe_top_rl

st.divider()

st.subheader("Calculated Pipe Levels")

a1, a2, a3 = st.columns(3)

a1.metric(
    "Pipe Centre RL",
    f"{pipe_center_rl:.3f}",
)

a2.metric(
    "Pipe Top RL",
    f"{pipe_top_rl:.3f}",
)

a3.metric(
    "Available Clearance",
    f"{available_clearance:.3f} m",
)

if available_clearance < required_clearance:
    st.warning(
        "Pipe top is below the required G.L. clearance."
    )


# ============================================================
# GENERATE
# ============================================================

st.divider()

if st.button(
    "Generate Edited Drawing",
    type="primary",
    use_container_width=True,
):

    if master_file is None:
        st.error(
            "Upload master_plan1.dxf first."
        )
        st.stop()

    if ezdxf is None:
        st.error(
            "ezdxf is missing. Add ezdxf to requirements.txt "
            "and redeploy Streamlit."
        )
        st.stop()

    new_length_mm = section_length_m * 1000.0

    try:
        with st.spinner(
            "Editing the existing CAD dimensions and Section A-A geometry..."
        ):

            output, edited_doc, old_length = modify_master(
                master_file,
                new_length_mm,
                gl_rl,
                bed_rl,
            )

        st.success(
            "The existing master drawing has been edited."
        )

        st.write(
            f"Section A-A length changed from "
            f"{old_length / 1000.0:.3f} m "
            f"to {section_length_m:.3f} m."
        )

        st.write(
            f"G.L. changed to {gl_rl:.3f} m."
        )

        st.write(
            f"Bed Level changed to {bed_rl:.3f} m."
        )

        filename = (
            f"Bridge_{drawing_no}_"
            f"Edited_Chainage_"
            f"{chainage.replace('/', '_').replace('.', '_')}.dxf"
        )

        st.download_button(
            label="⬇ Download Edited DXF",
            data=output,
            file_name=filename,
            mime="application/dxf",
            use_container_width=True,
        )

        st.info(
            "The program now modifies the existing 30140 mm and "
            "97.300 G.L. dimensions in the supplied 462 master drawing. "
            "It also horizontally stretches the Section A-A geometry "
            "between the existing barrel boundaries."
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

with st.expander("Master drawing diagnostics"):

    if master_file is None:
        st.write("No master DXF uploaded.")

    elif ezdxf is None:
        st.error("ezdxf is not installed.")

    else:
        try:
            diagnostic_doc = read_dxf(master_file)

            st.success("Master DXF successfully read.")

            st.write(
                "DXF version:",
                diagnostic_doc.dxfversion,
            )

            st.write(
                "Model-space entities:",
                len(diagnostic_doc.modelspace()),
            )

            st.write(
                "Layers:",
                len(diagnostic_doc.layers),
            )

            st.write(
                "Blocks:",
                len(diagnostic_doc.blocks),
            )

            length_dims = find_section_length_dimensions(
                diagnostic_doc
            )

            gl_dims = find_gl_dimensions(
                diagnostic_doc
            )

            bed_dims = find_bed_level_dimensions(
                diagnostic_doc
            )

            st.write(
                "Section A-A length dimensions found:",
                len(length_dims),
            )

            st.write(
                "G.L. dimensions found:",
                len(gl_dims),
            )

            st.write(
                "Bed-level dimensions found:",
                len(bed_dims),
            )

            if length_dims:
                st.write(
                    "Current Section A-A length:",
                    f"{length_dims[0].dxf.actual_measurement:.0f} mm",
                )

            if gl_dims:
                st.write(
                    "Current G.L.:",
                    gl_dims[0].dxf.text,
                )

        except Exception as error:
            st.error("DXF diagnostic failed.")
            st.code(str(error), language="text")
