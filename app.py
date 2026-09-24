import streamlit as st
import ezdxf
import tempfile
import os

st.set_page_config(page_title="Parametric DXF Generator", layout="centered")

st.title("Micro-Tunneling / Culvert DXF Generator")
st.write("Upload your base template DXF and update dimensional parameters for Sections A-A and B-B.")

# Sidebar parameter inputs
st.sidebar.header("Section Parameters")
pipe_length = st.sidebar.number_input("Total Length (m)", value=30.0, step=0.5)
trench_width = st.sidebar.number_input("Trench / Bed Width (mm)", value=2500.0, step=50.0)
pipe_dia = st.sidebar.number_input("Pipe Diameter (mm)", value=1200.0, step=50.0)
pipe_thickness = st.sidebar.number_input("Pipe Wall Thickness (mm)", value=120.0, step=5.0)

uploaded_file = st.file_uploader("Upload Base DXF Template (.dxf)", type=["dxf"])

if uploaded_file is not None:
    st.info(f"File uploaded: {uploaded_file.name}")
    
    if st.button("Generate & Update Drawing"):
        # Create temporary files to prevent binary stream decode errors
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as temp_in:
            temp_in.write(uploaded_file.getvalue())
            temp_in_path = temp_in.name

        temp_out_path = temp_in_path.replace(".dxf", "_out.dxf")

        try:
            # Read DXF directly from disk
            doc = ezdxf.readfile(temp_in_path)
            msp = doc.modelspace()

            # Update placeholder text entities
            updated_count = 0
            for entity in msp.query("TEXT MTEXT"):
                txt = entity.dxf.text
                original = txt
                
                if "{LENGTH}" in txt:
                    txt = txt.replace("{LENGTH}", f"{pipe_length:.2f} m")
                if "{WIDTH}" in txt:
                    txt = txt.replace("{WIDTH}", f"{trench_width:.0f}")
                if "{DIA}" in txt:
                    txt = txt.replace("{DIA}", f"{pipe_dia:.0f} mm")
                if "{THK}" in txt:
                    txt = txt.replace("{THK}", f"{pipe_thickness:.1f} mm")
                
                if txt != original:
                    entity.dxf.text = txt
                    updated_count += 1

            # Save clean modified DXF
            doc.saveas(temp_out_path)

            with open(temp_out_path, "rb") as f:
                out_bytes = f.read()

            st.success(f"Success! Updated {updated_count} dynamic text references.")
            st.download_button(
                label="Download Modified DXF",
                data=out_bytes,
                file_name=f"Modified_{uploaded_file.name}",
                mime="application/dxf"
            )
        except Exception as e:
            st.error(f"Error processing DXF: {e}")
        finally:
            # Clean up temporary files
            if os.path.exists(temp_in_path):
                os.remove(temp_in_path)
            if os.path.exists(temp_out_path):
                os.remove(temp_out_path)
