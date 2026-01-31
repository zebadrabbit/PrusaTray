"""Test PrusaLink parser implementation."""

import sys
from tray_prusa.adapters import parse_prusalink_state
from tray_prusa.models import PrinterStatus


def test_prusalink_printing():
    """Test PrusaLink response when printing."""
    print("Testing PrusaLink printing state...")
    
    data = {
        "printer": {
            "state": "PRINTING",
            "temp_nozzle": 215.0,
            "temp_bed": 60.0
        },
        "job": {
            "id": 123,
            "progress": 45.5,
            "time_remaining": 1800,
            "time_printing": 900,
            "file": {
                "name": "test_model.gcode"
            }
        }
    }
    
    state = parse_prusalink_state(data)
    
    assert state.status == PrinterStatus.PRINTING, f"Expected PRINTING, got {state.status}"
    assert abs(state.progress - 0.455) < 0.001, f"Expected 0.455, got {state.progress}"
    assert state.eta_seconds == 1800, f"Expected 1800, got {state.eta_seconds}"
    assert state.job_name == "test_model.gcode", f"Expected test_model.gcode, got {state.job_name}"
    assert state.nozzle_temp == 215.0, f"Expected 215.0, got {state.nozzle_temp}"
    assert state.bed_temp == 60.0, f"Expected 60.0, got {state.bed_temp}"
    
    print("✓ PrusaLink printing state parsed correctly")


def test_prusalink_idle():
    """Test PrusaLink response when idle."""
    print("\nTesting PrusaLink idle state...")
    
    data = {
        "printer": {
            "state": "IDLE",
            "temp_nozzle": 25.0,
            "temp_bed": 24.0
        },
        "job": {}
    }
    
    state = parse_prusalink_state(data)
    
    assert state.status == PrinterStatus.IDLE, f"Expected IDLE, got {state.status}"
    assert state.progress is None or state.progress == 0.0, f"Expected None/0, got {state.progress}"
    assert state.job_name is None, f"Expected None, got {state.job_name}"
    assert state.nozzle_temp == 25.0, f"Expected 25.0, got {state.nozzle_temp}"
    
    print("✓ PrusaLink idle state parsed correctly")


def test_prusalink_paused():
    """Test PrusaLink response when paused."""
    print("\nTesting PrusaLink paused state...")
    
    data = {
        "printer": {
            "state": "PAUSED",
            "temp_nozzle": 215.0,
            "temp_bed": 60.0
        },
        "job": {
            "id": 456,
            "progress": 75.0,
            "time_remaining": 600,
            "file": {
                "name": "paused_print.gcode"
            }
        }
    }
    
    state = parse_prusalink_state(data)
    
    assert state.status == PrinterStatus.PAUSED, f"Expected PAUSED, got {state.status}"
    assert abs(state.progress - 0.75) < 0.001, f"Expected 0.75, got {state.progress}"
    assert state.eta_seconds == 600, f"Expected 600, got {state.eta_seconds}"
    
    print("✓ PrusaLink paused state parsed correctly")


def test_prusalink_minimal():
    """Test PrusaLink response with minimal data."""
    print("\nTesting PrusaLink minimal response...")
    
    data = {
        "printer": {
            "state": "READY"
        }
    }
    
    state = parse_prusalink_state(data)
    
    assert state.status == PrinterStatus.IDLE, f"Expected IDLE, got {state.status}"
    assert state.nozzle_temp is None, f"Expected None, got {state.nozzle_temp}"
    assert state.bed_temp is None, f"Expected None, got {state.bed_temp}"
    
    print("✓ PrusaLink minimal response parsed correctly")


def test_prusalink_progress_edge_cases():
    """Test progress clamping."""
    print("\nTesting PrusaLink progress edge cases...")
    
    # Progress > 100
    data = {
        "printer": {"state": "PRINTING"},
        "job": {"progress": 150.0}
    }
    state = parse_prusalink_state(data)
    assert state.progress == 1.0, f"Expected clamped to 1.0, got {state.progress}"
    
    # Progress = 0
    data = {
        "printer": {"state": "PRINTING"},
        "job": {"progress": 0.0}
    }
    state = parse_prusalink_state(data)
    assert state.progress == 0.0, f"Expected 0.0, got {state.progress}"
    
    print("✓ PrusaLink progress clamping works correctly")


def main():
    """Run all tests."""
    print("=" * 60)
    print("PrusaLink Parser Tests")
    print("=" * 60)
    
    try:
        test_prusalink_printing()
        test_prusalink_idle()
        test_prusalink_paused()
        test_prusalink_minimal()
        test_prusalink_progress_edge_cases()
        
        print("\n" + "=" * 60)
        print("✓ All PrusaLink parser tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
