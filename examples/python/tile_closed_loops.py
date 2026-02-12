#!/usr/bin/env python3

import json
import xml.etree.ElementTree as ET
from pathlib import Path
import cairosvg

# Configuration
SIZE = 4
TILE_COLUMNS = 12
TILE_ROWS = 13
OUTPUT_NAME = "tiled_closed_loops.png"
MAX_ORIENTATION_PASSES = 50

TILE_SIZE = 11
GAP = 1
MARGIN = 1
ROUND_RADIUS = 1.1
EDGE_BOW = 0.35

STROKE_COLOR = "#2c3e50"
TILE_BG_COLOR = "#f8f8f8"
CANVAS_BG_COLOR = "white"


def find_svg_files(base_path):
    return list(Path(base_path).rglob("*.svg"))


def load_metadata(json_path):
    with open(json_path, "r", encoding="utf-8") as handle:
        records = json.load(handle)

    return {record["id"]: record for record in records}


def get_manhattan(record):
    if "distance" in record:
        return record["distance"]["manhattan"]

    return record["manhattan"]


def get_start_end(record):
    if "position" in record:
        start = record["position"]["start"]
        end = record["position"]["end"]

        return start["x"], start["y"], end["x"], end["y"]

    return record["x"], record["y"], record["end"]["x"], record["end"]["y"]


def grid_to_svg_point(x, y):
    return (2 * x + 0.5, 2 * y + 0.5)


def svg_id_from_path(svg_path):
    return int(svg_path.stem.split("_", 1)[1])


def decode_path(hex_path, path_len):
    value = int(hex_path, 16)
    moves = [0] * path_len

    for idx in range(path_len - 1, -1, -1):
        moves[idx] = value % 4
        value //= 4

    return moves


def get_closing_move(start_x, start_y, end_x, end_y):
    dx = start_x - end_x
    dy = start_y - end_y

    if (dx, dy) == (1, 0):
        return 0

    if (dx, dy) == (0, 1):
        return 1

    if (dx, dy) == (-1, 0):
        return 2

    if (dx, dy) == (0, -1):
        return 3

    return None


def build_loop_points(start_x, start_y, moves):
    deltas = {0: (1, 0), 1: (0, 1), 2: (-1, 0), 3: (0, -1)}
    x = start_x
    y = start_y
    points = [(x, y)]

    for move in moves:
        dx, dy = deltas[move]
        x += dx
        y += dy

        points.append((x, y))

    if len(points) > 1 and points[-1] == points[0]:
        points.pop()

    return points


def grid_points_to_svg(points):
    return [grid_to_svg_point(px, py) for px, py in points]


def polygon_area(points):
    count = len(points)

    area = sum(
        points[idx][0] * points[(idx + 1) % count][1]
        - points[(idx + 1) % count][0] * points[idx][1]
        for idx in range(count)
    )

    return 0.5 * area


