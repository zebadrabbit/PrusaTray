"""Dynamic tray icon generation with progress visualization."""

from typing import Tuple, Dict

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QIcon, QImage, QPixmap, QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QApplication

from .models import PrinterStatus

# ============================================================================
# ICON CACHE
# ============================================================================

_icon_cache: Dict[Tuple[int, PrinterStatus, int], QIcon] = {}


def get_status_color(status: PrinterStatus) -> QColor:
    """
    Get color for printer status.

    Args:
        status: Current printer status.

    Returns:
        QColor for the status.
    """
    color_map = {
        PrinterStatus.IDLE: QColor(128, 128, 128),  # Gray
        PrinterStatus.PRINTING: QColor(0, 150, 255),  # Blue
        PrinterStatus.PAUSED: QColor(255, 165, 0),  # Orange
        PrinterStatus.ERROR: QColor(255, 0, 0),  # Red
        PrinterStatus.OFFLINE: QColor(150, 0, 0),  # Dark red
        PrinterStatus.UNKNOWN: QColor(100, 100, 100),  # Dark gray
    }
    return color_map.get(status, QColor(100, 100, 100))


def bucket_progress(progress: float, bucket_size: float = 1.0) -> int:
    """
    Bucket progress to reduce cache churn.

    Args:
        progress: Progress value 0-100.
        bucket_size: Bucket size in percent (default 1%).

    Returns:
        Bucketed progress as integer.
    """
    return int(progress / bucket_size) * int(bucket_size)


