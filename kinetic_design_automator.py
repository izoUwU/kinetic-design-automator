import sys
import json
import os
try:
    import cv2
    import numpy as np
    from PIL import Image, ImageQt
    import csv
    from analyzer import Analyzer
    HAVE_CV2 = True
except ImportError as e:
    HAVE_CV2 = False
    CV2_IMPORT_ERROR = str(e)

try:
    import pya
    if hasattr(pya, 'Application'):
        IN_KLAYOUT = True
    else:
        raise ImportError("Not KLayout's integrated pya")
except ImportError:
    import klayout.db as pya
    IN_KLAYOUT = False
import copy # Needed to copy parameter dictionaries
import math # Needed for isnan, isinf
import re # For sanitizing filenames
import ast # Safe parsing of GDS layer list fields from the GUI
import threading # Background preview rebuilds (keeps the GUI responsive)

# ===================================================================
# Configuration Parameters (Global and Quadrant-Specific Defaults)
# ===================================================================

# Global Chip Parameters
GLOBAL_PARAMS = {
    'dbu_um': 0.001,
    'enable_3_plasma_layers': True,
    'enable_graphene': False,
    'batch_production_count': 1,
    'export_etch_mask': False,
    'export_gold_mask': False,
    'export_full_mask': False,
    'enable_kinetic_naming': True,
    'kinetic_depth': 190.0,
    'enable_gtt_label': True,
    'gtt_number': 1,
    'quadrant_gap_x': 2300.0,
    'quadrant_gap_y': 2000.0,
    'boundary_size_um': 16500.0,
    'boundary_width_um': 1.0,
    'enable_quadrant_sample_names': True,
    'sample_name_base': "",
    'single_quadrant_type': "TL",
    'sample_name_suffix_list': ["_A", "_B", "_C", "_D"],
    'sample_name_font_height_um': 500.0,
    'sample_name_font_width_um': 250.0,
    'sample_name_offset_x_um': 0.0,
    'sample_name_offset_y_um': 200.0,
    # Global Alignment Triangle
    'triangle_width_um': 1000.0,
    'triangle_height_um': 1000.0,
    'triangle_layer_gds': [1, 0],  # etch layer
    'triangle_offset_x_um': 0.0,
    'triangle_offset_y_um': 500.0,
}

# 3D Extrusion Parameters (used only for the single-quadrant 3D DXF export)
PARAMS_3D = {
    'enable_3d_dxf': True,
    'merge_layer5_into_layer2': False,
    'box_extrude_down_um': 30.0,
    'layer1_extrude_down_um': 3.0,
    'layer2_extrude_up_um': 1.5,
    'layer2_z_shift_um': -3.0,
    'layer5_extrude_up_um': 1.5,
    'graphene_extrude_up_um': 0.5,
}

# Default Quadrant Parameters
DEFAULT_QUADRANT_PARAMS = {
    'contact_width': 200.0, 'contact_height': 200.0, 'capacitor_width': 0.0, 'capacitor_height': 0.0,
    'wire_L1_width': 4, 'encap_offset': 1, 'wire_L1_length': 2400.0, 'wire_L1_grid_penetration_um': 1.0,
    'num_wires_per_contact': 1, 'wire_contact_inset_um': 60.0, 'wire_spacing_um': 0.0, 'wire_spacing_um': 0.0, 'wire_spacing_um': 0.0, 'capacitor_pair_spacing': 322.0,
    'vertical_pitch': 150.0, 'num_pairs': 32, 
    'stagger_offset': -500.0,
    'enable_stagger': True,
    'enable_capacitor_grid': True, 'capacitor_grid_line_width_um': 5.0, 'capacitor_grid_gap_um': 7.0,
    'enable_custom_cap_grid_reductions': False, 'capacitor_grid_l2_width_reduction_um': 1.0, 'capacitor_grid_l2_length_reduction_um': 1.0,
    'plasma_layer_count': 3,
    'plasma_l1_layer': 12, 'plasma_l1_width_um': 10.0, 'plasma_l1_gap_um': 10.0,
    'plasma_l2_layer': 13, 'plasma_l2_width_um': 10.0, 'plasma_l2_gap_um': 20.0,
    'plasma_l3_layer': 14, 'plasma_l3_width_um': 10.0, 'plasma_l3_gap_um': 50.0,
    'stem_marker_strip_length_um': 100.0,
    'stem_marker_array_coverage_left_um': 1400.0, 'stem_marker_array_coverage_right_um': 1400.0,
    'corner_box_size': 400.0, 'corner_box_height': 450.0, 'corner_wire_L2_width': 20.0, 'corner_wire_horizontal_length': 4600.0,
    'clearance': 400.0, 'central_vertical_wire_spacing': 100.0, 'paired_fiducial_spacing': 250.0,
    'text_height': 120.0, 'text_width': 30.0, 'g_text_height': 200.0, 'g_text_width': 50.0, 'g_label_position': 'sides', 'g1g2_label_offset_x': 50.0, 'g1g2_label_offset_y': 0.0,
    'g3g4_label_offset_x': 50.0, 'g3g4_label_offset_y': 0.0, 'contact_label_offset_x': 50.0, 'contact_label_offset_y': 0.0,
    'marker_box_size_um': 16.0, 'marker_box_series_count': 5, 'marker_box_series_spacing_um': 200.0,
    'marker_box_offset_x_um': -1000.0, 'marker_box_offset_y_um': 0.0,
    'marker_gold_pair_offset_y_um': -40.0,
    'gold_box_size_um': 16.0, 'gold_box_series_count': 5, 'gold_box_series_spacing_um': 200.0,
    'gold_box_vertical_separation_um': 80.0,
    'enable_quadrant_crosshairs': True, 'crosshair_gds_layers': [1, 2], 'quadrant_crosshair_length_um': 400.0, 'quadrant_crosshair_width_um': 10.0,
    'quadrant_crosshair_offset_x_um': 800.0, 'quadrant_crosshair_offset_y_um': 50.0,
    'enable_quadrant_triangle': True, 'quadrant_triangle_gds_layers': [1, 2], 'quadrant_triangle_width_um': 200.0, 'quadrant_triangle_height_um': 200.0,
    'quadrant_triangle_offset_y_um': -50.0,
    'sample_name_gds_layers': [1],
    'surface_metal_gds_layer': 5,
    'split_stem_markers': False,
    'stem_marker_wire_clearance_um': 0.5,
}

# Keys whose QLineEdit holds a list of integer GDS layer numbers (safe literal_eval).
_GDS_LAYER_LIST_KEYS = frozenset({
    'crosshair_gds_layers', 'quadrant_triangle_gds_layers', 'sample_name_gds_layers',
    'triangle_layer_gds',
})

# ===================================================================
# Per-parameter help / tooltip text (shown when hovering a form field's "(?)")
# ===================================================================
PARAMETER_HELP = {
    # Global
    'dbu_um': "Database unit (microns per GDS integer unit). Smaller = finer grid; 0.001 = 1 nm grid.",
    'enable_3_plasma_layers': "When on, all three plasma layers (12/13/14) are generated. When off, only plasma layer 1 is generated.",
    'enable_custom_cap_grid_reductions': "Use custom L2 width/length reductions instead of the standard encap offset for Capacitor grids.",
    'enable_graphene': "Draw the graphene membrane (layer 16) and its stem border (layer 15).",
    'quadrant_gap_x': "Horizontal gap (µm) between the four quadrants in the full-chip layout.",
    'quadrant_gap_y': "Vertical gap (µm) between the four quadrants in the full-chip layout.",
    'boundary_size_um': "Side length (µm) of the square chip boundary drawn on layer 4.",
    'boundary_width_um': "Line width (µm) of the chip-boundary outline on layer 4.",
    'enable_quadrant_sample_names': "Print the sample-name label above each quadrant on the full chip.",
    'sample_name_base': "Base sample name. Suffixes _A/_B/_C/_D are appended per quadrant.",
    'single_quadrant_type': "Select which quadrant the single-quadrant export behaves like (TL, TR, BL, BR).",
    'batch_production_count': "Number of batches to output (e.g. 5 will generate _1 through _5).",
    'batch_production_count': "Number of batches to output (e.g. 5 will generate _1 through _5).",
    'batch_production_count': "Number of batches to output (e.g. 5 will generate _1 through _5).",
    'export_etch_mask': "ETCH mask mode: output ONLY a full-chip DXF (*_ETCH.dxf) with the etch geometry, crosshairs and sample name all on layer 1. No other layers, no GDS, no single-quadrant outputs.",
    'export_gold_mask': "GOLD mask mode: output ONLY a full-chip DXF (*_GOLD.dxf) with the metal geometry, per-quadrant triangles and sample name on layer 2 — no crosshairs. No other layers, no GDS, no single-quadrant outputs. Optional GTT_### subtitle beneath each sample name (see enable_gtt_label).",
    'export_full_mask': "FULL mask mode: output ONLY the full-chip DXF (*_FULL.dxf) with every layer, but no full-chip GDS and no single-quadrant outputs (no SINGLE .gds/.dxf, no 3D DXF). Can be combined with the ETCH/GOLD mask checkboxes.",
    'kinetic_depth': "Kinetic etch depth (nm) used in the auto-generated K_ sample name when kinetic naming is enabled.",
    'enable_gtt_label': "When on (and Export GOLD mask is on), draw GTT_### centered beneath each sample name and append _GTT_### to the GOLD DXF filename.",
    'gtt_number': "3-digit GTT code (~42% of sample-name size). Used only when enable_gtt_label is on.",
    'sample_name_suffix_list': "Per-quadrant suffixes appended to the sample name (TL, TR, BL, BR order).",
    'sample_name_font_height_um': "Height (µm) of the sample-name text strokes.",
    'sample_name_font_width_um': "Width (µm) of the sample-name text strokes.",
    'sample_name_offset_x_um': "Horizontal offset (µm) of the sample-name text relative to the quadrant center.",
    'sample_name_offset_y_um': "Vertical offset (µm) of the sample-name text from the quadrant edge.",
    'triangle_width_um': "Width (µm) of the central alignment triangle on the full chip.",
    'triangle_height_um': "Height (µm) of the central alignment triangle on the full chip.",
    'triangle_layer_gds': "GDS [layer, datatype] for the central alignment triangle.",
    'triangle_offset_x_um': "Horizontal offset (µm) of the triangle tip from the chip center.",
    'triangle_offset_y_um': "Vertical offset (µm) of the triangle tip above/below the bottom boundary.",

    # Quadrant-level
    'contact_width':  "Width (µm) of each contact pad drawn at the ends of the wire rows.",
    'contact_height': "Height (µm) of each contact pad.",
    'capacitor_width':  "Width (µm) of the capacitor plates. Set to 0 to disable.",
    'capacitor_height': "Height (µm) of the capacitor plates.",
    'wire_L1_width': "Width (µm) of the L1 wires connecting contacts to capacitor grid.",
    'encap_offset': "Encapsulation (layer 1) inflate around every metal shape (µm). 0 disables the halo.",
    'wire_L1_length': "Length (µm) of each L1 wire (contact edge to wire start).",
    'wire_L1_grid_penetration_um': "How far (µm) the wires push into the capacitor grid from the outer edge.",
    'num_wires_per_contact': "Number of L1 wires landing on each contact pad. When > 1, kinetic naming uses K2, K3, ... (plain K when 1).",
    'wire_contact_inset_um': "Inset (µm) from the contact edges inside which wires must land.",
    'wire_spacing_um': "Explicit center-to-center distance (µm) between wires. If 0, spacing is computed automatically.",
    'wire_spacing_um': "Explicit center-to-center distance (µm) between wires. If 0, spacing is computed automatically.",
    'wire_spacing_um': "Explicit center-to-center distance (µm) between wires. If 0, spacing is computed automatically.",
    'capacitor_pair_spacing': "Center-to-center distance (µm) between the two capacitors in a pair.",
    'vertical_pitch': "Vertical pitch (µm) between successive contact rows.",
    'num_pairs': "Number of contact pairs per quadrant (rows).",
    'stagger_offset': "Signed length offset (µm) applied to staggered rows (even rows when stagger is enabled).",
    'enable_stagger': "Alternate wire lengths every other row so neighbouring rows don't clash.",
    'enable_capacitor_grid': "Draw the capacitor-plate grid (horizontal+vertical line array).",
    'capacitor_grid_line_width_um': "Line width (µm) of the capacitor grid.",
    'capacitor_grid_gap_um': "Gap (µm) between capacitor grid lines.",
    'capacitor_grid_l2_width_reduction_um': "Reduce the layer-2 grid-line width by this many µm vs layer-1.",
    'capacitor_grid_l2_length_reduction_um': "Reduce the layer-2 grid-line length by this many µm vs layer-1.",
    'plasma_layer_count': "Number of plasma layers to draw (up to 3).",
    'plasma_l1_layer': "GDS layer number for plasma layer 1.",
    'plasma_l1_width_um': "Strip width (µm) for plasma layer 1.",
    'plasma_l1_gap_um': "Gap (µm) between strips for plasma layer 1.",
    'plasma_l2_layer': "GDS layer number for plasma layer 2.",
    'plasma_l2_width_um': "Strip width (µm) for plasma layer 2.",
    'plasma_l2_gap_um': "Gap (µm) between strips for plasma layer 2.",
    'plasma_l3_layer': "GDS layer number for plasma layer 3.",
    'plasma_l3_width_um': "Strip width (µm) for plasma layer 3.",
    'plasma_l3_gap_um': "Gap (µm) between strips for plasma layer 3.",
    'stem_marker_strip_length_um': "Length (µm) of each plasma strip across the wire.",
    'stem_marker_array_coverage_left_um':  "Default total stem-strip coverage (µm) on the LEFT side of each contact.",
    'stem_marker_array_coverage_right_um': "Default total stem-strip coverage (µm) on the RIGHT side of each contact.",
    'corner_box_size':   "Width (µm) of the fiducial corner boxes (G1/G2/G3/G4 pads).",
    'corner_box_height': "Height (µm) of the fiducial corner boxes.",
    'corner_wire_L2_width': "Width (µm) of the frame wires running between fiducials.",
    'corner_wire_horizontal_length': "Length (µm) of the horizontal frame wires.",
    'clearance': "Extra space (µm) between the device area and the frame fiducials.",
    'central_vertical_wire_spacing': "Spacing (µm) between the two central vertical frame wires.",
    'paired_fiducial_spacing': "Vertical spacing (µm) between the two parallel frame wires near each fiducial.",
    'text_height': "Height (µm) of the numeric contact labels.",
    'text_width':  "Stroke width (µm) of the numeric contact labels.",
    'g_text_height': "Height (µm) of the G1/G2/G3/G4 fiducial labels.",
    'g_text_width':  "Stroke width (µm) of the G-pad labels.",
    'g_label_position': "Which side the G-pad labels are drawn on ('sides', 'top', 'bottom').",
    'g1g2_label_offset_x': "Horizontal offset (µm) of the G1/G2 labels from their pads.",
    'g1g2_label_offset_y': "Vertical offset (µm) of the G1/G2 labels from their pads.",
    'g3g4_label_offset_x': "Horizontal offset (µm) of the G3/G4 labels from their pads.",
    'g3g4_label_offset_y': "Vertical offset (µm) of the G3/G4 labels from their pads.",
    'contact_label_offset_x': "Horizontal offset (µm) of the per-contact numeric labels.",
    'contact_label_offset_y': "Vertical offset (µm) of the per-contact numeric labels.",
    'marker_box_size_um':        "Side length (µm) of the small alignment marker boxes.",
    'marker_box_series_count':   "How many marker boxes to draw in the alignment series.",
    'marker_box_series_spacing_um': "Center-to-center spacing (µm) of the alignment marker boxes.",
    'marker_box_offset_x_um': "X offset (µm) of the marker-box series from the quadrant origin.",
    'marker_box_offset_y_um': "Y offset (µm) of the marker-box series from the quadrant origin.",
    'enable_quadrant_crosshairs': "Draw the quadrant-level alignment crosshairs (layer 1 or configured).",
    'crosshair_gds_layers': "GDS layer numbers used for the quadrant crosshairs (e.g., [1, 2]).",
    'quadrant_crosshair_length_um': "Total length (µm) of each crosshair arm.",
    'quadrant_crosshair_width_um':  "Stroke width (µm) of the crosshair arms.",
    'quadrant_crosshair_offset_x_um': "X offset (µm) of the crosshair center from the quadrant center.",
    'quadrant_crosshair_offset_y_um': "Y offset (µm) of the crosshair center from the quadrant center.",
    'enable_quadrant_triangle': "Draw the small per-quadrant alignment triangle.",
    'quadrant_triangle_gds_layers': "GDS layer numbers used for the per-quadrant alignment triangle (e.g., [1, 2]). Honored exactly as set; the triangle stays on these layers regardless of the crosshair layer.",
    'quadrant_triangle_width_um':  "Width (µm) of the per-quadrant alignment triangle.",
    'quadrant_triangle_height_um': "Height (µm) of the per-quadrant alignment triangle.",
    'quadrant_triangle_offset_y_um': "Y offset (µm) of the per-quadrant triangle from the quadrant edge.",
    'sample_name_gds_layers': "GDS layer numbers the sample-name text is drawn on (e.g., [1], [1, 2], [1, 2, 3]). Works like crosshair_gds_layers.",
    'surface_metal_gds_layer': "GDS layer number used for surface metal (G-pads, frame wires, labels). Normally 5.",
    'split_stem_markers': "Split each stem strip in two with a gap near the wire (advanced / experimental).",
    'stem_marker_wire_clearance_um': "If split_stem_markers is on, the clear gap (µm) around each wire.",

    # 3D
    'enable_3d_dxf': "Write the 3D DXF (*_SINGLE_3D.dxf) alongside the 2D exports for the single quadrant.",
    'merge_layer5_into_layer2': "Before writing 2D outputs (GDS + 2D DXF), move every layer-5 shape onto layer 2. Applies to both FULL and SINGLE 2D outputs. 3D DXF always keeps layers 2 and 5 separate.",
    'box_extrude_down_um':   "How far down (µm) the enclosing rectangular box is extruded. Becomes the substrate thickness.",
    'layer1_extrude_down_um': "Depth (µm) of the trenches cut from the box (extruded down by this amount).",
    'layer2_extrude_up_um':   "Thickness (µm) of the layer-2 metal extruded upward.",
    'layer2_z_shift_um':      "Z shift (µm) applied to the layer-2 extrusion after extrusion (usually negative, places metal inside the trench).",
    'layer5_extrude_up_um':   "Thickness (µm) of the layer-5 surface-metal extrusion (G-pads, frame).",
    'graphene_extrude_up_um': "Thickness (µm) of the graphene membrane (layer 16) extruded upward.",
}


# ===================================================================
# GUI State Persistence
# ===================================================================
def _gui_state_path():
    import os
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base_dir = os.getcwd()
    return os.path.join(base_dir, "kinetic_design_state.json")


def _export_root_dir():
    import os
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


def _export_date_mmdd(global_params=None):
    """Return MMDD used for export subfolders (0624, etc.)."""
    if isinstance(global_params, dict):
        d = global_params.get('_export_date_mmdd')
        if d:
            return str(d)
    import datetime
    return datetime.datetime.now().strftime("%m%d")


def _export_subdir(kind, global_params=None):
    """Create and return <project>/<MMDD>_<kind>/ (kind: ETCH, GOLD, or ALL)."""
    import os
    folder = "{0}_{1}".format(_export_date_mmdd(global_params), kind)
    path = os.path.join(_export_root_dir(), folder)
    os.makedirs(path, exist_ok=True)
    return path


def _resolve_export_dir(mask_layer, global_params=None, output_dir=None):
    if output_dir is not None:
        import os
        os.makedirs(output_dir, exist_ok=True)
        return output_dir
    if mask_layer == 1:
        return _export_subdir('ETCH', global_params)
    if mask_layer == 2:
        return _export_subdir('GOLD', global_params)
    return _export_subdir('ALL', global_params)


def _export_path(output_dir, filename):
    import os
    return os.path.join(output_dir, filename)


def _migrate_legacy_state(data):
    """Silently rename legacy keys so saved states from earlier versions keep working."""
    if not isinstance(data, dict):
        return data
    g = data.get('global_params') or {}
    if isinstance(g, dict):
        if 'enable_layers_15_16' in g and 'enable_graphene' not in g:
            g['enable_graphene'] = bool(g.pop('enable_layers_15_16'))
        g.pop('enable_layers_15_16', None)
        g.pop('enable_layer_14_grid_markers', None)
        g.pop('enable_layer_13_stem_markers', None)
    q = data.get('quad_params') or {}
    if isinstance(q, dict):
        q.pop('enable_grid_markers', None)
        q.pop('grid_marker_inset_um', None)
    p3d = data.get('params_3d') or {}
    if isinstance(p3d, dict):
        if 'layer16_extrude_up_um' in p3d and 'graphene_extrude_up_um' not in p3d:
            p3d['graphene_extrude_up_um'] = float(p3d.pop('layer16_extrude_up_um'))
        p3d.pop('layer16_extrude_up_um', None)
    return data

def _load_gui_state():
    import os
    p = _gui_state_path()
    if not os.path.exists(p):
        legacy = os.path.join(os.path.dirname(p), "dhon_gui_state.json")
        if os.path.exists(legacy):
            p = legacy
        else:
            return {}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return _migrate_legacy_state(data)
    except Exception as e:
        print(f"Warning: failed to load GUI state: {e}")
        return {}

def _ask_yes_no(parent, title, message):
    """Cross-backend Yes/No dialog. Returns True if the user chose Yes."""
    try:
        yes = _qt_enum(QMessageBox, 'StandardButton.Yes')
        no = _qt_enum(QMessageBox, 'StandardButton.No')
        if yes is not None and no is not None:
            reply = QMessageBox.question(parent, title, message, yes | no)
            return reply == yes
    except Exception:
        pass
    try:
        ok = _qt_enum(QMessageBox, 'StandardButton.Ok')
        cancel = _qt_enum(QMessageBox, 'StandardButton.Cancel')
        if ok is not None and cancel is not None:
            reply = QMessageBox.warning(parent, title, message, ok | cancel)
            return reply == ok
    except Exception:
        pass
    return True


def _confirm_kinetic_depth_before_generate(parent, kinetic_depth, saved_state):
    """If the calendar date changed since the last Generate but kinetic_depth
    did not, ask the user to confirm before writing files."""
    import datetime
    try:
        depth = int(float(kinetic_depth))
    except Exception:
        return True
    if not isinstance(saved_state, dict):
        return True
    last_date = saved_state.get('last_generate_date')
    if not last_date:
        return True
    last_depth = saved_state.get('last_generate_kinetic_depth')
    if last_depth is None:
        return True
    try:
        last_depth = int(float(last_depth))
    except Exception:
        return True
    today = datetime.date.today().isoformat()
    if today == str(last_date):
        return True
    if depth != last_depth:
        return True
    return _ask_yes_no(
        parent,
        "Confirm depth",
        'Are you sure about the depth "{0}"?'.format(depth),
    )


def _kinetic_prefix(num_wires_per_contact):
    """K for one wire per contact; K2, K3, ... when num_wires_per_contact > 1."""
    try:
        n = int(num_wires_per_contact)
    except Exception:
        n = 1
    if n <= 1:
        return "K"
    return f"K{n}"


def _build_kinetic_sample_name_base(date_str, w_total, w_l1, depth, num_wires_per_contact=1):
    prefix = _kinetic_prefix(num_wires_per_contact)
    return f"{prefix}_{date_str}_{int(w_total)}{int(w_l1)}{int(depth)}"


def _format_gtt_label(gtt_number):
    """Return GTT_NNN label text for the gold-mask subtitle."""
    try:
        n = int(float(gtt_number))
    except Exception:
        n = 0
    n = max(0, min(999, n))
    return f"GTT_{n:03d}"


def _append_gtt_suffix(sample_name, gtt_number):
    """Append _GTT_NNN (3 digits) to export filenames for GOLD mask mode."""
    try:
        n = int(float(gtt_number))
    except Exception:
        n = 0
    n = max(0, min(999, n))
    return f"{sample_name}_GTT_{n:03d}"


