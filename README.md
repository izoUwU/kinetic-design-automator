# Kinetic Design Automator

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Framework: PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://pypi.org/project/PyQt6/)
[![CAD: KLayout & ezdxf](https://img.shields.io/badge/CAD-KLayout%20%7C%20ezdxf-orange.svg)](https://www.klayout.de/)
[![CV: OpenCV](https://img.shields.io/badge/Vision-OpenCV-red.svg)](https://opencv.org/)
[![Publication: Nanomaterials 2026](https://img.shields.io/badge/DOI-10.3390%2Fnano16090565-blue)](https://doi.org/10.3390/nano16090565)

**Kinetic Design Automator** is an automated CAD layout generator, asynchronous mask previewer, and optical micrograph analysis suite built specifically to design, synthesize, and verify the wafer-scale **suspended graphene variable capacitor** fabrication process published in *Nanomaterials* (2026).

It bridges physical microfabrication and semiconductor design automation: transforming over 100 process and geometry parameters into hierarchical GDS-II and DXF mask sets for maskless photolithography, verifying recipe parameters, and quantifying large-area 2D material transfer coverage across 64-trench arrays using computer vision.

---

## Scientific Background & Publication

This software was developed by **Tamzeed Bani Amin** in the **Thibado Research Group** at the **University of Arkansas** to automate the end-to-end design, mask fabrication, and inspection for:

> **Tamzeed B. Amin**, Md R. Kabir, Syed M. Rahman, Ashaduzzaman, James M. Mangum, and Paul M. Thibado  
> *"Arbitrarily Large Area Graphene Suspension with Ultralow Standoff for Varying Capacitance Applications,"*  
> **Nanomaterials** 2026, 16(9), 565.  
> DOI: [10.3390/nano16090565](https://doi.org/10.3390/nano16090565)

### Device Architecture Modeled
The application directly models and generates the full chip layout described in the paper:
- **Substrate**: 100 mm silicon wafers with a thick thermal silicon dioxide ($SiO_2$) layer (~1.5–3.0 $\mu$m).
- **Chip Architecture**: 4 identical or split devices in parallel per die (Quadrants A, B, C, D), each measuring approximately 8 mm &times; 8 mm.
- **Trench Array**: 64 parallel micro-trenches per device (nominally 6 $\mu$m wide, etched ~300 nm deep into the thermal oxide using 50:1 BOE).
- **Electrodes & Ultralow Standoff**: Gold electrode traces (~100 nm thick) deposited along the trench floors, achieving an ultralow mechanical standoff of ~200 nm between the trench floor and the suspended graphene membrane.
- **Membrane & Contact Geometry**: A 3 mm &times; 5 mm multilayer graphene sheet suspended simultaneously over all 64 trenches, resting on dual central contact traces and wired to 4 corner bonding pads (200 $\mu$m &times; 200 $\mu$m) for redundancy.
- **Fluid Release Etch Pattern**: Oxygen plasma etch mask that patterns alternating suspended graphene ribbons and fluid release holes (10 $\mu$m wide &times; 100 $\mu$m long, repeated every 20 $\mu$m) directly above the trenches to enable stiction-free Critical Point Drying (CPD).
- **Packaging**: Dicing lanes and 200 $\mu$m bonding pads tailored for West Bond 7KF wire bonding to 28-pin ceramic DIP packages.

---

## Core Capabilities & Toolchain

### 1. Parameterized Wafer Mask Generation
Translates over 100 user parameters into synchronized, multi-layer CAD outputs ready for Heidelberg / MLA maskless lithography systems:
- **`_FULL.gds`**: Hierarchical GDS-II stream file containing all structural, metallization, and etch layers.
- **`_ETCH.dxf`**: Wet etch mask layer defining the 64 oxide trenches (50:1 BOE etch).
- **`_GOLD.dxf`**: Metallization mask for trench bottom electrodes, dual graphene contact traces, buslines, and 200 $\mu$m wire-bonding pads.
- **`_PLASMA.dxf` / Graphene Release**: Oxygen plasma etch geometry defining fluid-escape release holes for critical point drying.
- **`_SINGLE_3D.dxf`**: 3D extruded solid geometry exported to AutoCAD to verify mechanical clearances and wire bond loop heights in 28-pin packages.
- **Vernier Alignment Keys**: 400 $\mu$m &times; 10 $\mu$m crosshairs ensuring sub-micron layer-to-layer overlay accuracy across the 100 mm wafer.

### 2. Multi-Threaded CAD Preview Engine
- **Non-Blocking Architecture**: Layout geometry calculations and polygon clipping run on background worker threads, preventing GUI freezing during heavy layout updates.
- **Interactive PyQt6 Canvas**: Real-time zoom, pan, and layer toggle allowing instant verification of trench pitches, pad offsets, and alignment mark placements.

### 3. Fabrication Safety Interlocks (Recipe Guardrails)
- **Stale Recipe Check (`dhon_gui_state.json`)**: Tracks generation timestamps alongside the target etch depth. If the system detects a date change without a corresponding change in the etch depth parameter, it prompts the operator to confirm whether the oxide etch rate has been recalibrated, preventing wasted wafer batches.

### 4. Optical Micrograph Analyzer (`analyzer.py`)
- **Automated Flake Coverage Measurement**: Analyzes optical microscope photographs of transferred graphene sheets over the 64-trench arrays.
- **Computer Vision Pipeline**: Powered by OpenCV and NumPy, featuring adaptive multi-thresholding, trench line registration, and contrast auto-tuning (`calibration_params.json`).
- **Yield Verification**: Automatically measures percentage coverage and membrane suspension integrity per trench, exporting CSV reports that correlate directly with downstream C-V (&plusmn;9 V, 100 kHz, ~5 pF per trench) and I-V electrical characterization.

---

## Repository Structure

```
kinetic-design-automator/
├── main.py                     # Entry point launcher
├── kinetic_design_automator.py # Core GUI & mask layout synthesis engine (~5,200 LOC)
├── analyzer.py                 # OpenCV optical micrograph analysis module
├── calibration_params.json     # Calibrated parameters for optical feature detection
├── requirements.txt            # Python package dependencies
├── .gitignore                  # Git ignore rules
├── LICENSE                     # MIT License
└── README.md                   # Full documentation and scientific context
```

---

## Installation & Setup

### Prerequisites
- **Python 3.10+** (64-bit)
- **Git**
- *(Optional)* [KLayout](https://www.klayout.de/) to view and verify raw GDS-II hierarchies.

### Quick Start
```bash
# 1. Clone the repository
git clone https://github.com/izoUwU/kinetic-design-automator.git
cd kinetic-design-automator

# 2. Set up virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

# 3. Install required libraries
pip install -r requirements.txt

# 4. Launch the application
python main.py
```

---

## Software Operation

### 1. Generating Chip Masks
1. **Global Parameters**: Set database resolution (`dbu_um = 0.001`), wafer dimensions, dicing street margins, and layer mappings.
2. **Quadrant Parameters (A–D)**: Tune trench counts (default 64), trench width (default 6 $\mu$m), pad size (200 $\mu$m), and standoff depth.
3. **Alignment**: Configure 400 $\mu$m &times; 10 $\mu$m crosshairs for maskless lithography alignment.
4. **Export**: Click **Generate Full Chip** to synthesize `.gds`, `.dxf`, and 3D CAD files.

### 2. Inspecting Micrographs with the Image Analyzer
1. Open the **Image Analyzer** tab.
2. Load an optical microscope image (`.jpg`, `.png`, `.tif`) taken after graphene transfer.
3. Click **Auto Tune Parameters** to automatically detect trench edges and evaluate pixel intensity profiles.
4. The tool overlays detected trench boundaries and highlights suspended membrane sections.
5. Click **Export CSV** to save trench-by-trench coverage percentages.

---

## Technical Stack

- **Language**: Python 3
- **CAD & Geometry**: KLayout Python API (`klayout.db`), `ezdxf`
- **GUI Framework**: PyQt6 (with multi-threaded QThread / QPainter rendering)
- **Computer Vision**: OpenCV (`cv2`), NumPy, Pillow (`PIL`)

---

## License

This software is released under the [MIT License](LICENSE).

---

## Author & Contact

**Tamzeed Bani Amin**  
Department of Physics, University of Arkansas, Fayetteville, AR  
Email: [tbamin@uark.edu](mailto:tbamin@uark.edu)  
LinkedIn: [linkedin.com/in/tamzeed-bani-amin](https://linkedin.com/in/tamzeed-bani-amin)