def build_rounded_closed_path(points, radius, bow):
    count = len(points)

    if count < 2:
        return ""

    def unit_vector(dx, dy):
        length = max(abs(dx), abs(dy))

        if length == 0:
            return (0.0, 0.0), 0.0

        return (dx / length, dy / length), float(length)

    def is_straight(v1, v2):
        return v1[0] == v2[0] and v1[1] == v2[1]

    def point_str(pt):
        return f"{pt[0]} {pt[1]}"

    path_parts = []

    area = polygon_area(points)
    outward_sign = -1.0 if area > 0 else 1.0

    entries = []
    exits = []
    corners = []

    for index in range(count):
        prev = points[index - 1]
        curr = points[index]
        next_pt = points[(index + 1) % count]
        v1, len1 = unit_vector(curr[0] - prev[0], curr[1] - prev[1])
        v2, len2 = unit_vector(next_pt[0] - curr[0], next_pt[1] - curr[1])
        corner_radius = min(radius, len1 * 0.5, len2 * 0.5)

        if is_straight(v1, v2):
            entries.append(curr)
            exits.append(curr)
            corners.append(False)

            continue

        entry = (curr[0] - v1[0] * corner_radius, curr[1] - v1[1] * corner_radius)
        exit_pt = (curr[0] + v2[0] * corner_radius, curr[1] + v2[1] * corner_radius)
        
        entries.append(entry)
        exits.append(exit_pt)
        corners.append(True)

    path_parts.append(f"M {point_str(exits[0])}")

    for index in range(count):
        next_index = (index + 1) % count
        p0 = exits[index]
        p1 = entries[next_index]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]

        _, segment_len = unit_vector(dx, dy)

        if segment_len > 0 and bow > 0:
            nx = -dy / segment_len * outward_sign
            ny = dx / segment_len * outward_sign
            mx = (p0[0] + p1[0]) * 0.5 + nx * bow
            my = (p0[1] + p1[1]) * 0.5 + ny * bow

            path_parts.append(f"Q {point_str((mx, my))} {point_str(p1)}")

        else:
            path_parts.append(f"L {point_str(p1)}")

        if corners[next_index]:
            corner = points[next_index]

            path_parts.append(f"Q {point_str(corner)} {point_str(exits[next_index])}")

    path_parts.append("Z")

    return " ".join(path_parts)


def d4_transforms(grid_size):
    n = grid_size - 1

    return [
        lambda x, y: (x, y),
        lambda x, y: (n - y, x),
        lambda x, y: (n - x, n - y),
        lambda x, y: (y, n - x),
        lambda x, y: (n - x, y),
        lambda x, y: (x, n - y),
        lambda x, y: (y, x),
        lambda x, y: (n - y, n - x),
    ]


def transform_points(points, transform):
    return [transform(x, y) for x, y in points]


def _point_on_segment(px, py, x1, y1, x2, y2, eps=1e-9):
    if (
        min(x1, x2) - eps <= px <= max(x1, x2) + eps
        and min(y1, y2) - eps <= py <= max(y1, y2) + eps
    ):
        cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)

        return abs(cross) <= eps

    return False


def _point_in_polygon(px, py, polygon):
    inside = False
    count = len(polygon)

    for i in range(count):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % count]

        if _point_on_segment(px, py, x1, y1, x2, y2):
            return True

        intersects = (y1 > py) != (y2 > py)

        if intersects:
            x_at_y = (x2 - x1) * (py - y1) / (y2 - y1) + x1

            if px < x_at_y:
                inside = not inside

    return inside


def points_to_bitmap(points):
    bitmap_size = 5
    bitmap = [[False] * bitmap_size for _ in range(bitmap_size)]

    if not points:
        return bitmap

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    width = max_x - min_x
    height = max_y - min_y

    if width <= 0 or height <= 0:
        return bitmap

    scale_x = width / bitmap_size
    scale_y = height / bitmap_size

    for row in range(bitmap_size):
        for col in range(bitmap_size):
            px = min_x + (col + 0.5) * scale_x
            py = min_y + (row + 0.5) * scale_y

            if _point_in_polygon(px, py, points):
                bitmap[row][col] = True

    return bitmap


def hamming_similarity(bitmap1, bitmap2):
    if not bitmap1 or not bitmap2:
        return 0.0

    total_cells = len(bitmap1) * len(bitmap1[0])
    
    matching_cells = sum(
        cell1 == cell2
        for row1, row2 in zip(bitmap1, bitmap2)
        for cell1, cell2 in zip(row1, row2)
    )

    return matching_cells / total_cells


def similarity_profile(bitmap, other_bitmaps):
    if not other_bitmaps:
        return ()

    similarities = (hamming_similarity(bitmap, other) for other in other_bitmaps)

    return tuple(-value for value in sorted(similarities, reverse=True))


