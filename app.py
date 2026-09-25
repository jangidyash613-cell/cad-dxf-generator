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
    page_title="Bridge Pipe Drawing Generator",
    page_icon="📐",
    layout="wide",
)

st.title("📐 Bridge Pipe Drawing Generator")
st.caption("Bridge + Pipe + Level data are variable; the uploaded master DXF is kept as the base drawing.")


# ============================================================
# Utility functions
# ============================================================

def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_levels(data):
    pipe_od_m = to_float(data["pipe_od"]) / 1000.0
    pipe_invert = to_float(data["pipe_invert_rl"])
    underside = to_float(data["bridge_underside_rl"])
    slope_percent = to_float(data["pipe_slope"])
    pipe_length = to_float(data["pipe_length"])

    pipe_centre = pipe_invert + pipe_od_m / 2.0
    pipe_top = pipe_invert + pipe_od_m

    end_invert = pipe_invert + (
        pipe_length * slope_percent / 100.0
    )

    clearance = underside - pipe_top

    return {
        "pipe_od_m": pipe_od_m,
        "pipe_center_rl": pipe_centre,
        "pipe_top_rl": pipe_top,
        "pipe_end_invert_rl": end_invert,
        "available_clearance": clearance,
    }


def read_uploaded_dxf(uploaded_file):
    """
    Read the uploaded DXF through a real temporary file.

    This is intentionally used instead of:
        ezdxf.read(io.BytesIO(...))

    because ezdxf's normal file reader is more reliable when it receives
    an actual DXF file path.
    """

    if ezdxf is None:
        raise RuntimeError(
            "The ezdxf package is not installed. "
            "Add 'ezdxf' to requirements.txt and redeploy."
        )

    if uploaded_file is None:
        raise RuntimeError("No master drawing was uploaded.")

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:
        raise RuntimeError("The uploaded file is empty.")

    suffix = Path(uploaded_file.name).suffix.lower()

    # Do not reject the drawing merely because of its filename.
    # We inspect the actual DXF contents.
    if suffix not in (".dxf", ""):
        raise RuntimeError(
            "Please upload the master drawing as a DXF file."
        )

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".dxf",
            delete=False,
        ) as temp:
            temp.write(file_bytes)
            temp.flush()
            temp_path = temp.name

        try:
            doc = ezdxf.readfile(temp_path)
        except Exception as first_error:
            # Try the recovery reader for drawings with minor DXF problems.
            try:
                from ezdxf import recover

                doc, auditor = recover.readfile(temp_path)

                if auditor.has_errors:
                    st.warning(
                        "The DXF was opened with ezdxf recovery mode. "
                        "Some non-critical DXF errors may exist."
                    )
            except Exception as recovery_error:
                raise RuntimeError(
                    "The uploaded file has a DXF filename, but ezdxf "
                    "could not read its contents. "
                    "The application has tried normal and recovery DXF "
                    "reading. Please upload the original AutoCAD DXF."
                ) from recovery_error

        return doc

    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


def ensure_layer(doc, name, color):
    if name not in doc.layers:
        doc.layers.add(name=name, color=color)


def add_generated_pipe(doc, data, levels):
    """
    Adds generated pipe geometry.

    IMPORTANT:
    This is intentionally on separate layers. It does not delete or
    overwrite the master drawing.

    The coordinates are currently a placeholder until the exact
    462 master drawing entity positions are mapped.
    """

    msp = doc.modelspace()

    ensure_layer(doc, "GENERATED_PIPE", 1)
    ensure_layer(doc, "GENERATED_TEXT", 2)

    # Temporary origin.
    # This must later be replaced with the actual pipe position
    # found in the 462 master drawing.
    x0 = 0.0
    y0 = 0.0

    od = levels["pipe_od_m"]
    length = to_float(data["pipe_length"], 20.0)
    angle_deg = to_float(data["crossing_angle"], 90.0)

    angle = math.radians(angle_deg)

    dx = length * math.cos(angle)
    dy = length * math.sin(angle)

    # Perpendicular vector for pipe width.
    nx = -math.sin(angle) * od / 2.0
    ny = math.cos(angle) * od / 2.0

    geometry = [
        # Centreline
        ((x0, y0), (x0 + dx, y0 + dy)),

        # Pipe sides
        (
            (x0 + nx, y0 + ny),
            (x0 + dx + nx, y0 + dy + ny),
        ),
        (
            (x0 - nx, y0 - ny),
            (x0 + dx - nx, y0 + dy - ny),
        ),

        # Start cap
        (
            (x0 + nx, y0 + ny),
            (x0 - nx, y0 - ny),
        ),

        # End cap
        (
            (x0 + dx + nx, y0 + dy + ny),
            (x0 + dx - nx, y0 + dy - ny),
        ),
    ]

    for start, end in geometry:
        msp.add_line(
            start,
            end,
            dxfattribs={"layer": "GENERATED_PIPE"},
        )

    notes = [
        f"BRIDGE/DRAWING NO.: {data['drawing_no']}",
        f"CHAINAGE: {data['chainage']}",
        f"PIPE OD: {data['pipe_od']:.1f} mm",
        f"NO. OF PIPES: {data['number_of_pipes']}",
        f"PIPE INVERT RL: {to_float(data['pipe_invert_rl']):.3f}",
        f"PIPE CENTRE RL: {levels['pipe_center_rl']:.3f}",
        f"PIPE TOP RL: {levels['pipe_top_rl']:.3f}",
        f"PIPE END INVERT RL: {levels['pipe_end_invert_rl']:.3f}",
        f"AVAILABLE CLEARANCE: {levels['available_clearance']:.3f} m",
    ]

    y = -2.0

    for note in notes:
        text = msp.add_text(
            note,
            dxfattribs={
                "layer": "GENERATED_TEXT",
                "height": 0.25,
            },
        )
        text.set_placement((x0, y))
        y -= 0.35


