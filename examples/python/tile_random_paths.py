#!/usr/bin/env python3

import random
import xml.etree.ElementTree as ET
from pathlib import Path
import cairosvg

# Configuration
SIZE = 4
GRID_SIZE = 5
TILE_COUNT = GRID_SIZE * GRID_SIZE
OUTPUT_NAME = "tiled_output.png"

TILE_SIZE = 11
GAP = 1
MARGIN = 1

STROKE_COLOR = "#2c3e50"
TILE_BG_COLOR = "#f8f8f8"
CANVAS_BG_COLOR = "white"


def find_svg_files(base_path):
    return list(Path(base_path).rglob("*.svg"))


def load_svg_path(svg_file):
    tree = ET.parse(svg_file)
    root = tree.getroot()

    return root.find(".//{http://www.w3.org/2000/svg}path")


def create_tiled_png(svg_files, output_path, grid_size=GRID_SIZE):
    canvas_size = MARGIN * 2 + TILE_SIZE * grid_size + GAP * (grid_size - 1)

    ET.register_namespace("", "http://www.w3.org/2000/svg")

    svg_root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"0 0 {canvas_size} {canvas_size}",
            "width": str(canvas_size * 10),
            "height": str(canvas_size * 10),
        },
    )

    ET.SubElement(
        svg_root,
        "rect",
        {
            "width": str(canvas_size),
            "height": str(canvas_size),
            "fill": CANVAS_BG_COLOR,
        },
    )

    for idx, svg_file in enumerate(svg_files[: grid_size * grid_size]):
        x = MARGIN + (idx % grid_size) * (TILE_SIZE + GAP)
        y = MARGIN + (idx // grid_size) * (TILE_SIZE + GAP)

        path_elem = load_svg_path(svg_file)

        if path_elem is None:
            continue

        group = ET.SubElement(svg_root, "g", {"transform": f"translate({x}, {y})"})

        ET.SubElement(
            group,
            "rect",
            {"width": str(TILE_SIZE), "height": str(TILE_SIZE), "fill": TILE_BG_COLOR},
        )

        ET.SubElement(
            group,
            "path",
            {
                "d": path_elem.get("d", ""),
                "fill": "none",
                "stroke": STROKE_COLOR,
                "stroke-width": "1",
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
            },
        )

    svg_bytes = ET.tostring(svg_root, encoding="utf-8", xml_declaration=True)

    cairosvg.svg2png(bytestring=svg_bytes, write_to=str(output_path))


if __name__ == "__main__":
    base_dir = Path(__file__).parent.parent.parent / str(SIZE)
    svg_files = find_svg_files(base_dir)
    selected = random.sample(svg_files, TILE_COUNT)
    output_path = Path(__file__).parent / OUTPUT_NAME

    create_tiled_png(selected, output_path)
