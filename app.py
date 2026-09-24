import streamlit as st
import ezdxf
from ezdxf.math import Vec3
import tempfile
import os
import re

st.set_page_config(page_title="Parametric DXF Generator", layout="centered")

st.title("🚇 Micro-Tunneling Drawing Generator (Geometry + Text)")
st.write("Adjust parameters to dynamically update both drawing geometry and text labels.")

# Upload file or use default
uploaded_file = st.file_uploader("Upload Base DXF Template", type=["dxf"])

# UI Inputs
st.sidebar.header("Input Dimensions")

# Current/Base dimensions (used for calculating scale factors)
st.sidebar.subheader("Baseline (Original) Dimensions")
base_length = st.sidebar.number_input("Original Length (mm)", value=18500.0, step=100.0)
base_outer_dia = st.sidebar.number_input("Original Pipe Outer Dia (mm)", value=1200.0, step=50.0)
base_thk = st.sidebar.number_input("Original Wall Thickness (mm)", value=120.0, step=5.0)

# Target new dimensions
st.sidebar.subheader("New Target Dimensions")
new_length = st.sidebar.number_input("New Length (mm)", value=22000.0, step=100.0)
new_outer_dia = st.sidebar.number_input("New Pipe Outer Dia (mm)", value=1500.0, step=50.0)
new_thk = st.sidebar.number_input("New Wall Thickness (mm)", value=150.0, step=5.0)
new_width = st.sidebar.number_input("Trench / Formation Width (mm)", value=3500.0, step=100.0)

# Layer selection
st.sidebar.subheader("Target Layers for Geometry")
pipe_layer = st.sidebar.text_input("Pipe Geometry Layer", value="CULVERT")
dim_layer = st.sidebar.text_input("Dimension Layer", value="Prop. Dimensions")

def update_geometry_and_text(doc, base_len, new_len, base_dia, new_dia, base_t, new_t, width):
    msp = doc.modelspace()
    
    # Calculate geometric scaling factors
    len_scale = new_len / base_len if base_len > 0 else 1.0
    outer_radius_new = new_dia / 2.0
    inner_radius_new = (new_dia - (2 * new_t)) / 2.0
    
    # ---------------------------------------------------------
    # 1. Update Geometry: Circles (Section Views / Pipe Section)
    # ---------------------------------------------------------
    for circle in msp.query('CIRCLE'):
        if circle.dxf.layer.upper() == pipe_layer.upper() or pipe_layer == "":
            current_r = circle.dxf.radius
            # Detect whether it is the inner or outer circle based on radius
            base_inner_r = (base_dia - (2 * base_t)) / 2.0
            base_outer_r = base_dia / 2.0
            
            # If close to base outer radius, scale to new outer radius
            if abs(current_r - base_outer_r) < 50:
                circle.dxf.radius = outer_radius_new
            # If close to base inner radius, scale to new inner radius
            elif abs(current_r - base_inner_r) < 50:
                circle.dxf.radius = inner_radius_new

    # ---------------------------------------------------------
    # 2. Update Geometry: Lines (Length Stretches in Section B-B)
    # ---------------------------------------------------------
    # For horizontal pipe lines running along the length axis
    delta_length = new_len - base_len
    if abs(delta_length) > 0.001:
        for line in msp.query('LINE'):
            if line.dxf.layer.upper() == pipe_layer.upper() or pipe_layer == "":
                start = line.dxf.start
                end = line.dxf.end
                
                # Check if it's a longitudinal line (mostly horizontal: delta_x >> delta_y)
                dx = end.x - start.x
                dy = end.y - start.y
                if abs(dx) > abs(dy) and abs(dx) > (base_len * 0.5):
                    # Adjust the line length by moving the endpoint
                    if end.x > start.x:
                        line.dxf.end = Vec3(start.x + (dx * len_scale), end.y, end.z)
                    else:
                        line.dxf.start = Vec3(end.x + (-dx * len_scale), start.y, start.z)

    # ---------------------------------------------------------
    # 3. Update Text and Dimension Overrides
    # ---------------------------------------------------------
    replacements = {
        "{LENGTH}": f"{new_len:.0f}",
        "{DIA}": f"{new_dia:.0f}",
        "{THK}": f"{new_thk:.0f}",
        "{WIDTH}": f"{width:.0f}",
        str(int(base_len)): str(int(new_len)),
        str(int(base_dia)): str(int(new_dia)),
        str(int(base_t)): str(int(new_t)),
    }

    containers = [msp] + [doc.layout(name) for name in doc.layout_names()] + [b for b in doc.blocks]
    for container in containers:
        for e in container.query('TEXT MTEXT DIMENSION'):
            if e.dxftype() == 'TEXT':
                for old_val, new_val in replacements.items():
                    if old_val in e.dxf.text:
                        e.dxf.text = e.dxf.text.replace(old_val, new_val)
            elif e.dxftype() == 'MTEXT':
                for old_val, new_val in replacements.items():
                    if old_val in e.text:
                        e.text = e.text.replace(old_val, new_val)
            elif e.dxftype() == 'DIMENSION':
                if e.dxf.text:
                    for old_val, new_val in replacements.items():
                        if old_val in e.dxf.text:
                            e.dxf.text = e.dxf.text.replace(old_val, new_val)

if uploaded_file is not None:
    if st.button("Generate & Download Updated DXF", type="primary"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as tmp_in:
            tmp_in.write(uploaded_file.getbuffer())
            tmp_in_path = tmp_in.name

        tmp_out_path = tmp_in_path.replace(".dxf", "_out.dxf")

        try:
            doc = ezdxf.readfile(tmp_in_path)

            update_geometry_and_text(
                doc,
                base_length, new_length,
                base_outer_dia, new_outer_dia,
                base_thk, new_thk,
                new_width
            )

            doc.saveas(tmp_out_path)

            with open(tmp_out_path, "rb") as f:
                st.success("Drawing geometry and dimensions successfully updated!")
                st.download_button(
                    label="📥 Download Modified DXF",
                    data=f.read(),
                    file_name="Parametric_" + uploaded_file.name,
                    mime="application/dxf"
                )
        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            if os.path.exists(tmp_in_path):
                os.remove(tmp_in_path)
            if os.path.exists(tmp_out_path):
                os.remove(tmp_out_path)
