```python
# ============================================================
# BRIDGE / PIPE UNDER BRIDGE DRAWING GENERATOR
# Single Python File
# ============================================================
#
# INSTALL:
#
# pip install flask ezdxf werkzeug
#
# RUN:
#
# python app.py
#
# OPEN:
#
# http://127.0.0.1:5000
#
# ============================================================

from flask import (
    Flask,
    request,
    render_template_string,
    send_file,
    jsonify
)

from werkzeug.utils import secure_filename

from pathlib import Path

import ezdxf

import os
import uuid
import math
import json


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "output"
TEMPLATE_FOLDER = BASE_DIR / "templates"

UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)
TEMPLATE_FOLDER.mkdir(exist_ok=True)


# ============================================================
# MASTER DRAWING
# ============================================================
#
# Put your fixed master drawing here:
#
# templates/master.dxf
#
# Your 462 DWG should eventually be converted to DXF and
# placed here.
#
# Everything in the master drawing remains CONSTANT.
#
# Only:
#
#       BRIDGE
#       PIPE
#       LEVEL
#
# parameters are changed.
#
# ============================================================

MASTER_TEMPLATE = TEMPLATE_FOLDER / "master.dxf"


# ============================================================
# HTML
# ============================================================

HTML = r"""
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>
Bridge Pipe Drawing Generator
</title>


<style>

* {
    box-sizing: border-box;
}


body {

    margin: 0;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    background: #f2f4f7;

    color: #1f2937;

}


.header {

    background: #17202a;

    color: white;

    padding: 25px;

}


.header h1 {

    margin: 0;

    font-size: 28px;

}


.header p {

    margin-top: 8px;

    opacity: .8;

}


.container {

    width: 95%;

    max-width: 1200px;

    margin: 25px auto 60px;

}


.card {

    background: white;

    padding: 25px;

    margin-bottom: 20px;

    border-radius: 10px;

    box-shadow:
        0 2px 10px
        rgba(0,0,0,.08);

}


.card h2 {

    margin-top: 0;

    border-bottom:
        1px solid #e5e7eb;

    padding-bottom: 12px;

}


.grid {

    display: grid;

    grid-template-columns:
        repeat(3, 1fr);

    gap: 18px;

}


.field {

    display: flex;

    flex-direction: column;

}


.field label {

    font-weight: bold;

    font-size: 14px;

    margin-bottom: 7px;

}


.field input {

    padding: 11px;

    border:
        1px solid #cbd5e1;

    border-radius: 6px;

    font-size: 15px;

}


input:focus {

    outline: none;

    border-color: #2563eb;

}


button {

    border: none;

    padding:
        12px 22px;

    border-radius: 6px;

    cursor: pointer;

    background: #2563eb;

    color: white;

    font-weight: bold;

    font-size: 15px;

}


button:hover {

    background: #1d4ed8;

}


button.secondary {

    background: #475569;

}


button.success {

    background: #15803d;

}


.upload-box {

    border:
        2px dashed #94a3b8;

    border-radius: 8px;

    padding: 25px;

    text-align: center;

}


#analysis {

    margin-top: 20px;

    background: #111827;

    color: #e5e7eb;

    padding: 18px;

    border-radius: 6px;

    max-height: 400px;

    overflow: auto;

    white-space: pre-wrap;

    font-family: monospace;

}


.results {

    background: #f8fafc;

    padding: 20px;

    border-radius: 8px;

}


.result-row {

    display: flex;

    justify-content: space-between;

    padding: 8px 0;

    border-bottom:
        1px solid #e5e7eb;

}


.download {

    display: inline-block;

    margin-top: 20px;

    padding:
        12px 20px;

    background: #15803d;

    color: white;

    text-decoration: none;

    border-radius: 6px;

    font-weight: bold;

}


.status {

    margin-top: 15px;

    font-weight: bold;

}


.warning {

    background: #fff7ed;

    border-left:
        4px solid #f97316;

    padding: 15px;

    margin-top: 15px;

}


@media(max-width:850px) {

    .grid {

        grid-template-columns: 1fr;

    }

}


</style>

</head>


<body>


<div class="header">

    <h1>
        Bridge Pipe Drawing Generator
    </h1>

    <p>
        Fixed Master Drawing +
        Variable Bridge / Pipe / Level Data
    </p>

</div>


<div class="container">


<!-- ===================================================== -->
<!-- UPLOAD -->
<!-- ===================================================== -->

<div class="card">

<h2>
1. Upload Drawing
</h2>


<div class="upload-box">

<input
    type="file"
    id="cadFile"
    accept=".dwg,.dxf"
>


<br><br>


<button
    onclick="analyzeDrawing()"
>

Analyze Drawing

</button>


<div
    id="uploadStatus"
    class="status"
>
</div>

</div>


<pre id="analysis">
No drawing analyzed yet.
</pre>


</div>



<!-- ===================================================== -->
<!-- BRIDGE -->
<!-- ===================================================== -->

<div class="card">

<h2>
2. Bridge Data
</h2>


<div class="grid">


<div class="field">

<label>
Bridge / Drawing No.
</label>

<input
    id="bridge_no"
    value="462"
>

</div>


<div class="field">

<label>
Chainage
</label>

<input
    id="chainage"
    placeholder="273.640"
>

</div>


<div class="field">

<label>
Span Length (m)
</label>

<input
    id="span_length"
    type="number"
    step="0.001"
>

</div>


<div class="field">

<label>
Bridge Width (m)
</label>

<input
    id="bridge_width"
    type="number"
    step="0.001"
>

</div>


</div>

</div>



<!-- ===================================================== -->
<!-- PIPE -->
<!-- ===================================================== -->

<div class="card">

<h2>
3. Pipe Data
</h2>


<div class="grid">


<div class="field">

<label>
Pipe Outside Diameter (mm)
</label>

<input
    id="pipe_od"
    type="number"
    value="1200"
    step="1"
>

</div>


<div class="field">

<label>
Pipe Inside Diameter (mm)
</label>

<input
    id="pipe_id"
    type="number"
    step="1"
>

</div>


<div class="field">

<label>
Pipe Wall Thickness (mm)
</label>

<input
    id="pipe_wall"
    type="number"
    step="1"
>

</div>


<div class="field">

<label>
Number of Pipes
</label>

<input
    id="pipe_count"
    type="number"
    value="1"
    min="1"
>

</div>


<div class="field">

<label>
Pipe Length (m)
</label>

<input
    id="pipe_length"
    type="number"
    value="20"
    step="0.001"
>

</div>


<div class="field">

<label>
Pipe Slope (%)
</label>

<input
    id="pipe_slope"
    type="number"
    value="0"
    step="0.001"
>

</div>


<div class="field">

<label>
Pipe Spacing (mm)
</label>

<input
    id="pipe_spacing"
    type="number"
    value="0"
    step="1"
>

</div>


<div class="field">

<label>
Crossing Angle (°)
</label>

<input
    id="crossing_angle"
    type="number"
    value="90"
    step="0.1"
>

</div>


</div>

</div>



<!-- ===================================================== -->
<!-- LEVELS -->
<!-- ===================================================== -->

<div class="card">

<h2>
4. Level Data
</h2>


<div class="grid">


<div class="field">

<label>
Existing / Bed RL
</label>

<input
    id="existing_rl"
    type="number"
    step="0.001"
>

</div>


<div class="field">

<label>
Bridge Underside RL
</label>

<input
    id="bridge_rl"
    type="number"
    step="0.001"
>

</div>


<div class="field">

<label>
Pipe Invert RL
</label>

<input
    id="invert_rl"
    type="number"
    step="0.001"
>

</div>


<div class="field">

<label>
Required Cover (m)
</label>

<input
    id="cover"
    type="number"
    value="0"
    step="0.001"
>

</div>


<div class="field">

<label>
Required Clearance (m)
</label>

<input
    id="clearance"
    type="number"
    value="0"
    step="0.001"
>

</div>


</div>

</div>



<!-- ===================================================== -->
<!-- GENERATE -->
<!-- ===================================================== -->

<div class="card">

<h2>
5. Generate Drawing
</h2>


<button
    class="success"
    onclick="generateDrawing()"
>

Generate Drawing

</button>


<div
    id="generateStatus"
    class="status"
>
</div>

</div>



<!-- ===================================================== -->
<!-- RESULTS -->
<!-- ===================================================== -->

<div class="card">

<h2>
6. Calculated Drawing Data
</h2>


<div
    id="results"
    class="results"
>

No drawing generated.

</div>


<a
    id="download"
    class="download"
    style="display:none"
>

Download DXF

</a>


</div>


</div>


<script>


// ========================================================
// ANALYZE
// ========================================================


async function analyzeDrawing() {


    const file =
        document
        .getElementById("cadFile")
        .files[0];


    if (!file) {

        alert(
            "Please select a DWG or DXF file."
        );

        return;

    }


    const form =
        new FormData();


    form.append(
        "file",
        file
    );


    document
        .getElementById("uploadStatus")
        .innerText =
            "Analyzing drawing...";


    try {


        const response =
            await fetch(
                "/analyze",
                {

                    method: "POST",

                    body: form

                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.error ||
                "Analysis failed."
            );

        }


        document
            .getElementById("analysis")
            .textContent =
                JSON.stringify(
                    data,
                    null,
                    2
                );


        document
            .getElementById("uploadStatus")
            .innerText =
                "Drawing analyzed successfully.";


    }

    catch(error) {


        document
            .getElementById("uploadStatus")
            .innerText =
                "ERROR: " +
                error.message;


    }

}



// ========================================================
// GENERATE
// ========================================================


async function generateDrawing() {


    const data = {


        bridge: {


            bridge_no:
                document
                .getElementById(
                    "bridge_no"
                ).value,


            chainage:
                document
                .getElementById(
                    "chainage"
                ).value,


            span_length:
                Number(
                    document
                    .getElementById(
                        "span_length"
                    ).value
                ),


            bridge_width:
                Number(
                    document
                    .getElementById(
                        "bridge_width"
                    ).value
                )


        },


        pipe: {


            od:
                Number(
                    document
                    .getElementById(
                        "pipe_od"
                    ).value
                ),


            id:
                Number(
                    document
                    .getElementById(
                        "pipe_id"
                    ).value
                ),


            wall:
                Number(
                    document
                    .getElementById(
                        "pipe_wall"
                    ).value
                ),


            count:
                Number(
                    document
                    .getElementById(
                        "pipe_count"
                    ).value
                ),


            length:
                Number(
                    document
                    .getElementById(
                        "pipe_length"
                    ).value
                ),


            slope:
                Number(
                    document
                    .getElementById(
                        "pipe_slope"
                    ).value
                ),


            spacing:
                Number(
                    document
                    .getElementById(
                        "pipe_spacing"
                    ).value
                ),


            angle:
                Number(
                    document
                    .getElementById(
                        "crossing_angle"
                    ).value
                )


        },


        levels: {


            existing:
                Number(
                    document
                    .getElementById(
                        "existing_rl"
                    ).value
                ),


            bridge:
                Number(
                    document
                    .getElementById(
                        "bridge_rl"
                    ).value
                ),


            invert:
                Number(
                    document
                    .getElementById(
                        "invert_rl"
                    ).value
                ),


            cover:
                Number(
                    document
                    .getElementById(
                        "cover"
                    ).value
                ),


            clearance:
                Number(
                    document
                    .getElementById(
                        "clearance"
                    ).value
                )


        }


    };


    document
        .getElementById(
            "generateStatus"
        )
        .innerText =
            "Generating drawing...";


    try {


        const response =
            await fetch(
                "/generate",
                {

                    method: "POST",

                    headers: {

                        "Content-Type":
                            "application/json"

                    },

                    body:
                        JSON.stringify(
                            data
                        )

                }
            );


        const result =
            await response.json();


        if (!response.ok) {

            throw new Error(
                result.error ||
                "Generation failed."
            );

        }


        showResults(
            result
        );


        document
            .getElementById(
                "generateStatus"
            )
            .innerText =
                "Drawing generated successfully.";


    }

    catch(error) {


        document
            .getElementById(
                "generateStatus"
            )
            .innerText =
                "ERROR: " +
                error.message;


    }

}



// ========================================================
// RESULTS
// ========================================================


function showResults(data) {


    const c =
        data.calculations;


    document
        .getElementById(
            "results"
        )
        .innerHTML = `


        <div class="result-row">

            <span>
                Pipe Centre RL
            </span>

            <strong>
                ${c.pipe_center_rl.toFixed(3)}
            </strong>

        </div>


        <div class="result-row">

            <span>
                Pipe Top RL
            </span>

            <strong>
                ${c.pipe_top_rl.toFixed(3)}
            </strong>

        </div>


        <div class="result-row">

            <span>
                Pipe Bottom / Invert RL
            </span>

            <strong>
                ${c.pipe_invert_rl.toFixed(3)}
            </strong>

        </div>


        <div class="result-row">

            <span>
                Pipe End Invert RL
            </span>

            <strong>
                ${c.pipe_end_invert_rl.toFixed(3)}
            </strong>

        </div>


        <div class="result-row">

            <span>
                Bridge Clearance
            </span>

            <strong>
                ${c.bridge_clearance.toFixed(3)}
                m
            </strong>

        </div>


        `;


    const link =
        document
        .getElementById(
            "download"
        );


    link.href =
        data.download_url;


    link.style.display =
        "inline-block";


}



// ========================================================

</script>


</body>

</html>
"""


# ============================================================
# CAD ANALYSIS
# ============================================================


def analyze_dxf_file(filename):

    doc = ezdxf.readfile(filename)

    msp = doc.modelspace()


    entity_count = {}

    layers = {}

    text_objects = []

    dimensions = []


    for entity in msp:


        entity_type =
            entity.dxftype()


        entity_count[
            entity_type
        ] = (
            entity_count.get(
                entity_type,
                0
            ) + 1
        )


        layer =
            getattr(
                entity.dxf,
                "layer",
                "0"
            )


        layers[layer] =
            layers.get(
                layer,
                0
            ) + 1


        # ----------------------------------------------
        # TEXT
        # ----------------------------------------------


        if entity_type == "TEXT":


            text_objects.append({

                "text":
                    entity.dxf.text,

                "layer":
                    layer,

                "x":
                    round(
                        entity.dxf.insert.x,
                        3
                    ),

                "y":
                    round(
                        entity.dxf.insert.y,
                        3
                    )

            })


        # ----------------------------------------------
        # MTEXT
        # ----------------------------------------------


        elif entity_type == "MTEXT":


            text_objects.append({

                "text":
                    entity.text,

                "layer":
                    layer,

                "x":
                    round(
                        entity.dxf.insert.x,
                        3
                    ),

                "y":
                    round(
                        entity.dxf.insert.y,
                        3
                    )

            })


        # ----------------------------------------------
        # DIMENSIONS
        # ----------------------------------------------


        elif entity_type == "DIMENSION":


            dimensions.append({

                "layer":
                    layer,

                "type":
                    int(
                        entity.dxf.dimtype
                    ),

                "text":
                    getattr(
                        entity.dxf,
                        "text",
                        ""
                    )

            })


    return {


        "units":
            doc.header.get(
                "$INSUNITS",
                0
            ),


        "entity_count":
            entity_count,


        "layers":
            layers,


        "text_count":
            len(
                text_objects
            ),


        "texts":
            text_objects[:500],


        "dimension_count":
            len(
                dimensions
            ),


        "dimensions":
            dimensions[:500],


        "variable_parameters": [

            "BRIDGE DATA",

            "PIPE DATA",

            "LEVEL DATA"

        ],


        "constant_parameters": [

            "Jacking Pit",

            "Receiving Pit",

            "PCC",

            "DLC",

            "Curtain Wall",

            "Revetment",

            "Filter",

            "Wing Return",

            "Protection Works",

            "Standard Notes",

            "Symbols",

            "Title Block"

        ]

    }



# ============================================================
# DRAWING GENERATOR
# ============================================================


def generate_drawing(
    bridge,
    pipe,
    levels
):


    # --------------------------------------------------------
    # Check master drawing
    # --------------------------------------------------------


    if not MASTER_TEMPLATE.exists():


        raise Exception(

            "Master drawing not found.\n\n"

            "Convert your 462 DWG to DXF and save it as:\n\n"

            "templates/master.dxf"

        )


    # --------------------------------------------------------
    # Load master
    # --------------------------------------------------------


    doc =
        ezdxf.readfile(
            MASTER_TEMPLATE
        )


    msp =
        doc.modelspace()


    # --------------------------------------------------------
    # Create generated layer
    # --------------------------------------------------------


    GENERATED_LAYER =
        "GENERATED_PIPE"


    if (
        GENERATED_LAYER
        not in doc.layers
    ):


        doc.layers.new(
            GENERATED_LAYER
        )


    # --------------------------------------------------------
    # Pipe dimensions
    # --------------------------------------------------------


    pipe_od_m =
        pipe["od"] / 1000.0


    pipe_radius =
        pipe_od_m / 2.0


    # --------------------------------------------------------
    # Pipe centre RL
    # --------------------------------------------------------


    pipe_center_rl = (

        levels["invert"]

        +

        pipe_radius

    )


    # --------------------------------------------------------
    # Pipe top RL
    # --------------------------------------------------------


    pipe_top_rl = (

        levels["invert"]

        +

        pipe_od_m

    )


    # --------------------------------------------------------
    # Slope
    # --------------------------------------------------------


    slope =
        pipe["slope"] / 100.0


    pipe_end_invert_rl = (

        levels["invert"]

        +

        (
            pipe["length"]
            * slope
        )

    )


    # --------------------------------------------------------
    # Clearance
    # --------------------------------------------------------


    bridge_clearance = (

        levels["bridge"]

        -

        pipe_top_rl

    )


    # --------------------------------------------------------
    # DRAWING COORDINATES
    # --------------------------------------------------------
    #
    # IMPORTANT:
    #
    # These coordinates are placeholders until we map the
    # actual 462 DWG entities.
    #
    # Once the actual DWG is analyzed, these values should
    # reference the actual pipe alignment in your drawing.
    #
    # --------------------------------------------------------


    start_x = 0

    start_y = 0


    angle =
        math.radians(
            pipe["angle"]
        )


    end_x = (

        start_x

        +

        pipe["length"]
        *
        math.cos(angle)

    )


    end_y = (

        start_y

        +

        pipe["length"]
        *
        math.sin(angle)

    )


    # --------------------------------------------------------
    # DRAW PIPE CENTRE LINE
    # --------------------------------------------------------


    msp.add_line(

        (
            start_x,
            start_y,
            pipe_center_rl
        ),

        (
            end_x,
            end_y,
            pipe_center_rl
            +
            (
                pipe_end_invert_rl
                -
                levels["invert"]
            )
        ),

        dxfattribs={

            "layer":
                GENERATED_LAYER

        }

    )


    # --------------------------------------------------------
    # DRAW PIPE CROSS SECTIONS
    # --------------------------------------------------------


    msp.add_circle(

        (
            start_x,
            start_y,
            pipe_center_rl
        ),

        pipe_radius,

        dxfattribs={

            "layer":
                GENERATED_LAYER

        }

    )


    msp.add_circle(

        (
            end_x,
            end_y,
            pipe_center_rl
            +
            (
                pipe_end_invert_rl
                -
                levels["invert"]
            )
        ),

        pipe_radius,

        dxfattribs={

            "layer":
                GENERATED_LAYER

        }

    )


    # --------------------------------------------------------
    # ADD PIPE TEXT
    # --------------------------------------------------------


    text_height =
        max(
            0.15,
            pipe_radius * 0.5
        )


    msp.add_text(

        (
            f"PIPE OD: "
            f"{pipe['od']:.0f} mm"
        ),

        height=text_height,

        dxfattribs={

            "layer":
                GENERATED_LAYER

        }

    ).set_placement(

        (
            start_x,
            start_y + 1,
            pipe_center_rl
        )

    )


    msp.add_text(

        (
            f"PIPE INVERT RL: "
            f"{levels['invert']:.3f}"
        ),

        height=text_height,

        dxfattribs={

            "layer":
                GENERATED_LAYER

        }

    ).set_placement(

        (
            start_x,
            start_y + 1.5,
            levels["invert"]
        )

    )


    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------


    filename = (

        "bridge_pipe_"

        +

        uuid.uuid4().hex

        +

        ".dxf"

    )


    output_file =
        OUTPUT_FOLDER / filename


    doc.saveas(
        output_file
    )


    # --------------------------------------------------------
    # RETURN RESULTS
    # --------------------------------------------------------


    return (

        output_file,

        {

            "pipe_center_rl":
                pipe_center_rl,

            "pipe_top_rl":
                pipe_top_rl,

            "pipe_invert_rl":
                levels["invert"],

            "pipe_end_invert_rl":
                pipe_end_invert_rl,

            "bridge_clearance":
                bridge_clearance

        }

    )



# ============================================================
# HOME PAGE
# ============================================================


@app.route(
    "/",
    methods=["GET"]
)


def home():


    return render_template_string(
        HTML
    )



# ============================================================
# ANALYZE ROUTE
# ============================================================


@app.route(
    "/analyze",
    methods=["POST"]
)


def analyze():


    if "file" not in request.files:


        return jsonify({

            "error":
                "No CAD file uploaded."

        }), 400


    file =
        request.files["file"]


    if not file.filename:


        return jsonify({

            "error":
                "No file selected."

        }), 400


    extension =
        Path(
            file.filename
        ).suffix.lower()


    if extension not in [
        ".dxf",
        ".dwg"
    ]:


        return jsonify({

            "error":
                "Only DWG or DXF files are supported."

        }), 400


    # --------------------------------------------------------
    # IMPORTANT:
    #
    # ezdxf cannot directly read DWG.
    #
    # For now, DXF analysis is supported.
    #
    # --------------------------------------------------------


    if extension == ".dwg":


        return jsonify({

            "error":
                "DWG requires conversion to DXF first. "
                "Please export the drawing as DXF for this version."

        }), 400


    filename = (

        str(
            UPLOAD_FOLDER
            /

            (
                uuid.uuid4().hex
                +
                ".dxf"
            )
        )

    )


    file.save(
        filename
    )


    try:


        result =
            analyze_dxf_file(
                filename
            )


        return jsonify(
            result
        )


    except Exception as e:


        return jsonify({

            "error":
                str(e)

        }), 500



# ============================================================
# GENERATE ROUTE
# ============================================================


@app.route(
    "/generate",
    methods=["POST"]
)


def generate():


    try:


        data =
            request.get_json()


        bridge =
            data["bridge"]


        pipe =
            data["pipe"]


        levels =
            data["levels"]


        output_file, calculations = (

            generate_drawing(

                bridge,

                pipe,

                levels

            )

        )


        return jsonify({

            "success":
                True,


            "calculations":
                calculations,


            "download_url":
                "/download/"
                +
                output_file.name

        })


    except Exception as e:


        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500



# ============================================================
# DOWNLOAD
# ============================================================


@app.route(
    "/download/<filename>"
)


def download(filename):


    file =
        OUTPUT_FOLDER
        /
        secure_filename(
            filename
        )


    if not file.exists():


        return (
            "File not found",
            404
        )


    return send_file(

        file,

        as_attachment=True,

        download_name=
            file.name

    )



# ============================================================
# START SERVER
# ============================================================


if __name__ == "__main__":


    print()
    print(
        "=============================================="
    )

    print(
        " BRIDGE PIPE DRAWING GENERATOR"
    )

    print(
        "=============================================="
    )

    print()

    print(
        "Open:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print()

    print(
        "Master drawing:"
    )

    print(
        MASTER_TEMPLATE
    )

    print()


    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True

    )
```

