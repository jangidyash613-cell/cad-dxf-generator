import os
import math
import uuid
from pathlib import Path

from flask import Flask, request, send_file, render_template_string, jsonify

try:
    import ezdxf
except ImportError:
    ezdxf = None

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

TEMPLATE_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

MASTER_DXF = TEMPLATE_DIR / "master.dxf"


HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Bridge Pipe Drawing Generator</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: Arial, sans-serif;
            background: #eef1f5;
            color: #172033;
        }
        .container {
            max-width: 1100px;
            margin: 30px auto;
            padding: 20px;
        }
        h1 { margin-bottom: 8px; }
        .subtitle {
            color: #5d6675;
            margin-bottom: 24px;
        }
        .card {
            background: white;
            border-radius: 14px;
            padding: 22px;
            margin-bottom: 18px;
            box-shadow: 0 4px 18px rgba(0,0,0,.07);
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
        }
        label {
            display: block;
            font-weight: 700;
            margin-bottom: 6px;
        }
        input, select {
            width: 100%;
            padding: 11px 12px;
            border: 1px solid #cbd2dc;
            border-radius: 8px;
            font-size: 15px;
        }
        button {
            border: 0;
            border-radius: 9px;
            padding: 12px 20px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            background: #1264d6;
            color: white;
        }
        button:hover { background: #0d4fae; }
        .secondary {
            background: #687386;
        }
        .result {
            background: #f6f8fb;
            border-radius: 10px;
            padding: 15px;
            margin-top: 15px;
            white-space: pre-wrap;
        }
        .warning {
            background: #fff5d8;
            border: 1px solid #efd98d;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 16px;
        }
        .success {
            background: #e8f7ed;
            border: 1px solid #a8d9b7;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 16px;
        }
        .error {
            background: #fdeaea;
            border: 1px solid #e0a5a5;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 16px;
        }
        @media (max-width: 700px) {
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>Bridge Pipe Drawing Generator</h1>
    <div class="subtitle">
        Generate a pipe-under-bridge drawing from a fixed CAD template.
    </div>

    {% if not dxf_available %}
    <div class="warning">
        The Python package <b>ezdxf</b> is not installed.
        Install it with: <b>pip install ezdxf flask</b>
    </div>
    {% endif %}

    <div class="card">
        <h2>1. Master Drawing</h2>
        <form action="/upload-master" method="post" enctype="multipart/form-data">
            <input type="file" name="master_file" accept=".dxf,.dwg" required>
            <br><br>
            <button type="submit" class="secondary">Upload Master CAD</button>
        </form>

        {% if master_exists %}
        <div class="success" style="margin-top:15px;">
            Master DXF is available and ready.
        </div>
        {% endif %}
    </div>

    <form action="/generate" method="post">
        <div class="card">
            <h2>2. Bridge Data</h2>
            <div class="grid">
                <div>
                    <label>Bridge / Drawing No.</label>
                    <input name="drawing_no" value="462">
                </div>
                <div>
                    <label>Chainage</label>
                    <input name="chainage" value="273.640">
                </div>
                <div>
                    <label>Span Length (m)</label>
                    <input name="span_length" type="number" step="0.001" value="2.400">
                </div>
                <div>
                    <label>Bridge Width (m)</label>
                    <input name="bridge_width" type="number" step="0.001" value="8.000">
                </div>
            </div>
        </div>

        <div class="card">
            <h2>3. Pipe Data</h2>
            <div class="grid">
                <div>
                    <label>Pipe OD (mm)</label>
                    <input name="pipe_od" type="number" step="0.1" value="1200">
                </div>
                <div>
                    <label>Pipe ID (mm)</label>
                    <input name="pipe_id" type="number" step="0.1" value="1000">
                </div>
                <div>
                    <label>Number of Pipes</label>
                    <input name="number_of_pipes" type="number" min="1" step="1" value="1">
                </div>
                <div>
                    <label>Pipe Length (m)</label>
                    <input name="pipe_length" type="number" step="0.001" value="20">
                </div>
                <div>
                    <label>Pipe Slope (%)</label>
                    <input name="pipe_slope" type="number" step="0.001" value="0.500">
                </div>
                <div>
                    <label>Pipe Spacing (m)</label>
                    <input name="pipe_spacing" type="number" step="0.001" value="1.500">
                </div>
                <div>
                    <label>Crossing Angle (degrees)</label>
                    <input name="crossing_angle" type="number" step="0.1" value="90">
                </div>
            </div>
        </div>

        <div class="card">
            <h2>4. Level Data</h2>
            <div class="grid">
                <div>
                    <label>Existing / Bed RL (m)</label>
                    <input name="bed_rl" type="number" step="0.001" value="100.000">
                </div>
                <div>
                    <label>Bridge Underside RL (m)</label>
                    <input name="bridge_underside_rl" type="number" step="0.001" value="103.000">
                </div>
                <div>
                    <label>Pipe Invert RL (m)</label>
                    <input name="pipe_invert_rl" type="number" step="0.001" value="101.000">
                </div>
                <div>
                    <label>Required Cover (m)</label>
                    <input name="required_cover" type="number" step="0.001" value="1.000">
                </div>
                <div>
                    <label>Required Clearance (m)</label>
                    <input name="required_clearance" type="number" step="0.001" value="0.600">
                </div>
            </div>
        </div>

        <div class="card">
            <h2>5. Generate</h2>
            <button type="submit">Generate Drawing</button>
            <div id="result"></div>
        </div>
    </form>
</div>
</body>
</html>
"""


def number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_values(data):
    pipe_od_mm = number(data.get("pipe_od"))
    pipe_od_m = pipe_od_mm / 1000.0

    pipe_invert_rl = number(data.get("pipe_invert_rl"))
    bridge_underside_rl = number(data.get("bridge_underside_rl"))
    pipe_slope_percent = number(data.get("pipe_slope"))
    pipe_length = number(data.get("pipe_length"))

    pipe_center_rl = pipe_invert_rl + (pipe_od_m / 2.0)
    pipe_top_rl = pipe_invert_rl + pipe_od_m

    slope_difference = pipe_length * (pipe_slope_percent / 100.0)
    pipe_end_invert_rl = pipe_invert_rl + slope_difference

    available_clearance = bridge_underside_rl - pipe_top_rl

    return {
        "pipe_od_m": pipe_od_m,
        "pipe_center_rl": pipe_center_rl,
        "pipe_top_rl": pipe_top_rl,
        "pipe_end_invert_rl": pipe_end_invert_rl,
        "available_clearance": available_clearance,
    }


def ensure_layer(doc, name, color=1):
    if name not in doc.layers:
        doc.layers.add(name=name, color=color)


def add_generated_geometry(doc, data, calc):
    """
    Adds a clearly separated generated pipe group.

    IMPORTANT:
    The master drawing remains unchanged. This function currently adds
    generated geometry rather than guessing which existing master entities
    correspond to site-specific dimensions.

    Once the exact 462 drawing entity/layer mapping is known, this function
    is the place to update the existing master entities instead.
    """
    msp = doc.modelspace()

    ensure_layer(doc, "GENERATED_PIPE", 1)
    ensure_layer(doc, "GENERATED_TEXT", 2)

    # Drawing coordinates are intentionally isolated from the master template.
    # These are placeholder coordinates until the exact CAD coordinate system
    # of the 462 master drawing is mapped.
    x0 = 0.0
    y0 = 0.0

    od = calc["pipe_od_m"]
    length = number(data.get("pipe_length"), 20.0)
    angle = number(data.get("crossing_angle"), 90.0)

    rad = math.radians(angle)
    dx = length * math.cos(rad)
    dy = length * math.sin(rad)

    # Main pipe centerline.
    msp.add_line(
        (x0, y0),
        (x0 + dx, y0 + dy),
        dxfattribs={"layer": "GENERATED_PIPE"}
    )

    # Pipe outline as two offset lines for a simple representation.
    nx = -math.sin(rad) * od / 2.0
    ny = math.cos(rad) * od / 2.0

    msp.add_line(
        (x0 + nx, y0 + ny),
        (x0 + dx + nx, y0 + dy + ny),
        dxfattribs={"layer": "GENERATED_PIPE"}
    )

    msp.add_line(
        (x0 - nx, y0 - ny),
        (x0 + dx - nx, y0 + dy - ny),
        dxfattribs={"layer": "GENERATED_PIPE"}
    )

    # End caps.
    msp.add_line(
        (x0 + nx, y0 + ny),
        (x0 - nx, y0 - ny),
        dxfattribs={"layer": "GENERATED_PIPE"}
    )

    msp.add_line(
        (x0 + dx + nx, y0 + dy + ny),
        (x0 + dx - nx, y0 + dy - ny),
        dxfattribs={"layer": "GENERATED_PIPE"}
    )

    text_lines = [
        f"BRIDGE/DRAWING NO.: {data.get('drawing_no', '')}",
        f"CHAINAGE: {data.get('chainage', '')}",
        f"PIPE OD: {data.get('pipe_od', '')} mm",
        f"NO. OF PIPES: {data.get('number_of_pipes', '')}",
        f"PIPE INVERT RL: {number(data.get('pipe_invert_rl')):.3f}",
        f"PIPE CENTRE RL: {calc['pipe_center_rl']:.3f}",
        f"PIPE TOP RL: {calc['pipe_top_rl']:.3f}",
        f"PIPE END INVERT RL: {calc['pipe_end_invert_rl']:.3f}",
        f"AVAILABLE CLEARANCE: {calc['available_clearance']:.3f} m",
    ]

    text_y = y0 - 2.0

    for line in text_lines:
        msp.add_text(
            line,
            dxfattribs={
                "layer": "GENERATED_TEXT",
                "height": 0.25,
            }
        ).set_placement((x0, text_y))
        text_y -= 0.35


def generate_dxf(data):
    if ezdxf is None:
        raise RuntimeError(
            "ezdxf is not installed. Install it using: pip install ezdxf"
        )

    if not MASTER_DXF.exists():
        raise RuntimeError(
            "No master.dxf found. Upload your master DXF first."
        )

    doc = ezdxf.readfile(str(MASTER_DXF))
    calc = calculate_values(data)

    add_generated_geometry(doc, data, calc)

    output_name = f"generated_{uuid.uuid4().hex[:10]}.dxf"
    output_path = OUTPUT_DIR / output_name
    doc.saveas(str(output_path))

    return output_path, calc


@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        HTML,
        master_exists=MASTER_DXF.exists(),
        dxf_available=ezdxf is not None,
    )


@app.route("/upload-master", methods=["POST"])
def upload_master():
    if "master_file" not in request.files:
        return "No master file uploaded.", 400

    file = request.files["master_file"]

    if not file.filename:
        return "No master file selected.", 400

    extension = Path(file.filename).suffix.lower()

    if extension == ".dwg":
        return (
            "DWG upload is not directly supported by ezdxf. "
            "Please save/export the master drawing as DXF and upload the DXF."
        ), 400

    if extension != ".dxf":
        return "Please upload a DXF file.", 400

    file.save(str(MASTER_DXF))

    return (
        '<p>Master DXF uploaded successfully.</p>'
        '<p><a href="/">Return to generator</a></p>'
    )


@app.route("/generate", methods=["POST"])
def generate():
    data = {
        "drawing_no": request.form.get("drawing_no", ""),
        "chainage": request.form.get("chainage", ""),
        "span_length": request.form.get("span_length", ""),
        "bridge_width": request.form.get("bridge_width", ""),
        "pipe_od": request.form.get("pipe_od", ""),
        "pipe_id": request.form.get("pipe_id", ""),
        "number_of_pipes": request.form.get("number_of_pipes", ""),
        "pipe_length": request.form.get("pipe_length", ""),
        "pipe_slope": request.form.get("pipe_slope", ""),
        "pipe_spacing": request.form.get("pipe_spacing", ""),
        "crossing_angle": request.form.get("crossing_angle", ""),
        "bed_rl": request.form.get("bed_rl", ""),
        "bridge_underside_rl": request.form.get("bridge_underside_rl", ""),
        "pipe_invert_rl": request.form.get("pipe_invert_rl", ""),
        "required_cover": request.form.get("required_cover", ""),
        "required_clearance": request.form.get("required_clearance", ""),
    }

    try:
        output_path, calc = generate_dxf(data)

        return render_template_string(
            """
            <!doctype html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Drawing Generated</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        max-width: 800px;
                        margin: 50px auto;
                        padding: 20px;
                    }
                    .box {
                        background: #f4f7fa;
                        padding: 20px;
                        border-radius: 10px;
                        margin: 20px 0;
                    }
                    a, button {
                        display: inline-block;
                        padding: 12px 18px;
                        background: #1264d6;
                        color: white;
                        text-decoration: none;
                        border-radius: 8px;
                        border: 0;
                        cursor: pointer;
                    }
                </style>
            </head>
            <body>
                <h1>Drawing Generated Successfully</h1>

                <div class="box">
                    <p><b>Pipe Centre RL:</b> {{ "%.3f"|format(calc.pipe_center_rl) }}</p>
                    <p><b>Pipe Top RL:</b> {{ "%.3f"|format(calc.pipe_top_rl) }}</p>
                    <p><b>Pipe End Invert RL:</b> {{ "%.3f"|format(calc.pipe_end_invert_rl) }}</p>
                    <p><b>Available Clearance:</b> {{ "%.3f"|format(calc.available_clearance) }} m</p>
                </div>

                <p>
                    <a href="/download/{{ filename }}">Download DXF</a>
                </p>

                <p>
                    <a href="/">Generate Another Drawing</a>
                </p>
            </body>
            </html>
            """,
            calc=type("Calc", (), calc),
            filename=output_path.name,
        )

    except Exception as exc:
        return render_template_string(
            """
            <!doctype html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Generation Error</title>
            </head>
            <body style="font-family:Arial;max-width:800px;margin:50px auto;padding:20px;">
                <h1>Drawing Generation Error</h1>
                <div style="background:#fdeaea;padding:20px;border-radius:10px;">
                    {{ error }}
                </div>
                <p><a href="/">Return to generator</a></p>
            </body>
            </html>
            """,
            error=str(exc),
        ), 500


@app.route("/download/<filename>", methods=["GET"])
def download(filename):
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name

    if not file_path.exists():
        return "File not found.", 404

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=safe_name,
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "ezdxf_installed": ezdxf is not None,
        "master_dxf_exists": MASTER_DXF.exists(),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

