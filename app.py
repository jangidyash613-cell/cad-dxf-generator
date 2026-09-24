import streamlit as st
import ezdxf
import tempfile
import os
import re

st.set_page_config(
    page_title="Micro-Tunneling DXF Customizer",
    layout="wide"
)

st.title("🚇 Micro-Tunneling & Pipe Crossing CAD Generator")
st.markdown("Upload your baseline template DXF (`Br 462 ST-BRC...`), enter new dimensions, and generate the modified CAD file.")

# Sidebar - Inputs for the variables
st.sidebar.header("Design Parameters")

col1, col2 = st.sidebar.columns(2)
with col1:
    track_length = st.number_input("Length under Track (mm)", value=18500.0, step=100.0)
    total_length = st.number_input("Total Barrel Length (mm)", value=32000.0, step=500.0)
    width = st.number_input("Trench / Excavation Width (mm)", value=3200.0, step=50.0)

with col2:
    pipe_dia = st.number_input("Pipe Outer Diameter (OD) (mm)", value=1800.0, step=50.0)
    pipe_id = st.number_input("Pipe Inner Diameter (ID) (mm)", value=1500.0, step=50.0)
    pipe_thickness = st.number_input("Pipe Wall Thickness (mm)", value=150.0, step=5.0)

st.sidebar.markdown("---")
st.sidebar.subheader("Section A-A & B-B Labels")
label_sec_aa = st.sidebar.text_input("Section A-A Custom Note", "SECTION A-A (CROSS SECTION)")
label_sec_bb = st.sidebar.text_input("Section B-B Custom Note", "SECTION B-B (LONGITUDINAL)")

# File uploader
uploaded_file = st.file_uploader("Upload Base DXF Drawing", type=["dxf"])

def update_text_entity(text_str, params):
    """
    Intelligently replace placeholders or known patterns in drawing annotations.
    """
    # Replace direct placeholders if present in template
    text_str = text_str.replace("{LENGTH}", f"{params['length']:.0f}")
    text_str = text_str.replace("{WIDTH}", f"{params['width']:.0f}")
    text_str = text_str.replace("{DIA}", f"{params['dia']:.0f}")
    text_str = text_str.replace("{THK}", f"{params['thk']:.0f}")
    
    # Generic regex updates for matching common formats: e.g. "Dia. 1200", "150 thk", "L = 20.0m"
    # Update Diameter callouts: e.g. "1200 mm DIA", "Ø1200"
    text_str = re.sub(r'(%%c|Ø|\bDIA\.?\s*)\d+', rf'\g<1>{int(params["dia"])}', text_str, flags=re.IGNORECASE)
    
    # Update Thickness callouts: e.g. "120 THK", "THICKNESS 120"
    text_str = re.sub(r'(\bTHK\.?\s*|\bTHICKNESS\s*)\d+', rf'\g<1>{int(params["thk"])}', text_str, flags=re.IGNORECASE)
    
    return text_str

if uploaded_file is not None:
    st.success("File uploaded successfully!")

    if st.button("Generate & Download Updated DXF", type="primary"):
        # 1. Save uploaded stream safely to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as tmp_in:
            tmp_in.write(uploaded_file.getbuffer())
            tmp_in_path = tmp_in.name

        tmp_out_path = tmp_in_path.replace(".dxf", "_modified.dxf")

        try:
            # 2. Open using ezdxf file reader
            doc = ezdxf.readfile(tmp_in_path)
            
            params = {
                "length": track_length,
                "total_len": total_length,
                "width": width,
                "dia": pipe_dia,
                "id": pipe_id,
                "thk": pipe_thickness
            }

            count = 0
            
            # 3. Process Modelspace, Paperspace, and Blocks
            all_layouts = [doc.modelspace()] + [doc.layout(name) for name in doc.layout_names()]
            
            for layout in all_layouts:
                for entity in layout.query("TEXT MTEXT"):
                    old_text = entity.dxf.text if entity.dxftype() == "TEXT" else entity.text
                    new_text = update_text_entity(old_text, params)
                    if new_text != old_text:
                        if entity.dxftype() == "TEXT":
                            entity.dxf.text = new_text
                        else:
                            entity.text = new_text
                        count += 1

            # Search in block definitions (where sections like A-A and B-B are usually stored)
            for block in doc.blocks:
                for entity in block.query("TEXT MTEXT"):
                    old_text = entity.dxf.text if entity.dxftype() == "TEXT" else entity.text
                    new_text = update_text_entity(old_text, params)
                    if new_text != old_text:
                        if entity.dxftype() == "TEXT":
                            entity.dxf.text = new_text
                        else:
                            entity.text = new_text
                        count += 1

            # 4. Save to temporary output
            doc.saveas(tmp_out_path)

            # 5. Read back as bytes for browser download
            with open(tmp_out_path, "rb") as f:
                output_bytes = f.read()

            st.success(f"Processing Complete! Updated {count} text annotations.")
            st.download_button(
                label="📥 Click here to Download DXF",
                data=output_bytes,
                file_name="Updated_" + uploaded_file.name,
                mime="application/dxf"
            )

        except Exception as e:
            st.error(f"Failed to process file: {str(e)}")
        finally:
            # Clean up disk memory
            if os.path.exists(tmp_in_path):
                os.remove(tmp_in_path)
            if os.path.exists(tmp_out_path):
                os.remove(tmp_out_path)
