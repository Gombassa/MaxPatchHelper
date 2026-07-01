import os
import json
import pytest

from assistant.validate import validate_patch

def load_example(relative_path):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(base_dir, relative_path)
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)

def test_validate_sine_generator():
    """Verify that the standard valid sine wave generator patch passes validation."""
    patch_data = load_example("data/example_patches/max/sine_generator.json")
    if "patch" in patch_data:
        patch_data = patch_data["patch"]
    result = validate_patch(patch_data, domain_override="msp")
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    assert result["domain"] == "msp"

def test_validate_audio_effect_volume():
    """Verify that the standard valid M4L volume patch passes validation."""
    patch_data = load_example("data/example_patches/m4l/audio_effect_volume.json")
    if "patch" in patch_data:
        patch_data = patch_data["patch"]
    result = validate_patch(patch_data, domain_override="m4l")
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    assert result["domain"] == "m4l"
    assert result["device_type"] == "audio_effect"

def test_validate_duplicate_ids():
    """Verify that duplicate box IDs are caught as errors."""
    patch_data = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "toggle"}},
                {"box": {"id": "obj-1", "maxclass": "number"}}
            ]
        }
    }
    result = validate_patch(patch_data)
    assert result["valid"] is False
    assert any("Duplicate box ID" in err for err in result["errors"])

def test_validate_invalid_line_references():
    """Verify that lines referencing non-existent box IDs are caught as errors."""
    patch_data = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "toggle"}},
                {"box": {"id": "obj-2", "maxclass": "number"}}
            ],
            "lines": [
                {"patchline": {"source": ["obj-1", 0], "destination": ["obj-99", 0]}}
            ]
        }
    }
    result = validate_patch(patch_data)
    assert result["valid"] is False
    assert any("references non-existent destination box ID: 'obj-99'" in err for err in result["errors"])

def test_validate_m4l_missing_plugin_plugout():
    """Verify that M4L Audio Effect fails if it has UI/live elements but lacks plugin~/plugout~."""
    patch_data = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "live.dial", "parameter_enable": 1, "varname": "dial_1", "saved_attribute_attributes": {"valueof": {"parameter_longname": "Dial1"}}}}
            ]
        }
    }
    result = validate_patch(patch_data, domain_override="m4l")
    # The domain is 'm4l', but it has no plugin~ and no plugout~.
    # It will infer device_type as 'unknown', but if we explicitly test it:
    assert result["device_type"] == "unknown"

def test_validate_m4l_ui_param_constraints():
    """Verify M4L UI dial rules: requires parameter_enable=1, unique varname, unique parameter_longname."""
    # Test duplicate longname
    patch_data = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "live.dial", "parameter_enable": 1, "varname": "dial_1", "saved_attribute_attributes": {"valueof": {"parameter_longname": "SharedName"}}}},
                {"box": {"id": "obj-2", "maxclass": "live.dial", "parameter_enable": 1, "varname": "dial_2", "saved_attribute_attributes": {"valueof": {"parameter_longname": "SharedName"}}}}
            ]
        }
    }
    result = validate_patch(patch_data, domain_override="m4l")
    assert result["valid"] is False
    assert any("duplicate parameter_longname: 'SharedName'" in err for err in result["errors"])

    # Test missing parameter_enable=1
    patch_data_2 = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "live.dial", "parameter_enable": 0, "varname": "dial_1", "saved_attribute_attributes": {"valueof": {"parameter_longname": "Dial1"}}}}
            ]
        }
    }
    result_2 = validate_patch(patch_data_2, domain_override="m4l")
    assert result_2["valid"] is False
    assert any("must have 'parameter_enable' set to 1" in err for err in result_2["errors"])

def test_validate_bounds_checking():
    """Verify that out-of-bounds inlet/outlet index connections are flagged as errors."""
    patch_data = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "newobj", "text": "cycle~", "numinlets": 2, "numoutlets": 1}},
                {"box": {"id": "obj-2", "maxclass": "newobj", "text": "dac~", "numinlets": 2, "numoutlets": 0}}
            ],
            "lines": [
                {"patchline": {"source": ["obj-1", 1], "destination": ["obj-2", 0]}} # obj-1 has only 1 outlet (valid indices: 0). Index 1 is out of bounds!
            ]
        }
    }
    result = validate_patch(patch_data)
    assert result["valid"] is False
    assert any("references out-of-bounds outlet 1 of box 'obj-1'" in err for err in result["errors"])

    # Test out of bounds inlet
    patch_data_inlet = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "newobj", "text": "cycle~", "numinlets": 2, "numoutlets": 1}},
                {"box": {"id": "obj-2", "maxclass": "newobj", "text": "dac~", "numinlets": 2, "numoutlets": 0}}
            ],
            "lines": [
                {"patchline": {"source": ["obj-1", 0], "destination": ["obj-2", 2]}} # obj-2 has only 2 inlets (valid: 0, 1). Index 2 is out of bounds!
            ]
        }
    }
    result_inlet = validate_patch(patch_data_inlet)
    assert result_inlet["valid"] is False
    assert any("references out-of-bounds inlet 2 of box 'obj-2'" in err for err in result_inlet["errors"])


