import io
import math
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
st.caption("Bridge + Pipe + Level data driven CAD drawing generator")


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate(data):
    od_m = to_float(data["pipe_od_mm"]) / 1000.0
    invert_rl = to_float(data["pipe_invert_rl"])
    underside_rl = to_float(data["bridge_underside_rl"])
    slope_percent = to_float(data["pipe_slope_percent"])
    pipe_length = to_float(data["pipe_length_m"])

    center_rl = invert_rl + od_m / 2.0
    top_rl = invert_rl + od_m
    end_invert_rl = invert_rl + pipe_length * slope_percent / 100.0
    available_clearance = underside_rl - top_rl

    return {
        "pipe_od_m": od_m,
        "pipe_center_rl": center_rl,
        "pipe_top_rl": top_rl,
        "pipe_end_invert_rl": end_invert_rl,
        "available_clearance": available_clearance,
    }


def add_layer(doc, name, color):
    if name not in doc.layers:
        doc.layers.add(name=name, color=color)


def add_generated_pipe(doc, data, calc):
    """Add a temporary generated pipe representation.

    The master drawing is retained. The exact 462 entity mapping is not guessed.
    """
    msp = doc.modelspace()
    add_layer(doc, "GENERATED_PIPE", 1)
    add_layer(doc, "GENERATED_TEXT", 2)

    # Temporary origin. This must later be mapped to the real pipe location
    # in the 462 master drawing.
    x0 = 0.0
    y0 = 0.0

    od = calc["pipe_od_m"]
    length = max(to_float(data["pipe_length_m"], 20.0), 0.001)
    angle = math.radians(to_float(data["crossing_angle_deg"], 90.0))

    dx = length * math.cos(angle)
    dy = length * math.sin(angle)

    nx = -math.sin(angle) * od / 2.0
    ny = math.cos(angle) * od / 2.0

    geometry = [
        ((x0, y0), (x0 + dx, y0 + dy)),
        ((x0 + nx, y0 + ny), (x0 + dx + nx, y0 + dy + ny)),
        ((x0 - nx, y0 - ny), (x0 + dx - nx, y0 + dy - ny)),
        ((x0 + nx, y0 + ny), (x0 - nx, y0 - ny)),
        ((x0 + dx + nx, y0 + dy + ny), (x0 + dx - nx, y0 + dy - ny)),
    ]

    for start, end in geometry:
        msp.add_line(start, end, dxfattribs={"layer": "GENERATED_PIPE"})

    notes = [
        f"BRIDGE/DRAWING NO.: {data['drawing_no']}",
        f"CHAINAGE: {data['chainage']}",
        f"PIPE OD: {data['pipe_od_mm']:.1f} mm",
        f"NO. OF PIPES: {data['number_of_pipes']}",
        f"PIPE INVERT RL: {to_float(data['pipe_invert_rl']):.3f}",
        f"PIPE CENTRE RL: {calc['pipe_center_rl']:.3f}",
        f"PIPE TOP RL: {calc['pipe_top_rl']:.3f}",
        f"PIPE END INVERT RL: {calc['pipe_end_invert_rl']:.3f}",
        f"AVAILABLE CLEARANCE: {calc['available_clearance']:.3f} m",
    ]

    y = -2.0
    for note in notes:
        entity = msp.add_text(
            note,
            dxfattribs={"layer": "GENERATED_TEXT", "height": 0.25},
        )
        entity.set_placement((x0, y))
        y -= 0.35


def read_uploaded_dxf(uploaded_file):
    """Read a DXF using its bytes, not its filename extension.

    This fixes the common situation where Streamlit receives a valid DXF but
    the filename check incorrectly rejects it.
    """
    if ezdxf is None:
        raise RuntimeError(
            "The package 'ezdxf' is not installed. Add 'ezdxf' to requirements.txt."
        )

    raw = uploaded_file.getvalue()
    if not raw:
        raise RuntimeError("The uploaded file is empty.")

    # DXF is an ASCII/text CAD exchange format in the normal case. Decode only
    # for validation; ezdxf itself receives the original bytes.
    sample = raw[:4096].decode("utf-8", errors="ignore").upper()

    # Do NOT reject based only on the filename. Check for common DXF markers.
    looks_like_dxf = (
        "SECTION" in sample
        and ("HEADER" in sample or "ENTITIES" in sample or "TABLES" in sample)
    )

    if not looks_like_dxf:
        raise RuntimeError(
            "The uploaded file does not appear to be a valid ASCII DXF. "
            "Please open it in AutoCAD and use Save As > DXF."
        )

    try:
        return ezdxf.read(io.BytesIO(raw))
    except Exception as exc:
        raise RuntimeError(
            "The file has a DXF filename but ezdxf could not read it. "
            "Please re-save the drawing as AutoCAD DXF 2013/2018 and upload it again."
        ) from exc


def generate_dxf(uploaded_file, data):
    doc = read_uploaded_dxf(uploaded_file)
    calc = calculate(data)
    add_generated_pipe(doc, data, calc)

    buffer = io.StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode("utf-8"), calc


with st.sidebar:
    st.header("1. Master Drawing")
    master_file = st.file_uploader(
        "Upload your DXF master drawing",
        type=["dxf"],
        accept_multiple_files=False,
        help="Upload the actual .dxf file. The app validates the file contents, not just the filename.",
    )

    if master_file is not None:
        st.success(f"Loaded: {master_file.name}")
        st.caption(f"Size: {len(master_file.getvalue()) / 1024:.1f} KB")

    st.divider()
    st.info(
        "Variable inputs: Bridge Data, Pipe Data and Level Data. "
        "Other master drawing geometry is kept as the template."
    )