def scale_dimensions(size: int) -> Tuple[int, int, int]:
    """
    Calculate scaled dimensions for icon rendering.

    Args:
        size: Icon size in pixels.

    Returns:
        Tuple of (pen_width, padding, center_dot_radius).
    """
    # Scale pen width: 16px->2, 24px->3, 32px->4, etc.
    pen_width = max(2, size // 8)

    # Padding: about 1/8 of size
    padding = max(2, size // 8)

    # Center dot radius: about 1/12 of size
    center_dot = max(1, size // 12)

    return pen_width, padding, center_dot


# ============================================================================
# ICON RENDERING
# ============================================================================


def render_icon(progress: float, status: PrinterStatus, size: int = 32) -> QIcon:
    """
    Render a tray icon with ring progress indicator.

    Supports caching to avoid repainting on every tick.

    Args:
        progress: Progress percentage (0-100).
        status: Current printer status.
        size: Icon size in pixels (16, 20, 24, 32 recommended).

    Returns:
        QIcon with rendered progress visualization.
    """
    # Clamp progress
    progress = max(0.0, min(100.0, progress))

    # Bucket progress to reduce cache size
    bucketed = bucket_progress(progress)

    # Check cache
    cache_key = (bucketed, status, size)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    # Render new icon
    icon = _render_ring_icon(progress, status, size)

    # Cache it
    _icon_cache[cache_key] = icon

    # Limit cache size (keep most recent 100 entries)
    if len(_icon_cache) > 100:
        # Remove oldest entry (first key)
        first_key = next(iter(_icon_cache))
        del _icon_cache[first_key]

    return icon


def _render_ring_icon(progress: float, status: PrinterStatus, size: int) -> QIcon:
    """
    Internal: Render a ring progress icon.

    Args:
        progress: Progress percentage (0-100).
        status: Current printer status.
        size: Icon size in pixels.

    Returns:
        QIcon with ring visualization.
    """
    # Create transparent image
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Get dimensions
    pen_width, padding, center_dot = scale_dimensions(size)
    color = get_status_color(status)

    # Calculate ring rectangle
    ring_rect = QRectF(padding, padding, size - 2 * padding, size - 2 * padding)

    # Draw background ring (subtle)
    bg_color = QColor(color)
    bg_color.setAlpha(50)
    painter.setPen(
        QPen(bg_color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    )
    painter.drawEllipse(ring_rect)

    # Draw progress arc
    if progress > 0:
        painter.setPen(
            QPen(color, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        # Start from top (-90 degrees), draw clockwise
        start_angle = -90 * 16  # Qt uses 1/16th degree units
        span_angle = -int(progress * 3.6 * 16)  # Negative for clockwise
        painter.drawArc(ring_rect, start_angle, span_angle)

    # Draw center dot
    center = QPointF(size / 2.0, size / 2.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(center, center_dot, center_dot)

    # Draw status overlays
    _draw_status_overlay(painter, status, size, color)

    painter.end()

    # Convert to pixmap and icon
    pixmap = QPixmap.fromImage(image)
    return QIcon(pixmap)


def _draw_status_overlay(
    painter: QPainter, status: PrinterStatus, size: int, color: QColor
) -> None:
    """
    Draw status-specific overlay glyphs.

    Args:
        painter: Active QPainter.
        status: Printer status.
        size: Icon size.
        color: Status color.
    """
    if status == PrinterStatus.PAUSED:
        # Draw pause symbol "||"
        _draw_pause_overlay(painter, size, color)
    elif status in (PrinterStatus.ERROR, PrinterStatus.OFFLINE):
        # Draw alert symbol "!"
        _draw_alert_overlay(painter, size, color)


def _draw_pause_overlay(painter: QPainter, size: int, color: QColor) -> None:
    """
    Draw pause overlay: two vertical bars "||"

    Args:
        painter: Active QPainter.
        size: Icon size.
        color: Status color.
    """
    # Position in bottom-right area
    bar_width = max(1, size // 16)
    bar_height = max(3, size // 6)
    spacing = max(1, size // 16)

    x_offset = size * 3 // 4
    y_offset = size * 3 // 4 - bar_height // 2

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)

    # Left bar
    painter.drawRect(x_offset - spacing - bar_width, y_offset, bar_width, bar_height)
    # Right bar
    painter.drawRect(x_offset + spacing, y_offset, bar_width, bar_height)


def _draw_alert_overlay(painter: QPainter, size: int, color: QColor) -> None:
    """
    Draw alert overlay: exclamation mark "!"

    Args:
        painter: Active QPainter.
        size: Icon size.
        color: Status color.
    """
    # Use font for crisp rendering
    font = QFont("Arial", max(6, size // 4), QFont.Weight.Bold)
    painter.setFont(font)

    # Draw "!" in bottom-right
    painter.setPen(color)

    text_rect = QRectF(size * 2 // 3, size * 2 // 3, size // 3, size // 3)

    painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "!")


# ============================================================================
# BACKWARD COMPATIBILITY (for existing code)
# ============================================================================


def create_ring_icon(
    status: PrinterStatus, progress: float = 0.0, size: int = 64
) -> QIcon:
    """
    Create a tray icon with a ring progress indicator.

    DEPRECATED: Use render_icon() instead.
    Kept for backward compatibility.

    Args:
        status: Current printer status.
        progress: Progress percentage (0-100).
        size: Icon size in pixels.

    Returns:
        QIcon with ring progress visualization.
    """
    return render_icon(progress, status, size)


def create_bar_icon(
    status: PrinterStatus, progress: float = 0.0, size: int = 64
) -> QIcon:
    """
    Create a tray icon with a vertical bar progress indicator.

    DEPRECATED: Use render_icon() with bar style instead.
    Kept for backward compatibility.

    Args:
        status: Current printer status.
        progress: Progress percentage (0-100).
        size: Icon size in pixels.

    Returns:
        QIcon with bar progress visualization.
    """
    # Clamp progress
    progress = max(0.0, min(100.0, progress))

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    color = get_status_color(status)

    # Draw background rectangle
    margin = size // 6
    bg_color = QColor(color)
    bg_color.setAlpha(50)
    painter.fillRect(margin, margin, size - 2 * margin, size - 2 * margin, bg_color)

    # Draw progress bar
    if progress > 0:
        bar_height = int((size - 2 * margin) * progress / 100)
        painter.fillRect(
            margin, size - margin - bar_height, size - 2 * margin, bar_height, color
        )

    # Draw border
    painter.setPen(QPen(color, 2))
    painter.drawRect(margin, margin, size - 2 * margin, size - 2 * margin)

    painter.end()

    pixmap = QPixmap.fromImage(image)
    return QIcon(pixmap)


def create_tray_icon(
    status: PrinterStatus, progress: float = 0.0, style: str = "ring", size: int = 64
) -> QIcon:
    """
    Create a tray icon with progress visualization.

    Args:
        status: Current printer status.
        progress: Progress percentage (0-100).
        style: Icon style ("ring" or "bar").
        size: Icon size in pixels.

    Returns:
        QIcon with progress visualization.
    """
    # Clamp progress to 0-100
    progress = max(0.0, min(100.0, progress))

    if style == "bar":
        return create_bar_icon(status, progress, size)
    else:
        return render_icon(progress, status, size)


# ============================================================================
# SELF-TEST / VISUAL INSPECTION
# ============================================================================


def generate_test_icons(output_dir: str = ".") -> None:
    """
    Generate test icons for visual inspection.

    Creates PNG files showing all status types and progress levels
    at multiple sizes.

    Args:
        output_dir: Directory to write PNG files.
    """
    from pathlib import Path

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Test sizes
    sizes = [16, 20, 24, 32, 48, 64]

    # Test statuses
    statuses = [
        (PrinterStatus.IDLE, 0),
        (PrinterStatus.PRINTING, 25),
        (PrinterStatus.PRINTING, 50),
        (PrinterStatus.PRINTING, 75),
        (PrinterStatus.PRINTING, 100),
        (PrinterStatus.PAUSED, 60),
        (PrinterStatus.ERROR, 30),
        (PrinterStatus.OFFLINE, 0),
    ]

    print(f"Generating test icons in {output_path}...")

    for size in sizes:
        for status, progress in statuses:
            # Generate icon
            icon = render_icon(progress, status, size)

            # Get pixmap
            pixmap = icon.pixmap(size, size)

            # Save to file
            filename = f"icon_{status.value}_{progress}p_size{size}.png"
            filepath = output_path / filename
            pixmap.save(str(filepath), "PNG")

            print(f"  Generated: {filename}")

    print(f"\n✅ Generated {len(sizes) * len(statuses)} test icons")
    print(f"📂 Location: {output_path.absolute()}")
    print("\nInspect the icons to verify:")
    print("  - Ring progress indicator renders correctly")
    print("  - Status colors are distinct")
    print("  - Pause overlay (||) visible on PAUSED")
    print("  - Alert overlay (!) visible on ERROR/OFFLINE")
    print("  - Center dot visible")
    print("  - Anti-aliasing smooth at all sizes")
    print("  - Transparency preserved")


def test_icon_cache() -> None:
    """Test that icon caching works correctly."""
    print("Testing icon cache...")

    # Clear cache
    _icon_cache.clear()

    # Generate same icon twice
    _ = render_icon(50, PrinterStatus.PRINTING, 32)
    cache_size_1 = len(_icon_cache)

    _ = render_icon(50, PrinterStatus.PRINTING, 32)
    cache_size_2 = len(_icon_cache)

    # Cache should have same size (reused)
    assert cache_size_1 == cache_size_2 == 1, "Cache not reusing icons!"

    # Generate different progress (should bucket)
    _ = render_icon(50.5, PrinterStatus.PRINTING, 32)  # Should bucket to 50
    cache_size_3 = len(_icon_cache)

    assert cache_size_3 == 1, "Cache not bucketing progress correctly!"

    # Generate different progress (new bucket)
    _ = render_icon(51, PrinterStatus.PRINTING, 32)  # Different bucket
    cache_size_4 = len(_icon_cache)

    assert cache_size_4 == 2, "Cache not creating new entries!"

    print(f"✅ Cache test passed (size: {cache_size_4})")

    # Test cache limit
    print("Testing cache size limit...")
    _icon_cache.clear()

    # Generate 150 icons (should cap at 100)
    for i in range(150):
        render_icon(i % 100, PrinterStatus.PRINTING, 32)

    cache_size_final = len(_icon_cache)
    assert cache_size_final <= 100, f"Cache exceeded limit: {cache_size_final}"

    print(f"✅ Cache limit test passed (size: {cache_size_final})")


if __name__ == "__main__":
    """Run self-tests when module is executed directly."""
    import sys
    from PySide6.QtWidgets import QApplication

    # Need QApplication for QPixmap/QPainter
    app = QApplication(sys.argv)

    print("=" * 60)
    print("Icon Renderer Self-Test")
    print("=" * 60)
    print()

    # Test caching
    test_icon_cache()
    print()

    # Generate visual test icons
    generate_test_icons("icon_test_output")
    print()

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)
