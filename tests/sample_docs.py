"""Test document generator for BoardBridge document parsing unit tests."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle


def generate_test_pdf(path: Path) -> Path:
    """Generate a 3-page test PDF with headings, tables, broken words, and a scanned page."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(path), pagesize=letter)

    # --- Page 1 ---
    # Repeated Header
    c.setFont("Helvetica", 9)
    c.drawString(72, 750, "BoardBridge System Documentation")

    # Document Title and Headings
    c.setFont("Helvetica-Bold", 20)
    c.drawString(72, 700, "System Architecture Guide")

    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 660, "Overview and Kernel Initialization")

    # Body with broken word across lines
    c.setFont("Helvetica", 10)
    c.drawString(72, 620, "This document outlines the firmware regu-")
    c.drawString(72, 605, "lation and peripheral management principles.")

    # Standalone page number
    c.setFont("Helvetica", 10)
    c.drawString(72, 100, "Page 1 of 3")

    # Repeated Footer
    c.setFont("Helvetica", 9)
    c.drawString(72, 50, "Confidential - Internal Use Only")
    c.showPage()

    # --- Page 2 ---
    # Repeated Header
    c.setFont("Helvetica", 9)
    c.drawString(72, 750, "BoardBridge System Documentation")

    # Heading
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 700, "Peripheral Fee Structure")

    # Table with numbers
    table_data = [
        ["Service", "Fee (Rs)"],
        ["Cheque book", "150"],
        ["Duplicate statement", "100"],
    ]
    t = Table(table_data, colWidths=[150, 100])
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    t.wrapOn(c, 400, 200)
    t.drawOn(c, 72, 580)

    # Paragraph outside table
    c.setFont("Helvetica", 10)
    c.drawString(72, 530, "Normal paragraph text outside the table describing the peripheral fee structure.")

    # Standalone page number
    c.drawString(72, 100, "- 2 -")

    # Repeated Footer
    c.setFont("Helvetica", 9)
    c.drawString(72, 50, "Confidential - Internal Use Only")
    c.showPage()

    # --- Page 3 (Simulated Scanned Page with Image and < 25 extractable chars) ---
    # Repeated Header
    c.setFont("Helvetica", 9)
    c.drawString(72, 750, "BoardBridge System Documentation")

    # Scanned image with text inside
    img = Image.new("RGB", (400, 150), color="white")
    d = ImageDraw.Draw(img)
    d.text((20, 40), "Scanned Page Document", fill="black")
    d.text((20, 70), "2.1 Fees and Operations", fill="black")

    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)

    c.drawImage(ImageReader(img_buf), 72, 450, width=300, height=120)

    # Repeated Footer
    c.setFont("Helvetica", 9)
    c.drawString(72, 50, "Confidential - Internal Use Only")
    c.showPage()

    c.save()
    return path


def generate_test_html(path: Path) -> Path:
    """Generate an HTML test document with nav, script, footer, headings, table, and Unicode."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Zephyr RTOS Hardware Guide</title>
    <style>
        body { font-family: sans-serif; }
        .hidden { display: none; }
    </style>
    <script>
        function maliciousTracker() { return "bad_code"; }
    </script>
</head>
<body>
    <nav>
        <a href="#overview">Overview</a>
        <a href="#drivers">Drivers</a>
    </nav>
    <header>
        <p>Top Notification Banner</p>
    </header>
    <main>
        <h1>Zephyr RTOS Sensor Architecture</h1>
        <p>The sensor subsystem provides a unified hardware abstraction layer for RTOS drivers.</p>
        <h2>BME280 Driver Implementation</h2>
        <p>This driver communicates via I2C or SPI bus protocols.</p>
        <h3>I2C Bus Configuration</h3>
        <p>Below is the register address mapping table for device initialization.</p>
        <table>
            <thead>
                <tr><th>Register</th><th>Address</th><th>Default</th></tr>
            </thead>
            <tbody>
                <tr><td>CHIP_ID</td><td>0xD0</td><td>0x60</td></tr>
                <tr><td>RESET</td><td>0xE0</td><td>0x00</td></tr>
            </tbody>
        </table>
        <p>Unicode Tamil Support: வணக்கம் Zephyr RTOS</p>
    </main>
    <aside>
        <p>Related Links and advertisements</p>
    </aside>
    <footer>
        <p>&copy; 2026 BoardBridge Systems. All rights reserved.</p>
    </footer>
</body>
</html>
"""
    path.write_bytes(html_content.encode("utf-8"))
    return path
