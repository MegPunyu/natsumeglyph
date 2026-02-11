#!/usr/bin/env python3

import random
import xml.etree.ElementTree as ET
from pathlib import Path
import cairosvg

# Configuration
SIZE = 4
GRID_SIZE = 5
TILE_COUNT = GRID_SIZE * GRID_SIZE
OUTPUT_TEMPLATE = "tiled_filtered_output_{index}.png"

TILE_SIZE = 11
GAP = 1
MARGIN = 1

STROKE_COLOR = "#2c3e50"
TILE_BG_COLOR = "#f8f8f8"
CANVAS_BG_COLOR = "white"

# Example filters: adjust freely
# - Use sets for exact matches
# - Use None to disable a filter
FILTER_SETS = [
    {
        "sym": {"none"},
        "turns": {10},
        "turnrun": None,
        "longrun": None,
        "maxsegcount": None,
        "minsegcount": None,
        "angle": {0, 2},
        "manhattan": None,
        "signedabs": {6, 7, 8, 9, 10},
        "edge_touch": None,
        "exposure": {"one_exposed_vertex"},
        "turn": None,
    },
    {
        "sym": None,
        "turns": {24, 25, 26},
        "turnrun": {1, 2, 3},
        "longrun": {1, 2},
        "maxsegcount": None,
        "minsegcount": None,
        "angle": None,
        "manhattan": None,
        "signedabs": {0, 1, 2, 3, 4, 5},
        "edge_touch": None,
        "exposure": None,
        "turn": None,
    },
]


def find_svg_files(base_path):
    return list(Path(base_path).rglob("*.svg"))


def load_svg_path(svg_file):
    tree = ET.parse(svg_file)
    root = tree.getroot()

    return root.find(".//{http://www.w3.org/2000/svg}path")


def parse_features(svg_path):
    features = {}
    parts = svg_path.parts

    for part in parts:
        if part.startswith("sym_"):
            features["sym"] = part.split("_", 1)[1]
            continue

        if part.startswith("turns_"):
            features["turns"] = int(part.split("_", 1)[1])
            continue

        if part.startswith("turnrun_"):
            features["turnrun"] = int(part.split("_", 1)[1])
            continue

        if part.startswith("longrun_"):
            features["longrun"] = int(part.split("_", 1)[1])
            continue

        if part.startswith("maxsegcount_"):
            features["maxsegcount"] = int(part.split("_", 1)[1])
            continue

        if part.startswith("minsegcount_"):
            features["minsegcount"] = int(part.split("_", 1)[1])
            continue

        if part.startswith("angle_"):
            features["angle"] = int(part.split("_", 1)[1])
            continue

        if part.startswith("manhattan_"):
            features["manhattan"] = int(part.split("_", 1)[1])
            continue

        if part.startswith("signedabs_"):
            features["signedabs"] = int(part.split("_", 1)[1])
            continue

        if part.startswith("edge_touch_"):
            features["edge_touch"] = int(part.replace("edge_touch_", "", 1))
            continue

        if part.startswith("exposure_"):
            features["exposure"] = part.split("_", 1)[1]
            continue

        if part.startswith("turn_"):
            features["turn"] = part.split("_", 1)[1]
            continue

    return features


def matches_filters(features, filters):
    for key, allowed in filters.items():
        if allowed is None:
            continue

        if key not in features:
            return False

        if features[key] not in allowed:
            return False

    return True


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

    for index, filters in enumerate(FILTER_SETS, start=1):
        filtered = []

        for svg_file in svg_files:
            features = parse_features(svg_file)

            if matches_filters(features, filters):
                filtered.append(svg_file)

        if len(filtered) < TILE_COUNT:
            raise ValueError(
                "Not enough tiles after filtering for set "
                f"{index}: {len(filtered)} < {TILE_COUNT}"
            )

        selected = random.sample(filtered, TILE_COUNT)
        output_path = Path(__file__).parent / OUTPUT_TEMPLATE.format(index=index)

        create_tiled_png(selected, output_path)