def test_validate_invalid_live_objects():
    """Verify that invalid live.* objects (hallucinations like live.control) are flagged as errors."""
    # Test newobj with text live.control
    patch_data_control = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "newobj", "text": "live.control @parameter_enable 1"}},
                {"box": {"id": "obj-2", "maxclass": "live.dial", "parameter_enable": 1, "varname": "dial_1", "saved_attribute_attributes": {"valueof": {"parameter_longname": "Dial1"}}}}
            ]
        }
    }
    result_control = validate_patch(patch_data_control, domain_override="m4l")
    assert result_control["valid"] is False
    assert any("Invalid object class 'live.control' in box 'obj-1'" in err for err in result_control["errors"])

    # Test direct maxclass live.control
    patch_data_direct = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "live.control"}}
            ]
        }
    }
    result_direct = validate_patch(patch_data_direct, domain_override="m4l")
    assert result_direct["valid"] is False
    assert any("Invalid object class 'live.control' in box 'obj-1'" in err for err in result_direct["errors"])


def test_validate_m4l_object_in_general_domain():
    """Verify M4L-only objects in a patch scoped to general Max/MSP are flagged as
    itemized errors, not silently reclassified to domain 'm4l' with M4L requirements enforced."""
    patch_data = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "newobj", "text": "plugout~", "numinlets": 2, "numoutlets": 0}},
                {"box": {"id": "obj-2", "maxclass": "live.thisdevice", "numinlets": 0, "numoutlets": 2}}
            ]
        }
    }
    result = validate_patch(patch_data, domain_override="msp")
    assert result["valid"] is False
    assert result["domain"] == "msp"
    assert any("M4L-only object 'plugout~'" in err and "remove it" in err for err in result["errors"])
    assert any("M4L-only object 'live.thisdevice'" in err and "remove it" in err for err in result["errors"])
    assert not any("must contain a" in err for err in result["errors"])

def test_validate_m4l_object_in_m4l_domain_unchanged():
    """Verify the same M4L objects are legitimate when the domain actually is 'm4l' —
    guards the existing M4L enforcement path from ever being broken by future edits."""
    patch_data = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "newobj", "text": "plugout~", "numinlets": 2, "numoutlets": 0}},
                {"box": {"id": "obj-2", "maxclass": "live.thisdevice", "numinlets": 0, "numoutlets": 2}}
            ]
        }
    }
    result = validate_patch(patch_data, domain_override="m4l")
    assert result["domain"] == "m4l"
    assert not any("M4L-only object" in err for err in result["errors"])

def test_validate_signal_control_inlet_conflict():
    """Verify that dac~ is flagged when the same inlet receives both a signal-rate
    audio source (cycle~) and a control-rate source (toggle) — they cannot share an inlet."""
    patch_data = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "newobj", "text": "cycle~ 440", "numinlets": 2, "numoutlets": 1}},
                {"box": {"id": "obj-2", "maxclass": "toggle", "numinlets": 1, "numoutlets": 1}},
                {"box": {"id": "obj-3", "maxclass": "newobj", "text": "dac~", "numinlets": 2, "numoutlets": 0}}
            ],
            "lines": [
                {"patchline": {"source": ["obj-1", 0], "destination": ["obj-3", 0]}},
                {"patchline": {"source": ["obj-2", 0], "destination": ["obj-3", 0]}}
            ]
        }
    }
    result = validate_patch(patch_data)
    assert result["valid"] is False
    assert any(
        "Object 'obj-3' (dac~) inlet 0 receives both a signal-rate audio input and a control-rate message" in err
        for err in result["errors"]
    )

def test_validate_m4l_device_type_enforcement():
    """Verify M4L Instrument device-type enforcement: both required anchors (plugout~ and
    a MIDI input object) are checked independently once device_type is classified as 'instrument'."""
    # Sub-case a: MIDI input present, but no plugout~
    patch_missing_plugout = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "newobj", "text": "notein", "numinlets": 0, "numoutlets": 3}}
            ]
        }
    }
    result_a = validate_patch(patch_missing_plugout, domain_override="m4l", device_type_override="instrument")
    assert result_a["valid"] is False
    assert any("M4L Instrument must contain a 'plugout~' object." in err for err in result_a["errors"])

    # Sub-case b: plugout~ present, but no MIDI input object
    patch_missing_midiin = {
        "patcher": {
            "fileversion": 1,
            "boxes": [
                {"box": {"id": "obj-1", "maxclass": "newobj", "text": "plugout~", "numinlets": 2, "numoutlets": 0}}
            ]
        }
    }
    result_b = validate_patch(patch_missing_midiin, domain_override="m4l", device_type_override="instrument")
    assert result_b["valid"] is False
    assert any("M4L Instrument must contain a MIDI input object (like 'midiin' or 'notein')." in err for err in result_b["errors"])


