import json
import os
from typing import List, Dict, Any, Union, Optional
from pydantic import BaseModel, Field, ValidationError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(BASE_DIR, "data", "inlet_outlet_index.json")

TRUSTED_PORT_COUNTS = {
    "live.dial": (1, 2),
    "live.slider": (1, 2),
    "live.numbox": (1, 2),
    "live.button": (1, 2),
    "live.toggle": (1, 2),
    "live.text": (1, 2),
    "live.menu": (1, 2),
    "live.tab": (1, 2),
    "live.arrows": (1, 2),
    "live.thisdevice": (0, 2),
    "live.path": (1, 2),
    "live.observer": (2, 2),
    "live.object": (2, 2),
    "live.remote~": (2, 1),
    "plugin~": (0, 2),
    "plugout~": (2, 0),
    "dac~": (2, 0),
    "adc~": (0, 2),
    "cycle~": (2, 1),
    "gain~": (1, 2),
    "number": (1, 2),
    "flonum": (1, 2),
    "toggle": (1, 1),
    "button": (1, 1),
    "metro": (2, 1),
}

VALID_LIVE_OBJECTS = {
    "live.dial",
    "live.slider",
    "live.numbox",
    "live.button",
    "live.toggle",
    "live.text",
    "live.menu",
    "live.tab",
    "live.arrows",
    "live.gain~",
    "live.meter~",
    "live.step",
    "live.grid",
    "live.line",
    "live.drop",
    "live.banks",
    "live.comment",
    "live.thisdevice",
    "live.path",
    "live.observer",
    "live.object",
    "live.remote~",
    "live.param~"
}

def get_true_ports(maxclass: str, text: Optional[str] = None) -> tuple:
    """Returns (numinlets, numoutlets) from trusted table or structured index if known."""
    name = maxclass
    if maxclass == "newobj" and text:
        parts = text.strip().split()
        if parts:
            name = parts[0]
            
    if name in TRUSTED_PORT_COUNTS:
        return TRUSTED_PORT_COUNTS[name]
        
    if not os.path.exists(INDEX_PATH):
        return None, None
    try:
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            index_data = json.load(f).get("inlet_outlet_index", {})
        if name in index_data:
            info = index_data[name]
            return len(info.get("inlets", [])), len(info.get("outlets", []))
    except Exception:
        pass
    return None, None

class BoxDetails(BaseModel):
    id: str
    maxclass: str
    text: Optional[str] = None
    numinlets: Optional[int] = None
    numoutlets: Optional[int] = None
    outlettype: Optional[List[str]] = None
    patching_rect: Optional[List[float]] = None
    presentation: Optional[int] = None
    presentation_rect: Optional[List[float]] = None
    varname: Optional[str] = None
    parameter_enable: Optional[int] = None
    saved_attribute_attributes: Optional[Dict[str, Any]] = None
    model_config = {"extra": "allow"}

class BoxWrapper(BaseModel):
    box: BoxDetails

class LineDetails(BaseModel):
    source: List[Union[str, int]]
    destination: List[Union[str, int]]
    model_config = {"extra": "allow"}

class LineWrapper(BaseModel):
    patchline: LineDetails

class PatcherDetails(BaseModel):
    fileversion: int
    rect: Optional[List[float]] = None
    classnamespace: Optional[str] = None
    boxes: List[BoxWrapper]
    lines: Optional[List[LineWrapper]] = Field(default_factory=list)
    model_config = {"extra": "allow"}

class PatchWrapper(BaseModel):
    patcher: PatcherDetails
    model_config = {"extra": "allow"}