def _save_gui_state(state):
    try:
        with open(_gui_state_path(), 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        print(f"Warning: failed to save GUI state: {e}")

# ===================================================================
# Helper Functions
# ===================================================================
def get_dbu_converter(layout):
    dbu = layout.dbu if layout and layout.dbu > 0 else 0.001
    def tod(val_um):
        try:
            numeric_val = float(val_um)
            return 0 if math.isnan(numeric_val) or math.isinf(numeric_val) else int(round(numeric_val / dbu))
        except:
            return 0
    return tod

def _apply_plasma_layer_count_from_global(global_params, quad_params):
    """Global 'enable 3 plasma layers' drives plasma_layer_count (3 or 1)."""
    if global_params.get('enable_3_plasma_layers', True):
        quad_params['plasma_layer_count'] = 3
    else:
        quad_params['plasma_layer_count'] = 1

# ===================================================================
# Robotic Stick Font Library & Text Generation
# ===================================================================
STICK_FONT = {
    '0': [[(0,0.5), (0,0), (1,0), (1,1), (0,1), (0,0.5)]],
    '1': [[(0.5, 0), (0.5, 1)]],
    '2': [[(0,1), (1,1), (1,0.5), (0,0.5), (0,0), (1,0)]],
    '3': [[(0,1), (1,1), (1,0.5), (0,0.5)], [(1,0.5), (1,0), (0,0)]],
    '4': [[(0,1), (0,0.5), (1,0.5)], [(1,1), (1,0)]],
    '5': [[(1,1), (0,1), (0,0.5), (1,0.5), (1,0), (0,0)]],
    '6': [[(1,1), (0,1), (0,0), (1,0), (1,0.5), (0,0.5)]],
    '7': [[(0,1), (1,1), (1,0)]],
    '8': [[(0,0.5), (0,0), (1,0), (1,1), (0,1), (0,0.5)], [(0,0.5), (1,0.5)]],
    '9': [[(1,0), (1,1), (0,1), (0,0.5), (1,0.5)]],
    'A': [[(0,0), (0,1), (1,1), (1,0)], [(0,0.5), (1,0.5)]],
    'B': [[(0,0.5), (0,1), (1,1), (1,0.5), (0,0.5)], [(0,0.5), (0,0), (1,0), (1,0.5)]],
    'C': [[(1,1), (0,1), (0,0), (1,0)]],
    'D': [[(0,0.5), (0,1), (0.8,1), (1,0.8), (1,0.2), (0.8,0), (0,0), (0,0.5)]],
    'E': [[(1,1), (0,1), (0,0), (1,0)], [(0,0.5), (0.8,0.5)]],
    'F': [[(1,1), (0,1), (0,0)], [(0,0.5), (0.8,0.5)]],
    'G': [[(1,1), (0,1), (0,0), (1,0), (1,0.5), (0.6,0.5)]],
    'H': [[(0,0), (0,1)], [(1,0), (1,1)], [(0,0.5), (1,0.5)]],
    'I': [[(0.5,0), (0.5,1)], [(0.2,1), (0.8,1)], [(0.2,0), (0.8,0)]],
    'J': [[(1,1), (1,0.2), (0.8,0), (0.2,0), (0,0.2), (0,0.5)]],
    'K': [[(0,0), (0,1)], [(1,1), (0,0.5), (1,0)]],
    'L': [[(0,1), (0,0), (1,0)]],
    'M': [[(0,0), (0,1), (0.5,0.5), (1,1), (1,0)]],
    'N': [[(0,0), (0,1), (1,0), (1,1)]],
    'O': [[(0,0.5), (0,0), (1,0), (1,1), (0,1), (0,0.5)]],
    'P': [[(0,0), (0,1), (1,1), (1,0.5), (0,0.5)]],
    'Q': [[(0,0.5), (0,0), (1,0), (1,1), (0,1), (0,0.5)], [(0.5,0.5), (1,0)]],
    'R': [[(0,0), (0,1), (1,1), (1,0.5), (0,0.5)], [(0.5,0.5), (1,0)]],
    'S': [[(1,1), (0,1), (0,0.5), (1,0.5), (1,0), (0,0)]],
    'T': [[(0,1), (1,1)], [(0.5,1), (0.5,0)]],
    'U': [[(0,1), (0,0), (1,0), (1,1)]],
    'V': [[(0,1), (0.5,0), (1,1)]],
    'W': [[(0,1), (0.2,0), (0.5,0.5), (0.8,0), (1,1)]],
    'X': [[(0,1), (1,0)], [(0,0), (1,1)]],
    'Y': [[(0,1), (0.5,0.5), (1,1)], [(0.5,0.5), (0.5,0)]],
    'Z': [[(0,1), (1,1), (0,0), (1,0)]],
    '-': [[(0.2,0.5), (0.8,0.5)]],
    '_': [[(0,0), (1,0)]],
    ' ': []
}

def generate_stick_text_region(text, w_um, h_um, layout):
    region = pya.Region()
    dbu = layout.dbu if layout.dbu > 0 else 0.001
    char_w_dbu = int(round(w_um / dbu))
    char_h_dbu = int(round(h_um / dbu))
    spacing_dbu = int(round((w_um * 0.4) / dbu))
    stroke_dbu = int(round(max(1.0, h_um * 0.1) / dbu))
    
    current_x = 0
    for char in str(text).upper():
        if char in STICK_FONT:
            for stroke in STICK_FONT[char]:
                pts = [pya.Point(current_x + int(round(x * char_w_dbu)), int(round(y * char_h_dbu))) for x, y in stroke]
                if len(pts) > 1:
                    path = pya.Path(pts, stroke_dbu)
                    poly = path.simple_polygon()
                    if poly and not poly.is_empty():
                        region.insert(poly)
        current_x += char_w_dbu + spacing_dbu
    region.merge()
    return region

def scale_region_anisotropic(region, sx, sy):
    """ Scales a pya.Region anisotropically by stretching its polygon points. """
    new_region = pya.Region()
    for poly in region.each():
        pts = [pya.Point(int(round(p.x * sx)), int(round(p.y * sy))) for p in poly.each_point_hull()]
        scaled_poly = pya.Polygon(pts)
        for h in range(poly.holes()):
            hole_pts = [pya.Point(int(round(p.x * sx)), int(round(p.y * sy))) for p in poly.each_point_hole(h)]
            scaled_poly.insert_hole(hole_pts)
        if not scaled_poly.is_empty(): 
            new_region.insert(scaled_poly)
    return new_region

def create_text(x_start, y_start, text, cell, layer_id, text_height, anchor="top-left", vertical=False, use_klayout_font=False, text_width=None):
    tod = get_dbu_converter(cell.layout())
    try:
        text_h_num = float(text_height); x_start_num = float(x_start); y_start_num = float(y_start)
        if text_h_num <= 0: return
    except: return

    text_w_num = float(text_width) if text_width is not None else text_h_num * 0.6
    gen = pya.TextGenerator.default_generator() if use_klayout_font else None
    
    if vertical: 
        char_spacing = text_h_num / 5.0
        for i, char_to_draw in enumerate(str(text)):
            if char_to_draw == ' ': continue 
            char_bottom_y = y_start_num - text_h_num - i * (text_h_num + char_spacing)
            if use_klayout_font:
                raw_region = gen.text(char_to_draw, cell.layout().dbu, text_h_num)
                if text_width is not None:
                    sx_ratio = float(text_width) / (text_h_num * 0.6)
                    if abs(sx_ratio - 1.0) > 0.01: raw_region = scale_region_anisotropic(raw_region, sx_ratio, 1.0)
                region = raw_region
            else:
                region = generate_stick_text_region(char_to_draw, text_w_num, text_h_num, cell.layout())
            region.transform(pya.Trans(tod(x_start_num), tod(char_bottom_y)))
            cell.shapes(layer_id).insert(region)
    else: 
        if use_klayout_font:
            raw_region = gen.text(str(text), cell.layout().dbu, text_h_num)
            if text_width is not None:
                sx_ratio = float(text_width) / (text_h_num * 0.6)
                if abs(sx_ratio - 1.0) > 0.01: raw_region = scale_region_anisotropic(raw_region, sx_ratio, 1.0)
            region = raw_region
        else:
            region = generate_stick_text_region(text, text_w_num, text_h_num, cell.layout())
            
        if region.is_empty(): return
        
        bbox = region.bbox()
        target_x_dbu = tod(x_start_num)
        target_y_dbu = tod(y_start_num)
        
        if anchor == "top-left":
            dx = target_x_dbu - bbox.left
            dy = target_y_dbu - bbox.top
        elif anchor == "top-center":
            dx = target_x_dbu - bbox.center().x
            dy = target_y_dbu - bbox.top
        elif anchor == "bottom-center":
            dx = target_x_dbu - bbox.center().x
            dy = target_y_dbu - bbox.bottom
        elif anchor == "bottom-left":
            dx = target_x_dbu - bbox.left
            dy = target_y_dbu - bbox.bottom
        elif anchor == "center-left":
            dx = target_x_dbu - bbox.left
            dy = target_y_dbu - bbox.center().y
        elif anchor == "center-right":
            dx = target_x_dbu - bbox.right
            dy = target_y_dbu - bbox.center().y
        elif anchor == "center":
            dx = target_x_dbu - bbox.center().x
            dy = target_y_dbu - bbox.center().y
        else:
            dx = target_x_dbu - bbox.left
            dy = target_y_dbu - bbox.top
            
        region.transform(pya.Trans(int(dx), int(dy)))
        
        # Merge and smooth
        region.merge()
        region.smooth(0.01)
        
        # FRACTURE logic: Split complex polygons with holes into simple trapezoids.
        # This is the "magic bullet" for AutoCAD extrusion of numbers like 0, 6, 8, 9.
        fractured_region = pya.Region()
        for poly in region.each():
            # Decompose each character polygon into simple, non-overlapping trapezoids (rectangles)
            temp_reg = pya.Region(poly)
            fractured_region.insert(temp_reg.decompose_trapezoids(0))
        
        cell.shapes(layer_id).insert(fractured_region)

# ===================================================================
# Quadrant Design Function (Core Logic Module)
# ===================================================================
class QuadrantBuilder:
    def __init__(self, layout, cell_name, params, layers):
        self.layout = layout
        self.cell_name = cell_name
        self.params = params
        self.layers = layers
        self.quadrant_cell = layout.create_cell(cell_name)
        self.tod = get_dbu_converter(layout)
        self.all_metal_shapes_encap = []
        self.devices_bbox_dbu = pya.Box()

    def _parse_params(self):
        p = self.params
        self.w_l1 = float(p['wire_L1_width']); self.enc_off = float(p['encap_offset'])
        self.c_w = float(p['contact_width']); self.c_h = float(p['contact_height'])
        self.cap_w = float(p['capacitor_width']); self.cap_h = float(p['capacitor_height'])
        self.wire_len = float(p['wire_L1_length']); self.cap_pair_spacing = float(p['capacitor_pair_spacing'])
        self.v_pitch = float(p['vertical_pitch']); self.stag_off = float(p['stagger_offset'])
        self.n_pairs = int(p['num_pairs']); self.en_stag = bool(p['enable_stagger'])
        self.wire_l1_grid_penetration = float(p.get('wire_L1_grid_penetration_um', 1.0))
        self.num_wires = int(p.get('num_wires_per_contact', 1))
        self.wire_contact_inset_um = float(p.get('wire_contact_inset_um', 60.0))
        self.wire_spacing_um = float(p.get('wire_spacing_um', 0.0))
        self.enable_cap_grid = bool(p.get('enable_capacitor_grid', True))
        self.cap_grid_lw = float(p.get('capacitor_grid_line_width_um', 5.0))
        self.cap_grid_gap = float(p.get('capacitor_grid_gap_um', 7.0))
        self.enable_custom_cap_grid_reductions = bool(p.get('enable_custom_cap_grid_reductions', False))
        self.cap_grid_l2_width_reduction = float(p.get('capacitor_grid_l2_width_reduction_um', 1.0))
        self.cap_grid_l2_length_reduction = float(p.get('capacitor_grid_l2_length_reduction_um', 1.0))
        self.corn_box_size = float(p['corner_box_size']); self.corn_box_h = float(p['corner_box_height'])
        self.frame_wire_w = float(p['corner_wire_L2_width']); self.frame_len_h = float(p['corner_wire_horizontal_length'])
        self.clearance = float(p['clearance']); self.v_wire_spacing = float(p['central_vertical_wire_spacing'])
        self.paired_fiducial_spacing = float(p['paired_fiducial_spacing'])
        self.txt_h = float(p['text_height']); self.txt_w = float(p['text_width'])
        self.g_txt_h = float(p.get('g_text_height', self.txt_h * 1.5)); self.g_txt_w = float(p.get('g_text_width', self.txt_w * 1.5))
        self.g_pos = p.get('g_label_position', 'sides').lower()
        self.g1g2_off_x = float(p.get('g1g2_label_offset_x', 100.0)); self.g1g2_off_y = float(p.get('g1g2_label_offset_y', 0.0))
        self.g3g4_off_x = float(p.get('g3g4_label_offset_x', 100.0)); self.g3g4_off_y = float(p.get('g3g4_label_offset_y', 0.0))
        self.contact_label_offset_x = float(p.get('contact_label_offset_x', 100.0))
        self.contact_label_offset_y = float(p.get('contact_label_offset_y', 0.0))
        self.marker_box_size_um = float(p.get('marker_box_size_um', 16.0))
        self.marker_box_series_count = int(p.get('marker_box_series_count', 5))
        self.marker_box_series_spacing_um = float(p.get('marker_box_series_spacing_um', 200.0))
        self.marker_box_offset_x_um = float(p.get('marker_box_offset_x_um', 1000.0))
        self.marker_box_offset_y_um = float(p.get('marker_box_offset_y_um', 0.0))
        self.marker_gold_pair_offset_y_um = float(p.get('marker_gold_pair_offset_y_um', 0.0))
        self.gold_box_size_um = float(p.get('gold_box_size_um', 16.0))
        self.gold_box_series_count = int(p.get('gold_box_series_count', 5))
        self.gold_box_series_spacing_um = float(p.get('gold_box_series_spacing_um', 200.0))
        self.gold_box_vertical_separation_um = float(p.get('gold_box_vertical_separation_um', 80.0))
        self.stem_marker_strip_length = float(p.get('stem_marker_strip_length_um', 100.0))
        self.stem_marker_array_coverage_left = float(p.get('stem_marker_array_coverage_left_um', 1100.0))
        self.stem_marker_array_coverage_right = float(p.get('stem_marker_array_coverage_right_um', 1300.0))
        self.stem_marker_override_left = p.get('stem_marker_lengths_left', [])
        self.stem_marker_override_right = p.get('stem_marker_lengths_right', [])
        
        self.plasma_layer_count = int(p.get('plasma_layer_count', 3))
        self.plasma_configs = []
        for i in range(1, 4):
            layer_num = int(p.get(f'plasma_l{i}_layer', 11 + i))
            width = float(p.get(f'plasma_l{i}_width_um', 10.0))
            gap = float(p.get(f'plasma_l{i}_gap_um', 10.0 * i))
            self.plasma_configs.append({'layer': layer_num, 'width': width, 'gap': gap})

        self.en_quad_ch = bool(p.get('enable_quadrant_crosshairs', True))
        _ch_def = DEFAULT_QUADRANT_PARAMS['crosshair_gds_layers']
        _tri_def = DEFAULT_QUADRANT_PARAMS['quadrant_triangle_gds_layers']
        self.crosshair_gds_layer_nums = _normalize_gds_layer_list(
            p.get('crosshair_gds_layers', p.get('crosshair_gds_layer', _ch_def)), _ch_def)
        # Honor the configured triangle layers exactly. The small per-quadrant
        # triangles stay on the etch/metal layers the user sets; only the
        # crosshairs live on their own (e.g. layer 3). No auto-move.
        self.quadrant_triangle_layer_nums = _normalize_gds_layer_list(
            p.get('quadrant_triangle_gds_layers'), _tri_def)

        self.quad_ch_len = float(p.get('quadrant_crosshair_length_um', 400.0))
        self.quad_ch_w = float(p.get('quadrant_crosshair_width_um', 10.0))
        self.quad_ch_off_x = float(p.get('quadrant_crosshair_offset_x_um', 800.0))
        self.quad_ch_off_y = float(p.get('quadrant_crosshair_offset_y_um', 50.0))
        self.en_quad_tri = bool(p.get('enable_quadrant_triangle', True))

        self.quad_tri_w = float(p.get('quadrant_triangle_width_um', 200.0))
        self.quad_tri_h = float(p.get('quadrant_triangle_height_um', 200.0))
        self.quad_tri_off_y = float(p.get('quadrant_triangle_offset_y_um', -50.0))
        self.split_stem_markers = bool(p.get('split_stem_markers', False))
        self.stem_marker_wire_clearance_um = float(p.get('stem_marker_wire_clearance_um', 0.5))
        self.surface_metal_layer_num = int(p.get('surface_metal_gds_layer', 5))

    def _setup_layers(self):
        l = self.layers
        self.layer_encap = l['etch']
        self.layer_metal = l['metal']
        # Surface metal: G-pads, frame wires, labels — sits at Z=0 (not inside trench)
        self.layer_surface_metal = self.layout.layer(pya.LayerInfo(self.surface_metal_layer_num, 0, "top metal"))
        self.text_layer = self.layer_surface_metal
        # Crosshair and triangle layers are configurable lists
        self.layers_crosshairs = [self.layout.layer(pya.LayerInfo(n, 0)) for n in getattr(self, 'crosshair_gds_layer_nums', [1])]
        self.layers_quadrant_triangles = [self.layout.layer(pya.LayerInfo(n, 0)) for n in getattr(self, 'quadrant_triangle_layer_nums', [1])]
        
        # Setup Plasma layers
        self.plasma_layers = []
        for i in range(min(self.plasma_layer_count, 3)):
            lnum = self.plasma_configs[i]['layer']
            if lnum > 0:
                w = self.plasma_configs[i]['width']
                g = self.plasma_configs[i]['gap']
                w_str = str(int(w)) if w.is_integer() else str(w)
                g_str = str(int(g)) if g.is_integer() else str(g)
                if self.plasma_layer_count == 1 and i == 0:
                    layer_name = "Plasma Layer ({0})".format(lnum)
                else:
                    layer_name = f"plasma {w_str}-{g_str}"
                self.plasma_layers.append(self.layout.layer(pya.LayerInfo(lnum, 0, layer_name)))
                
        self.layer_stem_border = l.get('stem_border')
        self.layer_graphene = l.get('graphene')

    def _draw_capacitors(self, y_center, cap_center_x_l, cap_center_x_r):
        tod = self.tod
        if self.enable_cap_grid and self.cap_grid_lw > 0 and self.cap_w > 0 and self.cap_h > 0:
            import math
            cap_grid_pitch = self.cap_grid_lw + self.cap_grid_gap
            
            if getattr(self, 'enable_custom_cap_grid_reductions', False):
                wid_red = self.cap_grid_l2_width_reduction
                len_red = self.cap_grid_l2_length_reduction
            else:
                wid_red = getattr(self, 'enc_off', 1.0) * 2.0
                len_red = getattr(self, 'enc_off', 1.0) * 2.0
                
            for center_x in [cap_center_x_l, cap_center_x_r]:
                bbox_x_min, bbox_y_min = center_x - self.cap_w / 2.0, y_center - self.cap_h / 2.0
                num_h_lines, start_y = (0, 0)
                if self.cap_h >= self.cap_grid_lw:
                    num_h_lines = int(math.floor((self.cap_h - self.cap_grid_lw) / cap_grid_pitch)) + 1
                    grid_total_h = (num_h_lines - 1) * cap_grid_pitch + self.cap_grid_lw
                    start_y = bbox_y_min + (self.cap_h - grid_total_h) / 2.0
                    for i in range(num_h_lines):
                        y_b, y_t = start_y + i * cap_grid_pitch, start_y + i * cap_grid_pitch + self.cap_grid_lw
                        self.quadrant_cell.shapes(self.layer_encap).insert(pya.Box(tod(bbox_x_min), tod(y_b), tod(bbox_x_min + self.cap_w), tod(y_t)))
                        
                        l2_x1 = bbox_x_min + len_red / 2.0
                        l2_x2 = bbox_x_min + self.cap_w - len_red / 2.0
                        l2_y1 = y_b + wid_red / 2.0
                        l2_y2 = y_t - wid_red / 2.0
                        if l2_x2 > l2_x1 and l2_y2 > l2_y1:
                            self.quadrant_cell.shapes(self.layer_metal).insert(pya.Box(tod(l2_x1), tod(l2_y1), tod(l2_x2), tod(l2_y2)))
                            
                num_v_lines, start_x = (0, 0)
                if self.cap_w >= self.cap_grid_lw:
                    num_v_lines = int(math.floor((self.cap_w - self.cap_grid_lw) / cap_grid_pitch)) + 1
                    grid_total_w = (num_v_lines - 1) * cap_grid_pitch + self.cap_grid_lw
                    start_x = bbox_x_min + (self.cap_w - grid_total_w) / 2.0
                    for i in range(num_v_lines):
                        x_l, x_r = start_x + i * cap_grid_pitch, start_x + i * cap_grid_pitch + self.cap_grid_lw
                        self.quadrant_cell.shapes(self.layer_encap).insert(pya.Box(tod(x_l), tod(bbox_y_min), tod(x_r), tod(bbox_y_min + self.cap_h)))
                        
                        l2_x1 = x_l + wid_red / 2.0
                        l2_x2 = x_r - wid_red / 2.0
                        l2_y1 = bbox_y_min + len_red / 2.0
                        l2_y2 = bbox_y_min + self.cap_h - len_red / 2.0
                        if l2_x2 > l2_x1 and l2_y2 > l2_y1:
                            self.quadrant_cell.shapes(self.layer_metal).insert(pya.Box(tod(l2_x1), tod(l2_y1), tod(l2_x2), tod(l2_y2)))
            cap_l_box_bbox = pya.Box(tod(cap_center_x_l-self.cap_w/2), tod(y_center-self.cap_h/2), tod(cap_center_x_l+self.cap_w/2), tod(y_center+self.cap_h/2))
            cap_r_box_bbox = pya.Box(tod(cap_center_x_r-self.cap_w/2), tod(y_center-self.cap_h/2), tod(cap_center_x_r+self.cap_w/2), tod(y_center+self.cap_h/2))
        else:
            if self.cap_w > 0 and self.cap_h > 0:
                cap_l_box = pya.Box(tod(cap_center_x_l - self.cap_w/2), tod(y_center - self.cap_h/2), tod(cap_center_x_l + self.cap_w/2), tod(y_center + self.cap_h/2))
                cap_r_box = pya.Box(tod(cap_center_x_r - self.cap_w/2), tod(y_center - self.cap_h/2), tod(cap_center_x_r + self.cap_w/2), tod(y_center + self.cap_h/2))
                self.quadrant_cell.shapes(self.layer_metal).insert(cap_l_box)
                self.quadrant_cell.shapes(self.layer_metal).insert(cap_r_box)
                self.all_metal_shapes_encap.extend([cap_l_box, cap_r_box])
                cap_l_box_bbox, cap_r_box_bbox = cap_l_box, cap_r_box
            else:
                cap_l_box_bbox = pya.Box()
                cap_r_box_bbox = pya.Box()
        return cap_l_box_bbox, cap_r_box_bbox

    def _draw_contact_pads_and_wires(self, idx, y_center, contact_edge_x_l, contact_edge_x_r, wire_start_x_l, wire_start_x_r, custom_cov_left, custom_cov_right):
        import math
        tod = self.tod
        merged_contact_l_box = pya.Box(tod(contact_edge_x_l - self.c_w), tod(y_center - self.c_h/2), tod(contact_edge_x_l), tod(y_center + self.c_h/2))
        merged_contact_r_box = pya.Box(tod(contact_edge_x_r), tod(y_center - self.c_h/2), tod(contact_edge_x_r + self.c_w), tod(y_center + self.c_h/2))
        
        y_wire_centers_um = []
        if self.enable_cap_grid and self.cap_grid_lw > 0 and self.cap_h >= self.cap_grid_lw:
            cap_grid_pitch = self.cap_grid_lw + self.cap_grid_gap
            num_h_lines = int(math.floor((self.cap_h - self.cap_grid_lw) / cap_grid_pitch)) + 1
            grid_total_h = (num_h_lines - 1) * cap_grid_pitch + self.cap_grid_lw
            start_y = (y_center - self.cap_h/2.0) + (self.cap_h - grid_total_h) / 2.0
            all_grid_y_centers_um = [start_y + i * cap_grid_pitch + self.cap_grid_lw / 2.0 for i in range(num_h_lines)]
            safe_y_min, safe_y_max = y_center - (self.c_h / 2.0) + self.wire_contact_inset_um, y_center + (self.c_h / 2.0) - self.wire_contact_inset_um
            valid_y = [y for y in all_grid_y_centers_um if safe_y_min <= y <= safe_y_max]
            if len(valid_y) > 0:
                if self.num_wires == 1: y_wire_centers_um.append(valid_y[len(valid_y) // 2])
                elif self.num_wires == 2 and len(valid_y) >= 2: y_wire_centers_um.extend([valid_y[0], valid_y[-1]])
                elif self.num_wires >= 3 and len(valid_y) >= 3: y_wire_centers_um.extend([valid_y[0], valid_y[len(valid_y) // 2], valid_y[-1]])
                else: y_wire_centers_um.extend(valid_y)
        if self.wire_spacing_um > 0.0 and self.num_wires > 1:
            y_wire_centers_um = []
            start_offset = (self.num_wires - 1) * self.wire_spacing_um / 2.0
            for w_idx in range(self.num_wires):
                y_wire_centers_um.append(y_center + start_offset - w_idx * self.wire_spacing_um)
        elif not y_wire_centers_um:
            eff_h = self.c_h - 2 * self.wire_contact_inset_um
            if eff_h > 0:
                if self.num_wires == 1: y_wire_centers_um.append(y_center)
                elif self.num_wires == 2: y_wire_centers_um.extend([y_center + eff_h/4, y_center - eff_h/4])
                else: y_wire_centers_um.extend([y_center + eff_h/4, y_center, y_center - eff_h/4])
            else: y_wire_centers_um.append(y_center)

        wire_pts_list = []
        for y_coord in y_wire_centers_um:
            wire_pts_list.append([pya.Point(tod(wire_start_x_l), tod(y_coord)), pya.Point(tod(contact_edge_x_l), tod(y_coord))])
            wire_pts_list.append([pya.Point(tod(wire_start_x_r), tod(y_coord)), pya.Point(tod(contact_edge_x_r), tod(y_coord))])

            # Draw multi-layer plasma
            for p_idx in range(min(self.plasma_layer_count, 3)):
                if p_idx < len(self.plasma_layers):
                    p_layer_id = self.plasma_layers[p_idx]
                    p_width = self.plasma_configs[p_idx]['width']
                    p_gap = self.plasma_configs[p_idx]['gap']
                    
                    if p_width > 0:
                        strip_pitch = p_width + p_gap
                        if strip_pitch > 0:
                            y_bot, y_top = y_coord - self.stem_marker_strip_length / 2.0, y_coord + self.stem_marker_strip_length / 2.0
                            
                            if custom_cov_left > 0:
                                for j in range(int(math.floor(custom_cov_left / strip_pitch)) + 1):
                                    strip_r = wire_start_x_l - j * strip_pitch
                                    strip_l = max(strip_r - p_width, wire_start_x_l - custom_cov_left)
                                    if strip_l < strip_r: self.quadrant_cell.shapes(p_layer_id).insert(pya.Box(tod(strip_l), tod(y_bot), tod(strip_r), tod(y_top)))
                            if custom_cov_right > 0:
                                for j in range(int(math.floor(custom_cov_right / strip_pitch)) + 1):
                                    strip_l = wire_start_x_r + j * strip_pitch
                                    strip_r = min(strip_l + p_width, wire_start_x_r + custom_cov_right)
                                    if strip_l < strip_r: self.quadrant_cell.shapes(p_layer_id).insert(pya.Box(tod(strip_l), tod(y_bot), tod(strip_r), tod(y_top)))

        if self.txt_h > 0:
            num = self.n_pairs - idx
            label_l, label_r = str(num), str(self.n_pairs + num)
            
            x_left = contact_edge_x_l - self.c_w - self.contact_label_offset_x
            y_left = y_center + self.contact_label_offset_y
            create_text(x_left, y_left, label_l, self.quadrant_cell, self.text_layer, self.txt_h, anchor="center-right")
            
            x_right = contact_edge_x_r + self.c_w + self.contact_label_offset_x
            y_right = y_center + self.contact_label_offset_y
            create_text(x_right, y_right, label_r, self.quadrant_cell, self.text_layer, self.txt_h, anchor="center-left")
        
        contacts_and_wires_metal = [merged_contact_l_box, merged_contact_r_box]
        self.all_metal_shapes_encap.extend(contacts_and_wires_metal)
        for shape in contacts_and_wires_metal:
            self.quadrant_cell.shapes(self.layer_metal).insert(shape)
        for pts in wire_pts_list:
            poly = pya.Path(pts, tod(self.w_l1)).simple_polygon()
            if poly and not poly.is_empty():
                self.quadrant_cell.shapes(self.layer_metal).insert(poly)
        
        enc_off_dbu = tod(self.enc_off)
        if self.enc_off > 0:
            for shape in self.all_metal_shapes_encap:
                self.quadrant_cell.shapes(self.layer_encap).insert(shape.enlarged(enc_off_dbu, enc_off_dbu))
            for pts in wire_pts_list:
                enc_path = pya.Path(pts, tod(self.w_l1) + 2 * enc_off_dbu, enc_off_dbu, enc_off_dbu).simple_polygon()
                if enc_path and not enc_path.is_empty(): self.quadrant_cell.shapes(self.layer_encap).insert(enc_path)
                
        return merged_contact_l_box, merged_contact_r_box

    def _draw_layer_15_16(self):
        """Build Stem Border (layer 15) and Graphene (layer 16) from the stem markers."""
        tod = self.tod
        if self.plasma_layer_count > 0 and len(self.plasma_layers) > 0 and self.n_pairs > 0:
            if self.layer_stem_border and self.layer_graphene:
                # Use only plasma layer 1 to cut out the graphene sheet
                region13 = pya.Region()
                region13.insert(self.quadrant_cell.shapes(self.plasma_layers[0]))
                region13.merge()

                # Layer 15 (Stem Border): bbox of the stem-marker array, padded.
                if not region13.is_empty():
                    border_box = region13.bbox()
                    padding_um = 20.0
                    border_box.enlarge(tod(padding_um))
                    self.quadrant_cell.shapes(self.layer_stem_border).insert(border_box)

                    # Layer 16 (Graphene): the stem-border sheet MINUS the stem strips.
                    sheet_region = pya.Region(border_box)
                    subtracted_region = sheet_region - region13

                    subtracted_region.merge()
                    subtracted_region.smooth(1.0)

                    # Fracture into trapezoids so AutoCAD can extrude cleanly.
                    fractured_membrane = subtracted_region.decompose_trapezoids(0)
                    self.quadrant_cell.shapes(self.layer_graphene).insert(fractured_membrane)

    def _draw_frames_and_fiducials(self):
        tod = self.tod
        devices_bbox_um = self.devices_bbox_dbu.transformed(pya.ICplxTrans(self.layout.dbu)) if not self.devices_bbox_dbu.empty() else pya.Box(0,0,0,0)
        y_top_center, y_bot_center = devices_bbox_um.top + self.clearance, devices_bbox_um.bottom - self.clearance
        half_frame_len, half_v_wire_spacing = self.frame_len_h / 2.0, self.v_wire_spacing / 2.0
        half_paired_fiducial_spacing = self.paired_fiducial_spacing / 2.0
        merged_fiducial_centers_um = [pya.Point(-half_frame_len, y_top_center), pya.Point(half_frame_len, y_top_center), pya.Point(-half_frame_len, y_bot_center), pya.Point(half_frame_len, y_bot_center)]
        corner_box_half_w, corner_box_half_h = self.corn_box_size / 2.0, self.corn_box_h / 2.0
        
        for center_pt_um in merged_fiducial_centers_um:
            self.quadrant_cell.shapes(self.layer_surface_metal).insert(pya.Box(tod(center_pt_um.x - corner_box_half_w), tod(center_pt_um.y - corner_box_half_h), tod(center_pt_um.x + corner_box_half_w), tod(center_pt_um.y + corner_box_half_h)))
        
        if tod(self.frame_wire_w) > 0:
            frame_wire_w_dbu = tod(self.frame_wire_w)
            wire_paths = [
                # Horizontal top
                pya.Path([pya.Point(tod(merged_fiducial_centers_um[0].x), tod(y_top_center + half_paired_fiducial_spacing)), pya.Point(tod(merged_fiducial_centers_um[1].x), tod(y_top_center + half_paired_fiducial_spacing))], frame_wire_w_dbu),
                pya.Path([pya.Point(tod(merged_fiducial_centers_um[0].x), tod(y_top_center - half_paired_fiducial_spacing)), pya.Point(tod(merged_fiducial_centers_um[1].x), tod(y_top_center - half_paired_fiducial_spacing))], frame_wire_w_dbu),
                # Horizontal bottom
                pya.Path([pya.Point(tod(merged_fiducial_centers_um[2].x), tod(y_bot_center + half_paired_fiducial_spacing)), pya.Point(tod(merged_fiducial_centers_um[3].x), tod(y_bot_center + half_paired_fiducial_spacing))], frame_wire_w_dbu),
                pya.Path([pya.Point(tod(merged_fiducial_centers_um[2].x), tod(y_bot_center - half_paired_fiducial_spacing)), pya.Point(tod(merged_fiducial_centers_um[3].x), tod(y_bot_center - half_paired_fiducial_spacing))], frame_wire_w_dbu),
                # Vertical side wires
                pya.Path([pya.Point(tod(-half_v_wire_spacing), tod(y_top_center + half_paired_fiducial_spacing)), pya.Point(tod(-half_v_wire_spacing), tod(y_bot_center - half_paired_fiducial_spacing))], frame_wire_w_dbu),
                pya.Path([pya.Point(tod(half_v_wire_spacing), tod(y_top_center + half_paired_fiducial_spacing)), pya.Point(tod(half_v_wire_spacing), tod(y_bot_center - half_paired_fiducial_spacing))], frame_wire_w_dbu)
            ]
            
            for wp in wire_paths:
                poly = wp.simple_polygon()
                if poly and not poly.is_empty():
                    # Fracture into simple rectangles for AutoCAD
                    fractured = pya.Region(poly).decompose_trapezoids(0)
                    self.quadrant_cell.shapes(self.layer_surface_metal).insert(fractured)
        
        if self.marker_box_size_um > 0 and self.marker_box_series_count > 0:
            half_box, pitch = self.marker_box_size_um / 2.0, self.marker_box_size_um + self.marker_box_series_spacing_um
            for base_loc in merged_fiducial_centers_um:
                offset_x = -self.marker_box_offset_x_um if base_loc.x < 0 else self.marker_box_offset_x_um
                series_center_x = base_loc.x + offset_x
                series_center_y = base_loc.y + self.marker_box_offset_y_um + getattr(self, 'marker_gold_pair_offset_y_um', 0.0)
                start_x = series_center_x - (self.marker_box_series_count - 1) / 2.0 * pitch
                for i in range(self.marker_box_series_count):
                    center_x = start_x + i * pitch
                    self.quadrant_cell.shapes(self.layer_encap).insert(pya.Box(tod(center_x - half_box), tod(series_center_y - half_box), tod(center_x + half_box), tod(series_center_y + half_box)))

        if getattr(self, 'gold_box_size_um', 0) > 0 and getattr(self, 'gold_box_series_count', 0) > 0:
            half_gold, gold_pitch = self.gold_box_size_um / 2.0, self.gold_box_size_um + self.gold_box_series_spacing_um
            for base_loc in merged_fiducial_centers_um:
                offset_x = -self.marker_box_offset_x_um if base_loc.x < 0 else self.marker_box_offset_x_um
                marker_series_center_x = base_loc.x + offset_x
                marker_series_center_y = base_loc.y + self.marker_box_offset_y_um + getattr(self, 'marker_gold_pair_offset_y_um', 0.0)
                gold_center_x = marker_series_center_x
                gold_center_y = marker_series_center_y + getattr(self, 'gold_box_vertical_separation_um', 80.0)
                gold_start_x = gold_center_x - (self.gold_box_series_count - 1) / 2.0 * gold_pitch
                for i in range(self.gold_box_series_count):
                    center_x = gold_start_x + i * gold_pitch
                    self.quadrant_cell.shapes(self.layer_surface_metal).insert(
                        pya.Box(tod(center_x - half_gold), tod(gold_center_y - half_gold), tod(center_x + half_gold), tod(gold_center_y + half_gold))
                    )
        
        if self.en_quad_ch and self.quad_ch_len > 0 and self.quad_ch_w > 0:
            ch_half_len, ch_half_w = self.quad_ch_len / 2.0, self.quad_ch_w / 2.0
            for i, ref_pt in enumerate(merged_fiducial_centers_um):
                off_x = self.quad_ch_off_x * (-1 if i % 2 == 0 else 1)
                off_y = self.quad_ch_off_y * (1 if i < 2 else -1)
                ch_x, ch_y = ref_pt.x + off_x, ref_pt.y + off_y
                box1 = pya.Box(tod(ch_x - ch_half_len), tod(ch_y - ch_half_w), tod(ch_x + ch_half_len), tod(ch_y + ch_half_w))
                box2 = pya.Box(tod(ch_x - ch_half_w), tod(ch_y - ch_half_len), tod(ch_x + ch_half_w), tod(ch_y + ch_half_len))
                for l in self.layers_crosshairs:
                    self.quadrant_cell.shapes(l).insert(box1)
                    self.quadrant_cell.shapes(l).insert(box2)
        
        if self.en_quad_tri and self.quad_tri_w > 0 and self.quad_tri_h > 0:
            base_y = y_bot_center - half_paired_fiducial_spacing + self.quad_tri_off_y
            tip_y = base_y - self.quad_tri_h
            poly = pya.SimplePolygon([pya.Point(tod(0), tod(tip_y)), pya.Point(tod(-self.quad_tri_w/2.0), tod(base_y)), pya.Point(tod(self.quad_tri_w/2.0), tod(base_y))])
            if not poly.is_empty(): 
                for l in self.layers_quadrant_triangles:
                    self.quadrant_cell.shapes(l).insert(poly)
            
        if self.g_txt_h > 0:
            labels = ["G1", "G2", "G3", "G4"]
            for i, center in enumerate(merged_fiducial_centers_um):
                label = labels[i]
                is_top, is_left = i < 2, i in [0, 2]
                off_x, off_y = (self.g1g2_off_x, self.g1g2_off_y) if is_top else (self.g3g4_off_x, self.g3g4_off_y)
                
                if self.g_pos == 'sides':
                    ty = center.y
                    if is_left:
                        tx = center.x - corner_box_half_w - off_x
                        create_text(tx, ty, label, self.quadrant_cell, self.text_layer, self.g_txt_h, anchor="center-right")
                    else:
                        tx = center.x + corner_box_half_w + off_x
                        create_text(tx, ty, label, self.quadrant_cell, self.text_layer, self.g_txt_h, anchor="center-left")
                else:
                    tx = center.x
                    if is_top:
                        ty = center.y + corner_box_half_h + off_y
                        create_text(tx, ty, label, self.quadrant_cell, self.text_layer, self.g_txt_h, anchor="bottom-center")
                    else:
                        ty = center.y - corner_box_half_h - off_y
                        create_text(tx, ty, label, self.quadrant_cell, self.text_layer, self.g_txt_h, anchor="top-center")
        
        return merged_fiducial_centers_um

    def build(self):
        try:
            self._parse_params()
        except Exception as e:
            print(f"Param extraction error for {self.cell_name}: {e}")
            return None, None, None

        self._setup_layers()

        if self.n_pairs > 0:
            cap_center_x_l = -self.cap_pair_spacing / 2.0
            cap_center_x_r = self.cap_pair_spacing / 2.0
            wire_start_x_l = cap_center_x_l - (self.cap_w / 2.0) + self.wire_l1_grid_penetration
            wire_start_x_r = cap_center_x_r + (self.cap_w / 2.0) - self.wire_l1_grid_penetration

            for idx in range(self.n_pairs):
                custom_cov_left = self.stem_marker_array_coverage_left
                if self.stem_marker_override_left and idx < len(self.stem_marker_override_left):
                    try: custom_cov_left = float(self.stem_marker_override_left[idx])
                    except: pass
                custom_cov_right = self.stem_marker_array_coverage_right
                if self.stem_marker_override_right and idx < len(self.stem_marker_override_right):
                    try: custom_cov_right = float(self.stem_marker_override_right[idx])
                    except: pass

                y_center = idx * self.v_pitch
                is_staggered_row = self.en_stag and (idx % 2 == 0)
                effective_wire_len = self.wire_len + self.stag_off if is_staggered_row else self.wire_len
                contact_edge_x_l = (cap_center_x_l - self.cap_w / 2.0) - effective_wire_len
                contact_edge_x_r = (cap_center_x_r + self.cap_w / 2.0) + effective_wire_len

                self.all_metal_shapes_encap = []

                cap_l_box_bbox, cap_r_box_bbox = self._draw_capacitors(y_center, cap_center_x_l, cap_center_x_r)
                
                merged_contact_l_box, merged_contact_r_box = self._draw_contact_pads_and_wires(
                    idx, y_center, contact_edge_x_l, contact_edge_x_r, wire_start_x_l, wire_start_x_r,
                    custom_cov_left, custom_cov_right
                )
                
                self.devices_bbox_dbu += merged_contact_l_box + merged_contact_r_box + cap_l_box_bbox + cap_r_box_bbox

        self._draw_layer_15_16()
        merged_fiducial_centers_um = self._draw_frames_and_fiducials()

        return self.quadrant_cell, merged_fiducial_centers_um, self.quadrant_cell.bbox().dup()

def create_quadrant(layout, cell_name, params, layers):
    builder = QuadrantBuilder(layout, cell_name, params, layers)
    return builder.build()

def _compute_crosshair_positions_from_fiducials(fiducial_centers_um, quad_params):
    """Return crosshair centers in um keyed by TL/TR/BL/BR."""
    if not fiducial_centers_um or len(fiducial_centers_um) < 4:
        return {}
    off_x = float(quad_params.get('quadrant_crosshair_offset_x_um', 800.0))
    off_y = float(quad_params.get('quadrant_crosshair_offset_y_um', 50.0))
    labels = ["TL", "TR", "BL", "BR"]
    out = {}
    for i, ref_pt in enumerate(fiducial_centers_um[:4]):
        dx = off_x * (-1 if i % 2 == 0 else 1)
        dy = off_y * (1 if i < 2 else -1)
        out[labels[i]] = (ref_pt.x + dx, ref_pt.y + dy)
    return out

def _print_crosshair_positions(tag, pos_map):
    """Pretty-print TL/BL/TR/BR crosshair centers in um."""
    if not pos_map:
        print("")
        print("=" * 62)
        print(f" {tag} CROSSHAIR CENTERS (um)")
        print("=" * 62)
        print("  unavailable")
        print("=" * 62)
        return
    order = ["TL", "BL", "TR", "BR"]
    print("")
    print("=" * 62)
    print(f" {tag} CROSSHAIR CENTERS (um)")
    print("=" * 62)
    for k in order:
        if k in pos_map:
            x, y = pos_map[k]
            print(f"  {k:>2} :  X = {x:>12.3f}   Y = {y:>12.3f}")
    print("=" * 62)
def _normalize_gds_layer_list(value, default):
    """Accept an int (3), list ([1, 2]), tuple, or string ("[3]", "3") of GDS layer
    numbers — same flexibility as crosshair_gds_layers — and return a list."""
    if value is None:
        return list(default)
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value.strip())
        except Exception:
            return list(default)
    if isinstance(value, bool):
        return list(default)
    if isinstance(value, int):
        return [int(value)]
    try:
        if hasattr(value, 'item') and not isinstance(value, (list, tuple, str, bytes)):
            value = int(value.item())
            return [value]
    except Exception:
        pass
    if isinstance(value, (list, tuple)) and len(value) > 0:
        try:
            return [int(x) for x in value]
        except Exception:
            return list(default)
    return list(default)


def _parse_layer_list_ui_text(txt, default):
    """Parse a QLineEdit value for a list-of-GDS-integers parameter."""
    try:
        return _normalize_gds_layer_list((txt or '').strip(), default)
    except Exception:
        return list(default)


def _quad_placement_offsets_um(bbox_dbu, dbu, gap_x, gap_y):
    """Placement offset (dx, dy) in um applied to each quadrant, given a single
    (identical) quadrant bbox. Mirrors the origin math in create_full_chip_design,
    so two masks with equal quadrant bboxes place every device identically."""
    max_w, max_h = bbox_dbu.width(), bbox_dbu.height()
    origins_x = [-(max_w * dbu + gap_x / 2.), gap_x / 2.]
    origins_y = [gap_y / 2., -(max_h * dbu + gap_y / 2.)]
    grid = {"TL": (0, 0), "TR": (1, 0), "BL": (0, 1), "BR": (1, 1)}
    left_um, bottom_um = bbox_dbu.left * dbu, bbox_dbu.bottom * dbu
    return {name: (origins_x[c] - left_um, origins_y[r] - bottom_um)
            for name, (c, r) in grid.items()}


def _reference_quadrant_bbox(dbu, quad_params, mask_layer, enable_graphene):
    """Build a throwaway quadrant in a scratch layout and return its bbox (dbu),
    configured exactly as create_full_chip_design would for the given mask layer."""
    try:
        scratch = pya.Layout()
        scratch.dbu = dbu
        slayers = {
            'etch': scratch.layer(pya.LayerInfo(1, 0)),
            'metal': scratch.layer(pya.LayerInfo(2, 0)),
            'crosshairs': scratch.layer(pya.LayerInfo(3, 0)),
            'border': scratch.layer(pya.LayerInfo(4, 0)),
            'stem_border': scratch.layer(pya.LayerInfo(15, 0)) if enable_graphene else None,
            'graphene': scratch.layer(pya.LayerInfo(16, 0)) if enable_graphene else None,
        }
        qp = copy.deepcopy(quad_params)
        if int(mask_layer) == 2:
            qp['crosshair_gds_layers'] = [3]
        else:
            qp['crosshair_gds_layers'] = [int(mask_layer)]
        qp['quadrant_triangle_gds_layers'] = [int(mask_layer)]
        qp['sample_name_gds_layers'] = [int(mask_layer)]
        _cell, _fids, bbox = create_quadrant(scratch, "ALIGN_REF", qp, slayers)
        return bbox
    except Exception as e:
        print(f"[ALIGN CHECK] Reference quadrant build failed: {e}")
        return None


def _verify_mask_alignment(gold_bbox_dbu, quad_params, global_params, tol_um=0.005):
    """On GOLD export, confirm every quadrant lands exactly where the ETCH mask
    would place it. The two masks share identical device geometry, so any device's
    misalignment equals the difference in its quadrant's placement offset. Returns
    (ok, max_error_um) and prints a report."""
    dbu = global_params['dbu_um']
    gap_x, gap_y = global_params['quadrant_gap_x'], global_params['quadrant_gap_y']
    enable_graphene = global_params.get('enable_graphene', False)
    etch_bbox = _reference_quadrant_bbox(dbu, quad_params, 1, enable_graphene)
    if (etch_bbox is None or gold_bbox_dbu is None
            or etch_bbox.empty() or gold_bbox_dbu.empty()):
        print("[ALIGN CHECK] Skipped — could not compute reference bbox.")
        return True, 0.0
    gold_off = _quad_placement_offsets_um(gold_bbox_dbu, dbu, gap_x, gap_y)
    etch_off = _quad_placement_offsets_um(etch_bbox, dbu, gap_x, gap_y)
    max_err, rows = 0.0, []
    for name in ["TL", "TR", "BL", "BR"]:
        gdx, gdy = gold_off[name]
        edx, edy = etch_off[name]
        ex, ey = gdx - edx, gdy - edy
        max_err = max(max_err, abs(ex), abs(ey))
        rows.append((name, ex, ey))
    ok = max_err <= tol_um
    print("")
    print("=" * 62)
    print(" GOLD<->ETCH ALIGNMENT CHECK (per-quadrant offset, um)")
    print("=" * 62)
    for name, ex, ey in rows:
        print(f"  {name:>2} :  dX = {ex:>10.4f}   dY = {ey:>10.4f}")
    print("-" * 62)
    if ok:
        print(f"  OK - masks aligned (max error {max_err:.4f} um <= {tol_um} um).")
    else:
        print("  *** WARNING: GOLD mask is MISALIGNED with ETCH ***")
        print(f"  max error {max_err:.4f} um exceeds tolerance {tol_um} um.")
        print("  Check that quadrant crosshairs are still drawn (they set the")
        print("  quadrant bbox used for placement).")
    print("=" * 62)
    return ok, max_err


def create_full_chip_design(global_params=None, quad_params=None, params_3d=None,
                            mask_layer=None, mask_suffix=None, output_dir=None,
                            full_dxf_only=False):
    """Build and export the full four-quadrant chip.

    Normal mode (mask_layer=None) writes <MMDD>_ALL/<name>_FULL.gds and .dxf.
    With full_dxf_only=True (FULL mask mode) only the <name>_FULL.dxf is written —
    the full-chip GDS is skipped.

    Mask mode (mask_layer=1 → ETCH, mask_layer=2 → GOLD): per-quadrant triangles,
    the central triangle and sample names are forced onto `mask_layer`. ETCH includes
    crosshairs; GOLD omits them. Every other layer is stripped, and ONLY a full-chip
    DXF (<MMDD>_<ETCH|GOLD>/<name>_<suffix>.dxf) is written — no GDS."""
    if global_params is None: global_params = GLOBAL_PARAMS
    if quad_params is None: quad_params = DEFAULT_QUADRANT_PARAMS

    quad_params = copy.deepcopy(quad_params)
    _apply_plasma_layer_count_from_global(global_params, quad_params)

    if mask_layer is not None:
        mask_layer = int(mask_layer)
        # Triangles (small per-quadrant + central) and sample names go on the mask
        # layer so they appear in the exported ETCH/GOLD DXF.
        quad_params['quadrant_triangle_gds_layers'] = [mask_layer]
        quad_params['sample_name_gds_layers'] = [mask_layer]
        if mask_layer == 2:
            # GOLD: crosshairs on throwaway layer 3 (stripped below) so the quadrant
            # bbox matches ETCH, but they do not appear in the gold mask output.
            quad_params['crosshair_gds_layers'] = [3]
        else:
            # ETCH: crosshairs belong on the mask layer and are kept in the export.
            quad_params['crosshair_gds_layers'] = [mask_layer]
        global_params = copy.deepcopy(global_params)
        global_params['triangle_layer_gds'] = [mask_layer, 0]

    chip_config = {
        "capacitor_pair_spacing": quad_params.get("capacitor_pair_spacing", 322.0),
        "capacitor_width": quad_params.get("capacitor_width", 0.0),
        "wire_L1_grid_penetration_um": quad_params.get("wire_L1_grid_penetration_um", 1.0),
        "wire_L1_length": quad_params.get("wire_L1_length", 2400.0),
        "stagger_offset": quad_params.get("stagger_offset", -500.0)
    }
    if mask_layer is None:
        try:
            import os
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chip_design.json")
            with open(config_path, "w") as f:
                json.dump(chip_config, f, indent=4)
        except Exception as e:
            print(f"Failed to save chip_design.json: {e}")


    layout = pya.Layout()
    layout.dbu = global_params['dbu_um']
    tod = get_dbu_converter(layout)

    layers = {
        'etch': layout.layer(pya.LayerInfo(1, 0, "etch")), 
        'metal': layout.layer(pya.LayerInfo(2, 0, "metal")),
        'crosshairs': layout.layer(pya.LayerInfo(3, 0, "crosshairs")), 
        'border': layout.layer(pya.LayerInfo(4, 0, "border")),
        'stem_border':  layout.layer(pya.LayerInfo(15, 0, "stem_border")) if global_params.get('enable_graphene', False) else None,
        'graphene':     layout.layer(pya.LayerInfo(16, 0, "graphene"))    if global_params.get('enable_graphene', False) else None,
    }
    
    quad_params_list = [copy.deepcopy(quad_params) for _ in range(4)]
    quad_cells_list, quad_names_list, quad_core_bboxes_dbu_list = [], ["TL", "TR", "BL", "BR"], []
    quad_crosshair_local_list = []
    for i in range(4):
        cell_obj, merged_fiducials_um, core_bbox_dbu = create_quadrant(layout, f"QUAD_{quad_names_list[i]}", quad_params_list[i], layers)
        if cell_obj is None:
            print(f"Failed to create Quadrant {quad_names_list[i]}. Aborting."); return
        quad_cells_list.append(cell_obj); quad_core_bboxes_dbu_list.append(core_bbox_dbu)
        quad_crosshair_local_list.append(_compute_crosshair_positions_from_fiducials(merged_fiducials_um, quad_params_list[i]))

    if mask_layer == 2:
        # GOLD export: verify every quadrant lands exactly where ETCH puts it.
        _verify_mask_alignment(quad_core_bboxes_dbu_list[0] if quad_core_bboxes_dbu_list else None,
                               quad_params, global_params)

    top_cell = layout.create_cell("TOP")
    max_w = max((b.width() for b in quad_core_bboxes_dbu_list if b and not b.empty()), default=0)
    max_h = max((b.height() for b in quad_core_bboxes_dbu_list if b and not b.empty()), default=0)
    gap_x, gap_y = global_params['quadrant_gap_x'], global_params['quadrant_gap_y']
    origins_x = [-(max_w * layout.dbu + gap_x / 2.), gap_x / 2.]
    origins_y = [gap_y / 2., -(max_h * layout.dbu + gap_y / 2.)]
    positions, quad_bboxes_in_top_dbu_list = [(0,0), (1,0), (0,1), (1,1)], []
    full_crosshair_positions = {}
    for i in range(4):
        bbox = quad_core_bboxes_dbu_list[i]
        if bbox is None or bbox.empty(): continue
        dx, dy = origins_x[positions[i][0]] - (bbox.left * layout.dbu), origins_y[positions[i][1]] - (bbox.bottom * layout.dbu)
        inst = top_cell.insert(pya.CellInstArray(quad_cells_list[i].cell_index(), pya.Trans(pya.Trans.R0, tod(dx), tod(dy))))
        quad_bboxes_in_top_dbu_list.append(inst.bbox())
        local_pos = quad_crosshair_local_list[i] if i < len(quad_crosshair_local_list) else {}
        qname = quad_names_list[i]
        if qname in local_pos:
            lx, ly = local_pos[qname]
            full_crosshair_positions[qname] = (lx + dx, ly + dy)

    if global_params.get('enable_quadrant_sample_names', False):
        base, suffixes = global_params.get('sample_name_base', "Sample"), global_params.get('sample_name_suffix_list', ["_A", "_B", "_C", "_D"])
        font_h, font_w = global_params.get('sample_name_font_height_um', 50.0), global_params.get('sample_name_font_width_um', 5.0)
        # Match main sample-name KLayout proportions (text_width is stroke for stick
        # labels — using it here squashes KLayout font horizontally).
        gtt_scale = 0.42
        gtt_h = font_h * gtt_scale
        gtt_w = font_w * gtt_scale
        gtt_gap = max(gtt_h * 0.35, 100.0)
        name_layer_nums = _normalize_gds_layer_list(quad_params.get('sample_name_gds_layers'), [1])
        text_layers = [layout.layer(pya.LayerInfo(int(n), 0)) for n in name_layer_nums]
        for i, q_name in enumerate(quad_names_list):
            if i >= len(quad_bboxes_in_top_dbu_list) or quad_bboxes_in_top_dbu_list[i].empty(): continue
            bbox = quad_bboxes_in_top_dbu_list[i]
            name = base + suffixes[i]
            x_center_um = (bbox.center().x * layout.dbu) + global_params['sample_name_offset_x_um']
            if q_name in ["TL", "TR"]:
                y_target_um = (bbox.top * layout.dbu) + global_params['sample_name_offset_y_um']
                anchor = "bottom-center"
            else:
                y_target_um = (bbox.bottom * layout.dbu) - global_params['sample_name_offset_y_um']
                anchor = "top-center"
            for n, text_layer in zip(name_layer_nums, text_layers):
                create_text(x_center_um, y_target_um, name, top_cell, text_layer, font_h,
                            anchor=anchor, use_klayout_font=True, text_width=font_w)
            if mask_layer == 2 and global_params.get('enable_gtt_label', True):
                gtt_label = _format_gtt_label(global_params.get('gtt_number', 1))
                gtt_layer = layout.layer(pya.LayerInfo(int(mask_layer), 0))
                if q_name in ["TL", "TR"]:
                    y_gtt = y_target_um - gtt_gap
                else:
                    y_gtt = y_target_um - font_h - gtt_gap
                create_text(x_center_um, y_gtt, gtt_label, top_cell, gtt_layer, gtt_h,
                            anchor="top-center", use_klayout_font=True, text_width=gtt_w)
            
    bound_size, bound_w = global_params['boundary_size_um'], global_params['boundary_width_um']
    if bound_size > 0 and bound_w > 0:
        half_b = bound_size / 2.0
        pts = [pya.Point(tod(-half_b), tod(-half_b)), pya.Point(tod(half_b), tod(-half_b)), pya.Point(tod(half_b), tod(half_b)), pya.Point(tod(-half_b), tod(half_b)), pya.Point(tod(-half_b), tod(-half_b))]
        top_cell.shapes(layers['border']).insert(pya.Path(pts, tod(bound_w)))
        
    tri_w, tri_h = global_params['triangle_width_um'], global_params['triangle_height_um']
    if tri_w > 0 and tri_h > 0:
        layer_info = global_params['triangle_layer_gds']
        tri_layer = layout.layer(pya.LayerInfo(int(layer_info[0]), int(layer_info[1])))
        half_b = global_params['boundary_size_um'] / 2.0
        base_center_x, base_y_ref = 0.0, -half_b
        tip = pya.Point(base_center_x + global_params['triangle_offset_x_um'], base_y_ref + global_params['triangle_offset_y_um'])
        base_y = tip.y + tri_h
        pts = [pya.Point(tod(p.x), tod(p.y)) for p in [tip, pya.Point(tip.x - tri_w/2.0, base_y), pya.Point(tip.x + tri_w/2.0, base_y)]]
        poly = pya.SimplePolygon(pts)
        if not poly.is_empty(): top_cell.shapes(tri_layer).insert(poly)

    sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', global_params.get('sample_name_base', "chip")).replace(" ", "_")
    if mask_layer == 2 and global_params.get('enable_gtt_label', True):
        sanitized_name = _append_gtt_suffix(sanitized_name, global_params.get('gtt_number', 1))
    if mask_layer is not None:
        suffix = mask_suffix or f"L{mask_layer}"
        gds_file, dxf_file = None, f"{sanitized_name}_{suffix}.dxf"
    else:
        gds_file = None if full_dxf_only else f"{sanitized_name}_FULL.gds"
        dxf_file = f"{sanitized_name}_FULL.dxf"

    export_dir = _resolve_export_dir(mask_layer, global_params, output_dir)
    if gds_file is not None:
        gds_file = _export_path(export_dir, gds_file)
    if dxf_file is not None:
        dxf_file = _export_path(export_dir, dxf_file)

    effective_3d_full = copy.deepcopy(PARAMS_3D)
    if params_3d:
        effective_3d_full.update(params_3d)
    if effective_3d_full.get('merge_layer5_into_layer2', False):
        if _merge_gds_layer_into(layout, 5, 2):
            print("Merged layer 5 into layer 2 for full-chip outputs (GDS + 2D DXF).")

    if mask_layer is not None:
        # Strip everything that is not the mask layer so the DXF contains a
        # single fabrication layer (etch or gold) and nothing else.
        for li in list(layout.layer_indexes()):
            try:
                if int(layout.get_info(li).layer) != mask_layer:
                    layout.delete_layer(li)
            except Exception:
                pass

    if gds_file is not None:
        try:
            save_opts = pya.SaveLayoutOptions(); save_opts.gds2_write_timestamps = False; save_opts.gds2_lib_name = "LIB"
            layout.write(gds_file, save_opts); print(f"Saved GDS: {gds_file}")
        except Exception as e: print(f"GDS Save Error: {e}")
    # Flatten all cell hierarchy so DXF has every shape directly accessible in AutoCAD
    # (no REFEDIT required — every layer is selectable in the drawing immediately)
    try: top_cell.flatten(True)
    except Exception as e: print(f"Warning: flatten failed: {e}")
    try:
        save_opts = pya.SaveLayoutOptions(); save_opts.format = "DXF"
        save_opts.dxf_polygon_mode = 0
        save_opts.keep_instances = False
        layout.write(dxf_file, save_opts); print(f"Saved DXF: {dxf_file}")
    except Exception as e: print(f"DXF Save Error: {e}")

# ===================================================================
# 3D DXF Export (Single-version only)
# ===================================================================
def _polygon_to_um_pts(polygon, dbu):
    pts = [(p.x * dbu, p.y * dbu) for p in polygon.each_point_hull()]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts

def _extrude_faces(points_um, z_bottom, z_top):
    """Return 3DFACE-friendly faces (quads where possible, triangles otherwise) for an
    extruded convex polygon. Emitting quads for each trapezoid cap and each side wall
    avoids the diagonal triangulation seams that AutoCAD would otherwise draw in wireframe."""
    faces = []
    n = len(points_um)
    if n < 3 or z_top == z_bottom:
        return faces
    zt, zb = (max(z_top, z_bottom), min(z_top, z_bottom))

    if n == 3:
        faces.append([(points_um[0][0], points_um[0][1], zt),
                      (points_um[1][0], points_um[1][1], zt),
                      (points_um[2][0], points_um[2][1], zt)])
        faces.append([(points_um[0][0], points_um[0][1], zb),
                      (points_um[2][0], points_um[2][1], zb),
                      (points_um[1][0], points_um[1][1], zb)])
    elif n == 4:
        faces.append([(points_um[0][0], points_um[0][1], zt),
                      (points_um[1][0], points_um[1][1], zt),
                      (points_um[2][0], points_um[2][1], zt),
                      (points_um[3][0], points_um[3][1], zt)])
        faces.append([(points_um[0][0], points_um[0][1], zb),
                      (points_um[3][0], points_um[3][1], zb),
                      (points_um[2][0], points_um[2][1], zb),
                      (points_um[1][0], points_um[1][1], zb)])
    else:
        # Fan-triangulate caps only as a fallback (decompose_trapezoids should keep this branch unused).
        for i in range(1, n - 1):
            faces.append([(points_um[0][0], points_um[0][1], zt),
                          (points_um[i][0], points_um[i][1], zt),
                          (points_um[i + 1][0], points_um[i + 1][1], zt)])
            faces.append([(points_um[0][0], points_um[0][1], zb),
                          (points_um[i + 1][0], points_um[i + 1][1], zb),
                          (points_um[i][0], points_um[i][1], zb)])

    for i in range(n):
        j = (i + 1) % n
        a, b = points_um[i], points_um[j]
        faces.append([(a[0], a[1], zb), (b[0], b[1], zb), (b[0], b[1], zt), (a[0], a[1], zt)])
    return faces

def _iter_decomposed_polys(region):
    """Yield convex polygons (trapezoids) from a region. Handles both list and Region return types."""
    try:
        decomp = region.decompose_trapezoids(0)
    except Exception:
        decomp = region
    if hasattr(decomp, 'each'):
        for p in decomp.each():
            yield p
    else:
        try:
            for p in decomp:
                yield p
        except TypeError:
            for p in region.each():
                yield p

def _region_to_3d_faces(region, z_bottom, z_top, dbu):
    """Decompose a region into trapezoids and return a list of 3DFACE-ready faces.
    Each face is a list of 3 or 4 (x, y, z) tuples (quads preferred, no artificial diagonals)."""
    faces = []
    if region is None or region.is_empty() or z_bottom == z_top:
        return faces
    for poly in _iter_decomposed_polys(region):
        pts = _polygon_to_um_pts(poly, dbu)
        if len(pts) >= 3:
            faces.extend(_extrude_faces(pts, z_bottom, z_top))
    return faces

def _merge_gds_layer_into(layout, src_gds, dst_gds, datatype=0):
    """Move every shape on GDS layer `src_gds` to `dst_gds` across the whole layout, then delete the source layer."""
    src_idx = None
    dst_idx = None
    for li in layout.layer_indexes():
        info = layout.get_info(li)
        if info.datatype != datatype:
            continue
        if info.layer == src_gds and src_idx is None:
            src_idx = li
        elif info.layer == dst_gds and dst_idx is None:
            dst_idx = li
    if src_idx is None:
        return False
    if dst_idx is None:
        dst_idx = layout.layer(pya.LayerInfo(dst_gds, datatype))
    try:
        layout.move_layer(src_idx, dst_idx)
    except Exception:
        for c in layout.each_cell():
            src_shapes = c.shapes(src_idx)
            if src_shapes.size() == 0:
                continue
            for shape in list(src_shapes.each()):
                c.shapes(dst_idx).insert(shape)
            src_shapes.clear()
    try:
        layout.delete_layer(src_idx)
    except Exception:
        try:
            for c in layout.each_cell():
                c.shapes(src_idx).clear()
        except Exception:
            pass
    return True

def _region_from_gds_layer(layout, cell, gds_layer, datatype=0):
    """Collect a merged Region of all shapes on the given GDS layer/datatype, walking the cell hierarchy recursively.
    Works regardless of whether `cell` has been flattened."""
    region = pya.Region()
    for li in layout.layer_indexes():
        info = layout.get_info(li)
        if info.layer == gds_layer and info.datatype == datatype:
            try:
                region.insert(layout.begin_shapes(cell, li))
            except Exception:
                region.insert(cell.shapes(li))
    region.merge()
    return region

_DXF_3D_LAYER_COLORS = {
    'BOX_MINUS_L1': 8,
    'LAYER2': 3,
    'LAYER5': 5,
    'GRAPHENE': 6,
}

def _write_3d_dxf_ezdxf(filename, faces_by_layer):
    """Preferred path: use the ezdxf library, which produces DXFs that AutoCAD always accepts.
    Each triangle is written as a 3DFACE entity on its design layer (max compatibility with all AutoCAD versions)."""
    import ezdxf
    doc = ezdxf.new(dxfversion='R2000')
    msp = doc.modelspace()

    for name in faces_by_layer.keys():
        color = _DXF_3D_LAYER_COLORS.get(name, 7)
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)

    for layer_name, faces in faces_by_layer.items():
        attr = {'layer': layer_name}
        for face in faces:
            if len(face) == 4:
                pts = [face[0], face[1], face[2], face[3]]
            elif len(face) == 3:
                pts = [face[0], face[1], face[2], face[2]]
            else:
                continue
            msp.add_3dface(pts, dxfattribs=attr)
    doc.saveas(filename)

def _write_3d_dxf_fallback(filename, faces_by_layer):
    """Hand-rolled AutoCAD R12 (AC1009) DXF writer used only when ezdxf is not installed.
    Writes every triangle as its own 3DFACE entity and includes all required sections
    (HEADER, LTYPE table, LAYER table, empty BLOCKS section, ENTITIES) so AutoCAD can load it."""
    minx = miny = minz = None
    maxx = maxy = maxz = None
    for faces in faces_by_layer.values():
        for face in faces:
            for x, y, z in face:
                if minx is None or x < minx: minx = x
                if miny is None or y < miny: miny = y
                if minz is None or z < minz: minz = z
                if maxx is None or x > maxx: maxx = x
                if maxy is None or y > maxy: maxy = y
                if maxz is None or z > maxz: maxz = z
    if minx is None:
        minx = miny = minz = 0.0
        maxx = maxy = maxz = 1.0

    def _pair(code, value):
        return "{}\n{}\n".format(code, value)
    def _fpair(code, value):
        return "{}\n{:.6f}\n".format(code, float(value))

    with open(filename, 'w') as f:
        f.write(_pair(0, "SECTION")); f.write(_pair(2, "HEADER"))
        f.write(_pair(9, "$ACADVER")); f.write(_pair(1, "AC1009"))
        f.write(_pair(9, "$INSBASE")); f.write(_fpair(10, 0.0)); f.write(_fpair(20, 0.0)); f.write(_fpair(30, 0.0))
        f.write(_pair(9, "$EXTMIN")); f.write(_fpair(10, minx)); f.write(_fpair(20, miny)); f.write(_fpair(30, minz))
        f.write(_pair(9, "$EXTMAX")); f.write(_fpair(10, maxx)); f.write(_fpair(20, maxy)); f.write(_fpair(30, maxz))
        f.write(_pair(9, "$LIMMIN")); f.write(_fpair(10, minx)); f.write(_fpair(20, miny))
        f.write(_pair(9, "$LIMMAX")); f.write(_fpair(10, maxx)); f.write(_fpair(20, maxy))
        f.write(_pair(0, "ENDSEC"))

        f.write(_pair(0, "SECTION")); f.write(_pair(2, "TABLES"))
        f.write(_pair(0, "TABLE")); f.write(_pair(2, "LTYPE")); f.write(_pair(70, 1))
        f.write(_pair(0, "LTYPE")); f.write(_pair(2, "CONTINUOUS")); f.write(_pair(70, 0))
        f.write(_pair(3, "Solid line")); f.write(_pair(72, 65)); f.write(_pair(73, 0)); f.write(_fpair(40, 0.0))
        f.write(_pair(0, "ENDTAB"))
        f.write(_pair(0, "TABLE")); f.write(_pair(2, "LAYER")); f.write(_pair(70, len(faces_by_layer) + 1))
        f.write(_pair(0, "LAYER")); f.write(_pair(2, "0")); f.write(_pair(70, 0)); f.write(_pair(62, 7)); f.write(_pair(6, "CONTINUOUS"))
        for name in faces_by_layer.keys():
            color = _DXF_3D_LAYER_COLORS.get(name, 7)
            f.write(_pair(0, "LAYER")); f.write(_pair(2, name)); f.write(_pair(70, 0))
            f.write(_pair(62, color)); f.write(_pair(6, "CONTINUOUS"))
        f.write(_pair(0, "ENDTAB"))
        f.write(_pair(0, "ENDSEC"))

        f.write(_pair(0, "SECTION")); f.write(_pair(2, "BLOCKS")); f.write(_pair(0, "ENDSEC"))

        f.write(_pair(0, "SECTION")); f.write(_pair(2, "ENTITIES"))
        for layer_name, faces in faces_by_layer.items():
            for face in faces:
                if len(face) == 4:
                    v4 = face[3]
                elif len(face) == 3:
                    v4 = face[2]
                else:
                    continue
                f.write(_pair(0, "3DFACE")); f.write(_pair(8, layer_name))
                f.write(_fpair(10, face[0][0])); f.write(_fpair(20, face[0][1])); f.write(_fpair(30, face[0][2]))
                f.write(_fpair(11, face[1][0])); f.write(_fpair(21, face[1][1])); f.write(_fpair(31, face[1][2]))
                f.write(_fpair(12, face[2][0])); f.write(_fpair(22, face[2][1])); f.write(_fpair(32, face[2][2]))
                f.write(_fpair(13, v4[0])); f.write(_fpair(23, v4[1])); f.write(_fpair(33, v4[2]))
        f.write(_pair(0, "ENDSEC"))
        f.write(_pair(0, "EOF"))

def _write_3d_dxf(filename, faces_by_layer):
    """Write a 3D DXF. Uses ezdxf when available (AutoCAD always accepts the result);
    otherwise falls back to a hand-rolled R12 writer."""
    try:
        _write_3d_dxf_ezdxf(filename, faces_by_layer)
        return
    except ImportError:
        print("ezdxf not installed; using built-in R12 DXF writer. Install with: pip install ezdxf")
    except Exception as e:
        print(f"ezdxf write failed ({e}); falling back to built-in R12 writer.")
    _write_3d_dxf_fallback(filename, faces_by_layer)

def create_3d_dxf_single(layout, top_cell, output_path, params_3d):
    """
    Build a 3D DXF of the single-quadrant design.

    Geometry rules (per user spec):
      - Rectangular box around the design, extruded DOWN by `box_extrude_down_um`.
      - Layer 1 extruded DOWN by `layer1_extrude_down_um`, then SUBTRACTED from the box.
      - Layer 2 extruded UP by `layer2_extrude_up_um`, then translated by (0, 0, layer2_z_shift_um).
      - Layer 5 extruded UP by `layer5_extrude_up_um` from z=0.
      - Graphene (layer 16) extruded UP by `graphene_extrude_up_um` from z=0.
    """
    dbu = layout.dbu if layout.dbu > 0 else 0.001
    bbox_dbu = top_cell.bbox()
    if bbox_dbu.empty():
        print("3D DXF: design bbox is empty, skipping.")
        return

    region_l1 = _region_from_gds_layer(layout, top_cell, 1)
    region_l2 = _region_from_gds_layer(layout, top_cell, 2)
    region_l5 = _region_from_gds_layer(layout, top_cell, 5)
    region_l16 = _region_from_gds_layer(layout, top_cell, 16)

    box_region = pya.Region(pya.Box(bbox_dbu.left, bbox_dbu.bottom, bbox_dbu.right, bbox_dbu.top))
    try:
        box_minus_l1 = box_region - region_l1
    except Exception:
        box_minus_l1 = pya.Region(box_region)

    z_box_bottom = -float(params_3d.get('box_extrude_down_um', 30.0))
    z_l1_bottom = -float(params_3d.get('layer1_extrude_down_um', 3.0))

    # Build (box - layer1) as two vertical slabs so that AutoCAD sees a clean solid:
    #   - z in [z_box_bottom, z_l1_bottom]: full rectangular box (slab below the trench floor)
    #   - z in [z_l1_bottom, 0]: box with the layer-1 trenches carved away
    faces_box = []
    faces_box.extend(_region_to_3d_faces(box_region, z_box_bottom, z_l1_bottom, dbu))
    faces_box.extend(_region_to_3d_faces(box_minus_l1, z_l1_bottom, 0.0, dbu))

    l2_up = float(params_3d.get('layer2_extrude_up_um', 1.5))
    l2_shift = float(params_3d.get('layer2_z_shift_um', -3.0))
    faces_l2 = _region_to_3d_faces(region_l2, l2_shift, l2_shift + l2_up, dbu)

    l5_up = float(params_3d.get('layer5_extrude_up_um', 1.5))
    faces_l5 = _region_to_3d_faces(region_l5, 0.0, l5_up, dbu)

    graphene_up = float(params_3d.get('graphene_extrude_up_um', 0.5))
    faces_graphene = _region_to_3d_faces(region_l16, 0.0, graphene_up, dbu)

    faces_by_layer = {
        'BOX_MINUS_L1': faces_box,
        'LAYER2': faces_l2,
        'LAYER5': faces_l5,
        'GRAPHENE': faces_graphene,
    }
    faces_by_layer = {k: v for k, v in faces_by_layer.items() if v}
    if not faces_by_layer:
        print("3D DXF: nothing to write.")
        return

    try:
        _write_3d_dxf(output_path, faces_by_layer)
        total = sum(len(v) for v in faces_by_layer.values())
        print(f"Saved 3D DXF: {output_path}  ({total} 3D faces across {len(faces_by_layer)} layers)")
    except Exception as e:
        print(f"3D DXF Save Error: {e}")


def create_single_quadrant_chip(global_params=None, quad_params=None, output_path_base=None, params_3d=None,
                                output_dir=None):
    if global_params is None: global_params = GLOBAL_PARAMS
    if quad_params is None: quad_params = DEFAULT_QUADRANT_PARAMS

    layout = pya.Layout()
    SINGLE_QUAD_PARAMS = {
        'dbu_um': 0.001, 'boundary_clearance_um': 500.0, 'boundary_width_um': 1.0, 'enable_sample_name': True,
        'sample_name_base': global_params.get('sample_name_base', 'sample'), 
        'sample_name_font_height_um': global_params.get('sample_name_font_height_um', 250.0), 
        'sample_name_font_width_um': global_params.get('sample_name_font_width_um', 200.0),
        'sample_name_offset_y_um': 300.0,
    }
    layout.dbu = SINGLE_QUAD_PARAMS['dbu_um']
    tod = get_dbu_converter(layout)
    
    layers = {
        'etch': layout.layer(pya.LayerInfo(1, 0, "etch")), 'metal': layout.layer(pya.LayerInfo(2, 0, "metal")),
        'crosshairs': layout.layer(pya.LayerInfo(3, 0, "crosshairs")), 'border': layout.layer(pya.LayerInfo(4, 0, "border")),
        'stem_border':  layout.layer(pya.LayerInfo(15, 0, "stem_border")) if global_params.get('enable_graphene', False) else None,
        'graphene':     layout.layer(pya.LayerInfo(16, 0, "graphene"))    if global_params.get('enable_graphene', False) else None,
    }
    
    single_quad_design_params = copy.deepcopy(quad_params)
    _apply_plasma_layer_count_from_global(global_params, single_quad_design_params)
    
    quad_cell, merged_fiducials_um, quad_bbox_dbu = create_quadrant(layout, "SINGLE_QUADRANT", single_quad_design_params, layers)
    if quad_cell is None or quad_bbox_dbu.empty():
        print("Failed to create the quadrant cell. Aborting."); return

    top_cell = layout.create_cell("TOP")
    center_trans = pya.Trans(-quad_bbox_dbu.center().x, -quad_bbox_dbu.center().y)
    instance = top_cell.insert(pya.CellInstArray(quad_cell.cell_index(), center_trans))
    placed_bbox_dbu = instance.bbox()
    single_crosshair_local = _compute_crosshair_positions_from_fiducials(merged_fiducials_um, single_quad_design_params)
    trans_um_x = center_trans.disp.x * layout.dbu
    trans_um_y = center_trans.disp.y * layout.dbu
    single_crosshair_top = {k: (v[0] + trans_um_x, v[1] + trans_um_y) for k, v in single_crosshair_local.items()}

    if global_params.get('enable_quadrant_sample_names', True):
        q_type = global_params.get('single_quadrant_type', 'TL')
        base_name = global_params.get('sample_name_base', "Sample")
        suffixes = global_params.get('sample_name_suffix_list', ["_A", "_B", "_C", "_D"])
        type_idx = {"TL": 0, "TR": 1, "BL": 2, "BR": 3}.get(q_type, 0)
        suffix = suffixes[type_idx] if type_idx < len(suffixes) else ""
        name = base_name + suffix

        font_h = global_params.get('sample_name_font_height_um', 500.0)
        font_w = global_params.get('sample_name_font_width_um', 250.0)
        off_x = global_params.get('sample_name_offset_x_um', 0.0)
        off_y = global_params.get('sample_name_offset_y_um', 200.0)
        name_layer_nums = _normalize_gds_layer_list(quad_params.get('sample_name_gds_layers'), [1])

        x_target_um = (placed_bbox_dbu.center().x * layout.dbu) + off_x
        if q_type in ["TL", "TR"]:
            y_target_um = (placed_bbox_dbu.top * layout.dbu) + off_y
            anchor = "bottom-center"
        else:
            y_target_um = (placed_bbox_dbu.bottom * layout.dbu) - off_y
            anchor = "top-center"

        for n in name_layer_nums:
            text_layer = layout.layer(pya.LayerInfo(int(n), 0))
            create_text(x_target_um, y_target_um, name, top_cell, text_layer, font_h, anchor=anchor,
                        use_klayout_font=True, text_width=font_w)

    clearance, bound_w = SINGLE_QUAD_PARAMS.get('boundary_clearance_um', 500.0), SINGLE_QUAD_PARAMS.get('boundary_width_um', 1.0)
    if bound_w > 0:
        # Use the full top_cell bbox (includes the sample-name text that was just added)
        # so the border always fully encloses the label, not just the quadrant.
        content_bbox_dbu = top_cell.bbox()
        if content_bbox_dbu.empty():
            content_bbox_dbu = placed_bbox_dbu
        b = content_bbox_dbu.enlarged(tod(clearance), tod(clearance))
        pts = [b.p1, pya.Point(b.p2.x, b.p1.y), b.p2, pya.Point(b.p1.x, b.p2.y), b.p1]
        top_cell.shapes(layers['border']).insert(pya.Path(pts, tod(bound_w)))
    
    if output_path_base:
        gds_file = f"{output_path_base}.gds"
        dxf_file = f"{output_path_base}.dxf"
        dxf_3d_file = f"{output_path_base}_3D.dxf"
    else:
        sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', SINGLE_QUAD_PARAMS.get('sample_name_base', "single_quad")).replace(" ", "_")
        export_dir = _resolve_export_dir(None, global_params, output_dir)
        gds_file = _export_path(export_dir, f"{sanitized_name}_SINGLE.gds")
        dxf_file = _export_path(export_dir, f"{sanitized_name}_SINGLE.dxf")
        dxf_3d_file = _export_path(export_dir, f"{sanitized_name}_SINGLE_3D.dxf")

    effective_3d = copy.deepcopy(PARAMS_3D)
    if params_3d:
        effective_3d.update(params_3d)

    # Build the 3D DXF FIRST, while layer 2 and layer 5 are still separate in the (unflattened)
    # hierarchy. The 3D extrusion recipe relies on them being distinct; merging them in 3D
    # yields the wrong shape.
    if effective_3d.get('enable_3d_dxf', True):
        try:
            create_3d_dxf_single(layout, top_cell, dxf_3d_file, effective_3d)
        except Exception as e:
            print(f"3D DXF build error: {e}")

    # Merge is a 2D-only operation: apply AFTER the 3D DXF has been written, BEFORE any 2D save.
    if effective_3d.get('merge_layer5_into_layer2', False):
        if _merge_gds_layer_into(layout, 5, 2):
            print("Merged layer 5 into layer 2 for 2D outputs (GDS + 2D DXF). 3D DXF is unaffected.")

    _print_crosshair_positions("SINGLE", single_crosshair_top)

    try:
        save_opts = pya.SaveLayoutOptions(); save_opts.gds2_write_timestamps = False; save_opts.gds2_lib_name = "LIB"
        layout.write(gds_file, save_opts); print(f"Saved GDS: {gds_file}")
    except Exception as e: print(f"GDS Save Error: {e}")
    # Flatten all cell hierarchy so DXF has every shape directly accessible in AutoCAD
    # (no REFEDIT required — every layer is selectable in the drawing immediately)
    try: top_cell.flatten(True)
    except Exception as e: print(f"Warning: flatten failed: {e}")
    try:
        save_opts = pya.SaveLayoutOptions(); save_opts.format = "DXF"
        save_opts.dxf_polygon_mode = 0
        save_opts.keep_instances = False
        layout.write(dxf_file, save_opts); print(f"Saved DXF: {dxf_file}")
    except Exception as e: print(f"DXF Save Error: {e}")


def export_single_quadrant(
    output_path_base,
    sample_name_base,
    *,
    stem_marker_strip_length_um=None,
    stem_marker_strip_width_um=None,
    stem_marker_strip_spacing_um=None,
    stem_marker_lengths_left=None,
    stem_marker_lengths_right=None,
    params_3d=None,
):
    """
    Programmatic export for the "single quadrant" design.

    - output_path_base: full path to write to (without extension, will produce .gds and .dxf).
    - sample_name_base: title text (will be sanitized for filenames by caller if desired)
    - stem_marker_*: override strip geometry (um)
    - stem_marker_lengths_left/right: per-contact stem array coverages (um)
    """
    if not output_path_base:
        raise ValueError("output_path_base is required")
    if not sample_name_base:
        sample_name_base = "sample"

    global_params = copy.deepcopy(GLOBAL_PARAMS)
    global_params["sample_name_base"] = str(sample_name_base)
    
    quad_params = copy.deepcopy(DEFAULT_QUADRANT_PARAMS)

    if stem_marker_strip_length_um is not None:
        quad_params['stem_marker_strip_length_um'] = float(stem_marker_strip_length_um)
    if stem_marker_strip_width_um is not None:
        quad_params['stem_marker_strip_width_um'] = float(stem_marker_strip_width_um)
    if stem_marker_strip_spacing_um is not None:
        quad_params['stem_marker_strip_spacing_um'] = float(stem_marker_strip_spacing_um)

    if stem_marker_lengths_left is not None:
        quad_params['stem_marker_lengths_left'] = list(stem_marker_lengths_left)
    if stem_marker_lengths_right is not None:
        quad_params['stem_marker_lengths_right'] = list(stem_marker_lengths_right)

    create_single_quadrant_chip(global_params, quad_params, output_path_base, params_3d=params_3d)


# ===================================================================
# Graphical User Interface (GUI) & Main Execution
# ===================================================================
if IN_KLAYOUT:
    QDialog = pya.QDialog
    QVBoxLayout = pya.QVBoxLayout
    QTabWidget = pya.QTabWidget
    QWidget = pya.QWidget
    QFormLayout = pya.QFormLayout
    QScrollArea = pya.QScrollArea
    QTableWidget = pya.QTableWidget
    QTableWidgetItem = pya.QTableWidgetItem
    QHBoxLayout = pya.QHBoxLayout
    QPushButton = pya.QPushButton
    QCheckBox = pya.QCheckBox
    QLineEdit = pya.QLineEdit
    QTextEdit = pya.QTextEdit
    QLabel = pya.QLabel
    QSplitter = pya.QSplitter
    QGroupBox = pya.QGroupBox
    QFrame = pya.QFrame
    QComboBox = pya.QComboBox
    QStackedWidget = pya.QStackedWidget
    QFileDialog = pya.QFileDialog
    QSlider = pya.QSlider
    QTreeWidget = pya.QTreeWidget
    QTreeWidgetItem = pya.QTreeWidgetItem
    QMessageBox = pya.QMessageBox
    QHeaderView = pya.QHeaderView
    QImage = pya.QImage
    QDateEdit = pya.QDateEdit
    QDate = pya.QDate

    QPainter = pya.QPainter
    QColor = pya.QColor
    QBrush = pya.QBrush
    QPen = pya.QPen
    QPolygonF = pya.QPolygonF
    QPainterPath = pya.QPainterPath
    QPointF = pya.QPointF
    QPixmap = pya.QPixmap
    QCursor = getattr(pya, 'QCursor', None)
    QTimer = pya.QTimer
    _Qt = pya.Qt
    _get_app = lambda: pya.Application.instance()
    _get_main_win = lambda app: app.main_window() if app else None
else:
    from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QTabWidget, QWidget, 
                                 QFormLayout, QScrollArea, QTableWidget, QTableWidgetItem, 
                                 QHBoxLayout, QPushButton, QCheckBox, QLineEdit, QTextEdit, QLabel,
                                 QSplitter, QGroupBox, QFrame, QComboBox, QStackedWidget, QFileDialog, QSlider, QTreeWidget, QTreeWidgetItem, QMessageBox, QHeaderView, QDateEdit)
    from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPolygonF, QPainterPath, QPixmap, QCursor, QImage
    from PyQt6.QtCore import QPointF, QTimer, Qt as _Qt, QDate
    _get_app = lambda: QApplication.instance() or QApplication(sys.argv)
    _get_main_win = lambda app: None

def _qt_enum(owner, path):
    """Resolve Qt enum across PyQt6 (nested enum classes) and pya (flat attributes).
    Example: _qt_enum(_Qt, 'Orientation.Horizontal') or _qt_enum(QPainter, 'RenderHint.Antialiasing')."""
    parts = path.split('.')
    # Try nested (PyQt6)
    cur = owner
    for part in parts:
        if hasattr(cur, part):
            cur = getattr(cur, part)
        else:
            cur = None; break
    if cur is not None and not isinstance(cur, type):
        return cur
    # Fall back to the last segment as a flat attribute on the owner (pya)
    leaf = parts[-1]
    if hasattr(owner, leaf):
        return getattr(owner, leaf)
    return None

def _connect_signal(signal, callback):
    """Connect a Qt signal across PyQt6 (.connect) and pya (callable signal)."""
    try:
        signal.connect(callback)
    except AttributeError:
        try:
            signal(callback)
        except Exception:
            pass

def _wheel_delta(event):
    try:
        return event.angleDelta().y()
    except AttributeError:
        try:
            return event.delta()
        except Exception:
            return 0

# ===================================================================
# Live 2D Preview (embedded in the GUI, updates as parameters change)
# ===================================================================
PREVIEW_LAYER_STYLE = [
    # (gds, display_name, rgb)
    (1,  "Etch (1)",           (220,  80,  80)),
    (2,  "Metal (2)",          ( 80, 120, 220)),
    (3,  "Crosshairs (3)",     (220, 200,  80)),
    (4,  "Border (4)",         (240, 240, 240)),
    (5,  "Surface Metal (5)",  ( 80, 220, 180)),
    (12, "plasma 10-10 (12)",  (240, 160,  80)),
    (13, "plasma 10-20 (13)",  (240, 120, 180)),
    (14, "plasma 10-50 (14)",  (200, 120, 240)),
    (15, "Stem Border (15)",   (120, 200, 240)),
    (16, "Graphene (16)",      (180, 180, 210)),
]
PREVIEW_PLASMA_LAYER_COLORS = [
    (240, 160,  80),  # plasma L1
    (240, 120, 180),  # plasma L2
    (200, 120, 240),  # plasma L3
]
# Painting z-order, bottom to top. Big/background layers are drawn first so
# small features (wires, stems, crosshairs) remain readable on top.
PREVIEW_LAYER_ORDER = [4, 16, 15, 1, 5, 2, 13, 3]


PREVIEW_LAYER_DEFAULT_VISIBLE_COUNT = 5  # first N layer toggles checked on startup
PREVIEW_PLASMA_EXTRA_GDS_LAYERS = (13, 14)  # L2/L3 panel rows — only when 3-plasma is on


def _pick_nice_scale_bar_um(pixels_per_um, target_px=115.0):
    """Return a ruler length in µm so the bar is ~target_px wide on screen.

    Uses 1–2–5–10 steps so the label stays readable zoomed in or zoomed out.
    `pixels_per_um` is the preview's world-to-screen scale (µm → px, magnitude).
    """
    if pixels_per_um <= 0 or not math.isfinite(pixels_per_um):
        return 1.0
    ideal_um = float(target_px) / pixels_per_um
    if ideal_um <= 0 or not math.isfinite(ideal_um):
        return 1.0
    exp = int(math.floor(math.log10(ideal_um)))
    base = 10.0 ** exp
    mant = ideal_um / base
    if mant <= 1.0:
        step = base
    elif mant <= 2.0:
        step = 2.0 * base
    elif mant <= 5.0:
        step = 5.0 * base
    else:
        step = 10.0 * base
    return max(step, 1e-9)


def _format_scale_bar_label(length_um):
    """Human-readable label for a scale-bar segment in µm."""
    try:
        L = float(length_um)
    except Exception:
        return ""
    if not math.isfinite(L) or L <= 0:
        return ""
    if L >= 1000.0:
        mm = L / 1000.0
        if mm >= 100.0:
            return "{:.0f} mm".format(mm)
        if mm >= 10.0:
            return "{:.1f} mm".format(mm)
        if mm >= 1.0:
            return "{:.2f} mm".format(mm)
        return "{:.3f} mm".format(mm)
    if L >= 100.0:
        return "{:.0f} µm".format(L)
    if L >= 10.0:
        return "{:.0f} µm".format(L)
    if L >= 1.0:
        return "{:.1f} µm".format(L)
    return "{:.2f} µm".format(L)


def _format_measure_distance_um(d_um):
    """Single distance readout for the interactive measure tool."""
    try:
        d = float(d_um)
    except Exception:
        return "—"
    if not math.isfinite(d) or d < 0:
        return "—"
    if d >= 1e6:
        return "{:.4g} m".format(d / 1e6)
    if d >= 1000.0:
        return "{:.4g} mm".format(d / 1000.0)
    if d >= 100.0:
        return "{:.1f} µm".format(d)
    if d >= 1.0:
        return "{:.2f} µm".format(d)
    return "{:.3f} µm".format(d)


def _fontmetrics_text_width(fm, text):
    """Text width from QFontMetrics across Qt / KLayout pya variants."""
    if fm is None:
        return max(8 * len(text), 8)
    for meth in ('horizontalAdvance', 'width'):
        fn = getattr(fm, meth, None)
        if callable(fn):
            try:
                return int(fn(text))
            except Exception:
                continue
    try:
        return int(fm.boundingRect(text).width())
    except Exception:
        return max(8 * len(text), 8)


def _preview_plasma_layer_configs(quad_params):
    """Return the same plasma layer config list used by QuadrantBuilder."""
    configs = []
    plasma_layer_count = int(quad_params.get('plasma_layer_count', 3))
    for i in range(1, 4):
        configs.append({
            'layer': int(quad_params.get(f'plasma_l{i}_layer', 11 + i)),
            'width': float(quad_params.get(f'plasma_l{i}_width_um', 10.0)),
            'gap': float(quad_params.get(f'plasma_l{i}_gap_um', 10.0 * i)),
        })
    return configs[:plasma_layer_count]


def _make_preview_layers(layout, global_params, quad_params=None):
    layers = {
        'etch':         layout.layer(pya.LayerInfo(1, 0, "etch")),
        'metal':        layout.layer(pya.LayerInfo(2, 0, "metal")),
        'crosshairs':   layout.layer(pya.LayerInfo(3, 0, "crosshairs")),
        'border':       layout.layer(pya.LayerInfo(4, 0, "border")),
        'stem_border':  layout.layer(pya.LayerInfo(15, 0, "stem_border")) if global_params.get('enable_graphene', False) else None,
        'graphene':     layout.layer(pya.LayerInfo(16, 0, "graphene"))    if global_params.get('enable_graphene', False) else None,
    }
    if quad_params is not None:
        for i, cfg in enumerate(_preview_plasma_layer_configs(quad_params)):
            layers[f'plasma_{i + 1}'] = layout.layer(pya.LayerInfo(cfg['layer'], 0, f"plasma {cfg['width']}-{cfg['gap']}"))
    else:
        layers.update({
            'plasma_12': layout.layer(pya.LayerInfo(12, 0, "plasma 10-10")),
            'plasma_13': layout.layer(pya.LayerInfo(13, 0, "plasma 10-20")),
            'plasma_14': layout.layer(pya.LayerInfo(14, 0, "plasma 10-50")),
        })
    return layers


def _extract_polys_from_top_cell(layout, top_cell, etch_halo_clip_um=0.0):
    """Pull every shape on every layer from `top_cell` and return (polys, bbox_um).

    When `etch_halo_clip_um` > 0, layer 1 (etch) has the region
    `metal_grown_by_etch_halo_clip_um` subtracted from it before polygons are
    extracted. This deletes the encap halo ring around every metal shape from
    the *preview geometry only* (the GDS / DXF exports stay untouched), which
    is what stops the ~1 px red fringe from bleeding out past every blue wire
    at fit view. Structural etch features — cap grids, contact-pad interiors,
    triangles, text — are unaffected because they don't sit under/around a
    matching metal polygon.
    """
    dbu = layout.dbu

    # Find the layer-1 and layer-2 indices (datatype 0) once.
    layer_etch_idx = None
    layer_metal_idx = None
    for li in layout.layer_indexes():
        info = layout.get_info(li)
        if info.datatype != 0:
            continue
        if info.layer == 1:
            layer_etch_idx = li
        elif info.layer == 2:
            layer_metal_idx = li

    metal_grown_region = None
    if etch_halo_clip_um and etch_halo_clip_um > 0 and layer_metal_idx is not None:
        try:
            metal_region = pya.Region(layout.begin_shapes(top_cell, layer_metal_idx))
            grown_dbu = int(round(float(etch_halo_clip_um) / dbu))
            if grown_dbu > 0:
                metal_grown_region = metal_region.sized(grown_dbu)
        except Exception:
            metal_grown_region = None

    polys_by_layer = {}
    for li in layout.layer_indexes():
        info = layout.get_info(li)
        if info.datatype != 0:
            continue
        gds = info.layer
        region = pya.Region(layout.begin_shapes(top_cell, li))
        if gds == 1 and metal_grown_region is not None:
            try:
                region = region - metal_grown_region
            except Exception:
                pass
        try:
            region.merge()
        except Exception:
            pass
        layer_polys = []
        for poly in region.each():
            hull = [(p.x * dbu, p.y * dbu) for p in poly.each_point_hull()]
            if len(hull) < 3:
                continue
            holes = []
            try:
                for h in range(poly.holes()):
                    hole = [(p.x * dbu, p.y * dbu) for p in poly.each_point_hole(h)]
                    if len(hole) >= 3:
                        holes.append(hole)
            except Exception:
                pass
            layer_polys.append((hull, holes))
        if layer_polys:
            polys_by_layer[gds] = layer_polys

    b = top_cell.bbox()
    if b.empty():
        bbox_um = (0.0, 0.0, 1.0, 1.0)
    else:
        bbox_um = (b.left * dbu, b.bottom * dbu, b.right * dbu, b.top * dbu)
    return polys_by_layer, bbox_um


def _build_preview_layout(global_params, quad_params):
    """Build a single-quadrant layout IN MEMORY (no file I/O) and return
    (polys_by_gds_layer, bbox_um, crosshair_pos_um). Each polygon is
    (hull_pts, [hole_pts, ...])."""
    layout = pya.Layout()
    layout.dbu = float(global_params.get('dbu_um', 0.001))
    layers = _make_preview_layers(layout, global_params)

    design_params = copy.deepcopy(quad_params)
    quad_cell, merged_fiducials_um, quad_bbox_dbu = create_quadrant(layout, "SINGLE_QUADRANT_PREVIEW", design_params, layers)
    if quad_cell is None or quad_bbox_dbu.empty():
        return {}, (0.0, 0.0, 1.0, 1.0), {}

    top_cell = layout.create_cell("PREVIEW_TOP")
    center_trans = pya.Trans(-quad_bbox_dbu.center().x, -quad_bbox_dbu.center().y)
    top_cell.insert(pya.CellInstArray(quad_cell.cell_index(), center_trans))
    local_ch = _compute_crosshair_positions_from_fiducials(merged_fiducials_um, design_params)
    trans_um_x = center_trans.disp.x * layout.dbu
    trans_um_y = center_trans.disp.y * layout.dbu
    crosshair_pos = {k: (v[0] + trans_um_x, v[1] + trans_um_y) for k, v in local_ch.items()}

    # Draw a preview-only border so the user sees the cell boundary.
    try:
        clearance_um = 500.0
        content_bbox = top_cell.bbox()
        if not content_bbox.empty() and layers.get('border') is not None:
            dbu = layout.dbu
            cl_dbu = int(round(clearance_um / dbu))
            b = content_bbox.enlarged(cl_dbu, cl_dbu)
            pts = [b.p1, pya.Point(b.p2.x, b.p1.y), b.p2, pya.Point(b.p1.x, b.p2.y), b.p1]
            top_cell.shapes(layers['border']).insert(pya.Path(pts, int(round(1.0 / dbu))))
    except Exception:
        pass

    # Halo clipping is opt-in (GUI toggle) so the default preview shows the
    # engineering-accurate etch ring around every metal shape.
    halo_clip = float(quad_params.get('_preview_etch_halo_clip_um', 0.0))
    polys_by_layer, bbox_um = _extract_polys_from_top_cell(layout, top_cell, etch_halo_clip_um=halo_clip)
    return polys_by_layer, bbox_um, crosshair_pos


def _build_full_chip_preview_layout(global_params, quad_params):
    """Build the full four-quadrant chip layout IN MEMORY (no file I/O).

    Mirrors `create_full_chip_design` but skips the file save and JSON export.
    Includes four quadrants, the outer boundary box, the central alignment
    triangle, and the quadrant sample-name labels if enabled.
    """
    layout = pya.Layout()
    layout.dbu = float(global_params.get('dbu_um', 0.001))
    tod = get_dbu_converter(layout)
    layers = _make_preview_layers(layout, global_params)

    quad_names = ["TL", "TR", "BL", "BR"]
    # All four quadrants share identical parameters in the preview, so build
    # the geometry once and instance the same cell four times (~4x faster).
    p = copy.deepcopy(quad_params)
    quad_cell, merged_fiducials_um, core_bbox = create_quadrant(layout, "QUAD_PREVIEW", p, layers)
    if quad_cell is None:
        return {}, (0.0, 0.0, 1.0, 1.0), {}
    local_ch_map = _compute_crosshair_positions_from_fiducials(merged_fiducials_um, p)
    quad_cells = [quad_cell] * 4
    quad_core_bboxes = [core_bbox] * 4
    quad_crosshair_local = [local_ch_map] * 4

    top_cell = layout.create_cell("PREVIEW_TOP_FULL")
    max_w = max((b.width() for b in quad_core_bboxes if b and not b.empty()), default=0)
    max_h = max((b.height() for b in quad_core_bboxes if b and not b.empty()), default=0)
    gap_x = float(global_params.get('quadrant_gap_x', 2300.0))
    gap_y = float(global_params.get('quadrant_gap_y', 2000.0))
    origins_x = [-(max_w * layout.dbu + gap_x / 2.0), gap_x / 2.0]
    origins_y = [gap_y / 2.0, -(max_h * layout.dbu + gap_y / 2.0)]
    positions = [(0, 0), (1, 0), (0, 1), (1, 1)]
    inst_bboxes = []
    crosshair_pos = {}
    for i in range(4):
        bbox = quad_core_bboxes[i]
        if bbox is None or bbox.empty():
            inst_bboxes.append(None)
            continue
        dx = origins_x[positions[i][0]] - (bbox.left * layout.dbu)
        dy = origins_y[positions[i][1]] - (bbox.bottom * layout.dbu)
        inst = top_cell.insert(pya.CellInstArray(
            quad_cells[i].cell_index(), pya.Trans(pya.Trans.R0, tod(dx), tod(dy))
        ))
        inst_bboxes.append(inst.bbox())
        qname = quad_names[i]
        local_map = quad_crosshair_local[i] if i < len(quad_crosshair_local) else {}
        if qname in local_map:
            lx, ly = local_map[qname]
            crosshair_pos[qname] = (lx + dx, ly + dy)

    # Outer boundary box on Layer 4
    bound_size = float(global_params.get('boundary_size_um', 0.0))
    bound_w = float(global_params.get('boundary_width_um', 0.0))
    if bound_size > 0 and bound_w > 0 and layers.get('border') is not None:
        half_b = bound_size / 2.0
        pts = [pya.Point(tod(-half_b), tod(-half_b)),
               pya.Point(tod(half_b), tod(-half_b)),
               pya.Point(tod(half_b), tod(half_b)),
               pya.Point(tod(-half_b), tod(half_b)),
               pya.Point(tod(-half_b), tod(-half_b))]
        top_cell.shapes(layers['border']).insert(pya.Path(pts, tod(bound_w)))

    # Central alignment triangle
    tri_w = float(global_params.get('triangle_width_um', 0.0))
    tri_h = float(global_params.get('triangle_height_um', 0.0))
    if tri_w > 0 and tri_h > 0:
        try:
            li = global_params.get('triangle_layer_gds', [1, 0])
            tri_layer = layout.layer(pya.LayerInfo(int(li[0]), int(li[1])))
        except Exception:
            tri_layer = layers['etch']
        half_b = bound_size / 2.0
        tip_x = 0.0 + float(global_params.get('triangle_offset_x_um', 0.0))
        tip_y = -half_b + float(global_params.get('triangle_offset_y_um', 0.0))
        base_y = tip_y + tri_h
        pts = [pya.Point(tod(tip_x), tod(tip_y)),
               pya.Point(tod(tip_x - tri_w / 2.0), tod(base_y)),
               pya.Point(tod(tip_x + tri_w / 2.0), tod(base_y))]
        try:
            top_cell.shapes(tri_layer).insert(pya.SimplePolygon(pts))
        except Exception:
            pass

    # Quadrant sample-name labels
    if global_params.get('enable_quadrant_sample_names', False):
        base = global_params.get('sample_name_base', "") or ""
        suffixes = global_params.get('sample_name_suffix_list', ["_A", "_B", "_C", "_D"])
        font_h = float(global_params.get('sample_name_font_height_um', 500.0))
        font_w = float(global_params.get('sample_name_font_width_um', 250.0))
        try:
            name_layer_nums = _normalize_gds_layer_list(quad_params.get('sample_name_gds_layers'), [1])
            text_layers = [layout.layer(pya.LayerInfo(int(n), 0)) for n in name_layer_nums]
        except Exception:
            text_layers = [layers['etch']]
        for i, q_name in enumerate(quad_names):
            inst_b = inst_bboxes[i]
            if inst_b is None or inst_b.empty():
                continue
            center_x_um = inst_b.center().x * layout.dbu + float(global_params.get('sample_name_offset_x_um', 0.0))
            name = (base + suffixes[i]) if i < len(suffixes) else base
            if q_name in ["TL", "TR"]:
                y_um = inst_b.top * layout.dbu + float(global_params.get('sample_name_offset_y_um', 0.0))
                anchor = "bottom-center"
            else:
                y_um = inst_b.bottom * layout.dbu - float(global_params.get('sample_name_offset_y_um', 0.0))
                anchor = "top-center"
            for n, text_layer in zip(name_layer_nums, text_layers):
                try:
                    create_text(center_x_um, y_um, name, top_cell, text_layer, font_h,
                                anchor=anchor, use_klayout_font=True, text_width=font_w)
                except Exception:
                    pass

    # Same opt-in halo clip as the single-quadrant preview — exports untouched.
    halo_clip = float(quad_params.get('_preview_etch_halo_clip_um', 0.0))
    polys_by_layer, bbox_um = _extract_polys_from_top_cell(layout, top_cell, etch_halo_clip_um=halo_clip)
    return polys_by_layer, bbox_um, crosshair_pos


class PreviewCanvas(QWidget):
    """Fast 2D preview with a QPixmap cache + LOD + viewport culling + AA.

    The render transform includes the current pan offset, so zooming in and
    then panning reveals geometry that was off-screen at zoom time (fixing the
    blit-only approach which only knew about the initial viewport).

    At low zoom, polygons whose on-screen extent is below a pixel threshold
    are skipped. At high zoom, polygons whose bbox doesn't intersect the
    widget viewport are skipped. Between the two, rendering stays fast even
    when layer 13 has thousands of tiny rectangles.

    Anti-aliasing is enabled so sub-pixel features (e.g. the ~1 µm encap
    halo layer 1 draws around every layer-2 metal shape at fit view) render
    as blended edges rather than full-pixel red fringes — matches KLayout /
    AutoCAD behaviour. The QPixmap cache absorbs the AA cost: each view
    change re-rasterises once and every subsequent paintEvent is a free blit.
    """
    _LOD_MIN_PX = 0.5  # cull polys smaller than this many pixels on-screen

    def __init__(self, parent=None):
        super(PreviewCanvas, self).__init__(parent)
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)
        try:
            _fp = _qt_enum(QWidget, 'FocusPolicy.StrongFocus')
            if _fp is not None:
                self.setFocusPolicy(_fp)
        except Exception:
            pass
        # Raw polygon data + per-polygon bbox (um) for fast cull decisions.
        self._polys_by_layer = {}         # {gds: [(hull_pts, [hole_pts,...])]}
        self._poly_bboxes_by_layer = {}   # {gds: [(minx, miny, maxx, maxy), ...]}
        # Pre-tessellated QPainterPaths (built once per set_data, reused every render).
        self._poly_paths_by_layer = {}    # {gds: [QPainterPath, ...]} aligned with bboxes
        self._layer_full_path = {}        # {gds: QPainterPath} all polys combined
        self._layer_bbox = {}             # {gds: (minx, miny, maxx, maxy)} union
        self._layer_min_extent = {}       # {gds: min over polys of max(w, h)} for LOD shortcut
        self._layer_min_narrow = {}       # {gds: min over polys of min(w, h)} for stroke shortcut
        self._layer_colors = {gds: rgb for (gds, _, rgb) in PREVIEW_LAYER_STYLE}
        self._layer_visible = {
            gds: (i < PREVIEW_LAYER_DEFAULT_VISIBLE_COUNT)
            for i, (gds, _, _) in enumerate(PREVIEW_LAYER_STYLE)
        }
        self._content_bbox_um = (0.0, 0.0, 1.0, 1.0)
        self._user_scale = 1.0
        self._user_offset = [0.0, 0.0]
        self._last_mouse = None
        self._message = "Waiting for parameters…"
        self._outline_only = False
        self._antialias = True
        self._pen_px = 1.2
        # Cache
        self._pixmap = None
        self._pixmap_key = None
        self._pixmap_view = None  # (scale, ox, oy) the pixmap was rendered at
        self._last_stats = (0, 0, 0.0)  # (drawn, culled, render_ms)
        # Deferred crisp re-render: pan/zoom blit the stale pixmap instantly,
        # then this timer triggers one full-quality render once input settles.
        self._rerender_timer = QTimer(self)
        try:
            self._rerender_timer.setSingleShot(True)
        except Exception:
            pass
        _connect_signal(self._rerender_timer.timeout, self._do_rerender)
        # Measure overlay: zoom-adaptive scale bar + cursor position in layout µm
        self._measure_overlay = True
        self._cursor_um = None  # (x_um, y_um) or None when pointer left widget
        # Interactive two-point distance (CAD-style). Overlay-only: never invalidates pixmap cache.
        self._measure_tool_active = False
        self._measure_phase = 1  # 1 = pick A, 2 = pick B (rubber), 3 = show result (click starts new A)
        self._measure_p1_um = None
        self._measure_p2_um = None
        self._measure_ui_btn = None  # optional checkable QPushButton to sync when tool exits
        self._measure_click_press_xy = None
        self._measure_click_threshold_px = 5.0
        self._rubber_paint_xy = None  # last position that triggered a repaint (throttle)
        # Object snap ("osnap"): pull picks onto real geometry borders so a
        # measurement reports the true edge-to-edge distance instead of
        # whatever pixel the hand happened to land on.
        self._snap_enabled = True
        self._snap_radius_px = 14.0
        self._snap_ui_btn = None
        self._snap_pt_um = None    # snapped point currently under the cursor
        self._snap_kind = None     # 'vertex' | 'edge' | None
        self._snap_seg_um = None   # ((x1, y1), (x2, y2)) edge being snapped to
        # Uniform grid over polygon bboxes, built lazily on first snap query.
        self._snap_index = None    # {(ix, iy): [(gds, poly_idx), ...]}
        self._snap_cell_um = None
        self._snap_big = []        # polys spanning too many cells to bucket

    # --- Public API ---------------------------------------------------------
    def attach_measure_ui_button(self, btn):
        """Optional checkable pushbutton to keep in sync when the tool auto-exits (Esc / new layout)."""
        self._measure_ui_btn = btn

    def attach_snap_ui_button(self, btn):
        """Optional checkable pushbutton kept in sync when snap is toggled from the canvas (S key)."""
        self._snap_ui_btn = btn

    def set_snap_enabled(self, enabled):
        self._snap_enabled = bool(enabled)
        if not self._snap_enabled:
            self._clear_snap_preview()
        btn = getattr(self, '_snap_ui_btn', None)
        if btn is not None:
            try:
                if btn.isChecked() != self._snap_enabled:
                    btn.setChecked(self._snap_enabled)
            except Exception:
                pass
        self.update()

    def set_measure_tool_active(self, active):
        self._measure_tool_active = bool(active)
        self._clear_snap_preview()
        if not self._measure_tool_active:
            self._measure_phase = 1
            self._measure_p1_um = None
            self._measure_p2_um = None
            self._measure_click_press_xy = None
            self._rubber_paint_xy = None
            btn = getattr(self, '_measure_ui_btn', None)
            if btn is not None:
                try:
                    if btn.isChecked():
                        btn.setChecked(False)
                except Exception:
                    pass
        else:
            self._measure_phase = 1
            self._measure_p1_um = None
            self._measure_p2_um = None
            self._measure_click_press_xy = None
            self._rubber_paint_xy = None
            try:
                self.setFocus()
            except Exception:
                pass
        self._apply_measure_cursor()
        self.update()

    def set_message(self, msg):
        self._message = msg
        self.update()

    @staticmethod
    def _bbox_similar(a, b, tol=0.10):
        """True when two content bboxes are close enough to keep the current view."""
        try:
            aw, ah = a[2] - a[0], a[3] - a[1]
            bw, bh = b[2] - b[0], b[3] - b[1]
            ref = max(aw, ah, bw, bh, 1e-9)
            if abs(aw - bw) > tol * ref or abs(ah - bh) > tol * ref:
                return False
            acx, acy = (a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0
            bcx, bcy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
            return abs(acx - bcx) <= tol * ref and abs(acy - bcy) <= tol * ref
        except Exception:
            return False

    def set_data(self, polys_by_layer, bbox_um):
        had_data = bool(self._polys_by_layer)
        old_bbox = self._content_bbox_um
        self._message = ""
        self._polys_by_layer = {}
        self._poly_bboxes_by_layer = {}
        self._poly_paths_by_layer = {}
        self._layer_full_path = {}
        self._layer_bbox = {}
        self._layer_min_extent = {}
        self._layer_min_narrow = {}
        fr = _qt_enum(_Qt, 'FillRule.OddEvenFill') or getattr(_Qt, 'OddEvenFill', None)
        for gds, polys in polys_by_layer.items():
            bboxes = []
            kept = []
            paths = []
            full = QPainterPath()
            if fr is not None:
                try: full.setFillRule(fr)
                except Exception: pass
            lminx = lminy = float('inf'); lmaxx = lmaxy = float('-inf')
            min_ext = float('inf'); min_narrow = float('inf')
            for hull, holes in polys:
                if len(hull) < 3:
                    continue
                xs = [p[0] for p in hull]; ys = [p[1] for p in hull]
                bminx, bminy, bmaxx, bmaxy = min(xs), min(ys), max(xs), max(ys)
                bboxes.append((bminx, bminy, bmaxx, bmaxy))
                kept.append((hull, holes))
                lminx = min(lminx, bminx); lminy = min(lminy, bminy)
                lmaxx = max(lmaxx, bmaxx); lmaxy = max(lmaxy, bmaxy)
                min_ext = min(min_ext, max(bmaxx - bminx, bmaxy - bminy))
                min_narrow = min(min_narrow, min(bmaxx - bminx, bmaxy - bminy))
                sub = QPainterPath()
                if fr is not None:
                    try: sub.setFillRule(fr)
                    except Exception: pass
                sub.moveTo(float(hull[0][0]), float(hull[0][1]))
                for x, y in hull[1:]:
                    sub.lineTo(float(x), float(y))
                sub.closeSubpath()
                for hole in holes:
                    sub.moveTo(float(hole[0][0]), float(hole[0][1]))
                    for x, y in hole[1:]:
                        sub.lineTo(float(x), float(y))
                    sub.closeSubpath()
                paths.append(sub)
                full.addPath(sub)
            self._polys_by_layer[gds] = kept
            self._poly_bboxes_by_layer[gds] = bboxes
            self._poly_paths_by_layer[gds] = paths
            if kept:
                self._layer_full_path[gds] = full
                self._layer_bbox[gds] = (lminx, lminy, lmaxx, lmaxy)
                self._layer_min_extent[gds] = min_ext
                self._layer_min_narrow[gds] = min_narrow
        self._content_bbox_um = bbox_um
        self._invalidate_cache()
        self._invalidate_snap_index()
        # Keep the user's pan/zoom across parameter tweaks when the content
        # extents barely moved; only snap back to fit on big layout changes.
        if had_data and self._bbox_similar(old_bbox, bbox_um):
            self.update()
        else:
            self.fit_to_view()
        self.set_measure_tool_active(False)

    def set_layer_visible(self, gds, visible):
        self._layer_visible[gds] = bool(visible)
        self._invalidate_cache()
        self.update()

    def set_outline_only(self, outline_only):
        self._outline_only = bool(outline_only)
        self._invalidate_cache()
        self.update()

    def set_antialias(self, antialias):
        self._antialias = bool(antialias)
        self._invalidate_cache()
        self.update()

    def set_measure_overlay(self, enabled):
        self._measure_overlay = bool(enabled)
        if not self._measure_overlay:
            self._cursor_um = None
        self.update()

    def fit_to_view(self):
        self._measure_soft_clear_picks()
        self._user_scale = 1.0
        self._user_offset = [0.0, 0.0]
        self._invalidate_cache()
        self.update()

    # --- Internals ----------------------------------------------------------
    def _invalidate_cache(self):
        self._pixmap = None
        self._pixmap_key = None
        self._pixmap_view = None

    def _can_fast_blit(self, key):
        """True when the cached pixmap differs from `key` only by pan/zoom, so
        we can reuse it as a cheap transformed blit while interacting."""
        old = self._pixmap_key
        if self._pixmap is None or old is None or self._pixmap_view is None:
            return False
        # key = (w, h, scale, ox, oy, outline, aa, vis) — ignore 2..4.
        return (old[0] == key[0] and old[1] == key[1]
                and old[5] == key[5] and old[6] == key[6] and old[7] == key[7])

    def _blit_cached(self, painter):
        """Draw the stale pixmap transformed to approximate the current view."""
        s0, ox0, oy0 = self._pixmap_view
        s1 = self._scale_for_current_view()
        if s0 <= 0 or s1 <= 0:
            painter.drawPixmap(0, 0, self._pixmap)
            return
        ox1, oy1 = self._user_offset
        w, h = self.width(), self.height()
        k = s1 / s0
        if abs(k - 1.0) < 1e-9:
            painter.drawPixmap(int(round(ox1 - ox0)), int(round(oy1 - oy0)), self._pixmap)
            return
        try:
            painter.save()
            # Smooth filtering so the transitional scaled blit never looks
            # blocky/pixelated while the crisp render is pending.
            for hint_path in ('RenderHint.SmoothPixmapTransform', 'SmoothPixmapTransform'):
                h_val = _qt_enum(QPainter, hint_path)
                if h_val is not None:
                    try:
                        painter.setRenderHint(h_val, True)
                        break
                    except Exception:
                        pass
            painter.translate(w / 2.0 + ox1, h / 2.0 + oy1)
            painter.scale(k, k)
            painter.translate(-(w / 2.0 + ox0), -(h / 2.0 + oy0))
            painter.drawPixmap(0, 0, self._pixmap)
        finally:
            try:
                painter.restore()
            except Exception:
                pass

    def _schedule_rerender(self, delay_ms=60):
        try:
            self._rerender_timer.start(delay_ms)
        except Exception:
            self._do_rerender()

    def _do_rerender(self):
        try:
            self._rerender_timer.stop()
        except Exception:
            pass
        if not self._polys_by_layer:
            return
        if self._pixmap is None or self._pixmap_key != self._current_cache_key():
            self._render_pixmap()
        self.update()

    def _current_cache_key(self):
        vis = tuple(sorted(gds for gds in self._polys_by_layer if self._layer_visible.get(gds, True)))
        # Pan is now part of the render, so it's part of the cache key too.
        return (
            int(self.width()), int(self.height()),
            int(round(self._user_scale * 1000.0)),
            int(round(self._user_offset[0])),
            int(round(self._user_offset[1])),
            bool(self._outline_only),
            bool(self._antialias),
            vis,
        )

    def _scale_for_current_view(self):
        minx, miny, maxx, maxy = self._content_bbox_um
        rx, ry = maxx - minx, maxy - miny
        if rx <= 0 or ry <= 0:
            return 0.0
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return 0.0
        fit = min(w / rx, h / ry) * 0.92
        return fit * self._user_scale

    def _viewport_content_bbox(self, scale):
        """Return the (minx, miny, maxx, maxy) in content (µm) coords that is
        currently visible in the widget, given the current pan/zoom."""
        w, h = self.width(), self.height()
        minx, miny, maxx, maxy = self._content_bbox_um
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        ox, oy = self._user_offset
        # Screen px (sx, sy) = (w/2 + ox + (x - cx) * scale, h/2 + oy - (y - cy) * scale)
        # Invert for sx in [0, w], sy in [0, h]:
        inv = 1.0 / scale
        vminx = cx + (0 - w / 2.0 - ox) * inv
        vmaxx = cx + (w - w / 2.0 - ox) * inv
        vmaxy = cy - (0 - h / 2.0 - oy) * inv
        vminy = cy - (h - h / 2.0 - oy) * inv
        if vminx > vmaxx: vminx, vmaxx = vmaxx, vminx
        if vminy > vmaxy: vminy, vmaxy = vmaxy, vminy
        return (vminx, vminy, vmaxx, vmaxy)

    def _widget_px_to_content_um(self, mx, my):
        """Map widget pixel (mx, my) to chip coordinates in µm (same frame as GDS preview)."""
        scale = self._scale_for_current_view()
        if scale <= 0 or not self._polys_by_layer:
            return None
        w, h = self.width(), self.height()
        minx, miny, maxx, maxy = self._content_bbox_um
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        ox, oy = self._user_offset
        x_um = cx + (mx - w / 2.0 - ox) / scale
        y_um = cy - (my - h / 2.0 - oy) / scale
        return (x_um, y_um)

    def _content_um_to_widget_px(self, x_um, y_um):
        """Inverse of _widget_px_to_content_um: chip µm → widget pixel (center of stroke)."""
        scale = self._scale_for_current_view()
        if scale <= 0 or not self._polys_by_layer:
            return None
        w, h = self.width(), self.height()
        minx, miny, maxx, maxy = self._content_bbox_um
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        ox, oy = self._user_offset
        sx = w / 2.0 + ox + (float(x_um) - cx) * scale
        sy = h / 2.0 + oy - (float(y_um) - cy) * scale
        return (sx, sy)

    def _measure_soft_clear_picks(self):
        """Clear in-progress measurement when the view is reset; keeps tool armed if it was on."""
        if not self._measure_tool_active:
            return
        self._measure_phase = 1
        self._measure_p1_um = None
        self._measure_p2_um = None
        self._rubber_paint_xy = None
        self._clear_snap_preview()

    # --- Object snap ---------------------------------------------------------
    def _clear_snap_preview(self):
        self._snap_pt_um = None
        self._snap_kind = None
        self._snap_seg_um = None

    def _invalidate_snap_index(self):
        self._snap_index = None
        self._snap_cell_um = None
        self._snap_big = []
        self._clear_snap_preview()

    def _build_snap_index(self):
        """Bucket every polygon bbox into a uniform grid so a snap query only
        touches the handful of shapes near the cursor, not all of layer 13."""
        idx = {}
        big = []
        minx, miny, maxx, maxy = self._content_bbox_um
        span = max(maxx - minx, maxy - miny, 1e-9)
        n = 0
        for bboxes in self._poly_bboxes_by_layer.values():
            n += len(bboxes)
        # ~2 cells per polygon along each axis keeps buckets small but sparse.
        divs = max(16, min(256, int(math.sqrt(max(n, 1))) * 2))
        cell = span / float(divs)
        if not (cell > 0.0):
            cell = 1.0
        for gds, bboxes in self._poly_bboxes_by_layer.items():
            for i, (a, b, c, d) in enumerate(bboxes):
                ix0 = int(math.floor((a - minx) / cell)); ix1 = int(math.floor((c - minx) / cell))
                iy0 = int(math.floor((b - miny) / cell)); iy1 = int(math.floor((d - miny) / cell))
                if (ix1 - ix0 + 1) * (iy1 - iy0 + 1) > 1024:
                    # Chip-spanning shape (die frame, ground plane): always test it.
                    big.append((gds, i))
                    continue
                for ix in range(ix0, ix1 + 1):
                    for iy in range(iy0, iy1 + 1):
                        idx.setdefault((ix, iy), []).append((gds, i))
        self._snap_index = idx
        self._snap_cell_um = cell
        self._snap_big = big

    def _snap_candidates(self, px, py, r_um):
        """(gds, poly_idx) pairs whose bbox is within r_um of the query point."""
        if self._snap_index is None:
            self._build_snap_index()
        cell = self._snap_cell_um or 1.0
        minx, miny = self._content_bbox_um[0], self._content_bbox_um[1]
        ix0 = int(math.floor((px - r_um - minx) / cell)); ix1 = int(math.floor((px + r_um - minx) / cell))
        iy0 = int(math.floor((py - r_um - miny) / cell)); iy1 = int(math.floor((py + r_um - miny) / cell))
        seen = set()
        out = []
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                for item in self._snap_index.get((ix, iy), ()):
                    if item not in seen:
                        seen.add(item)
                        out.append(item)
        for item in self._snap_big:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    def _snap_query(self, mx, my):
        """Nearest geometry border point to widget pixel (mx, my).

        Returns (x_um, y_um, kind, seg) with kind 'vertex' or 'edge' and seg the
        ((x1, y1), (x2, y2)) edge in µm ('vertex' hits carry the adjoining edge),
        or None when nothing lies inside the snap radius. Only visible layers
        take part, so the snap always matches what is actually on screen.
        """
        if not self._snap_enabled or not self._polys_by_layer:
            return None
        scale = self._scale_for_current_view()
        if scale <= 0:
            return None
        pt = self._widget_px_to_content_um(mx, my)
        if pt is None:
            return None
        px, py = pt
        r_um = self._snap_radius_px / scale
        r2 = r_um * r_um
        # Vertices outrank edges: within this much extra slack a corner wins,
        # which is what makes clicking near a rectangle's corner feel exact.
        vertex_slack = 6.0 / scale

        best_v = None; best_v_d2 = r2
        best_e = None; best_e_d2 = r2
        budget = 40000  # hard cap on segments examined, keeps mouse-move cheap

        for gds, i in self._snap_candidates(px, py, r_um):
            if not self._layer_visible.get(gds, False):
                continue
            bboxes = self._poly_bboxes_by_layer.get(gds)
            if bboxes is not None and i < len(bboxes):
                a, b, c, d = bboxes[i]
                if px < a - r_um or px > c + r_um or py < b - r_um or py > d + r_um:
                    continue
            polys = self._polys_by_layer.get(gds)
            if not polys or i >= len(polys):
                continue
            hull, holes = polys[i]
            rings = [hull]
            if holes:
                rings.extend(holes)
            for ring in rings:
                n = len(ring)
                if n < 2:
                    continue
                budget -= n
                if budget < 0:
                    break
                for j in range(n):
                    ax, ay = ring[j]
                    bx, by = ring[(j + 1) % n]
                    dvx = ax - px; dvy = ay - py
                    dv2 = dvx * dvx + dvy * dvy
                    if dv2 < best_v_d2:
                        best_v_d2 = dv2
                        best_v = ((ax, ay), ((ax, ay), (bx, by)))
                    vx = bx - ax; vy = by - ay
                    seg2 = vx * vx + vy * vy
                    if seg2 <= 1e-18:
                        continue
                    t = ((px - ax) * vx + (py - ay) * vy) / seg2
                    if t <= 0.0 or t >= 1.0:
                        continue  # endpoints are covered by the vertex pass
                    qx = ax + t * vx; qy = ay + t * vy
                    de2 = (qx - px) ** 2 + (qy - py) ** 2
                    if de2 < best_e_d2:
                        best_e_d2 = de2
                        best_e = ((qx, qy), ((ax, ay), (bx, by)))
            if budget < 0:
                break

        if best_v is not None:
            if best_e is None or math.sqrt(best_v_d2) <= math.sqrt(best_e_d2) + vertex_slack:
                return (best_v[0][0], best_v[0][1], 'vertex', best_v[1])
        if best_e is not None:
            return (best_e[0][0], best_e[0][1], 'edge', best_e[1])
        return None

    def _update_snap_preview(self, mx, my):
        """Refresh the snap marker under the cursor. True when it changed."""
        hit = self._snap_query(mx, my) if self._measure_tool_active else None
        old_pt, old_kind = self._snap_pt_um, self._snap_kind
        if hit is None:
            self._clear_snap_preview()
        else:
            self._snap_pt_um = (hit[0], hit[1])
            self._snap_kind = hit[2]
            self._snap_seg_um = hit[3]
        return (old_pt != self._snap_pt_um) or (old_kind != self._snap_kind)

    def _measure_point_at(self, mx, my):
        """Point a click at (mx, my) should record: snapped when geometry is near."""
        hit = self._snap_query(mx, my)
        if hit is not None:
            return (hit[0], hit[1])
        return self._widget_px_to_content_um(mx, my)

    def _apply_measure_cursor(self):
        if not self._measure_tool_active:
            try:
                self.unsetCursor()
            except Exception:
                pass
            return
        if QCursor is None:
            return
        cr = _qt_enum(_Qt, 'CursorShape.CrossCursor')
        if cr is None:
            return
        try:
            self.setCursor(QCursor(cr))
        except Exception:
            pass

    def _is_left_button(self, event):
        """Detect primary (left) mouse button across Qt5/6 and pya."""
        try:
            b = event.button()
        except Exception:
            b = None
        if b is None:
            return False
        lb = _qt_enum(_Qt, 'MouseButton.LeftButton')
        if lb is not None and b == lb:
            return True
        try:
            return int(b) == 1
        except Exception:
            return False

    def _is_right_button(self, event):
        try:
            b = event.button()
        except Exception:
            return False
        rb = _qt_enum(_Qt, 'MouseButton.RightButton')
        if rb is not None and b == rb:
            return True
        try:
            return int(b) == 2
        except Exception:
            return False

    def _measure_right_click_cancel(self):
        """Abort current picks (still in measure mode)."""
        self._measure_phase = 1
        self._measure_p1_um = None
        self._measure_p2_um = None
        self._rubber_paint_xy = None
        self._clear_snap_preview()

    def _measure_handle_click_at(self, mx, my):
        pt = self._measure_point_at(mx, my)
        if pt is None:
            return
        if self._measure_phase == 1:
            self._measure_p1_um = pt
            self._measure_phase = 2
            self._rubber_paint_xy = None
        elif self._measure_phase == 2:
            self._measure_p2_um = pt
            self._measure_phase = 3
        elif self._measure_phase == 3:
            self._measure_p1_um = pt
            self._measure_p2_um = None
            self._measure_phase = 2
            self._rubber_paint_xy = None

    def _draw_interactive_measure(self, painter):
        """CAD-style two-point dimension: endpoints, dashed rubber, result with label."""
        if not self._measure_tool_active or not self._polys_by_layer:
            return
        scale = self._scale_for_current_view()
        if scale <= 0:
            return

        accent = QColor(78, 210, 255)
        accent_soft = QColor(78, 210, 255, 200)
        white = QColor(248, 250, 255)
        dim = QColor(28, 32, 44, 220)

        def draw_endpoint(wx, wy):
            r = 5
            painter.setPen(QPen(accent, 2))
            painter.setBrush(QBrush(accent_soft))
            painter.drawEllipse(int(round(wx - r)), int(round(wy - r)), 2 * r, 2 * r)
            painter.setBrush(QBrush(QColor(0, 0, 0, 0)))

        p1 = self._measure_p1_um
        p2 = self._measure_p2_um
        cur = self._cursor_um

        self._draw_snap_marker(painter)

        if p1 is None:
            return
        w1 = self._content_um_to_widget_px(p1[0], p1[1])
        if w1 is None:
            return
        draw_endpoint(w1[0], w1[1])

        if self._measure_phase == 2 and cur is not None:
            w2 = self._content_um_to_widget_px(cur[0], cur[1])
            if w2 is None:
                return
            pen = QPen(accent_soft, 1)
            try:
                pen.setCosmetic(True)
            except Exception:
                pass
            dash = _qt_enum(_Qt, 'PenStyle.DashLine')
            if dash is not None:
                try:
                    pen.setStyle(dash)
                except Exception:
                    pass
            painter.setPen(pen)
            painter.drawLine(int(round(w1[0])), int(round(w1[1])), int(round(w2[0])), int(round(w2[1])))
            dx = cur[0] - p1[0]
            dy = cur[1] - p1[1]
            d = math.hypot(dx, dy)
            hint = _format_measure_distance_um(d)
            sub = "Δx {0:.2f}  Δy {1:.2f} µm".format(dx, dy)
            lx = int(round(w2[0] + 12))
            ly = int(round(w2[1] - 28))
            self._draw_measure_label_card(painter, lx, ly, hint, sub, dim, white)

        if self._measure_phase == 3 and p2 is not None:
            w2 = self._content_um_to_widget_px(p2[0], p2[1])
            if w2 is None:
                return
            draw_endpoint(w2[0], w2[1])
            pen = QPen(accent, 2)
            try:
                pen.setCosmetic(True)
            except Exception:
                pass
            painter.setPen(pen)
            painter.drawLine(int(round(w1[0])), int(round(w1[1])), int(round(w2[0])), int(round(w2[1])))
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            d = math.hypot(dx, dy)
            main = _format_measure_distance_um(d)
            sub = "Δx {0:.2f}  Δy {1:.2f} µm".format(dx, dy)
            mx_ = (w1[0] + w2[0]) / 2.0
            my_ = (w1[1] + w2[1]) / 2.0
            vx, vy = w2[0] - w1[0], w2[1] - w1[1]
            ln = math.hypot(vx, vy)
            if ln < 1e-6:
                ox, oy = 0.0, -22.0
            else:
                ox, oy = (-vy / ln) * 18.0, (vx / ln) * 18.0
            try:
                fm = painter.fontMetrics()
                tw = max(_fontmetrics_text_width(fm, main), _fontmetrics_text_width(fm, sub)) + 14
                th = fm.height() * 2 + 10
            except Exception:
                tw, th = 120, 40
            lx = int(round(mx_ + ox - tw / 2.0))
            ly = int(round(my_ + oy - th / 2.0))
            self._draw_measure_label_card(painter, lx, ly, main, sub, dim, white, bold_main=True)

    def _draw_snap_marker(self, painter):
        """AutoCAD-style osnap glyph: square on a corner, lozenge on an edge,
        with the target edge highlighted so it is obvious what will be picked."""
        pt = self._snap_pt_um
        if pt is None:
            return
        w = self._content_um_to_widget_px(pt[0], pt[1])
        if w is None:
            return
        sx, sy = int(round(w[0])), int(round(w[1]))
        snap_col = QColor(255, 206, 84)
        seg = self._snap_seg_um
        if seg is not None:
            a = self._content_um_to_widget_px(seg[0][0], seg[0][1])
            b = self._content_um_to_widget_px(seg[1][0], seg[1][1])
            if a is not None and b is not None:
                pen = QPen(QColor(255, 206, 84, 130), 3)
                try:
                    pen.setCosmetic(True)
                except Exception:
                    pass
                painter.setPen(pen)
                painter.drawLine(int(round(a[0])), int(round(a[1])),
                                 int(round(b[0])), int(round(b[1])))
        pen = QPen(snap_col, 2)
        try:
            pen.setCosmetic(True)
        except Exception:
            pass
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        r = 6
        if self._snap_kind == 'vertex':
            painter.drawRect(sx - r, sy - r, 2 * r, 2 * r)
        else:
            # Lozenge (rotated square) marks a point along an edge.
            painter.drawLine(sx, sy - r, sx + r, sy)
            painter.drawLine(sx + r, sy, sx, sy + r)
            painter.drawLine(sx, sy + r, sx - r, sy)
            painter.drawLine(sx - r, sy, sx, sy - r)

    def _draw_measure_label_card(self, painter, x, y, main, sub, bg, fg, bold_main=False):
        """Small floating readout with a dark card behind text for contrast."""
        fm = None
        try:
            fm = painter.fontMetrics()
            tw = max(_fontmetrics_text_width(fm, main), _fontmetrics_text_width(fm, sub)) + 14
            th = fm.height() * 2 + 10
        except Exception:
            tw = max(10 * len(main), 10 * len(sub)) + 14
            th = 40
        wdg_w, wdg_h = self.width(), self.height()
        x = max(4, min(x, wdg_w - tw - 4))
        y = max(4, min(y, wdg_h - th - 4))
        painter.setPen(QPen(QColor(0, 0, 0, 0)))
        painter.setBrush(QBrush(bg))
        try:
            painter.drawRoundedRect(x, y, tw, th, 6, 6)
        except Exception:
            painter.drawRect(x, y, tw, th)
        painter.setPen(QPen(fg, 1))
        try:
            f = painter.font()
            if bold_main and fm is not None:
                try:
                    f.setBold(True)
                    painter.setFont(f)
                except Exception:
                    pass
            if fm is not None:
                painter.drawText(x + 7, y + 4 + fm.ascent(), main)
                if bold_main:
                    try:
                        f.setBold(False)
                        painter.setFont(f)
                    except Exception:
                        pass
                painter.drawText(x + 7, y + 4 + fm.ascent() + fm.height(), sub)
            else:
                painter.drawText(x + 7, y + 18, main)
                painter.drawText(x + 7, y + 34, sub)
        except Exception:
            painter.drawText(x + 7, y + 20, main)
            painter.drawText(x + 7, y + 36, sub)

    def _draw_measure_overlay(self, painter):
        """Screen-space scale bar + label (adapts to zoom via current scale)."""
        if not self._measure_overlay:
            return
        scale = self._scale_for_current_view()
        if scale <= 0:
            return
        w, h = self.width(), self.height()
        if w < 80 or h < 80:
            return

        bar_um = _pick_nice_scale_bar_um(scale)
        bar_px = bar_um * scale
        max_bar = max(40.0, w * 0.42)
        while bar_px > max_bar and bar_um > 1e-9:
            bar_um *= 0.1
            bar_px = bar_um * scale

        margin = 10
        cap = 6
        y_line = margin + 36
        x1 = float(w - margin - bar_px)
        x2 = float(w - margin)
        if x1 < margin:
            return

        col = QColor(235, 235, 245)
        dim = QColor(160, 165, 190)
        xi1, xi2 = int(round(x1)), int(round(x2))
        yi = int(round(y_line))
        painter.setPen(QPen(col, 2))
        painter.drawLine(xi1, yi, xi2, yi)
        painter.setPen(QPen(dim, 1))
        painter.drawLine(xi1, yi - cap, xi1, yi + cap)
        painter.drawLine(xi2, yi - cap, xi2, yi + cap)

        label = _format_scale_bar_label(bar_um)
        if label:
            painter.setPen(QPen(col, 1))
            try:
                tw = painter.fontMetrics().boundingRect(label).width()
            except Exception:
                tw = max(8 * len(label), 40)
            cx_text = (x1 + x2) / 2.0 - tw / 2.0
            painter.drawText(int(cx_text), int(y_line - 6), label)

    def _render_pixmap(self):
        import time
        t0 = time.time()
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0 or not self._polys_by_layer:
            return
        pix = QPixmap(w, h)
        pix.fill(QColor(0, 0, 0, 0))

        scale = self._scale_for_current_view()
        if scale <= 0:
            self._pixmap = pix
            self._pixmap_key = self._current_cache_key()
            self._pixmap_view = (scale, self._user_offset[0], self._user_offset[1])
            return

        minx, miny, maxx, maxy = self._content_bbox_um
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        ox, oy = self._user_offset
        vminx, vminy, vmaxx, vmaxy = self._viewport_content_bbox(scale)
        min_poly_um = self._LOD_MIN_PX / scale

        p = QPainter(pix)
        # Anti-aliasing (when enabled) lets sub-pixel features (e.g. the 1 µm
        # etch halo around each metal wire at fit view) blend into a soft edge
        # instead of a harsh 1-px red line. Matches what KLayout / AutoCAD do.
        for hint_path in ('RenderHint.Antialiasing', 'Antialiasing'):
            h_val = _qt_enum(QPainter, hint_path)
            if h_val is not None:
                try:
                    p.setRenderHint(h_val, bool(self._antialias))
                    break
                except Exception:
                    pass
        # Pan baked into the transform so zoom+pan both rerender correctly.
        p.translate(w / 2.0 + ox, h / 2.0 + oy)
        p.scale(scale, -scale)
        p.translate(-cx, -cy)

        no_brush = QBrush(QColor(0, 0, 0, 0))
        fr = _qt_enum(_Qt, 'FillRule.OddEvenFill') or getattr(_Qt, 'OddEvenFill', None)

        # Per-layer fill alpha. Big base layers get low alpha so small features
        # (wires, stems) on top remain readable.
        fill_alpha = {
            4:   35,  # border — background
            16: 110,  # graphene — membrane
            15:  60,  # stem border
            1:   90,  # etch — halos around metal
            5:  110,  # surface metal — G-pads, frame
            2:  155,  # metal — main wires/pads, opaque-ish
            13: 170,  # stem markers — small features on top
            3:  210,  # crosshairs — always readable
        }

        total_drawn = 0; total_culled = 0
        ordered = PREVIEW_LAYER_ORDER + [g for g in self._polys_by_layer.keys() if g not in PREVIEW_LAYER_ORDER]
        for gds in ordered:
            polys = self._polys_by_layer.get(gds)
            if not polys:
                continue
            if not self._layer_visible.get(gds, True):
                continue
            bboxes = self._poly_bboxes_by_layer.get(gds) or []

            r, g_, bl = self._layer_colors.get(gds, (200, 200, 200))
            if self._outline_only:
                p.setBrush(no_brush)
                edge = QColor(r, g_, bl, 255)
            else:
                alpha = fill_alpha.get(gds, 110)
                p.setBrush(QBrush(QColor(r, g_, bl, alpha)))
                edge = QColor(r, g_, bl, 235)
            pen = QPen(edge)
            pen.setWidthF(float(self._pen_px))
            try:
                pen.setCosmetic(True)
            except Exception:
                pen.setWidthF(self._pen_px / max(scale, 1e-9))

            # Stroking thousands of polygons with the AA cosmetic pen is by
            # far the most expensive part of the render. When a polygon's
            # narrow dimension is only a few pixels on screen, the outline
            # adds nothing but cost (and artificially bolds sub-pixel
            # features), so those go to a fill-only path instead.
            # Outline mode always strokes (the stroke IS the geometry there).
            stroke_min_px = 0.0 if self._outline_only else 3.0
            min_stroke_um = stroke_min_px / scale

            # Fast path: whole layer visible, nothing LOD-culled, and every
            # poly big enough to stroke → draw the precomputed combined path
            # in one call, no per-poly Python loop.
            lb = self._layer_bbox.get(gds)
            full_path = self._layer_full_path.get(gds)
            if (full_path is not None and lb is not None
                    and lb[0] >= vminx and lb[2] <= vmaxx
                    and lb[1] >= vminy and lb[3] <= vmaxy
                    and self._layer_min_extent.get(gds, 0.0) >= min_poly_um
                    and self._layer_min_narrow.get(gds, 0.0) >= min_stroke_um):
                p.setPen(pen)
                p.drawPath(full_path)
                total_drawn += len(polys)
                continue

            poly_paths = self._poly_paths_by_layer.get(gds) or []
            path = QPainterPath()        # stroked + filled (big polys)
            path_small = QPainterPath()  # fill-only (tiny polys, stroke invisible)
            if fr is not None:
                try:
                    path.setFillRule(fr)
                    path_small.setFillRule(fr)
                except Exception: pass

            drawn = 0; culled = 0
            for i, (hull, holes) in enumerate(polys):
                small = False
                if i < len(bboxes):
                    bminx, bminy, bmaxx, bmaxy = bboxes[i]
                    # Viewport cull
                    if bmaxx < vminx or bminx > vmaxx or bmaxy < vminy or bminy > vmaxy:
                        culled += 1
                        continue
                    # LOD cull: skip polys whose on-screen size is sub-pixel
                    if max(bmaxx - bminx, bmaxy - bminy) < min_poly_um:
                        culled += 1
                        continue
                    small = min(bmaxx - bminx, bmaxy - bminy) < min_stroke_um
                if i < len(poly_paths):
                    sub = poly_paths[i]
                else:
                    sub = QPainterPath()
                    sub.moveTo(float(hull[0][0]), float(hull[0][1]))
                    for x, y in hull[1:]:
                        sub.lineTo(float(x), float(y))
                    sub.closeSubpath()
                    if holes:
                        for hole in holes:
                            sub.moveTo(float(hole[0][0]), float(hole[0][1]))
                            for x, y in hole[1:]:
                                sub.lineTo(float(x), float(y))
                            sub.closeSubpath()
                (path_small if small else path).addPath(sub)
                drawn += 1

            if drawn > 0:
                if not path.isEmpty():
                    p.setPen(pen)
                    p.drawPath(path)
                if not path_small.isEmpty():
                    no_pen = _qt_enum(_Qt, 'PenStyle.NoPen')
                    p.setPen(QPen(no_pen) if no_pen is not None else QPen(QColor(0, 0, 0, 0)))
                    # Fill at the stroke's alpha: on features this small the
                    # outline used to dominate the pixel coverage, so this
                    # keeps the same visual weight at a fraction of the cost.
                    p.setBrush(QBrush(QColor(r, g_, bl, 235)))
                    p.drawPath(path_small)
            total_drawn += drawn
            total_culled += culled

        p.end()
        self._pixmap = pix
        self._pixmap_key = self._current_cache_key()
        self._pixmap_view = (scale, self._user_offset[0], self._user_offset[1])
        self._last_stats = (total_drawn, total_culled, (time.time() - t0) * 1000.0)

    # --- Events -------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(18, 18, 26))

        if not self._polys_by_layer:
            painter.setPen(QPen(QColor(200, 200, 200)))
            align = int(_qt_enum(_Qt, 'AlignmentFlag.AlignCenter') or 0x84)
            painter.drawText(self.rect(), align, self._message or "")
            return

        key = self._current_cache_key()
        if self._pixmap is None or self._pixmap_key != key:
            if self._can_fast_blit(key):
                # Pan/zoom in progress: instantly blit the stale pixmap with a
                # cheap transform, then re-render crisp once input settles.
                self._blit_cached(painter)
                self._schedule_rerender()
            else:
                self._render_pixmap()
                if self._pixmap is not None and not self._pixmap.isNull():
                    painter.drawPixmap(0, 0, self._pixmap)
        elif self._pixmap is not None and not self._pixmap.isNull():
            # Pan is baked into the pixmap already — blit at (0, 0).
            painter.drawPixmap(0, 0, self._pixmap)

        minx, miny, maxx, maxy = self._content_bbox_um
        rx, ry = maxx - minx, maxy - miny
        drawn, culled, dt = self._last_stats
        footer = "drag=pan  wheel=zoom  dbl-click=fit   ({:.0f} × {:.0f} µm)   drew {:d}/{:d} polys  {:.0f} ms".format(
            rx, ry, drawn, drawn + culled, dt
        )
        if self._measure_overlay and self._cursor_um is not None:
            xu, yu = self._cursor_um
            scale = self._scale_for_current_view()
            nd = 3 if scale > 40.0 else 2
            if nd == 3:
                footer += "   cursor: {:.3f}, {:.3f} µm".format(xu, yu)
            else:
                footer += "   cursor: {:.2f}, {:.2f} µm".format(xu, yu)
        if self._measure_tool_active:
            if self._measure_phase == 1:
                footer += "   MEASURE: pick point A"
            elif self._measure_phase == 2:
                footer += "   MEASURE: pick point B  (right-click = reset)"
            else:
                footer += "   MEASURE: click for new A→B  ·  Esc = exit tool"
            if not self._snap_enabled:
                footer += "  ·  snap OFF (S)"
            elif self._snap_kind == 'vertex':
                footer += "  ·  SNAP: corner"
            elif self._snap_kind == 'edge':
                footer += "  ·  SNAP: edge"
            else:
                footer += "  ·  snap on (S)"
        painter.setPen(QPen(QColor(170, 170, 200)))
        painter.drawText(8, self.height() - 8, footer)
        self._draw_measure_overlay(painter)
        self._draw_interactive_measure(painter)

    def resizeEvent(self, event):
        self._invalidate_cache()
        try:
            super(PreviewCanvas, self).resizeEvent(event)
        except Exception:
            pass

    def _event_pos(self, event):
        """Widget-local mouse position as a (float x, float y), cross-backend."""
        for attr in ('position', 'posF', 'pos'):
            fn = getattr(event, attr, None)
            if fn is None:
                continue
            try:
                pt = fn()
            except Exception:
                continue
            try:
                return float(pt.x()), float(pt.y())
            except Exception:
                try:
                    return float(pt.x), float(pt.y)
                except Exception:
                    continue
        return float(self.width()) / 2.0, float(self.height()) / 2.0

    def _sync_cursor_from_event(self, event):
        """Layout-µm under cursor (for scale overlay + measure rubber band)."""
        if not self._polys_by_layer:
            self._cursor_um = None
            self._clear_snap_preview()
            return
        need = self._measure_overlay or self._measure_tool_active
        if not need:
            self._cursor_um = None
            self._clear_snap_preview()
            return
        mx, my = self._event_pos(event)
        self._update_snap_preview(mx, my)
        # While measuring, the readout follows the snapped point so the footer
        # µm and the rubber band agree with where the click would actually land.
        if self._measure_tool_active and self._snap_pt_um is not None:
            self._cursor_um = self._snap_pt_um
        else:
            self._cursor_um = self._widget_px_to_content_um(mx, my)

    def wheelEvent(self, event):
        d = _wheel_delta(event)
        if d == 0:
            return
        factor = 1.25 if d > 0 else 1 / 1.25

        # Zoom-at-cursor: keep the content point currently under the mouse
        # pinned to the same screen pixel after scaling. Standard CAD feel.
        w, h = self.width(), self.height()
        scale_before = self._scale_for_current_view()
        if scale_before <= 0:
            self._user_scale *= factor
            self._invalidate_cache()
            self.update()
            self._sync_cursor_from_event(event)
            return

        mx, my = self._event_pos(event)
        minx, miny, maxx, maxy = self._content_bbox_um
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        ox_before, oy_before = self._user_offset

        # Content point under mouse before zoom
        x_m = cx + (mx - w / 2.0 - ox_before) / scale_before
        y_m = cy - (my - h / 2.0 - oy_before) / scale_before

        self._user_scale *= factor
        scale_after = self._scale_for_current_view()
        if scale_after <= 0:
            self._invalidate_cache()
            self.update()
            self._sync_cursor_from_event(event)
            return

        # Solve for new offset so (x_m, y_m) still projects onto (mx, my).
        self._user_offset[0] = mx - w / 2.0 - (x_m - cx) * scale_after
        self._user_offset[1] = my - h / 2.0 + (y_m - cy) * scale_after

        # Zoom renders crisp immediately — magnifying the cached pixmap looks
        # pixelated and shrinking it exposes blank surroundings. Renders are
        # cheap enough to do per wheel notch; only a pathologically heavy
        # scene falls back to a smooth-scaled blit with a fast deferred render.
        if (self._last_stats[2] if self._last_stats else 0.0) <= 250.0:
            self._do_rerender()
        else:
            self.update()
            self._schedule_rerender(50)
        self._sync_cursor_from_event(event)

    def mousePressEvent(self, event):
        mx, my = self._event_pos(event)
        self._measure_click_press_xy = (mx, my)
        if self._is_left_button(event):
            try:
                pos = event.pos()
                self._last_mouse = (pos.x(), pos.y())
            except Exception:
                self._last_mouse = (int(round(mx)), int(round(my)))
        else:
            self._last_mouse = None
        self._sync_cursor_from_event(event)

    def mouseReleaseEvent(self, event):
        try:
            if self._is_right_button(event) and self._measure_tool_active:
                self._measure_right_click_cancel()
            elif self._measure_tool_active and self._is_left_button(event) and self._measure_click_press_xy is not None:
                x0, y0 = self._measure_click_press_xy
                mx2, my2 = self._event_pos(event)
                if math.hypot(mx2 - x0, my2 - y0) <= self._measure_click_threshold_px:
                    self._measure_handle_click_at(mx2, my2)
        finally:
            self._measure_click_press_xy = None
            self._last_mouse = None
        # Snap to a crisp render right away when a pan drag ends.
        if self._polys_by_layer and (self._pixmap is None or self._pixmap_key != self._current_cache_key()):
            self._do_rerender()
        else:
            self.update()

    def mouseMoveEvent(self, event):
        self._sync_cursor_from_event(event)
        panning = self._last_mouse is not None
        if not panning:
            if self._measure_tool_active:
                mx, my = self._event_pos(event)
                rp = self._rubber_paint_xy
                # Repaint on small moves too when a snap marker is live, so the
                # marker tracks corners instead of lagging the 4 px threshold.
                thresh = 1.0 if self._snap_pt_um is not None else 16.0
                if rp is None or (mx - rp[0]) ** 2 + (my - rp[1]) ** 2 >= thresh:
                    self._rubber_paint_xy = (mx, my)
                    self.update()
            elif self._measure_overlay:
                self.update()
            return
        x, y = event.pos().x(), event.pos().y()
        dx = x - self._last_mouse[0]
        dy = y - self._last_mouse[1]
        self._user_offset[0] += dx
        self._user_offset[1] += dy
        self._last_mouse = (x, y)
        # No cache invalidation: paintEvent translates the cached pixmap for
        # an instant pan; the crisp re-render happens when the drag pauses.
        self.update()

    def leaveEvent(self, event):
        self._cursor_um = None
        self._rubber_paint_xy = None
        self._clear_snap_preview()
        try:
            super(PreviewCanvas, self).leaveEvent(event)
        except Exception:
            pass
        self.update()

    def keyPressEvent(self, event):
        key = None
        try:
            key = event.key()
        except Exception:
            key = None
        esc = _qt_enum(_Qt, 'Key.Key_Escape')
        if esc is not None and key == esc and self._measure_tool_active:
            self.set_measure_tool_active(False)
            self.update()
            return
        key_s = _qt_enum(_Qt, 'Key.Key_S')
        if key_s is not None and key == key_s and self._measure_tool_active:
            self.set_snap_enabled(not self._snap_enabled)
            return
        try:
            super(PreviewCanvas, self).keyPressEvent(event)
        except Exception:
            pass

    def mouseDoubleClickEvent(self, event):
        self.fit_to_view()



class InteractiveImageViewer(QLabel):
    def __init__(self, parent=None, app=None):
        super(InteractiveImageViewer, self).__init__(parent)
        self.app = app
    def wheelEvent(self, event):
        if self.app: self.app.an_on_zoom(event)
    def mousePressEvent(self, event):
        if self.app: self.app.an_on_drag_start(event)
    def mouseMoveEvent(self, event):
        if self.app: self.app.an_on_drag_motion(event)
    def resizeEvent(self, event):
        super(InteractiveImageViewer, self).resizeEvent(event)
        if self.app: self.app.an_refresh_image_display()


class ChipDesignGUI(QDialog):
    def __init__(self, parent=None):
        super(ChipDesignGUI, self).__init__(parent)
        self.setWindowTitle("Kinetic Design Automator")
        self.resize(1500, 860)

        saved_state = _load_gui_state()
        self._saved_state = saved_state

        effective_global = copy.deepcopy(GLOBAL_PARAMS)
        for k, v in (saved_state.get('global_params') or {}).items():
            if k in effective_global:
                effective_global[k] = v
        # Per requirement: sample name is NEVER remembered across sessions.
        effective_global['sample_name_base'] = ""

        effective_quad = copy.deepcopy(DEFAULT_QUADRANT_PARAMS)
        for k, v in (saved_state.get('quad_params') or {}).items():
            if k in effective_quad:
                effective_quad[k] = v

        effective_3d = copy.deepcopy(PARAMS_3D)
        for k, v in (saved_state.get('params_3d') or {}).items():
            if k in effective_3d:
                effective_3d[k] = v

        # Outer horizontal split: [tabs + Apply/Cancel] | [live 2D preview + layer toggles]
        self.main_layout = QVBoxLayout(self)

        orient_h = _qt_enum(_Qt, 'Orientation.Horizontal')
        self.outer_splitter = QSplitter(orient_h) if orient_h is not None else QSplitter()

        # --- LEFT: tabs + buttons ---
        self.left_pane = QWidget()
        self.left_layout = QVBoxLayout(self.left_pane)
        try:
            self.left_layout.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self.tabs = QTabWidget(self.left_pane)
        self.left_layout.addWidget(self.tabs)
        
        # Tab 1: Global Parameters
        self.tab_global = QWidget()
        self.layout_global = QFormLayout(self.tab_global)
        self.global_inputs = {}
        self.populate_form(self.layout_global, effective_global, self.global_inputs)
        
        scroll1 = QScrollArea(self.tabs)
        scroll1.setWidget(self.tab_global)
        scroll1.setWidgetResizable(True)
        self.tabs.addTab(scroll1, "Global Parameters")
        
        # Tab 2: Quadrant Parameters
        self.tab_quad = QWidget()
        self.layout_quad = QFormLayout(self.tab_quad)
        self.quad_inputs = {}
        
        
        scroll2 = QScrollArea(self.tabs)
        scroll2.setWidget(self.tab_quad)
        scroll2.setWidgetResizable(True)
        self.tabs.addTab(scroll2, "Quadrant Parameters")
        
        # Tab 3: 3D Export Parameters (single-version DXF only)
        self.tab_3d = QWidget()
        self.layout_3d = QFormLayout(self.tab_3d)
        self.params_3d_inputs = {}
        lbl_3d_info = QLabel(
            "These parameters control the 3D DXF that is written alongside the 2D DXF/GDS "
            "for the SINGLE-quadrant export.\n"
            "Extrusion recipe:\n"
            "  - Rectangular box around the design, extruded DOWN by box_extrude_down_um.\n"
            "  - Layer 1 extruded DOWN by layer1_extrude_down_um, then SUBTRACTED from the box.\n"
            "  - Layer 2 extruded UP by layer2_extrude_up_um, then shifted by (0, 0, layer2_z_shift_um).\n"
            "  - Layer 5 extruded UP by layer5_extrude_up_um.\n"
            "  - Graphene (layer 16) extruded UP by graphene_extrude_up_um.\n"
            "If 'merge_layer5_into_layer2' is checked, layer-5 shapes are moved onto layer 2\n"
            "for the 2D outputs of BOTH the full chip (*_FULL.gds/.dxf) and the single quadrant\n"
            "(*_SINGLE.gds/.dxf). The 3D DXF is built first and always keeps layer 2 and layer 5\n"
            "separate so the extrusion recipe produces the correct shape."
        )
        lbl_3d_info.setWordWrap(True)
        self.layout_3d.addRow(lbl_3d_info)
        self.populate_form(self.layout_3d, effective_3d, self.params_3d_inputs)
        scroll3d = QScrollArea(self.tabs)
        scroll3d.setWidget(self.tab_3d)
        scroll3d.setWidgetResizable(True)
        self.tabs.addTab(scroll3d, "3D Export")

        
        # Tab 2.5: Plasma Layer Edits
        self.tab_plasma = QWidget()
        self.layout_plasma_main = QVBoxLayout(self.tab_plasma)
        self.plasma_inputs = {}
        
        plasma_keys = [
            'plasma_layer_count',
            'plasma_l1_layer', 'plasma_l1_width_um', 'plasma_l1_gap_um',
            'plasma_l2_layer', 'plasma_l2_width_um', 'plasma_l2_gap_um',
            'plasma_l3_layer', 'plasma_l3_width_um', 'plasma_l3_gap_um',
            'stem_marker_strip_length_um', 'stem_marker_array_coverage_left_um', 'stem_marker_array_coverage_right_um',
            'split_stem_markers', 'stem_marker_wire_clearance_um'
        ]
        
        quad_filtered = {k:v for k,v in effective_quad.items() if k not in plasma_keys}
        plasma_filtered = {k:v for k,v in effective_quad.items() if k in plasma_keys}
        
        self.populate_form(self.layout_quad, quad_filtered, self.quad_inputs)
        
        friendly_labels = {
            'plasma_layer_count': 'Number of Plasma Layers (1-3)',
            'plasma_l1_layer': 'GDS Layer', 'plasma_l1_width_um': 'Strip Width (um)', 'plasma_l1_gap_um': 'Gap (um)',
            'plasma_l2_layer': 'GDS Layer', 'plasma_l2_width_um': 'Strip Width (um)', 'plasma_l2_gap_um': 'Gap (um)',
            'plasma_l3_layer': 'GDS Layer', 'plasma_l3_width_um': 'Strip Width (um)', 'plasma_l3_gap_um': 'Gap (um)',
            'stem_marker_strip_length_um': 'Plasma Strip Length (um)',
            'stem_marker_array_coverage_left_um': 'Default Coverage - Left (um)',
            'stem_marker_array_coverage_right_um': 'Default Coverage - Right (um)',
            'split_stem_markers': 'Split Plasma Markers (Advanced)',
            'stem_marker_wire_clearance_um': 'Wire Clearance (um)'
        }
        
        # General Settings
        form_general = QWidget()
        layout_general = QFormLayout(form_general)
        general_keys = ['stem_marker_strip_length_um', 'stem_marker_array_coverage_left_um', 'stem_marker_array_coverage_right_um', 'split_stem_markers', 'stem_marker_wire_clearance_um']
        for k in general_keys:
            if k in plasma_filtered:
                v = plasma_filtered[k]
                lbl = QLabel(f"{friendly_labels.get(k, k)}  (?)")
                if PARAMETER_HELP.get(k): lbl.setToolTip(PARAMETER_HELP.get(k))
                if isinstance(v, bool):
                    cb = QCheckBox(); cb.setChecked(v); layout_general.addRow(lbl, cb); self.plasma_inputs[k] = cb
                else:
                    le = QLineEdit(str(v)); layout_general.addRow(lbl, le); self.plasma_inputs[k] = le
        self.layout_plasma_main.addWidget(form_general)
        
        # Tabs for L1, L2, L3
        self.plasma_tabs = QTabWidget()
        for i in range(1, 4):
            tab = QWidget()
            layout_tab = QFormLayout(tab)
            for k in [f'plasma_l{i}_layer', f'plasma_l{i}_width_um', f'plasma_l{i}_gap_um']:
                if k in plasma_filtered:
                    v = plasma_filtered[k]
                    lbl = QLabel(f"{friendly_labels.get(k, k)}  (?)")
                    if PARAMETER_HELP.get(k): lbl.setToolTip(PARAMETER_HELP.get(k))
                    le = QLineEdit(str(v)); layout_tab.addRow(lbl, le); self.plasma_inputs[k] = le
            self.plasma_tabs.addTab(tab, f"Plasma Layer {i}")
        self.layout_plasma_main.addWidget(self.plasma_tabs)
        
        scroll_plasma = QScrollArea(self.tabs)
        scroll_plasma.setWidget(self.tab_plasma)
        scroll_plasma.setWidgetResizable(True)
        self.tabs.addTab(scroll_plasma, "Plasma Layer Edits")
        
        self.cb_use_per_contact_stems = QCheckBox("Use per-contact plasma coverages")
        self.cb_use_per_contact_stems.setChecked(False)
        self.layout_plasma_main.addWidget(self.cb_use_per_contact_stems)
        self.stem_table = QTableWidget(0, 4)
        self.stem_table.setHorizontalHeaderLabels(["Left Contact #", "Left Coverage (um)", "Right Contact #", "Right Coverage (um)"])
        self.stem_table.horizontalHeader().setStretchLastSection(True)
        self.layout_plasma_main.addWidget(self.stem_table)
        
        self.lbl_paste = QLabel("Bulk Paste (From Notepad): Paste a list of coverage lengths separated by newlines. 1 value per line applies to both columns. 2 values per line apply to Left and Right.")
        self.lbl_paste.setWordWrap(True)
        self.layout_plasma_main.addWidget(self.lbl_paste)
        self.txt_paste = QTextEdit()
        self.txt_paste.setMaximumHeight(80)
        self.layout_plasma_main.addWidget(self.txt_paste)
        self.btn_apply_paste = QPushButton("Apply Pasted Values to Table")
        
        if IN_KLAYOUT: self.btn_apply_paste.clicked(self.apply_bulk_paste)
        else: self.btn_apply_paste.clicked.connect(self.apply_bulk_paste)
        self.layout_plasma_main.addWidget(self.btn_apply_paste)
        
        if IN_KLAYOUT:
            self.cb_use_per_contact_stems.clicked(self.update_stem_override_ui_state)
        else:
            self.cb_use_per_contact_stems.clicked.connect(self.update_stem_override_ui_state)

        
        # Tab 5: Image Analyzer
        self.tab_analyzer = QWidget()
        self.layout_analyzer = QVBoxLayout(self.tab_analyzer)
        if not HAVE_CV2:
            self.layout_analyzer.addWidget(QLabel("Image Analyzer requires cv2, numpy, and Pillow.\n" + CV2_IMPORT_ERROR))
        else:
            self.setup_analyzer_ui()
        self.tabs.addTab(self.tab_analyzer, "Image Analyzer")

        self.button_layout = QHBoxLayout()
        self.btn_generate = QPushButton("Apply & Generate")
        self.btn_cancel = QPushButton("Cancel")
        
        if IN_KLAYOUT:
            self.btn_generate.clicked(self.on_generate)
            self.btn_cancel.clicked(self.close)
        else:
            self.btn_generate.clicked.connect(self.on_generate)
            self.btn_cancel.clicked.connect(self.close)
            
        self.button_layout.addWidget(self.btn_generate)
        self.button_layout.addWidget(self.btn_cancel)
        self.left_layout.addLayout(self.button_layout)

        # --- CENTER: preview canvas + controls ---
        self.center_pane = QWidget()
        self.center_layout = QVBoxLayout(self.center_pane)
        try:
            self.center_layout.setContentsMargins(4, 4, 4, 4)
        except Exception:
            pass

        self.preview_header = QLabel("Live Preview")
        try:
            self.preview_header.setStyleSheet("font-weight: bold; padding: 2px;")
        except Exception:
            pass
        self.center_layout.addWidget(self.preview_header)

        # Single-vs-Full switcher sits right above the canvas so it is
        # visible from every tab on the left.
        self._preview_mode = 'single'
        self.preview_mode_row = QHBoxLayout()
        self.preview_mode_row.addWidget(QLabel("Mode:"))
        self.preview_mode_combo = QComboBox()
        self.preview_mode_combo.addItem("Single Quadrant")
        self.preview_mode_combo.addItem("Full Chip (4 Quadrants)")
        self.preview_mode_combo.setToolTip(
            "Switch between the single-quadrant live preview and the full-chip live preview.\n"
            "The full-chip view rebuilds all four quadrants plus the boundary, triangle,\n"
            "and sample-name labels — it is slower but reflects exactly what goes to the\n"
            "FULL GDS/DXF exports."
        )
        _connect_signal(self.preview_mode_combo.currentIndexChanged, self._on_preview_mode_changed)
        self.preview_mode_row.addWidget(self.preview_mode_combo, 1)
        self.center_layout.addLayout(self.preview_mode_row)

        self.preview_canvas = PreviewCanvas(self.center_pane)
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.preview_canvas)
        if HAVE_CV2 and hasattr(self, 'an_lbl_img'):
            self.center_stack.addWidget(self.an_lbl_img)
        self.center_layout.addWidget(self.center_stack, 1)
        
        # Connect tab change to swap stack
        def on_tab_changed(idx):
            if self.tabs.tabText(idx) == "Image Analyzer":
                self.center_stack.setCurrentIndex(1)
            else:
                self.center_stack.setCurrentIndex(0)
        
        if IN_KLAYOUT: self.tabs.currentChanged(on_tab_changed)
        else: self.tabs.currentChanged.connect(on_tab_changed)

        # Status line (shows "Rebuilding…" / "Updated in …ms" / errors)
        self.preview_status = QLabel("")
        try:
            self.preview_status.setStyleSheet("color: #9aa6bf; padding: 2px;")
        except Exception:
            pass
        self.center_layout.addWidget(self.preview_status)

        # Preview control row: Fit + Rebuild Now
        self.preview_btn_row = QHBoxLayout()
        self.btn_fit_view = QPushButton("Fit View")
        self.btn_rebuild_preview = QPushButton("Rebuild Now")
        _connect_signal(self.btn_fit_view.clicked, self.preview_canvas.fit_to_view)
        _connect_signal(self.btn_rebuild_preview.clicked, self._rebuild_preview)
        self.btn_measure_distance = QPushButton("Measure distance")
        self.btn_measure_distance.setCheckable(True)
        self.btn_measure_distance.setToolTip(
            "Interactive two-point distance in layout micrometres (same frame as the GDS preview).\n"
            "Turn on, click point A, then point B — length and Δx/Δy appear on canvas.\n"
            "Picks snap to the nearest visible polygon corner or edge (see 'Snap to edges'),\n"
            "so a measurement reports the true border-to-border distance.\n"
            "Right-click resets the current segment; Esc turns the tool off.\n"
            "Pan (left drag) and zoom still work; measurement graphics are drawn on top without re-rasterising the chip."
        )
        self.preview_canvas.attach_measure_ui_button(self.btn_measure_distance)
        _connect_signal(
            self.btn_measure_distance.clicked,
            lambda *args: self.preview_canvas.set_measure_tool_active(self.btn_measure_distance.isChecked()),
        )
        self.btn_measure_snap = QPushButton("Snap to edges")
        self.btn_measure_snap.setCheckable(True)
        self.btn_measure_snap.setChecked(True)
        self.btn_measure_snap.setToolTip(
            "Object snap for the measure tool (AutoCAD 'osnap').\n"
            "ON: each pick jumps to the nearest corner or edge of a visible layer\n"
            "within ~14 px — a square marker means a corner, a lozenge means a\n"
            "point on the highlighted edge. Corners win over edges when both are close.\n"
            "OFF: picks land exactly on the clicked pixel (free measurement).\n"
            "S toggles this while the measure tool has canvas focus.\n"
            "Only visible layers snap, so hide a layer to measure past it."
        )
        self.preview_canvas.attach_snap_ui_button(self.btn_measure_snap)
        _connect_signal(
            self.btn_measure_snap.clicked,
            lambda *args: self.preview_canvas.set_snap_enabled(self.btn_measure_snap.isChecked()),
        )
        self.preview_btn_row.addWidget(self.btn_fit_view)
        self.preview_btn_row.addWidget(self.btn_rebuild_preview)
        self.preview_btn_row.addWidget(self.btn_measure_distance)
        self.preview_btn_row.addWidget(self.btn_measure_snap)
        self.center_layout.addLayout(self.preview_btn_row)

        # --- RIGHT: scrollable layer toggle panel (narrow column) ---
        self.right_pane = QWidget()
        self.right_layout = QVBoxLayout(self.right_pane)
        try:
            self.right_layout.setContentsMargins(2, 2, 2, 2)
            self.right_layout.setSpacing(4)
        except Exception:
            pass

        _lbl = QLabel("Layers")
        try:
            _lbl.setStyleSheet("font-weight: bold;")
        except Exception:
            pass
        self.right_layout.addWidget(_lbl)

        # Global "Outline only" toggle – off by default so filled layers are visible.
        self.cb_outline_only = QCheckBox("Outline only")
        self.cb_outline_only.setChecked(False)
        _connect_signal(
            self.cb_outline_only.clicked,
            lambda *a: self.preview_canvas.set_outline_only(self.cb_outline_only.isChecked()),
        )
        self.right_layout.addWidget(self.cb_outline_only)

        # Anti-aliasing toggle. With AA on (default), sub-pixel features like
        # the 1 µm etch halo blend into soft edges the way KLayout renders
        # them. Turning it off gives a slightly faster, crisper-looking
        # aliased render at the cost of harsher halo fringes at fit view.
        self.cb_antialias = QCheckBox("Anti-aliasing")
        self.cb_antialias.setChecked(True)
        self.cb_antialias.setToolTip(
            "ON (default): sub-pixel features (e.g. the 1 µm etch halo around\n"
            "every metal wire) render as soft blended edges, matching KLayout\n"
            "and AutoCAD. Slightly slower.\n\n"
            "OFF: aliased rendering — crisper straight edges, faster rebuilds,\n"
            "but halos become a hard 1-pixel red line at fit view."
        )
        _connect_signal(
            self.cb_antialias.clicked,
            lambda *a: self.preview_canvas.set_antialias(self.cb_antialias.isChecked()),
        )
        self.right_layout.addWidget(self.cb_antialias)

        self.cb_measure_overlay = QCheckBox("Scale bar + cursor µm")
        self.cb_measure_overlay.setChecked(True)
        self.cb_measure_overlay.setToolTip(
            "Shows a zoom-adaptive horizontal scale bar (top-right) with a round\n"
            "1–2–5–10 length in µm or mm, and appends the cursor position in layout\n"
            "micrometres to the status line. Turn off for a cleaner view."
        )
        _connect_signal(
            self.cb_measure_overlay.clicked,
            lambda *a: self.preview_canvas.set_measure_overlay(self.cb_measure_overlay.isChecked()),
        )
        self.right_layout.addWidget(self.cb_measure_overlay)

        # Engineering view vs. cleaner readability view. When off (default),
        # the preview shows the layer-1 encap halo ring around every layer-2
        # metal shape — same as the exported GDS/DXF. When on, the preview
        # trims those rings (exports are never affected) so thin wires don't
        # appear fringed with red. Toggling triggers a full rebuild.
        self.cb_hide_etch_halo = QCheckBox("Hide etch halo around metal (preview only)")
        self.cb_hide_etch_halo.setChecked(False)
        self.cb_hide_etch_halo.setToolTip(
            "OFF (default, engineering-accurate): the preview shows layer 1 exactly\n"
            "as it will be fabricated, including the encap halo ring around every\n"
            "layer-2 metal shape.\n\n"
            "ON (readability): subtract the metal region (grown by encap_offset)\n"
            "from the preview's layer 1 so metal edges don't look fringed with red.\n"
            "GDS and DXF exports are never affected by this toggle."
        )
        _connect_signal(self.cb_hide_etch_halo.clicked, lambda *a: self._rebuild_preview())
        self.right_layout.addWidget(self.cb_hide_etch_halo)

        # All/None helpers
        _btn_row = QHBoxLayout()
        self.btn_layers_all = QPushButton("All")
        self.btn_layers_none = QPushButton("None")
        _connect_signal(self.btn_layers_all.clicked, lambda *a: self._set_all_layer_toggles(True))
        _connect_signal(self.btn_layers_none.clicked, lambda *a: self._set_all_layer_toggles(False))
        _btn_row.addWidget(self.btn_layers_all)
        _btn_row.addWidget(self.btn_layers_none)
        self.right_layout.addLayout(_btn_row)

        # Scroll area wraps the per-layer checkboxes so the panel stays narrow.
        self.layer_scroll = QScrollArea()
        self.layer_scroll.setWidgetResizable(True)
        try:
            self.layer_scroll.setFrameShape(getattr(QFrame, 'NoFrame', 0))
        except Exception:
            pass
        self._layer_scroll_inner = QWidget()
        self._layer_scroll_layout = QVBoxLayout(self._layer_scroll_inner)
        try:
            self._layer_scroll_layout.setContentsMargins(2, 2, 2, 2)
            self._layer_scroll_layout.setSpacing(2)
        except Exception:
            pass

        self.layer_toggles = {}
        for i, (gds, name, rgb) in enumerate(PREVIEW_LAYER_STYLE):
            cb = QCheckBox(name)
            visible = i < PREVIEW_LAYER_DEFAULT_VISIBLE_COUNT
            cb.setChecked(visible)
            self.preview_canvas.set_layer_visible(gds, visible)
            try:
                cb.setStyleSheet(
                    "QCheckBox {{ color: rgb({r},{g},{b}); }}".format(r=rgb[0], g=rgb[1], b=rgb[2])
                )
            except Exception:
                pass
            def _mk_cb(gds_val):
                return lambda *args: self.preview_canvas.set_layer_visible(gds_val, self.layer_toggles[gds_val].isChecked())
            _connect_signal(cb.clicked, _mk_cb(gds))
            self.layer_toggles[gds] = cb
            self._layer_scroll_layout.addWidget(cb)
        try:
            self._layer_scroll_layout.addStretch(1)
        except Exception:
            pass
        self.layer_scroll.setWidget(self._layer_scroll_inner)
        self.right_layout.addWidget(self.layer_scroll, 1)
        self._sync_plasma_layer_toggles()
        self._sync_gtt_field_enabled()
        gold_cb = self.global_inputs.get('export_gold_mask')
        gtt_cb = self.global_inputs.get('enable_gtt_label')
        if gold_cb is not None:
            _connect_signal(gold_cb.toggled, self._sync_gtt_field_enabled)
            _connect_signal(gold_cb.clicked, self._sync_gtt_field_enabled)
        if gtt_cb is not None:
            _connect_signal(gtt_cb.toggled, self._sync_gtt_field_enabled)
            _connect_signal(gtt_cb.clicked, self._sync_gtt_field_enabled)

        # Crosshair position readout (bottom of Layers panel).
        self.crosshair_pos_title = QLabel("Crosshair Positions (um)")
        try:
            self.crosshair_pos_title.setStyleSheet("font-weight: bold; padding-top: 4px;")
        except Exception:
            pass
        self.right_layout.addWidget(self.crosshair_pos_title)
        self.crosshair_pos_label = QLabel("Mode: SINGLE\nTL: --\nBL: --\nTR: --\nBR: --")
        try:
            self.crosshair_pos_label.setStyleSheet(
                "QLabel { background: #10151f; border: 1px solid #2e3a4d; border-radius: 4px; padding: 6px; "
                "font-family: Consolas, 'Courier New', monospace; font-size: 11px; }"
            )
        except Exception:
            pass
        self.crosshair_pos_label.setWordWrap(True)
        self.right_layout.addWidget(self.crosshair_pos_label)

        try:
            self.right_pane.setMaximumWidth(300)
            self.right_pane.setMinimumWidth(260)
        except Exception:
            pass

        # Assemble splitter: [forms] | [preview] | [layer panel]
        self.outer_splitter.addWidget(self.left_pane)
        self.outer_splitter.addWidget(self.center_pane)
        self.outer_splitter.addWidget(self.right_pane)
        try:
            self.outer_splitter.setStretchFactor(0, 3)
            self.outer_splitter.setStretchFactor(1, 5)
            self.outer_splitter.setStretchFactor(2, 0)
            self.outer_splitter.setCollapsible(2, False)
            self.outer_splitter.setSizes([560, 640, 260])
        except Exception:
            pass
        self.main_layout.addWidget(self.outer_splitter)

        # Debounced preview rebuild timer
        self._preview_timer = QTimer(self)
        try:
            self._preview_timer.setSingleShot(True)
        except Exception:
            pass
        _connect_signal(self._preview_timer.timeout, self._rebuild_preview)

        # Background-build plumbing: the worker thread drops its result into
        # _preview_result and this timer applies it on the GUI thread.
        self._preview_build_seq = 0
        self._preview_thread = None
        self._preview_result = None
        self._preview_rebuild_pending = False
        self._preview_poll_timer = QTimer(self)
        _connect_signal(self._preview_poll_timer.timeout, self._poll_preview_result)
        
        if 'num_pairs' in self.quad_inputs:
            if IN_KLAYOUT:
                self.quad_inputs['num_pairs'].textChanged(self.update_stem_table_wrapper)
            else:
                self.quad_inputs['num_pairs'].textChanged.connect(self.update_stem_table_wrapper)
                
        if 'stem_marker_strip_length_um' in self.quad_inputs:
            if IN_KLAYOUT:
                self.quad_inputs['stem_marker_strip_length_um'].textChanged(self.update_stem_table_wrapper)
            else:
                self.quad_inputs['stem_marker_strip_length_um'].textChanged.connect(self.update_stem_table_wrapper)
            
        self.update_stem_table()
        self._apply_saved_stem_state(self._saved_state)
        self.update_stem_override_ui_state()

        # Wire parameter inputs to schedule preview rebuilds, and fire the
        # first rebuild shortly after the dialog is shown.
        self._wire_preview_signals()
        # Trigger an initial rebuild after the event loop is up so the window
        # shows before we start crunching.
        try:
            QTimer.singleShot(100, self._rebuild_preview)
        except Exception:
            self._rebuild_preview()


    def setup_analyzer_ui(self):
        self.analyzer = Analyzer()
        self.analyzer_filepath = None
        self.local_trims = {}
        self.local_threshes = {}
        self.analyzer_zoom_factor = 1.0
        self.analyzer_pan_cx = 0.5
        self.analyzer_pan_cy = 0.5
        
        actions_row = QHBoxLayout()
        self.btn_load_img = QPushButton("Load Image")
        self.btn_auto_tune = QPushButton("Auto-Tune Thresholds")
        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_transfer = QPushButton("Transfer to Plasma Tab")
        self.btn_transfer.setStyleSheet("background-color: green; color: white;")
        
        if IN_KLAYOUT:
            self.btn_load_img.clicked(self.an_load_image)
            self.btn_auto_tune.clicked(self.an_auto_tune)
            self.btn_export_csv.clicked(self.an_export_csv)
            self.btn_transfer.clicked(self.an_transfer)
        else:
            self.btn_load_img.clicked.connect(self.an_load_image)
            self.btn_auto_tune.clicked.connect(self.an_auto_tune)
            self.btn_export_csv.clicked.connect(self.an_export_csv)
            self.btn_transfer.clicked.connect(self.an_transfer)
            
        actions_row.addWidget(self.btn_load_img)
        actions_row.addWidget(self.btn_auto_tune)
        actions_row.addWidget(self.btn_export_csv)
        actions_row.addWidget(self.btn_transfer)
        self.layout_analyzer.addLayout(actions_row)
        

        controls = QFormLayout()
        
        def add_slider_row(label_text, default_val, min_v, max_v, factor, is_float):
            row = QHBoxLayout()
            le = QLineEdit(str(default_val))
            le.setFixedWidth(60)
            slider = QSlider(_qt_enum(_Qt, 'Orientation.Horizontal') if _qt_enum(_Qt, 'Orientation.Horizontal') is not None else 1) # 1 = Qt.Horizontal
            slider.setRange(int(min_v * factor), int(max_v * factor))
            slider.setValue(int(float(default_val) * factor))
            
            def on_slider(val):
                v = val / factor
                le.setText(f"{v:.1f}" if is_float else str(int(v)))
            def on_le(text):
                try:
                    v = float(text)
                    slider.blockSignals(True)
                    slider.setValue(int(v * factor))
                    slider.blockSignals(False)
                    self.an_update_processing()
                except: pass
            
            if IN_KLAYOUT:
                slider.valueChanged(on_slider)
                le.textChanged(on_le)
            else:
                slider.valueChanged.connect(on_slider)
                le.textChanged.connect(on_le)
            
            row.addWidget(le)
            row.addWidget(slider)
            controls.addRow(label_text, row)
            return le, slider

        self.an_thresh, self.sl_thresh = add_slider_row("Manual Contact Thresh:", 100, 0, 255, 1, False)
        self.an_l_thresh, self.sl_l_thresh = add_slider_row("Left Gr. Thresh:", 100.0, 0, 255, 10, True)
        self.an_r_thresh, self.sl_r_thresh = add_slider_row("Right Gr. Thresh:", 100.0, 0, 255, 10, True)
        self.an_morph, self.sl_morph = add_slider_row("Morph Detach Size:", 3, 0, 30, 1, False)
        self.an_trim_l, self.sl_trim_l = add_slider_row("Trim Left (um):", 0.0, 0, 500, 10, True)
        self.an_trim_r, self.sl_trim_r = add_slider_row("Trim Right (um):", 0.0, 0, 500, 10, True)
        
        self.an_pts = QLineEdit("64")
        self.an_skipped = QLineEdit("")
        self.an_orient = QComboBox()
        self.an_orient.addItems(["Vertical", "Horizontal"])
        self.an_orient.setCurrentText("Horizontal")
        self.an_bg = QComboBox()
        self.an_bg.addItems(["Dark", "Light"])
        self.an_display = QComboBox()
        self.an_display.addItems(["Annotated", "Threshold Mask"])
        
        for w in [self.an_pts, self.an_skipped]:
            if IN_KLAYOUT: w.textChanged(self.an_update_processing)
            else: w.textChanged.connect(self.an_update_processing)
            
        for w in [self.an_orient, self.an_bg, self.an_display]:
            if IN_KLAYOUT: w.currentIndexChanged(self.an_update_processing)
            else: w.currentIndexChanged.connect(self.an_update_processing)
            
        controls.addRow("Total Points:", self.an_pts)
        controls.addRow("Skipped (e.g. 1,4):", self.an_skipped)
        controls.addRow("Orientation:", self.an_orient)
        controls.addRow("Background:", self.an_bg)
        controls.addRow("Display:", self.an_display)
        
        self.layout_analyzer.addLayout(controls)

        
        self.an_lbl_img = InteractiveImageViewer(self.tab_analyzer, app=self)
        self.an_lbl_img.setAlignment(_qt_enum(_Qt, 'AlignmentFlag.AlignCenter') if _qt_enum(_Qt, 'AlignmentFlag.AlignCenter') is not None else _Qt.AlignCenter)
        self.an_lbl_img.setStyleSheet("background-color: black;")
        self.an_lbl_img.setMinimumSize(400, 300)
        
        self.an_table = QTableWidget(0, 3)
        self.an_table.setHorizontalHeaderLabels(["Index", "Total Length (um)", "Graphene Cov (um)"])
        if IN_KLAYOUT: self.an_table.itemDoubleClicked(self.an_on_tree_double_click)
        else: self.an_table.cellDoubleClicked.connect(self.an_on_tree_double_click_qt)
        self.layout_analyzer.addWidget(self.an_table, 1)

    def an_load_image(self, dummy=None):
        if not HAVE_CV2: return
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Image")
        if not file_path: return
        try:
            self.analyzer.image = cv2.imread(file_path)
            self.analyzer.gray = cv2.cvtColor(self.analyzer.image, cv2.COLOR_BGR2GRAY)
            self.analyzer_filepath = file_path
            self.local_trims = {}
            self.local_threshes = {}
            self.analyzer_zoom_factor = 1.0
            self.analyzer_pan_cx = 0.5
            self.analyzer_pan_cy = 0.5
            
            opt_c, opt_lg, opt_rg = self.analyzer.auto_tune_parameters()
            self.an_thresh.setText(str(int(opt_c)))
            self.an_l_thresh.setText(f"{opt_lg:.1f}")
            self.an_r_thresh.setText(f"{opt_rg:.1f}")
            self.an_update_processing()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {e}")

    def an_auto_tune(self, dummy=None):
        if not HAVE_CV2 or self.analyzer.gray is None: return
        self.analyzer._reload_calibration_file()
        opt_c, opt_lg, opt_rg = self.analyzer.auto_tune_parameters()
        self.an_thresh.setText(str(int(opt_c)))
        self.an_l_thresh.setText(f"{opt_lg:.1f}")
        self.an_r_thresh.setText(f"{opt_rg:.1f}")
        self.an_update_processing()

    def an_update_processing(self, dummy=None):
        if not HAVE_CV2 or getattr(self.analyzer, 'image', None) is None: return
        self.analyzer._reload_calibration_file()
        try: thresh_val = int(self._get_text(self.an_thresh))
        except: thresh_val = 100
        try: l_graph_thresh_val = float(self._get_text(self.an_l_thresh))
        except: l_graph_thresh_val = 100.0
        try: r_graph_thresh_val = float(self._get_text(self.an_r_thresh))
        except: r_graph_thresh_val = 100.0
        try: trim_left_val = float(self._get_text(self.an_trim_l))
        except: trim_left_val = 0.0
        try: trim_right_val = float(self._get_text(self.an_trim_r))
        except: trim_right_val = 0.0
        try: morph_size = int(self._get_text(self.an_morph))
        except: morph_size = 3
        try: pts_count = int(self._get_text(self.an_pts))
        except: pts_count = 64
        
        orient = self.an_orient.currentText if IN_KLAYOUT else self.an_orient.currentText()
        bg = self.an_bg.currentText if IN_KLAYOUT else self.an_bg.currentText()
        skipped_str = self._get_text(self.an_skipped)
        skipped_pads = [int(x.strip()) for x in skipped_str.split(',') if x.strip().isdigit()]
        
        if pts_count <= 0: return
        
        points, thresh_img = self.analyzer.process(
            threshold=thresh_val,
            left_graph_thresh=l_graph_thresh_val,
            right_graph_thresh=r_graph_thresh_val,
            trim_left_um=trim_left_val,
            trim_right_um=trim_right_val,
            orientation=orient,
            bg_type=bg,
            morph_size=morph_size,
            num_points=pts_count,
            local_trims=self.local_trims,
            local_threshes=self.local_threshes,
            skipped_pads=skipped_pads
        )
        
        disp_mode = self.an_display.currentText if IN_KLAYOUT else self.an_display.currentText()
        if disp_mode == "Annotated":
            display_cv = self.analyzer.image.copy()
            display_cv = self.analyzer.draw_results(display_cv)
        else:
            if thresh_img is not None: display_cv = cv2.cvtColor(thresh_img, cv2.COLOR_GRAY2BGR)
            else: display_cv = self.analyzer.image.copy()
            
        display_cv_rgb = cv2.cvtColor(display_cv, cv2.COLOR_BGR2RGB)
        h, w, ch = display_cv_rgb.shape
        bytes_per_line = ch * w
        
        self.pil_img_original_cv = display_cv_rgb
        self.an_refresh_image_display()
        self.an_update_table(self.analyzer.points)

    
    def an_on_zoom(self, event):
        if not hasattr(self, 'pil_img_original_cv'): return
        
        d = 0
        if hasattr(event, 'angleDelta'):
            d = event.angleDelta().y()
        elif hasattr(event, 'delta'):
            d = event.delta()
            
        if d == 0: return
        
        old_zoom = getattr(self, 'analyzer_zoom_factor', 1.0)
        zoom = old_zoom * (1.25 if d > 0 else 1/1.25)
        zoom = max(1.0, min(zoom, 50.0))
        self.analyzer_zoom_factor = zoom
        
        if self.analyzer_zoom_factor != old_zoom:
            cw = self.an_lbl_img.width()
            ch = self.an_lbl_img.height()
            
            ex = event.position().x() if hasattr(event, 'position') else event.x()
            ey = event.position().y() if hasattr(event, 'position') else event.y()
            mc_x = ex - cw / 2.0
            mc_y = ey - ch / 2.0
            
            img_h, img_w, _ = self.pil_img_original_cv.shape
            fit_scale = min(cw / img_w, ch / img_h)
            
            old_actual = fit_scale * old_zoom
            new_actual = fit_scale * zoom
            
            native_dx = mc_x / old_actual
            native_dy = mc_y / old_actual
            
            pan_cx = getattr(self, 'analyzer_pan_cx', 0.5)
            pan_cy = getattr(self, 'analyzer_pan_cy', 0.5)
            
            native_cursor_x = pan_cx + native_dx / img_w
            native_cursor_y = pan_cy + native_dy / img_h
            
            self.analyzer_pan_cx = native_cursor_x - (mc_x / new_actual) / img_w
            self.analyzer_pan_cy = native_cursor_y - (mc_y / new_actual) / img_h
            
            self.analyzer_pan_cx = max(0.0, min(1.0, self.analyzer_pan_cx))
            self.analyzer_pan_cy = max(0.0, min(1.0, self.analyzer_pan_cy))
            
        if self.analyzer_zoom_factor == 1.0:
            self.analyzer_pan_cx = 0.5
            self.analyzer_pan_cy = 0.5
            
        self.an_refresh_image_display()

    def an_on_drag_start(self, event):
        self.an_drag_start_x = event.position().x() if hasattr(event, 'position') else event.x()
        self.an_drag_start_y = event.position().y() if hasattr(event, 'position') else event.y()
        self.an_drag_mode = 'pan'
        self.an_active_trim_line = None
        
        if not hasattr(self, 'pil_img_original_cv'): return
        
        cw = self.an_lbl_img.width()
        ch = self.an_lbl_img.height()
        img_h, img_w, _ = self.pil_img_original_cv.shape
        
        fit_scale = min(cw / img_w, ch / img_h)
        zoom = getattr(self, 'analyzer_zoom_factor', 1.0)
        actual_scale = fit_scale * zoom
        
        mc_x = self.an_drag_start_x - cw / 2.0
        mc_y = self.an_drag_start_y - ch / 2.0
        
        pan_cx = getattr(self, 'analyzer_pan_cx', 0.5)
        pan_cy = getattr(self, 'analyzer_pan_cy', 0.5)
        
        native_cursor_x = pan_cx * img_w + mc_x / actual_scale
        native_cursor_y = pan_cy * img_h + mc_y / actual_scale
        
        if hasattr(self.analyzer, 'trench_lines'):
            import math
            best_dist = float('inf')
            best_line = None
            for line_obj in self.analyzer.trench_lines:
                if line_obj.get('cvg_pixels', 0) == 0: continue
                pt1, pt2 = line_obj.get('pt1', (0,0)), line_obj.get('pt2', (0,0))
                l2 = (pt2[0] - pt1[0])**2 + (pt2[1] - pt1[1])**2
                if l2 == 0:
                    dist = math.hypot(native_cursor_x - pt1[0], native_cursor_y - pt1[1])
                else:
                    t = max(0, min(1, ((native_cursor_x - pt1[0])*(pt2[0] - pt1[0]) + (native_cursor_y - pt1[1])*(pt2[1] - pt1[1])) / l2))
                    proj_x = pt1[0] + t * (pt2[0] - pt1[0])
                    proj_y = pt1[1] + t * (pt2[1] - pt1[1])
                    dist = math.hypot(native_cursor_x - proj_x, native_cursor_y - proj_y)
                
                if dist < best_dist:
                    best_dist = dist
                    best_line = line_obj
            
            if best_dist < (20.0 / actual_scale) and best_line is not None:
                self.an_drag_mode = 'trim'
                self.an_active_trim_line = best_line

    def an_on_drag_motion(self, event):
        if not hasattr(self, 'pil_img_original_cv'): return
        
        ex = event.position().x() if hasattr(event, 'position') else event.x()
        ey = event.position().y() if hasattr(event, 'position') else event.y()
        
        dx = ex - getattr(self, 'an_drag_start_x', ex)
        dy = ey - getattr(self, 'an_drag_start_y', ey)
        
        cw = self.an_lbl_img.width()
        ch = self.an_lbl_img.height()
        img_h, img_w, _ = self.pil_img_original_cv.shape
        
        fit_scale = min(cw / img_w, ch / img_h)
        zoom = getattr(self, 'analyzer_zoom_factor', 1.0)
        actual_scale = fit_scale * zoom
        pan_cx = getattr(self, 'analyzer_pan_cx', 0.5)
        pan_cy = getattr(self, 'analyzer_pan_cy', 0.5)
        
        if getattr(self, 'an_drag_mode', 'pan') == 'trim' and getattr(self, 'an_active_trim_line', None):
            mc_x = ex - cw / 2.0
            mc_y = ey - ch / 2.0
            native_cursor_x = pan_cx * img_w + mc_x / actual_scale
            native_cursor_y = pan_cy * img_h + mc_y / actual_scale
            
            l = self.an_active_trim_line
            px = native_cursor_x - l['start_pt'][0]
            py = native_cursor_y - l['start_pt'][1]
            projected_dist = px * l['dx'] + py * l['dy']
            if projected_dist < 0: projected_dist = 0
            trim_pixels_total = projected_dist - l['base_cvg_start_idx']
            
            try: pts_count = int(self._get_text(self.an_pts))
            except: pts_count = 64
            mid = pts_count // 2
            
            try: global_trim_um = float(self._get_text(self.an_trim_l)) if int(l.get('orig_idx', 0)) < mid else float(self._get_text(self.an_trim_r))
            except: global_trim_um = 0.0
            
            target_total_trim_um = trim_pixels_total * l['global_um_per_pixel']
            new_local_trim = target_total_trim_um - global_trim_um
            
            self.local_trims[l['orig_idx']] = new_local_trim
            self.an_update_processing()
            return
            
        if zoom <= 1.0: return
        
        self.an_drag_start_x = ex
        self.an_drag_start_y = ey
        
        self.analyzer_pan_cx -= (dx / actual_scale) / img_w
        self.analyzer_pan_cy -= (dy / actual_scale) / img_h
        
        self.analyzer_pan_cx = max(0.0, min(1.0, self.analyzer_pan_cx))
        self.analyzer_pan_cy = max(0.0, min(1.0, self.analyzer_pan_cy))
        self.an_refresh_image_display()

    def an_refresh_image_display(self):
        if not hasattr(self, 'pil_img_original_cv'): return
        
        cw = self.an_lbl_img.width()
        ch = self.an_lbl_img.height()
        if cw < 10 or ch < 10: return
        
        img_h, img_w, _ = self.pil_img_original_cv.shape
        zoom = getattr(self, 'analyzer_zoom_factor', 1.0)
        fit_scale = min(cw / img_w, ch / img_h)
        actual_scale = fit_scale * zoom
        
        pan_cx = getattr(self, 'analyzer_pan_cx', 0.5)
        pan_cy = getattr(self, 'analyzer_pan_cy', 0.5)
        
        native_vw = cw / actual_scale
        native_vh = ch / actual_scale
        
        center_x = pan_cx * img_w
        center_y = pan_cy * img_h
        
        left = center_x - native_vw / 2.0
        top = center_y - native_vh / 2.0
        right = center_x + native_vw / 2.0
        bottom = center_y + native_vh / 2.0
        
        c_left = max(0, int(left))
        c_top = max(0, int(top))
        c_right = min(img_w, int(right))
        c_bottom = min(img_h, int(bottom))
        
        if c_right > c_left and c_bottom > c_top:
            crop_cv = self.pil_img_original_cv[c_top:c_bottom, c_left:c_right]
            target_w = int((float(c_right) - float(c_left)) * actual_scale)
            target_h = int((float(c_bottom) - float(c_top)) * actual_scale)
            
            if target_w > 0 and target_h > 0:
                resized_cv = cv2.resize(crop_cv, (target_w, target_h), interpolation=cv2.INTER_NEAREST if actual_scale > 1.5 else cv2.INTER_AREA)
                h, w, ch_n = resized_cv.shape
                bytes_per_line = ch_n * w
                fmt = _qt_enum(QImage, 'Format.Format_RGB888') or _qt_enum(QImage, 'Format_RGB888') or 13
                self._cv_crop_data = resized_cv.data.tobytes()
                qimg = QImage(self._cv_crop_data, w, h, bytes_per_line, fmt)
                
                # Create a black pixmap matching the label size and paint the crop in the center
                full_pixmap = QPixmap(cw, ch)
                full_pixmap.fill(QColor(0, 0, 0))
                
                draw_x = int((c_left - left) * actual_scale)
                draw_y = int((c_top - top) * actual_scale)
                
                painter = QPainter(full_pixmap)
                painter.drawImage(draw_x, draw_y, qimg)
                painter.end()
                
                self.an_lbl_img.setPixmap(full_pixmap)

    def an_on_tree_double_click_qt(self, row, col):
        self.an_on_tree_double_click(self.an_table.item(row, 0))

    def an_on_tree_double_click(self, item):
        if not item: return
        idx_str = self.an_table.item(item.row() if hasattr(item, 'row') else item, 0).text()
        try: pt_idx = int(idx_str) - 1
        except ValueError: return
        
        dlg = QDialog()
        dlg.setWindowTitle(f"Adjust Pad {idx_str}")
        dlg.setMinimumWidth(300)
        ly = QVBoxLayout(dlg)
        
        ly.addWidget(QLabel(f"Local Adjustments for Pad {idx_str}"))
        
        f1 = QFormLayout()
        trim_le = QLineEdit(str(self.local_trims.get(pt_idx, 0.0)))
        thresh_le = QLineEdit(str(self.local_threshes.get(pt_idx, "")))
        f1.addRow("Add Trim (um):", trim_le)
        f1.addRow("Fixed Thresh:", thresh_le)
        ly.addLayout(f1)
        
        btn_ly = QHBoxLayout()
        btn_apply = QPushButton("Apply")
        btn_clear = QPushButton("Clear")
        btn_apply.setStyleSheet("background-color: blue; color: white;")
        btn_ly.addWidget(btn_apply)
        btn_ly.addWidget(btn_clear)
        ly.addLayout(btn_ly)
        
        def apply():
            try: self.local_trims[pt_idx] = float(trim_le.text())
            except: self.local_trims.pop(pt_idx, None)
            try: self.local_threshes[pt_idx] = int(thresh_le.text())
            except: self.local_threshes.pop(pt_idx, None)
            dlg.accept()
            self.an_update_processing()
            
        def clear():
            self.local_trims.pop(pt_idx, None)
            self.local_threshes.pop(pt_idx, None)
            dlg.accept()
            self.an_update_processing()
            
        if IN_KLAYOUT:
            btn_apply.clicked(apply)
            btn_clear.clicked(clear)
        else:
            btn_apply.clicked.connect(apply)
            btn_clear.clicked.connect(clear)
            
        dlg.exec() if IN_KLAYOUT else dlg.exec()

    def an_update_table(self, points):
        if IN_KLAYOUT: self.an_table.rowCount = 0
        else: self.an_table.setRowCount(0)
        if points is None: return
        if IN_KLAYOUT: self.an_table.rowCount = len(points)
        else: self.an_table.setRowCount(len(points))
        
        for i, p in enumerate(points):
            idx = i + 1
            if p.get('is_skipped'):
                self.an_table.setItem(i, 0, QTableWidgetItem(str(idx)))
                self.an_table.setItem(i, 1, QTableWidgetItem("SKIPPED"))
                self.an_table.setItem(i, 2, QTableWidgetItem("SKIPPED"))
            else:
                self.an_table.setItem(i, 0, QTableWidgetItem(str(idx)))
                self.an_table.setItem(i, 1, QTableWidgetItem(f"{p.get('total_um', 0):.1f}"))
                self.an_table.setItem(i, 2, QTableWidgetItem(f"{p.get('coverage_um', 0):.1f}"))

    def an_export_csv(self, dummy=None):
        if not HAVE_CV2 or not getattr(self.analyzer, 'points', None):
            QMessageBox.warning(self, "Warning", "No data to export.")
            return
        img_stem = "graphene_coverage"
        if getattr(self, "analyzer_filepath", None):
            img_stem = os.path.splitext(os.path.basename(self.analyzer_filepath))[0]
        
        save_path, _ = QFileDialog.getSaveFileName(self, "Save CSV", f"{img_stem}.csv", "CSV files (*.csv)")
        if not save_path: return
        with open(save_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Contact Pt #", "Total Length (um)", "Graphene Coverage (um)", "Pixel Trench Ratio"])
            for i, p in enumerate(self.analyzer.points):
                if p.get('is_skipped'):
                    writer.writerow([i + 1, "SKIPPED", "SKIPPED", "SKIPPED"])
                else:
                    writer.writerow([i + 1, round(p.get('total_um', 0), 1), round(p.get('coverage_um', 0), 1), round(p.get('coverage_ratio', 0), 3)])
        QMessageBox.information(self, "Success", f"Data saved to {save_path}")

    def an_transfer(self, dummy=None):
        if not HAVE_CV2 or not getattr(self.analyzer, 'points', None):
            QMessageBox.warning(self, "Warning", "No data. Load an image and analyze first.")
            return
            
        pts = list(self.analyzer.points)
        n = len(pts)
        if n < 2: return
        
        half = n // 2
        left_cov = [0.0 if p.get('is_skipped') else float(p.get('coverage_um', 0.0)) for p in pts[:half]][::-1]
        right_cov = [0.0 if p.get('is_skipped') else float(p.get('coverage_um', 0.0)) for p in pts[half:half*2]][::-1]
        
        self.cb_use_per_contact_stems.setChecked(True)
        if IN_KLAYOUT: self.stem_table.rowCount = half
        else: self.stem_table.setRowCount(half)
        
        for r in range(half):
            self.stem_table.setItem(r, 0, QTableWidgetItem(str(r + 1)))
            self.stem_table.setItem(r, 1, QTableWidgetItem(str(left_cov[r])))
            self.stem_table.setItem(r, 2, QTableWidgetItem(str(half + r + 1)))
            self.stem_table.setItem(r, 3, QTableWidgetItem(str(right_cov[r])))
            
        self.update_stem_override_ui_state()
        self._schedule_preview_rebuild()
        self.tabs.setCurrentWidget(self.tab_plasma)
        QMessageBox.information(self, "Success", "Coverage values transferred to Plasma Layer Edits tab! Preview updated.")

    def _plasma_layers_enabled_in_preview(self):
        try:
            cb = self.global_inputs.get('enable_3_plasma_layers')
            if cb is not None:
                return bool(cb.isChecked())
        except Exception:
            pass
        return True

    def _plasma_l1_preview_label(self, three_on):
        """Checkbox label for GDS layer 12 in the live preview layer panel."""
        if not three_on:
            gds = 12
            try:
                l_in = self.plasma_inputs.get('plasma_l1_layer')
                if l_in is not None:
                    gds = int(float(self._get_text(l_in)))
            except Exception:
                pass
            return "Plasma Layer ({0})".format(gds)
        w, g, gds = 10.0, 10.0, 12
        try:
            w_in = self.plasma_inputs.get('plasma_l1_width_um')
            g_in = self.plasma_inputs.get('plasma_l1_gap_um')
            l_in = self.plasma_inputs.get('plasma_l1_layer')
            if w_in is not None:
                w = float(self._get_text(w_in))
            if g_in is not None:
                g = float(self._get_text(g_in))
            if l_in is not None:
                gds = int(float(self._get_text(l_in)))
        except Exception:
            pass
        w_str = str(int(w)) if w == int(w) else str(w)
        g_str = str(int(g)) if g == int(g) else str(g)
        return "plasma {0}-{1} ({2})".format(w_str, g_str, gds)

    def _sync_gtt_field_enabled(self, *args, **kwargs):
        try:
            gold_cb = self.global_inputs.get('export_gold_mask')
            gtt_cb = self.global_inputs.get('enable_gtt_label')
            gtt_le = self.global_inputs.get('gtt_number')
            gold_on = bool(gold_cb.isChecked()) if gold_cb is not None else False
            gtt_on = bool(gtt_cb.isChecked()) if gtt_cb is not None else False
            if gtt_le is not None:
                gtt_le.setEnabled(gold_on and gtt_on)
        except Exception:
            pass

    def _sync_plasma_layer_toggles(self, *args, **kwargs):
        """Plasma L2/L3 toggles (13/14) appear only when 3-plasma mode is on.
        Plasma L1 (12) is always in the panel and toggles normally."""
        three_on = self._plasma_layers_enabled_in_preview()
        cb12 = self.layer_toggles.get(12)
        if cb12 is not None:
            try:
                cb12.setText(self._plasma_l1_preview_label(three_on))
            except Exception:
                pass
        for gds in PREVIEW_PLASMA_EXTRA_GDS_LAYERS:
            cb = self.layer_toggles.get(gds)
            if cb is None:
                continue
            try:
                cb.setVisible(three_on)
            except Exception:
                pass
            if not three_on:
                try:
                    cb.setChecked(False)
                except Exception:
                    pass
                try:
                    self.preview_canvas.set_layer_visible(gds, False)
                except Exception:
                    pass
            else:
                try:
                    self.preview_canvas.set_layer_visible(gds, cb.isChecked())
                except Exception:
                    pass
        try:
            self.preview_canvas.update()
        except Exception:
            pass

    def _set_all_layer_toggles(self, state):
        """Toggle every visible layer visibility checkbox at once."""
        for gds, cb in getattr(self, 'layer_toggles', {}).items():
            try:
                if not cb.isVisible():
                    continue
            except Exception:
                pass
            try:
                cb.setChecked(bool(state))
            except Exception:
                pass
            try:
                self.preview_canvas.set_layer_visible(gds, bool(state))
            except Exception:
                pass

    # --- Live preview plumbing -------------------------------------------------
    def _wire_preview_signals(self):
        """Connect every parameter input to the debounced preview rebuild."""
        def connect_input(w):
            # text fields
            for sig_name in ('textChanged', 'editingFinished'):
                sig = getattr(w, sig_name, None)
                if sig is not None:
                    _connect_signal(sig, self._schedule_preview_rebuild)
            # check boxes
            for sig_name in ('clicked', 'stateChanged', 'toggled'):
                sig = getattr(w, sig_name, None)
                if sig is not None:
                    _connect_signal(sig, self._schedule_preview_rebuild)
        for d in (getattr(self, 'global_inputs', {}) or {},
                  getattr(self, 'quad_inputs', {}) or {},
                  getattr(self, 'plasma_inputs', {}) or {},
                  getattr(self, 'params_3d_inputs', {}) or {}):
            for w in d.values():
                connect_input(w)
        # Stem table edits and overrides also affect geometry
        if hasattr(self, 'cb_use_per_contact_stems'):
            _connect_signal(self.cb_use_per_contact_stems.clicked, self._schedule_preview_rebuild)
        if hasattr(self, 'stem_table'):
            sig = getattr(self.stem_table, 'itemChanged', None)
            if sig is not None:
                _connect_signal(sig, self._schedule_preview_rebuild)

    def _schedule_preview_rebuild(self, *args, **kwargs):
        self._sync_plasma_layer_toggles()
        try:
            self.preview_status.setText("Rebuilding preview…")
        except Exception:
            pass
        try:
            # Short debounce: the heavy build runs off the GUI thread, so we
            # can afford to kick it off almost immediately after a keystroke.
            self._preview_timer.start(150)
        except Exception:
            self._rebuild_preview()

    def _gather_preview_params(self):
        """Read form values into (global, quad, params_3d) dicts, keeping defaults on parse errors."""
        local_global = copy.deepcopy(GLOBAL_PARAMS)
        local_quad   = copy.deepcopy(DEFAULT_QUADRANT_PARAMS)
        local_3d     = copy.deepcopy(PARAMS_3D)

        def read_one(target, key, ui_elem):
            orig = target.get(key, None)
            try:
                if isinstance(orig, bool):
                    target[key] = bool(ui_elem.isChecked())
                else:
                    txt = self._get_text(ui_elem)
                    if isinstance(orig, list):
                        if key in _GDS_LAYER_LIST_KEYS:
                            target[key] = _parse_layer_list_ui_text(txt, orig)
                        else:
                            target[key] = ast.literal_eval(txt)
                    elif isinstance(orig, int) and not isinstance(orig, bool):
                        target[key] = int(float(txt))
                    elif isinstance(orig, float):
                        target[key] = float(txt)
                    else:
                        target[key] = txt
            except Exception:
                pass  # keep default

        for k, w in (getattr(self, 'global_inputs', {}) or {}).items(): read_one(local_global, k, w)
        for k, w in (getattr(self, 'quad_inputs', {})   or {}).items(): read_one(local_quad,   k, w)
        for k, w in (getattr(self, 'plasma_inputs', {}) or {}).items(): read_one(local_quad, k, w)
        for k, w in (getattr(self, 'params_3d_inputs', {}) or {}).items(): read_one(local_3d, k, w)

        # Per-contact stem overrides if enabled
        try:
            if self.cb_use_per_contact_stems.isChecked():
                left, right = [], []
                rows = self._get_rows(self.stem_table)
                for r in range(rows):
                    try: left.append(float(self.stem_table.item(r, 1).text()))
                    except Exception: left.append(local_quad.get('stem_marker_strip_length_um', 0.0))
                    try: right.append(float(self.stem_table.item(r, 3).text()))
                    except Exception: right.append(local_quad.get('stem_marker_strip_length_um', 0.0))
                local_quad['stem_marker_lengths_left'] = left
                local_quad['stem_marker_lengths_right'] = right
        except Exception:
            pass

        # Preview-only: opt-in etch-halo clip (exports never see this key).
        try:
            if getattr(self, 'cb_hide_etch_halo', None) is not None and self.cb_hide_etch_halo.isChecked():
                local_quad['_preview_etch_halo_clip_um'] = float(local_quad.get('encap_offset', 1.0)) + 0.5
            else:
                local_quad['_preview_etch_halo_clip_um'] = 0.0
        except Exception:
            local_quad['_preview_etch_halo_clip_um'] = 0.0

        _apply_plasma_layer_count_from_global(local_global, local_quad)

        if local_global.get('enable_kinetic_naming', True):
            local_global['enable_quadrant_sample_names'] = True
            try:
                if hasattr(self, 'kinetic_date_edit'):
                    if IN_KLAYOUT:
                        date_str = self.kinetic_date_edit.date.toString("MMdd")
                    else:
                        date_str = self.kinetic_date_edit.date().toString("MMdd")
                else:
                    import datetime
                    date_str = datetime.datetime.now().strftime("%m%d")
            except:
                import datetime
                date_str = datetime.datetime.now().strftime("%m%d")
            w_l1 = int(local_quad.get('wire_L1_width', 4))
            enc_off = int(local_quad.get('encap_offset', 1))
            w_total = w_l1 + 2 * enc_off
            depth = int(local_global.get('kinetic_depth', 190.0))
            num_wires = int(local_quad.get('num_wires_per_contact', 1))
            local_global['sample_name_base'] = _build_kinetic_sample_name_base(
                date_str, w_total, w_l1, depth, num_wires)

        return local_global, local_quad, local_3d

    def _on_preview_mode_changed(self, idx):
        try:
            self._preview_mode = 'full' if int(idx) == 1 else 'single'
        except Exception:
            self._preview_mode = 'single'
        try:
            header = "Live Preview — Full Chip" if self._preview_mode == 'full' else "Live Preview — Single Quadrant"
            self.preview_header.setText(header)
        except Exception:
            pass
        self._rebuild_preview()

    def _format_crosshair_panel_text(self, mode, pos_map):
        mode_text = "FULL" if mode == 'full' else "SINGLE"
        lines = [f"Mode: {mode_text}", ""]
        for key in ["TL", "BL", "TR", "BR"]:
            if pos_map and key in pos_map:
                x, y = pos_map[key]
                lines.append(f"{key}:  X={x:>10.3f}   Y={y:>10.3f}")
            else:
                lines.append(f"{key}:  --")
        return "\n".join(lines)

    def _update_crosshair_panel(self, mode, pos_map):
        try:
            self.crosshair_pos_label.setText(self._format_crosshair_panel_text(mode, pos_map))
        except Exception:
            pass

    @staticmethod
    def _build_preview_payload(mode, g, q):
        """Heavy geometry build. Pure computation (no Qt widgets) so it can
        run on a worker thread."""
        import time as _time
        t0 = _time.time()
        try:
            if mode == 'full':
                polys_by_layer, bbox_um, crosshair_pos = _build_full_chip_preview_layout(g, q)
            else:
                polys_by_layer, bbox_um, crosshair_pos = _build_preview_layout(g, q)
            return {'polys': polys_by_layer, 'bbox': bbox_um, 'crosshair': crosshair_pos,
                    'error': None, 'dt_ms': (_time.time() - t0) * 1000.0}
        except Exception as e:
            return {'polys': None, 'bbox': None, 'crosshair': {},
                    'error': e, 'dt_ms': (_time.time() - t0) * 1000.0}

    def _apply_preview_result(self, mode, payload):
        """Push a finished build to the canvas (GUI thread only)."""
        mode_label = "full chip" if mode == 'full' else "single"
        if payload.get('error') is not None:
            e = payload['error']
            try:
                self.preview_status.setText("Preview error: {}".format(e))
            except Exception:
                pass
            self._update_crosshair_panel(mode, {})
            self.preview_canvas.set_message("Preview error: {}".format(e))
            return
        import time as _time
        t1 = _time.time()
        polys_by_layer = payload['polys']
        self.preview_canvas.set_data(polys_by_layer, payload['bbox'])
        self._update_crosshair_panel(mode, payload['crosshair'])
        dt = payload['dt_ms'] + (_time.time() - t1) * 1000.0
        n_polys = sum(len(v) for v in polys_by_layer.values())
        try:
            self.preview_status.setText("{}: updated in {:.0f} ms  ({} polys, {} layers)".format(
                mode_label, dt, n_polys, len(polys_by_layer)))
        except Exception:
            pass

    def _rebuild_preview(self):
        """Rebuild the layout (single or full) and push polygons to the canvas.

        Standalone (PyQt6) mode runs the heavy geometry build on a daemon
        thread so typing/panning stays fluid; inside KLayout it stays
        synchronous (pya objects are safest on the main thread there)."""
        try:
            g, q, _ = self._gather_preview_params()
        except Exception as e:
            try:
                self.preview_status.setText("Preview error: {}".format(e))
            except Exception:
                pass
            return
        mode = getattr(self, '_preview_mode', 'single')
        try:
            self.preview_status.setText("Rebuilding preview…")
        except Exception:
            pass

        if IN_KLAYOUT:
            self._apply_preview_result(mode, self._build_preview_payload(mode, g, q))
            return

        self._preview_build_seq = getattr(self, '_preview_build_seq', 0) + 1
        seq = self._preview_build_seq
        th = getattr(self, '_preview_thread', None)
        if th is not None and th.is_alive():
            # A build is already running with stale params; rerun when it ends.
            self._preview_rebuild_pending = True
            return
        self._preview_rebuild_pending = False

        def work():
            self._preview_result = (seq, mode, self._build_preview_payload(mode, g, q))

        try:
            self._preview_thread = threading.Thread(target=work, daemon=True)
            self._preview_thread.start()
            self._preview_poll_timer.start(30)
        except Exception:
            # Threading unavailable for any reason → synchronous fallback.
            self._preview_thread = None
            self._apply_preview_result(mode, self._build_preview_payload(mode, g, q))

    def _poll_preview_result(self):
        res = getattr(self, '_preview_result', None)
        if res is not None:
            self._preview_result = None
            seq, mode, payload = res
            if seq == getattr(self, '_preview_build_seq', 0):
                self._apply_preview_result(mode, payload)
        th = getattr(self, '_preview_thread', None)
        if (th is None or not th.is_alive()) and getattr(self, '_preview_result', None) is None:
            try:
                self._preview_poll_timer.stop()
            except Exception:
                pass
            if getattr(self, '_preview_rebuild_pending', False):
                self._preview_rebuild_pending = False
                self._rebuild_preview()

    def _apply_saved_stem_state(self, saved_state):
        if not saved_state:
            return
        try:
            self.cb_use_per_contact_stems.setChecked(bool(saved_state.get('per_contact_enabled', False)))
        except Exception:
            pass
        stem_rows = saved_state.get('stem_rows') or []
        if not stem_rows:
            return
        rows_in_table = self._get_rows(self.stem_table)
        for r, row in enumerate(stem_rows):
            if r >= rows_in_table:
                break
            try:
                l_val, r_val = row[0], row[1]
            except Exception:
                continue
            if l_val is not None:
                self.stem_table.setItem(r, 1, QTableWidgetItem(str(l_val)))
            if r_val is not None:
                self.stem_table.setItem(r, 3, QTableWidgetItem(str(r_val)))

    def populate_form(self, form_layout, param_dict, input_dict):
        for k, v in param_dict.items():
            if k in ['stem_marker_lengths_left', 'stem_marker_lengths_right']:
                continue
            if k == 'gtt_number' or k == 'enable_gtt_label':
                continue  # rendered beside kinetic_depth
            help_text = PARAMETER_HELP.get(k, "")
            label = QLabel("{}  (?)".format(k))
            if help_text:
                label.setToolTip(help_text)
            if isinstance(v, bool):
                cb = QCheckBox()
                cb.setChecked(v)
                if help_text:
                    cb.setToolTip(help_text)
                input_dict[k] = cb
                
                if k == 'enable_kinetic_naming':
                    row_w = QWidget()
                    row_l = QHBoxLayout(row_w)
                    try:
                        row_l.setContentsMargins(0, 0, 0, 0)
                    except Exception:
                        pass
                    row_l.addWidget(cb)
                    
                    self.kinetic_date_edit = QDateEdit()
                    self.kinetic_date_edit.setCalendarPopup(True)
                    self.kinetic_date_edit.setDisplayFormat("MMdd")
                    import datetime
                    t = datetime.date.today()
                    try:
                        if IN_KLAYOUT:
                            self.kinetic_date_edit.date = QDate(t.year, t.month, t.day)
                        else:
                            self.kinetic_date_edit.setDate(QDate(t.year, t.month, t.day))
                    except Exception:
                        pass
                    self.kinetic_date_edit.setEnabled(v)
                    _connect_signal(cb.toggled, self.kinetic_date_edit.setEnabled)
                    
                    row_l.addWidget(QLabel("Date:"))
                    row_l.addWidget(self.kinetic_date_edit)
                    form_layout.addRow(label, row_w)
                else:
                    form_layout.addRow(label, cb)
            elif k == 'single_quadrant_type':
                cb_box = QComboBox()
                cb_box.addItems(["TL", "TR", "BL", "BR"])
                try:
                    cb_box.setCurrentText(str(v))
                except AttributeError:
                    idx = cb_box.findText(str(v))
                    if idx >= 0:
                        cb_box.setCurrentIndex(idx)
                if help_text:
                    cb_box.setToolTip(help_text)
                input_dict[k] = cb_box
                form_layout.addRow(label, cb_box)
            elif k == 'kinetic_depth':
                row_w = QWidget()
                row_l = QHBoxLayout(row_w)
                try:
                    row_l.setContentsMargins(0, 0, 0, 0)
                except Exception:
                    pass
                le = QLineEdit(str(v))
                if help_text:
                    le.setToolTip(help_text)
                input_dict[k] = le
                row_l.addWidget(le)
                enable_gtt = bool(param_dict.get('enable_gtt_label', True))
                gtt_enable_help = PARAMETER_HELP.get('enable_gtt_label', '')
                cb_gtt = QCheckBox("GTT")
                cb_gtt.setChecked(enable_gtt)
                if gtt_enable_help:
                    cb_gtt.setToolTip(gtt_enable_help)
                input_dict['enable_gtt_label'] = cb_gtt
                row_l.addWidget(cb_gtt)
                gtt_help = PARAMETER_HELP.get('gtt_number', '')
                gtt_v = param_dict.get('gtt_number', 1)
                try:
                    gtt_str = f"{int(float(gtt_v)):03d}"
                except Exception:
                    gtt_str = "001"
                gtt_le = QLineEdit(gtt_str)
                try:
                    gtt_le.setMaxLength(3)
                except Exception:
                    pass
                if gtt_help:
                    gtt_le.setToolTip(gtt_help)
                input_dict['gtt_number'] = gtt_le
                row_l.addWidget(gtt_le)
                _connect_signal(cb_gtt.toggled, self._sync_gtt_field_enabled)
                form_layout.addRow(label, row_w)
            else:
                le = QLineEdit(str(v))
                if help_text:
                    le.setToolTip(help_text)
                input_dict[k] = le
                form_layout.addRow(label, le)

    def update_stem_table_wrapper(self, dummy_arg=None):
        self.update_stem_table()

    def _get_text(self, elem):
        try:
            return elem.text if IN_KLAYOUT else elem.text()
        except AttributeError:
            return elem.currentText if IN_KLAYOUT else elem.currentText()

    def _get_rows(self, elem):
        return elem.rowCount if IN_KLAYOUT else elem.rowCount()

    def apply_bulk_paste(self, dummy_arg=None):
        text = self.txt_paste.plainText if IN_KLAYOUT else self.txt_paste.toPlainText()
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        for r, line in enumerate(lines):
            if r >= self._get_rows(self.stem_table): break
            parts = line.replace(',', ' ').split()
            if len(parts) >= 1: self.stem_table.setItem(r, 1, QTableWidgetItem(parts[0]))
            if len(parts) >= 2: self.stem_table.setItem(r, 3, QTableWidgetItem(parts[1]))
            elif len(parts) == 1: self.stem_table.setItem(r, 3, QTableWidgetItem(parts[0]))

    def update_stem_override_ui_state(self, dummy_arg=None):
        enabled = self.cb_use_per_contact_stems.isChecked()
        self.stem_table.setEnabled(enabled)
        self.lbl_paste.setEnabled(enabled)
        self.txt_paste.setEnabled(enabled)
        self.btn_apply_paste.setEnabled(enabled)

    def update_stem_table(self):
        try:
            val_text = self._get_text(self.quad_inputs['num_pairs'])
            num_pairs = int(float(val_text))
        except:
            num_pairs = int(DEFAULT_QUADRANT_PARAMS.get('num_pairs', 32))
            
        current_rows = self._get_rows(self.stem_table)
        if num_pairs > current_rows:
            if IN_KLAYOUT: self.stem_table.rowCount = num_pairs
            else: self.stem_table.setRowCount(num_pairs)
            
            try: default_l = self._get_text(self.quad_inputs['stem_marker_array_coverage_left_um'])
            except: default_l = str(DEFAULT_QUADRANT_PARAMS.get('stem_marker_array_coverage_left_um', 1100.0))
            try: default_r = self._get_text(self.quad_inputs['stem_marker_array_coverage_right_um'])
            except: default_r = str(DEFAULT_QUADRANT_PARAMS.get('stem_marker_array_coverage_right_um', 1300.0))
                
            for r in range(current_rows, num_pairs):
                self.stem_table.setItem(r, 1, QTableWidgetItem(default_l))
                self.stem_table.setItem(r, 3, QTableWidgetItem(default_r))
                
        if num_pairs < current_rows:
            self.stem_table.setRowCount(num_pairs)
            
        for r in range(num_pairs):
            l_lbl, r_lbl = QTableWidgetItem(str(r + 1)), QTableWidgetItem(str(num_pairs + r + 1))
            if not IN_KLAYOUT:
                from PyQt6.QtCore import Qt
                l_lbl.setFlags(l_lbl.flags() & ~Qt.ItemFlag.ItemIsEditable)
                r_lbl.setFlags(r_lbl.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.stem_table.setItem(r, 0, l_lbl)
            self.stem_table.setItem(r, 2, r_lbl)
            
    def on_generate(self, dummy_arg=None):
        import copy
        error_msg = ""
        local_global_params = copy.deepcopy(GLOBAL_PARAMS)
        local_quad_params = copy.deepcopy(DEFAULT_QUADRANT_PARAMS)
        for k, ui_elem in self.global_inputs.items():
            orig_val = GLOBAL_PARAMS.get(k, None)
            if isinstance(orig_val, bool): local_global_params[k] = ui_elem.isChecked()
            elif isinstance(orig_val, list):
                try:
                    t = self._get_text(ui_elem)
                    if k in _GDS_LAYER_LIST_KEYS:
                        local_global_params[k] = _parse_layer_list_ui_text(t, orig_val)
                    else:
                        local_global_params[k] = ast.literal_eval(t)
                except Exception:
                    error_msg += f"Invalid format for {k}\n"
            elif isinstance(orig_val, int):
                try: local_global_params[k] = int(float(self._get_text(ui_elem)))
                except: error_msg += f"Invalid int format for {k}\n"
            elif isinstance(orig_val, float):
                try: local_global_params[k] = float(self._get_text(ui_elem))
                except: error_msg += f"Invalid float format for {k}\n"
            else: local_global_params[k] = self._get_text(ui_elem)
                
        
        for k, ui_elem in self.plasma_inputs.items():
            orig_val = DEFAULT_QUADRANT_PARAMS.get(k, None)
            if isinstance(orig_val, bool): local_quad_params[k] = ui_elem.isChecked()
            elif isinstance(orig_val, list):
                try:
                    t = self._get_text(ui_elem)
                    if k in _GDS_LAYER_LIST_KEYS:
                        local_quad_params[k] = _parse_layer_list_ui_text(t, orig_val)
                    else:
                        local_quad_params[k] = ast.literal_eval(t)
                except Exception:
                    error_msg += f"Invalid format for {k}\n"
            elif isinstance(orig_val, int):
                try: local_quad_params[k] = int(float(self._get_text(ui_elem)))
                except: error_msg += f"Invalid int format for {k}\n"
            elif isinstance(orig_val, float):
                try: local_quad_params[k] = float(self._get_text(ui_elem))
                except: error_msg += f"Invalid float format for {k}\n"
            else: local_quad_params[k] = self._get_text(ui_elem)

        for k, ui_elem in self.quad_inputs.items():
            orig_val = DEFAULT_QUADRANT_PARAMS.get(k, None)
            if isinstance(orig_val, bool): local_quad_params[k] = ui_elem.isChecked()
            elif isinstance(orig_val, list):
                try:
                    t = self._get_text(ui_elem)
                    if k in _GDS_LAYER_LIST_KEYS:
                        local_quad_params[k] = _parse_layer_list_ui_text(t, orig_val)
                    else:
                        local_quad_params[k] = ast.literal_eval(t)
                except Exception:
                    error_msg += f"Invalid format for {k}\n"
            elif isinstance(orig_val, int):
                try: local_quad_params[k] = int(float(self._get_text(ui_elem)))
                except: error_msg += f"Invalid int format for {k}\n"
            elif isinstance(orig_val, float):
                try: local_quad_params[k] = float(self._get_text(ui_elem))
                except: error_msg += f"Invalid float format for {k}\n"
            else: local_quad_params[k] = self._get_text(ui_elem)
                
        if self.cb_use_per_contact_stems.isChecked():
            left_lengths = []
            right_lengths = []
            for r in range(self._get_rows(self.stem_table)):
                try: left_lengths.append(float(self._get_text(self.stem_table.item(r, 1))))
                except: left_lengths.append(DEFAULT_QUADRANT_PARAMS.get('stem_marker_array_coverage_left_um', 1100.0))
                
                try: right_lengths.append(float(self._get_text(self.stem_table.item(r, 3))))
                except: right_lengths.append(DEFAULT_QUADRANT_PARAMS.get('stem_marker_array_coverage_right_um', 1300.0))
                
            local_quad_params['stem_marker_lengths_left'] = left_lengths[::-1]
            local_quad_params['stem_marker_lengths_right'] = right_lengths[::-1]
        else:
            local_quad_params['stem_marker_lengths_left'] = []
            local_quad_params['stem_marker_lengths_right'] = []
        
        _apply_plasma_layer_count_from_global(local_global_params, local_quad_params)
        
        local_params_3d = copy.deepcopy(PARAMS_3D)
        for k, ui_elem in self.params_3d_inputs.items():
            orig_val = PARAMS_3D.get(k, None)
            if isinstance(orig_val, bool):
                local_params_3d[k] = ui_elem.isChecked()
            elif isinstance(orig_val, int):
                try: local_params_3d[k] = int(float(self._get_text(ui_elem)))
                except: error_msg += f"Invalid int format for 3D.{k}\n"
            elif isinstance(orig_val, float):
                try: local_params_3d[k] = float(self._get_text(ui_elem))
                except: error_msg += f"Invalid float format for 3D.{k}\n"
            else:
                local_params_3d[k] = self._get_text(ui_elem)

        if error_msg:
            print("Errors parsing parameters:\n" + error_msg)

        try:
            stem_rows = []
            for r in range(self._get_rows(self.stem_table)):
                try:
                    l_item = self.stem_table.item(r, 1)
                    r_item = self.stem_table.item(r, 3)
                    l_val = self._get_text(l_item) if l_item is not None else None
                    r_val = self._get_text(r_item) if r_item is not None else None
                    stem_rows.append([l_val, r_val])
                except Exception:
                    stem_rows.append([None, None])

            persisted_global = copy.deepcopy(local_global_params)
            persisted_global['sample_name_base'] = ""

            gen_meta = {}
            if isinstance(getattr(self, '_saved_state', None), dict):
                if self._saved_state.get('last_generate_date') is not None:
                    gen_meta['last_generate_date'] = self._saved_state['last_generate_date']
                if self._saved_state.get('last_generate_kinetic_depth') is not None:
                    gen_meta['last_generate_kinetic_depth'] = self._saved_state['last_generate_kinetic_depth']

            _save_gui_state({
                'global_params': persisted_global,
                'quad_params': local_quad_params,
                'params_3d': local_params_3d,
                'per_contact_enabled': bool(self.cb_use_per_contact_stems.isChecked()),
                'stem_rows': stem_rows,
                **gen_meta,
            })
        except Exception as e:
            print(f"Warning: could not persist GUI state: {e}")

        try:
            batch_count = local_global_params.get('batch_production_count', 1)
            batch_count = max(1, min(batch_count, 5)) # cap between 1 and 5

            if not _confirm_kinetic_depth_before_generate(
                    self, local_global_params.get('kinetic_depth', 190.0), self._saved_state):
                print("Generation cancelled.")
                return

            try:
                if hasattr(self, 'kinetic_date_edit'):
                    if IN_KLAYOUT:
                        export_date_mmdd = self.kinetic_date_edit.date.toString("MMdd")
                    else:
                        export_date_mmdd = self.kinetic_date_edit.date().toString("MMdd")
                else:
                    import datetime
                    export_date_mmdd = datetime.datetime.now().strftime("%m%d")
            except Exception:
                import datetime
                export_date_mmdd = datetime.datetime.now().strftime("%m%d")
            local_global_params['_export_date_mmdd'] = export_date_mmdd
            
            base_sample_name = local_global_params.get('sample_name_base', '')
            if local_global_params.get('enable_kinetic_naming', True):
                local_global_params['enable_quadrant_sample_names'] = True
                try:
                    if hasattr(self, 'kinetic_date_edit'):
                        if IN_KLAYOUT:
                            date_str = self.kinetic_date_edit.date.toString("MMdd")
                        else:
                            date_str = self.kinetic_date_edit.date().toString("MMdd")
                    else:
                        import datetime
                        date_str = datetime.datetime.now().strftime("%m%d")
                except Exception:
                    import datetime
                    date_str = datetime.datetime.now().strftime("%m%d")
                    
                w_l1 = int(local_quad_params.get('wire_L1_width', 4))
                enc_off = int(local_quad_params.get('encap_offset', 1))
                w_total = w_l1 + 2 * enc_off
                depth = int(local_global_params.get('kinetic_depth', 190.0))
                num_wires = int(local_quad_params.get('num_wires_per_contact', 1))
                base_sample_name = _build_kinetic_sample_name_base(
                    date_str, w_total, w_l1, depth, num_wires)

            # Mask modes: full-chip DXF only, everything on a single layer.
            mask_jobs = []
            if local_global_params.get('export_etch_mask', False):
                mask_jobs.append((1, 'ETCH'))
            if local_global_params.get('export_gold_mask', False):
                mask_jobs.append((2, 'GOLD'))
            # FULL mask mode: full-chip DXF only (all layers), no GDS, no single outputs.
            full_mask = bool(local_global_params.get('export_full_mask', False))

            for i in range(1, batch_count + 1):
                batch_global_params = copy.deepcopy(local_global_params)
                if batch_count > 1:
                    suffix = f"_{i}"
                    batch_global_params['sample_name_base'] = f"{base_sample_name}{suffix}" if base_sample_name else f"sample{suffix}"
                else:
                    batch_global_params['sample_name_base'] = base_sample_name
                
                print(f"Generating batch {i}/{batch_count} with base name: {batch_global_params.get('sample_name_base', 'sample')}...")
                if mask_jobs or full_mask:
                    for mask_layer, mask_suffix in mask_jobs:
                        mask_params = copy.deepcopy(batch_global_params)
                        print(f"{mask_suffix} mask mode: layer {mask_layer} only, full-chip DXF only.")
                        create_full_chip_design(mask_params, local_quad_params, params_3d=local_params_3d,
                                                mask_layer=mask_layer, mask_suffix=mask_suffix)
                    if full_mask:
                        print("FULL mask mode: full-chip DXF only (all layers, no GDS, no single).")
                        create_full_chip_design(copy.deepcopy(batch_global_params), local_quad_params,
                                                params_3d=local_params_3d, full_dxf_only=True)
                else:
                    create_full_chip_design(batch_global_params, local_quad_params, params_3d=local_params_3d)
                    create_single_quadrant_chip(batch_global_params, local_quad_params, params_3d=local_params_3d)
                
            print(f"Layout Generation Complete! ({batch_count} batches)")

            import datetime
            today = datetime.date.today().isoformat()
            depth_val = int(float(local_global_params.get('kinetic_depth', 190.0)))
            if not isinstance(getattr(self, '_saved_state', None), dict):
                self._saved_state = {}
            self._saved_state['last_generate_date'] = today
            self._saved_state['last_generate_kinetic_depth'] = depth_val
            try:
                state = _load_gui_state()
                if not isinstance(state, dict):
                    state = {}
                state['last_generate_date'] = today
                state['last_generate_kinetic_depth'] = depth_val
                _save_gui_state(state)
            except Exception as e:
                print(f"Warning: could not persist last-generate metadata: {e}")
        except Exception as e:
            print(f"Failed to generate UI output: {str(e)}")


if __name__ == "__main__":
    try:
        app = _get_app()
        main_win = _get_main_win(app)
        dialog = ChipDesignGUI(main_win)
        
        if IN_KLAYOUT:
            dialog.exec_()
        else:
            dialog.exec()
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        # print(f"GUI Failed: deploying layout quietly. Error: {e}")
        GLOBAL_PARAMS['enable_optional_layers'] = True
        create_full_chip_design()
        create_single_quadrant_chip()