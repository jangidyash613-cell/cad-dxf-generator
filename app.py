import io
import math
import streamlit as st

try:
    import ezdxf
except ImportError:
    ezdxf = None

st.set_page_config(page_title='Bridge Pipe Drawing Generator', page_icon='📐', layout='wide')
st.title('📐 Bridge Pipe Drawing Generator')
st.caption('Generate a pipe-under-bridge DXF from a fixed master drawing.')


def n(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def calc(d):
    od = n(d['pipe_od']) / 1000.0
    inv = n(d['pipe_invert_rl'])
    underside = n(d['bridge_underside_rl'])
    slope = n(d['pipe_slope'])
    length = n(d['pipe_length'])
    return {
        'pipe_center_rl': inv + od / 2,
        'pipe_top_rl': inv + od,
        'pipe_end_invert_rl': inv + length * slope / 100,
        'available_clearance': underside - (inv + od),
        'pipe_od_m': od,
    }


def make_dxf(master_bytes, d):
    if ezdxf is None:
        raise RuntimeError('ezdxf is not installed. Add ezdxf to requirements.txt.')
    try:
        doc = ezdxf.read(io.BytesIO(master_bytes))
    except Exception as exc:
        raise RuntimeError('Master file must be DXF. Convert DWG to DXF first.') from exc

    c = calc(d)
    if 'GENERATED_PIPE' not in doc.layers:
        doc.layers.add(name='GENERATED_PIPE', color=1)
    if 'GENERATED_TEXT' not in doc.layers:
        doc.layers.add(name='GENERATED_TEXT', color=2)

    msp = doc.modelspace()
    x0, y0 = 0.0, 0.0  # Replace after mapping the actual 462 CAD coordinates.
    od = c['pipe_od_m']
    length = n(d['pipe_length'], 20)
    a = math.radians(n(d['crossing_angle'], 90))
    dx, dy = length * math.cos(a), length * math.sin(a)
    nx, ny = -math.sin(a) * od / 2, math.cos(a) * od / 2

    lines = [
        ((x0, y0), (x0 + dx, y0 + dy)),
        ((x0 + nx, y0 + ny), (x0 + dx + nx, y0 + dy + ny)),
        ((x0 - nx, y0 - ny), (x0 + dx - nx, y0 + dy - ny)),
        ((x0 + nx, y0 + ny), (x0 - nx, y0 - ny)),
        ((x0 + dx + nx, y0 + dy + ny), (x0 + dx - nx, y0 + dy - ny)),
    ]
    for p1, p2 in lines:
        msp.add_line(p1, p2, dxfattribs={'layer': 'GENERATED_PIPE'})

    labels = [
        f"BRIDGE/DRAWING NO.: {d['drawing_no']}",
        f"CHAINAGE: {d['chainage']}",
        f"PIPE OD: {d['pipe_od']} mm",
        f"NO. OF PIPES: {d['number_of_pipes']}",
        f"PIPE INVERT RL: {n(d['pipe_invert_rl']):.3f}",
        f"PIPE CENTRE RL: {c['pipe_center_rl']:.3f}",
        f"PIPE TOP RL: {c['pipe_top_rl']:.3f}",
        f"PIPE END INVERT RL: {c['pipe_end_invert_rl']:.3f}",
    ]
    y = -2.0
    for s in labels:
        t = msp.add_text(s, dxfattribs={'layer': 'GENERATED_TEXT', 'height': 0.25})
        t.set_placement((0, y))
        y -= 0.35

    out = io.StringIO()
    doc.write(out)
    return out.getvalue().encode('utf-8'), c


with st.sidebar:
    st.header('Master CAD')
    master = st.file_uploader('Upload master DXF', type=['dxf'])
    st.info('DWG is not directly readable by ezdxf. Convert the master DWG to DXF first.')

c1, c2, c3 = st.columns(3)
with c1:
    st.subheader('Bridge Data')
    drawing_no = st.text_input('Bridge / Drawing No.', '462')
    chainage = st.text_input('Chainage', '273.640')
    span_length = st.number_input('Span Length (m)', value=2.400, step=0.001, format='%.3f')
    bridge_width = st.number_input('Bridge Width (m)', value=8.000, step=0.001, format='%.3f')
with c2:
    st.subheader('Pipe Data')
    pipe_od = st.number_input('Pipe OD (mm)', min_value=1.0, value=1200.0, step=1.0)
    pipe_id = st.number_input('Pipe ID (mm)', min_value=0.0, value=1000.0, step=1.0)
    number_of_pipes = st.number_input('Number of Pipes', min_value=1, value=1, step=1)
    pipe_length = st.number_input('Pipe Length (m)', min_value=0.001, value=20.0, step=0.001)
    pipe_slope = st.number_input('Pipe Slope (%)', value=0.500, step=0.001, format='%.3f')
    pipe_spacing = st.number_input('Pipe Spacing (m)', min_value=0.0, value=1.500, step=0.001)
    crossing_angle = st.number_input('Crossing Angle (degrees)', value=90.0, step=0.1)
with c3:
    st.subheader('Level Data')
    bed_rl = st.number_input('Existing / Bed RL (m)', value=100.000, step=0.001, format='%.3f')
    bridge_underside_rl = st.number_input('Bridge Underside RL (m)', value=103.000, step=0.001, format='%.3f')
    pipe_invert_rl = st.number_input('Pipe Invert RL (m)', value=101.000, step=0.001, format='%.3f')
    required_cover = st.number_input('Required Cover (m)', value=1.000, step=0.001, format='%.3f')
    required_clearance = st.number_input('Required Clearance (m)', value=0.600, step=0.001, format='%.3f')

data = locals()
c = calc(data)

st.divider()
st.subheader('Calculated Levels')
a, b, cc, d4 = st.columns(4)
a.metric('Pipe Centre RL', f"{c['pipe_center_rl']:.3f} m")
b.metric('Pipe Top RL', f"{c['pipe_top_rl']:.3f} m")
cc.metric('End Invert RL', f"{c['pipe_end_invert_rl']:.3f} m")
d4.metric('Available Clearance', f"{c['available_clearance']:.3f} m")

if c['available_clearance'] < required_clearance:
    st.warning('Available clearance is below the required clearance.')
else:
    st.success('Available clearance meets the required clearance.')

if st.button('Generate Drawing', type='primary', use_container_width=True):
    if ezdxf is None:
        st.error('ezdxf is missing. Add ezdxf to requirements.txt and redeploy.')
    elif master is None:
        st.error('Please upload the master DXF first.')
    else:
        try:
            output, _ = make_dxf(master.getvalue(), data)
            filename = f"Bridge_{drawing_no}_Chainage_{chainage.replace('.', '_')}.dxf"
            st.success('Drawing generated successfully.')
            st.download_button('⬇ Download Generated DXF', output, filename, 'application/dxf', use_container_width=True)
            st.info('This version keeps the master DXF as the base and adds generated pipe geometry. Exact replacement of the existing 462 drawing objects requires mapping the actual CAD entities.')
        except Exception as exc:
            st.error(f'Drawing generation failed: {exc}')