def validate_patch(
    patch_data: Union[str, Dict[str, Any]], 
    domain_override: Optional[str] = None,
    device_type_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validates a Max MSP or Max for Live patch JSON structure.
    Supports both raw patcher format and the wrapped assistant format.
    """
    errors = []
    warnings = []
    
    # 1. Parse JSON if string
    if isinstance(patch_data, str):
        try:
            raw_data = json.loads(patch_data)
        except json.JSONDecodeError as e:
            return {
                "valid": False,
                "errors": [f"Invalid JSON syntax: {e}"],
                "warnings": [],
                "domain": "unknown",
                "device_type": "unknown"
            }
    else:
        raw_data = patch_data

    # 2. Check for patcher root key directly on raw_data
    if not isinstance(raw_data, dict) or "patcher" not in raw_data:
        return {
            "valid": False,
            "errors": ["Root object must contain a 'patcher' key. Wrapper keys like 'description', 'domain', or 'patch' are not allowed at the top level."],
            "warnings": [],
            "domain": domain_override or "max",
            "device_type": "unknown"
        }
    
    patch_json = raw_data
    domain = domain_override or "max"

    # 4. Validate structure using Pydantic
    try:
        validated_patch = PatchWrapper.model_validate(patch_json)
    except ValidationError as e:
        for err in e.errors():
            loc_str = " -> ".join(str(l) for l in err["loc"])
            errors.append(f"Pydantic Validation Error at {loc_str}: {err['msg']}")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "domain": domain,
            "device_type": "unknown"
        }

    patcher = validated_patch.patcher
    
    # 5. Extract boxes and lines for validation
    boxes = [b.box for b in patcher.boxes]
    lines = [l.patchline for l in (patcher.lines or [])]
    
    # Map box ID to box object for fast lookup
    box_map = {b.id: b for b in boxes}
    
    # 6. Verify unique box IDs
    seen_ids = set()
    for b in boxes:
        if b.id in seen_ids:
            errors.append(f"Duplicate box ID found: '{b.id}'")
        seen_ids.add(b.id)

    # 6b. Verify box inlet/outlet counts against trusted port counts
    for b in boxes:
        name = b.maxclass
        if b.maxclass == "newobj" and b.text:
            parts = b.text.strip().split()
            if parts:
                name = parts[0]
        # Check for invalid live.* objects (hallucinations)
        if name.startswith("live.") and name not in VALID_LIVE_OBJECTS:
            errors.append(
                f"Invalid object class '{name}' in box '{b.id}'. There is no such object as '{name}' in Max. "
                f"Valid live.* objects are: {', '.join(sorted(VALID_LIVE_OBJECTS))}. "
                f"If you wanted to reference the M4L device, use 'live.thisdevice' or path 'live_set this_device'. "
                f"For LOM controls, use 'live.path', 'live.observer', or 'live.object'."
            )
        if name in TRUSTED_PORT_COUNTS:
            true_inlets, true_outlets = TRUSTED_PORT_COUNTS[name]
            if b.numinlets is not None and b.numinlets != true_inlets:
                errors.append(f"Object '{b.id}' ({name}) should have {true_inlets} inlets, but has {b.numinlets}.")
            if b.numoutlets is not None and b.numoutlets != true_outlets:
                errors.append(f"Object '{b.id}' ({name}) should have {true_outlets} outlets, but has {b.numoutlets}.")

    # 7. Verify line connections (referencing valid box IDs and inlet/outlet bounds)
    for idx, line in enumerate(lines):
        # Validate source
        if not line.source or len(line.source) < 2:
            errors.append(f"Line #{idx} has invalid source list format.")
            continue
        src_id = str(line.source[0])
        src_outlet = line.source[1]
        if src_id not in box_map:
            errors.append(f"Line #{idx} references non-existent source box ID: '{src_id}'")
        else:
            # Check source outlet index bounds
            src_box = box_map[src_id]
            true_inlets, true_outlets = get_true_ports(src_box.maxclass, src_box.text)
            num_outlets = true_outlets if true_outlets is not None else src_box.numoutlets
            if num_outlets is not None and isinstance(src_outlet, int):
                if src_outlet < 0 or src_outlet >= num_outlets:
                    src_name = src_box.maxclass
                    if src_box.maxclass == "newobj" and src_box.text:
                        src_name = src_box.text.strip().split()[0]
                    valid_range = f"0 to {num_outlets - 1}" if num_outlets > 0 else "none (0 outlets)"
                    errors.append(
                        f"Line #{idx} references out-of-bounds outlet {src_outlet} of box '{src_id}' "
                        f"({src_name}) which has only {num_outlets} outlets (valid indices: {valid_range})."
                    )
            
        # Validate destination
        if not line.destination or len(line.destination) < 2:
            errors.append(f"Line #{idx} has invalid destination list format.")
            continue
        dest_id = str(line.destination[0])
        dest_inlet = line.destination[1]
        if dest_id not in box_map:
            errors.append(f"Line #{idx} references non-existent destination box ID: '{dest_id}'")
        else:
            # Check destination inlet index bounds
            dest_box = box_map[dest_id]
            true_inlets, true_outlets = get_true_ports(dest_box.maxclass, dest_box.text)
            num_inlets = true_inlets if true_inlets is not None else dest_box.numinlets
            if num_inlets is not None and isinstance(dest_inlet, int):
                if dest_inlet < 0 or dest_inlet >= num_inlets:
                    dest_name = dest_box.maxclass
                    if dest_box.maxclass == "newobj" and dest_box.text:
                        dest_name = dest_box.text.strip().split()[0]
                    valid_range = f"0 to {num_inlets - 1}" if num_inlets > 0 else "none (0 inlets)"
                    errors.append(
                        f"Line #{idx} references out-of-bounds inlet {dest_inlet} of box '{dest_id}' "
                        f"({dest_name}) which has only {num_inlets} inlets (valid indices: {valid_range})."
                    )

    # 7b. Check for dac~ inlet conflicts (control rate + signal rate sharing the same inlet)
    for b in boxes:
        name = b.maxclass
        if b.maxclass == "newobj" and b.text:
            parts = b.text.strip().split()
            if parts:
                name = parts[0]
        if name == "dac~":
            inlet_sources = {}
            for line in lines:
                if not line.destination or len(line.destination) < 2:
                    continue
                if not line.source or len(line.source) < 2:
                    continue
                dest_id = str(line.destination[0])
                dest_inlet = line.destination[1]
                if dest_id == b.id:
                    src_id = str(line.source[0])
                    if src_id in box_map:
                        src_box = box_map[src_id]
                        inlet_sources.setdefault(dest_inlet, []).append(src_box)
            
            for inlet_idx, srcs in inlet_sources.items():
                if len(srcs) > 1:
                    has_dsp = False
                    has_control = False
                    for s in srcs:
                        s_name = s.maxclass
                        if s.maxclass == "newobj" and s.text:
                            s_parts = s.text.strip().split()
                            if s_parts:
                                s_name = s_parts[0]
                        if s_name.endswith("~") or s_name == "plugin~":
                            has_dsp = True
                        else:
                            has_control = True
                    if has_dsp and has_control:
                        errors.append(
                            f"Object '{b.id}' (dac~) inlet {inlet_idx} receives both a signal-rate audio input "
                            f"and a control-rate message (e.g. toggle/dial/number). They cannot share the same inlet."
                        )

    # Helper to check for object presence (supporting both maxclass and newobj text)
    def has_object(name_or_list) -> bool:
        names = [name_or_list] if isinstance(name_or_list, str) else name_or_list
        for b in boxes:
            if b.maxclass in names:
                return True
            if b.maxclass == "newobj" and b.text:
                parts = b.text.strip().split()
                if parts and parts[0] in names:
                    return True
        return False

    # 8. M4L Domain-Specific Validations
    device_type = device_type_override or "unknown"
    
    # Inferred domain if any live. objects or plugin~/plugout~ are present
    has_live_objects = (
        any(b.maxclass.startswith("live.") for b in boxes) or
        has_object(["plugin~", "plugout~", "live.thisdevice", "live.path", "live.observer", "live.object", "live.remote~"])
    )
    if has_live_objects and domain != "m4l":
        domain = "m4l"
        warnings.append("Patch contains Live API / M4L UI objects. Automatically treating domain as 'm4l'.")

    if domain == "m4l":
        # Check presence of M4L anchors
        has_plugin = has_object("plugin~")
        has_plugout = has_object("plugout~")
        has_midiin = has_object(["midiin", "notein", "ctlin"])
        has_midiout = has_object(["midiout", "noteout", "ctlout"])
        has_thisdevice = has_object("live.thisdevice")
        
        if not has_thisdevice:
            warnings.append("M4L patches should ideally contain a 'live.thisdevice' object for reliable initialization.")
            
        # Infer device type if still unknown:
        if device_type == "unknown":
            if has_plugin and has_plugout:
                device_type = "audio_effect"
            elif has_midiin and has_midiout and not has_plugin:
                device_type = "midi_effect"
            elif has_midiin and has_plugout and not has_plugin:
                device_type = "instrument"
            
        # M4L UI Parameter Constraints
        ui_classes = [
            "live.dial", "live.slider", "live.numbox", "live.button", 
            "live.toggle", "live.tab", "live.arrows", "live.text", 
            "live.menu", "live.gain~"
        ]
        
        seen_longnames = set()
        seen_varnames = set()
        
        for b in boxes:
            if b.maxclass in ui_classes:
                # Check parameter_enable is 1
                if b.parameter_enable != 1:
                    errors.append(f"M4L UI object '{b.id}' ({b.maxclass}) must have 'parameter_enable' set to 1.")
                
                # Check unique varname
                if not b.varname:
                    errors.append(f"M4L UI object '{b.id}' ({b.maxclass}) is missing a 'varname'.")
                else:
                    if b.varname in seen_varnames:
                        errors.append(f"M4L UI object '{b.id}' has duplicate varname: '{b.varname}'")
                    seen_varnames.add(b.varname)
                
                # Check unique parameter_longname
                longname = None
                if b.saved_attribute_attributes and "valueof" in b.saved_attribute_attributes:
                    longname = b.saved_attribute_attributes["valueof"].get("parameter_longname")
                
                if not longname:
                    errors.append(f"M4L UI object '{b.id}' ({b.maxclass}) is missing a 'parameter_longname' under saved attributes.")
                else:
                    if longname in seen_longnames:
                        errors.append(f"M4L UI object '{b.id}' has duplicate parameter_longname: '{longname}'")
                    seen_longnames.add(longname)

        # Enforce device type rules
        if device_type == "audio_effect":
            if not has_plugin:
                errors.append("M4L Audio Effect must contain a 'plugin~' object.")
            if not has_plugout:
                errors.append("M4L Audio Effect must contain a 'plugout~' object.")
        elif device_type == "instrument":
            if not has_plugout:
                errors.append("M4L Instrument must contain a 'plugout~' object.")
            if not has_midiin:
                errors.append("M4L Instrument must contain a MIDI input object (like 'midiin' or 'notein').")
        elif device_type == "midi_effect":
            if not has_midiin:
                errors.append("M4L MIDI Effect must contain a MIDI input object (like 'midiin' or 'notein').")
            if not has_midiout:
                errors.append("M4L MIDI Effect must contain a MIDI output object (like 'midiout' or 'noteout').")

    elif domain == "msp":
        # Check if contains audio-rate objects but no outputs
        has_dsp = any(b.maxclass.endswith("~") for b in boxes)
        has_audio_out = any(b.maxclass in ["dac~", "ezdac~", "plugout~"] for b in boxes)
        if has_dsp and not has_audio_out:
            warnings.append("MSP patch contains audio-rate ('~') objects but no audio output object (like 'dac~' or 'ezdac~').")
            
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "domain": domain,
        "device_type": device_type
    }
