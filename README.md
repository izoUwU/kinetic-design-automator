# Kinetic Design Automator

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Framework: PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://pypi.org/project/PyQt6/)
[![CAD: KLayout & ezdxf](https://img.shields.io/badge/CAD-KLayout%20%7C%20ezdxf-orange.svg)](https://www.klayout.de/)
[![CV: OpenCV](https://img.shields.io/badge/Vision-OpenCV-red.svg)](https://opencv.org/)

**Kinetic Design Automator** is an automated CAD layout generator, asynchronous mask previewer, and optical micrograph analysis suite designed for cleanroom fabrication of micro- and nano-scale devices (specifically 2D material membranes such as suspended graphene on silicon).

It integrates parameterized GDS-II and DXF layout synthesis, a responsive GUI with non-blocking threaded preview rendering, lithography recipe guardrails, and computer-vision-based flake coverage analysis into a unified workflow.

---

## Scientific Context & Citation

This software was developed in the **Thibado Research Group** at the **University of Arkansas** to automate the design, mask generation, and verification of suspended graphene capacitors across 100 mm silicon wafers.

If you use this software in academic or industrial work, please cite the corresponding wafer-scale fabrication process:

> **T. B. Amin**, M. R. Kabir, S. M. Rahman, Ashaduzzaman, J. M. Mangum, and P. M. Thibado,  
> *"Arbitrarily Large Area Graphene Suspension with Ultralow Standoff for Varying Capacitance Applications,"*  
> **Nanomaterials** 16(9), 565, 2026.  
> DOI: [10.3390/nano16090565](https://doi.org/10.3390/nano16090565)

---

## Key Features

### 1. Parameterized Wafer Mask Generation
- **100+ Design Parameters**: Configure global wafer properties, trench geometry, pad dimensions, buslines, isolation moats, dicing lanes, and alignment crosshairs.
- **Multi-Layer Mask Output**:
  - `_FULL.gds`: Hierarchical multi-layer GDS-II chip database.
  - `_ETCH.dxf`: Wet chemical etching mask (e.g. 50:1 BOE for micro-trenches).
  - `_GOLD.dxf`: Cr/Au metallization and contact pad lithography mask.
  - `_SINGLE_3D.dxf`: Full 3D extruded solid geometry for AutoCAD / mechanical integration.
- **Maskless Lithography Ready**: Direct export formatted for Heidelberg and MLA maskless lithography systems.

### 2. Live Asynchronous Preview Engine
- **Non-Blocking Threaded Architecture**: Background worker threads handle geometry synthesis and polygon decimation, keeping the PyQt6 user interface completely responsive during heavy layout recalculations.
- **Multi-View Modes**: Switch between full chip overview, individual quadrants, alignment markers, and layer-specific isolation.

### 3. Process Guardrails & Recipe Integrity
- **Stale Recipe Interlock**: Tracks layout generation timestamps and etch depth settings (`dhon_gui_state.json`). If the run date changes without an intentional update to the etch depth, the application prompts the operator for confirmation, preventing accidental mask remakes with outdated calibration splits.

### 4. Automated Optical Micrograph Analyzer (`analyzer.py`)
- **Computer Vision Pipeline**: Built on OpenCV and NumPy to analyze optical microscope images of 2D material transfers over micro-trench arrays.
- **Automated Parameter Tuning**: Auto-tunes multi-stage intensity thresholds, trench contrast, and edge-drop metrics.
- **Quantitative Metrics & Export**: Calculates percentage coverage per trench and overall suspended yield, exporting structured CSV data for direct correlation with C-V and I-V electrical characterization.

---

## Repository Structure

```
kinetic-design-automator/
├── main.py                     # Application entry point
├── kinetic_design_automator.py # Core GUI and mask layout synthesis engine (~5,200 LOC)
├── analyzer.py                 # Computer vision optical image analyzer module
├── calibration_params.json     # Calibrated parameters for optical feature detection
├── requirements.txt            # Python dependencies
├── .gitignore                  # Git ignore rules
├── LICENSE                     # MIT License
└── README.md                   # Documentation and usage guide
```

---

## Installation & Setup

### Prerequisites
- **Python 3.10+** (64-bit recommended)
- **Git**
- *(Optional)* [KLayout](https://www.klayout.de/) if you want to inspect output GDS-II files in the standalone viewer.

### Step 1: Clone the Repository
```bash
git clone https://github.com/izoUwU/kinetic-design-automator.git
cd kinetic-design-automator
```

### Step 2: Create a Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

> **Note on KLayout**: The standalone Python module `klayout` is installed via PyPI. Kinetic Design Automator works seamlessly out-of-the-box in standalone Python, and can also be imported directly inside KLayout's integrated Macro Development environment.

---

## Usage Guide

### 1. Launching the Application
Run the main launcher:
```bash
python main.py
```
Or run the core module directly:
```bash
python kinetic_design_automator.py
```

### 2. Designing a Mask Set
1. **Global Parameters Tab**: Set database units (`dbu_um`), wafer diameter, plasma isolation layers, and batch production counts.
2. **Quadrant Tabs (A - D)**: Independently configure trench widths (e.g. 6 &mu;m), pad dimensions (e.g. 200 &mu;m), trench pitch, and lead offsets.
3. **Alignment & Crosshairs**: Customize multi-layer vernier alignment keys and 400 &mu;m &times; 10 &mu;m crosshairs for maskless alignment.
4. **Generate Full Chip**: Click **Generate Full Chip** to compute layout geometry, write GDS-II and DXF files, and launch the 2D CAD viewer.

### 3. Using the Image Analyzer
1. Switch to the **Image Analyzer** tab.
2. Click **Load Image** to select an optical micrograph (`.jpg`, `.png`, `.tif`) of transferred graphene/2D flakes over micro-trenches.
3. Click **Auto Tune Parameters** to run the multi-threshold optimization algorithm.
4. Review the traced trench lines and coverage boundaries on the interactive canvas.
5. Click **Export CSV** to save coverage percentages and trench-by-trench statistics.

---

## Technologies Used

- **Python 3**: Core language.
- **KLayout Python API (`klayout.db`)**: High-performance geometric hierarchy, cell instantiation, and GDS-II stream writer.
- **PyQt6**: Responsive desktop graphical user interface.
- **ezdxf**: 2D and 3D DXF file creation and polygon mesh extrusion.
- **OpenCV (`cv2`) & NumPy**: Image thresholding, contour extraction, and optical image feature measurement.
- **Pillow (`PIL`)**: High-fidelity image manipulation and format conversion.

---

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## Author & Contact

**Tamzeed Bani Amin**  
Department of Physics, University of Arkansas, Fayetteville, AR  
Email: [tbamin@uark.edu](mailto:tbamin@uark.edu)  
LinkedIn: [linkedin.com/in/tamzeed-bani-amin](https://linkedin.com/in/tamzeed-bani-amin)