def choose_orientation(points, grid_size, existing_bitmaps):
    _, best_points, best_bitmap = max(
        (
            (similarity_profile(bitmap, existing_bitmaps), transformed, bitmap)
            for transform in d4_transforms(grid_size)
            for transformed in [transform_points(points, transform)]
            for bitmap in [points_to_bitmap(transformed)]
        ),
        key=lambda item: item[0],
    )

    return best_points, best_bitmap


def compute_orientations(
    selected_paths, metadata, grid_size, previous_orientations=None
):
    base_data = []

    for svg_file in selected_paths:
        record_id = svg_id_from_path(svg_file)
        record = metadata.get(record_id)

        if record is None:
            continue

        moves = decode_path(record["path"], record["pathLen"])
        start_x, start_y, end_x, end_y = get_start_end(record)
        closing_move = get_closing_move(start_x, start_y, end_x, end_y)

        if closing_move is None:
            continue

        loop_moves = moves + [closing_move]
        base_points = build_loop_points(start_x, start_y, loop_moves)
    
        base_data.append(base_points)

    if previous_orientations is None:
        previous_orientations = [None] * len(base_data)

    oriented_loops = []
    oriented_bitmaps = []

    identity_transform = d4_transforms(grid_size)[0]
    all_bitmaps = [
        (
            prev_orientation[1]
            if prev_orientation is not None
            else points_to_bitmap(transform_points(base_points, identity_transform))
        )
        for base_points, prev_orientation in zip(base_data, previous_orientations)
    ]

    for idx, base_points in enumerate(base_data):
        other_bitmaps = all_bitmaps[:idx] + all_bitmaps[idx + 1 :]

        oriented_points, bitmap = choose_orientation(
            base_points, grid_size, other_bitmaps
        )

        oriented_loops.append(oriented_points)
        oriented_bitmaps.append(bitmap)
    
        all_bitmaps[idx] = bitmap

    return oriented_loops, oriented_bitmaps


def canonical_loop_signature(moves):
    size = len(moves)

    if size == 0:
        return ()

    rotations = [moves[i:] + moves[:i] for i in range(size)]
    reversed_moves = [((move + 2) % 4) for move in reversed(moves)]
    reversed_rotations = [reversed_moves[i:] + reversed_moves[:i] for i in range(size)]

    candidates = rotations + reversed_rotations

    return min(tuple(candidate) for candidate in candidates)


def apply_matrix(vec, matrix):
    x, y = vec
    a, b, c, d = matrix

    return (a * x + b * y, c * x + d * y)


def transform_moves(moves, matrix):
    dir_to_vec = {
        0: (1, 0),
        1: (0, 1),
        2: (-1, 0),
        3: (0, -1),
    }

    vec_to_dir = {v: k for k, v in dir_to_vec.items()}

    transformed = []

    for move in moves:
        vec = dir_to_vec[move]

        transformed.append(vec_to_dir[apply_matrix(vec, matrix)])

    return transformed


def d4_canonical_signature(moves):
    rotations = [
        (1, 0, 0, 1),
        (0, -1, 1, 0),
        (-1, 0, 0, -1),
        (0, 1, -1, 0),
    ]

    mirror = (-1, 0, 0, 1)

    transforms = rotations[:]

    for matrix in rotations:
        a, b, c, d = matrix
        ma, mb, mc, md = mirror

        transforms.append(
            (a * ma + b * mc, a * mb + b * md, c * ma + d * mc, c * mb + d * md)
        )

    candidates = []

    for matrix in transforms:
        transformed = transform_moves(moves, matrix)

        candidates.append(canonical_loop_signature(transformed))

    return min(candidates)


