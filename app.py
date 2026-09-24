import streamlit as st
import ezdxf
import io

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
        try:
            # Read DXF stream into ezdxf
            file_contents = uploaded_file.getvalue().decode("latin1")
            doc = ezdxf.read(io.StringIO(file_contents))
            msp = doc.modelspace()

            # Replace placeholder tags in TEXT and MTEXT entities
            updated_count = 0
            for entity in msp.query("TEXT MTEXT"):
                txt = entity.dxf.text
                original = txt
                
                # Tag mapping: match placeholders or customize to target exact layer text
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

            # Export modified drawing to memory
            out_stream = io.StringIO()
            doc.write(out_stream)
            out_bytes = out_stream.getvalue().encode("latin1")

            st.success(f"Updated {updated_count} dynamic text references.")
            st.download_button(
                label="Download Modified DXF",
                data=out_bytes,
                file_name=f"Modified_{uploaded_file.name}",
                mime="application/dxf"
            )
        except Exception as e:
            st.error(f"Error processing DXF: {e}")