def make_output_dxf(uploaded_file, data):
    doc = read_uploaded_dxf(uploaded_file)

    levels = calculate_levels(data)

    add_generated_pipe(
        doc,
        data,
        levels,
    )

    with tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".dxf",
        delete=False,
    ) as output:
        output_path = output.name

    try:
        doc.saveas(output_path)

        with open(output_path, "rb") as f:
            output_bytes = f.read()

    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass

    return output_bytes, levels, doc


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.header("Master Drawing")

    master_file = st.file_uploader(
        "Upload Master DXF",
        type=["dxf"],
        help="Upload your AutoCAD DXF master drawing.",
    )

    if master_file:
        st.success(
            f"Loaded: {master_file.name}"
        )

        st.caption(
            f"File size: {len(master_file.getvalue()):,} bytes"
        )

    st.divider()

    st.info(
        "The master DXF is used as the fixed drawing template. "
        "Only Bridge Data, Pipe Data and Level Data are intended "
        "to be variable."
    )


# ============================================================
# Input sections
# ============================================================

bridge_col, pipe_col, level_col = st.columns(3)


with bridge_col:
    st.subheader("Bridge Data")

    drawing_no = st.text_input(
        "Bridge / Drawing No.",
        value="462",
    )

    chainage = st.text_input(
        "Chainage",
        value="273.640",
    )

    span_length = st.number_input(
        "Span Length (m)",
        value=2.400,
        step=0.001,
        format="%.3f",
    )

    bridge_width = st.number_input(
        "Bridge Width (m)",
        value=8.000,
        step=0.001,
        format="%.3f",
    )


with pipe_col:
    st.subheader("Pipe Data")

    pipe_od = st.number_input(
        "Pipe OD (mm)",
        min_value=1.0,
        value=1200.0,
        step=1.0,
        format="%.1f",
    )

    pipe_id = st.number_input(
        "Pipe ID (mm)",
        min_value=0.0,
        value=1000.0,
        step=1.0,
        format="%.1f",
    )

    number_of_pipes = st.number_input(
        "Number of Pipes",
        min_value=1,
        value=1,
        step=1,
    )

    pipe_length = st.number_input(
        "Pipe Length (m)",
        min_value=0.001,
        value=20.000,
        step=0.001,
        format="%.3f",
    )

    pipe_slope = st.number_input(
        "Pipe Slope (%)",
        value=0.500,
        step=0.001,
        format="%.3f",
    )

    pipe_spacing = st.number_input(
        "Pipe Spacing (m)",
        min_value=0.000,
        value=1.500,
        step=0.001,
        format="%.3f",
    )

    crossing_angle = st.number_input(
        "Crossing Angle (degrees)",
        value=90.0,
        step=0.1,
        format="%.1f",
    )


with level_col:
    st.subheader("Level Data")

    bed_rl = st.number_input(
        "Existing / Bed RL (m)",
        value=100.000,
        step=0.001,
        format="%.3f",
    )

    bridge_underside_rl = st.number_input(
        "Bridge Underside RL (m)",
        value=103.000,
        step=0.001,
        format="%.3f",
    )

    pipe_invert_rl = st.number_input(
        "Pipe Invert RL (m)",
        value=101.000,
        step=0.001,
        format="%.3f",
    )

    required_cover = st.number_input(
        "Required Cover (m)",
        value=1.000,
        step=0.001,
        format="%.3f",
    )

    required_clearance = st.number_input(
        "Required Clearance (m)",
        value=0.600,
        step=0.001,
        format="%.3f",
    )