def create_tiled_png(loop_points, output_path, columns=TILE_COLUMNS, rows=TILE_ROWS):
    canvas_width = MARGIN * 2 + TILE_SIZE * columns + GAP * (columns - 1)
    canvas_height = MARGIN * 2 + TILE_SIZE * rows + GAP * (rows - 1)

    ET.register_namespace("", "http://www.w3.org/2000/svg")

    svg_root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"0 0 {canvas_width} {canvas_height}",
            "width": str(canvas_width * 10),
            "height": str(canvas_height * 10),
        },
    )

    ET.SubElement(
        svg_root,
        "rect",
        {
            "width": str(canvas_width),
            "height": str(canvas_height),
            "fill": CANVAS_BG_COLOR,
        },
    )

    for idx, points in enumerate(loop_points[: columns * rows]):
        x = MARGIN + (idx % columns) * (TILE_SIZE + GAP)
        y = MARGIN + (idx // columns) * (TILE_SIZE + GAP)

        svg_points = grid_points_to_svg(points)
        closed_path = build_rounded_closed_path(svg_points, ROUND_RADIUS, EDGE_BOW)

        if not closed_path:
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
                "d": closed_path,
                "fill": STROKE_COLOR,
                "stroke": STROKE_COLOR,
                "stroke-width": "0.4",
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
            },
        )

    svg_bytes = ET.tostring(svg_root, encoding="utf-8", xml_declaration=True)

    cairosvg.svg2png(bytestring=svg_bytes, write_to=str(output_path))


if __name__ == "__main__":
    base_dir = Path(__file__).parent.parent.parent / str(SIZE)
    json_path = base_dir / f"{SIZE}.json"

    metadata = load_metadata(json_path)
    svg_files = find_svg_files(base_dir)

    representative_by_signature = {}
    moves_by_signature = {}

    for svg_file in svg_files:
        record_id = svg_id_from_path(svg_file)
        record = metadata.get(record_id)

        if record is None:
            continue

        if get_manhattan(record) != 1:
            continue

        moves = decode_path(record["path"], record["pathLen"])
        start_x, start_y, end_x, end_y = get_start_end(record)
        closing_move = get_closing_move(start_x, start_y, end_x, end_y)

        if closing_move is None:
            continue

        loop_moves = moves + [closing_move]
        signature = canonical_loop_signature(loop_moves)

        if signature not in representative_by_signature:
            representative_by_signature[signature] = svg_file
            moves_by_signature[signature] = loop_moves

    representative_by_d4 = {}

    for signature, svg_file in representative_by_signature.items():
        loop_moves = moves_by_signature[signature]
        d4_signature = d4_canonical_signature(loop_moves)

        representative_by_d4.setdefault(d4_signature, svg_file)

    max_tiles = TILE_COLUMNS * TILE_ROWS
    grid_size = SIZE + 2

    selected_paths = sorted(representative_by_d4.values(), key=svg_id_from_path)[
        :max_tiles
    ]

    oriented_loops = []
    oriented_bitmaps = []
    previous_loops = None
    previous_orientations = None

    for _ in range(MAX_ORIENTATION_PASSES):
        new_loops, new_bitmaps = compute_orientations(
            selected_paths, metadata, grid_size, previous_orientations
        )

        if previous_loops is not None and new_loops == previous_loops:
            oriented_loops = new_loops
            oriented_bitmaps = new_bitmaps

            break

        previous_loops = new_loops
        oriented_loops = new_loops
        oriented_bitmaps = new_bitmaps
        previous_orientations = list(zip(new_loops, new_bitmaps))

    ranked_items = sorted(
        (
            (
                similarity_profile(
                    bitmap,
                    oriented_bitmaps[:index] + oriented_bitmaps[index + 1 :],
                ),
                loop_points,
            )
            for index, (bitmap, loop_points) in enumerate(
                zip(oriented_bitmaps, oriented_loops)
            )
        ),
        key=lambda item: item[0],
    )

    oriented_loops = [item[1] for item in ranked_items]
    output_path = Path(__file__).parent / OUTPUT_NAME

    create_tiled_png(oriented_loops, output_path, columns=TILE_COLUMNS, rows=TILE_ROWS)