st.header("2. Variable Inputs")

bridge_col, pipe_col, level_col = st.columns(3)

with bridge_col:
    st.subheader("Bridge Data")
    drawing_no = st.text_input("Bridge / Drawing No.", value="462")
    chainage = st.text_input("Chainage", value="273.640")
    span_length = st.number_input("Span Length (m)", value=2.400, step=0.001, format="%.3f")
    bridge_width = st.number_input("Bridge Width (m)", value=8.000, step=0.001, format="%.3f")

with pipe_col:
    st.subheader("Pipe Data")
    pipe_od = st.number_input("Pipe OD (mm)", min_value=1.0, value=1200.0, step=1.0)
    pipe_id = st.number_input("Pipe ID (mm)", min_value=0.0, value=1000.0, step=1.0)
    number_of_pipes = st.number_input("Number of Pipes", min_value=1, value=1, step=1)
    pipe_length = st.number_input("Pipe Length (m)", min_value=0.001, value=20.0, step=0.001)
    pipe_slope = st.number_input("Pipe Slope (%)", value=0.500, step=0.001, format="%.3f")
    pipe_spacing = st.number_input("Pipe Spacing (m)", min_value=0.0, value=1.500, step=0.001)
    crossing_angle = st.number_input("Crossing Angle (degrees)", value=90.0, step=0.1)

with level_col:
    st.subheader("Level Data")
    bed_rl = st.number_input("Existing / Bed RL (m)", value=100.000, step=0.001, format="%.3f")
    bridge_underside_rl = st.number_input("Bridge Underside RL (m)", value=103.000, step=0.001, format="%.3f")
    pipe_invert_rl = st.number_input("Pipe Invert RL (m)", value=101.000, step=0.001, format="%.3f")
    required_cover = st.number_input("Required Cover (m)", value=1.000, step=0.001, format="%.3f")
    required_clearance = st.number_input("Required Clearance (m)", value=0.600, step=0.001, format="%.3f")


data = {
    "drawing_no": drawing_no,
    "chainage": chainage,
    "span_length_m": span_length,
    "bridge_width_m": bridge_width,
    "pipe_od_mm": pipe_od,
    "pipe_id_mm": pipe_id,
    "number_of_pipes": number_of_pipes,
    "pipe_length_m": pipe_length,
    "pipe_slope_percent": pipe_slope,
    "pipe_spacing_m": pipe_spacing,
    "crossing_angle_deg": crossing_angle,
    "bed_rl": bed_rl,
    "bridge_underside_rl": bridge_underside_rl,
    "pipe_invert_rl": pipe_invert_rl,
    "required_cover": required_cover,
    "required_clearance": required_clearance,
}

calc = calculate(data)

st.divider()
st.header("3. Calculated Levels")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Pipe Centre RL", f"{calc['pipe_center_rl']:.3f} m")
c2.metric("Pipe Top RL", f"{calc['pipe_top_rl']:.3f} m")
c3.metric("End Invert RL", f"{calc['pipe_end_invert_rl']:.3f} m")
c4.metric("Available Clearance", f"{calc['available_clearance']:.3f} m")

if calc["available_clearance"] < required_clearance:
    st.warning(
        f"Available clearance {calc['available_clearance']:.3f} m is below "
        f"the required {required_clearance:.3f} m."
    )
else:
    st.success("Available clearance meets the required clearance.")

st.divider()

if st.button("Generate Drawing", type="primary", use_container_width=True):
    if ezdxf is None:
        st.error("ezdxf is missing. Add ezdxf to requirements.txt and redeploy.")
        st.stop()

    if master_file is None:
        st.error("Please upload your DXF master drawing first.")
        st.stop()

    with st.spinner("Reading master DXF and generating drawing..."):
        try:
            output, result = generate_dxf(master_file, data)
        except Exception as exc:
            st.error(f"Drawing generation failed: {exc}")
            st.stop()

    safe_chainage = str(chainage).replace("/", "_").replace("\\", "_").replace(".", "_")
    filename = f"Bridge_{drawing_no}_Chainage_{safe_chainage}.dxf"

    st.success("DXF generated successfully.")

    st.download_button(
        label="⬇ Download Generated DXF",
        data=output,
        file_name=filename,
        mime="application/dxf",
        use_container_width=True,
    )

    st.info(
        "The uploaded master DXF is retained as the base. The current generated "
        "pipe is placed on GENERATED_PIPE. Exact editing of the existing 462 "
        "drawing objects still requires mapping the real CAD entities."
    )

with st.expander("CAD diagnostic information"):
    if master_file is None:
        st.write("Upload a DXF to inspect it.")
    elif ezdxf is None:
        st.write("ezdxf is not installed.")
    else:
        try:
            diagnostic_doc = read_uploaded_dxf(master_file)
            st.write("DXF loaded successfully.")
            st.write(f"DXF version: {diagnostic_doc.dxfversion}")
            st.write(f"Layers: {len(diagnostic_doc.layers)}")
            st.write(f"Blocks: {len(diagnostic_doc.blocks)}")
            st.write(f"Modelspace entities: {len(diagnostic_doc.modelspace())}")
        except Exception as exc:
            st.error(str(exc))