data = {
    "drawing_no": drawing_no,
    "chainage": chainage,
    "span_length": span_length,
    "bridge_width": bridge_width,
    "pipe_od": pipe_od,
    "pipe_id": pipe_id,
    "number_of_pipes": number_of_pipes,
    "pipe_length": pipe_length,
    "pipe_slope": pipe_slope,
    "pipe_spacing": pipe_spacing,
    "crossing_angle": crossing_angle,
    "bed_rl": bed_rl,
    "bridge_underside_rl": bridge_underside_rl,
    "pipe_invert_rl": pipe_invert_rl,
    "required_cover": required_cover,
    "required_clearance": required_clearance,
}


# ============================================================
# Calculations
# ============================================================

levels = calculate_levels(data)

st.divider()
st.subheader("Calculated Levels")

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Pipe Centre RL",
    f"{levels['pipe_center_rl']:.3f} m",
)

c2.metric(
    "Pipe Top RL",
    f"{levels['pipe_top_rl']:.3f} m",
)

c3.metric(
    "End Invert RL",
    f"{levels['pipe_end_invert_rl']:.3f} m",
)

c4.metric(
    "Available Clearance",
    f"{levels['available_clearance']:.3f} m",
)

if levels["available_clearance"] < required_clearance:
    st.warning(
        f"Available clearance is {levels['available_clearance']:.3f} m, "
        f"below the required {required_clearance:.3f} m."
    )
else:
    st.success(
        f"Available clearance is {levels['available_clearance']:.3f} m "
        f"and meets the required clearance."
    )


# ============================================================
# Generate
# ============================================================

st.divider()

if st.button(
    "Generate Drawing",
    type="primary",
    use_container_width=True,
):

    if master_file is None:
        st.error(
            "Please upload your master DXF first."
        )
        st.stop()

    if ezdxf is None:
        st.error(
            "ezdxf is not installed. Add ezdxf to requirements.txt "
            "and redeploy the Streamlit application."
        )
        st.stop()

    try:
        with st.spinner("Reading master DXF and generating drawing..."):

            output_bytes, final_levels, document = make_output_dxf(
                master_file,
                data,
            )

        entity_count = len(document.modelspace())
        layer_count = len(document.layers)
        block_count = len(document.blocks)

        st.success(
            "Drawing generated successfully."
        )

        st.write(
            f"Master DXF read successfully: "
            f"{entity_count:,} model-space entities, "
            f"{layer_count:,} layers, "
            f"{block_count:,} blocks."
        )

        filename = (
            f"Bridge_{drawing_no}_"
            f"Chainage_{chainage.replace('.', '_')}.dxf"
        )

        st.download_button(
            label="⬇ Download Generated DXF",
            data=output_bytes,
            file_name=filename,
            mime="application/dxf",
            use_container_width=True,
        )

        st.info(
            "The uploaded master drawing is retained. "
            "Generated pipe geometry is currently placed on "
            "GENERATED_PIPE and GENERATED_TEXT layers. "
            "Exact modification of the original 462 drawing "
            "objects requires mapping their actual CAD entities."
        )

    except Exception as error:
        st.error(
            "Drawing generation failed."
        )

        st.code(
            str(error),
            language="text",
        )

        st.markdown(
            """
**Important:** This error is now coming from the actual DXF reader,
not from the filename extension. If your `master_plan1.dxf` is the
same file that was previously validated, this version should read it
using a temporary `.dxf` file and `ezdxf.readfile()`.

If it still fails, the exact error shown in the box above will tell us
which DXF feature is causing the problem.
"""
        )


# ============================================================
# Diagnostics
# ============================================================

with st.expander("DXF diagnostics"):

    if master_file is None:
        st.write("No master DXF uploaded.")
    else:
        st.write("Filename:", master_file.name)
        st.write("Bytes:", len(master_file.getvalue()))

        if ezdxf is None:
            st.error("ezdxf is not installed.")
        else:
            if st.button("Test Master DXF"):
                try:
                    test_doc = read_uploaded_dxf(master_file)

                    st.success("DXF read successfully.")

                    st.write(
                        "DXF version:",
                        test_doc.dxfversion,
                    )

                    st.write(
                        "Model-space entities:",
                        len(test_doc.modelspace()),
                    )

                    st.write(
                        "Layers:",
                        len(test_doc.layers),
                    )

                    st.write(
                        "Blocks:",
                        len(test_doc.blocks),
                    )

                except Exception as error:
                    st.error(
                        "DXF test failed."
                    )
                    st.code(
                        str(error),
                        language="text",
                    )
