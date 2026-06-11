"""
topology.py
-----------
Identifies which cells share the same fronthaul link by correlating
packet-loss events across cells.

Algorithm:
1. Load pkt_stats CSVs for all 24 cells.
2. Build a binary loss vector per cell (1 = loss in that slot, 0 = no loss).
3. Compute pairwise Jaccard similarity on loss events.
4. Cluster cells using a threshold: cells in the same cluster share a link.
5. Respect seed constraints: Cell1 → Link2, Cell2 → Link3.
6. Assign clusters to Link1 / Link2 / Link3.

Run standalone:
    python topology.py
"""

import os
import csv
import json
import logging
import itertools
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

CLEAN_DIR = os.path.join(os.path.dirname(__file__), "data", "cleaned")
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")
NUM_CELLS = 24

# Seed constraints from the problem statement
SEEDS = {1: "Link2", 2: "Link3"}  # cell_number → link_name

# Jaccard similarity threshold for "same link"
JACCARD_THRESHOLD = 0.25


def load_loss_vector(cell: int) -> set[int]:
    """Return set of slot indices where packet loss occurred."""
    path = os.path.join(CLEAN_DIR, f"pkt_stats_cell{cell}.csv")
    if not os.path.isfile(path):
        return set()
    loss_slots = set()
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row.get("loss_flag", 0)) == 1:
                loss_slots.add(int(row["slot"]))
    return loss_slots


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_cells(loss_vectors: dict[int, set]) -> list[set[int]]:
    """
    Single-linkage clustering: merge cells whose Jaccard similarity exceeds
    JACCARD_THRESHOLD.
    """
    # Start: each cell in its own cluster
    clusters: list[set[int]] = [{c} for c in loss_vectors]

    merged = True
    while merged:
        merged = False
        new_clusters: list[set[int]] = []
        used = set()
        for i in range(len(clusters)):
            if i in used:
                continue
            group = clusters[i].copy()
            for j in range(i + 1, len(clusters)):
                if j in used:
                    continue
                # Check any member pair
                sim = max(
                    jaccard(loss_vectors[a], loss_vectors[b])
                    for a in clusters[i]
                    for b in clusters[j]
                )
                if sim >= JACCARD_THRESHOLD:
                    group |= clusters[j]
                    used.add(j)
                    merged = True
            new_clusters.append(group)
            used.add(i)
        clusters = new_clusters

    return clusters


def assign_links(clusters: list[set[int]]) -> dict[str, list[int]]:
    """
    Assign each cluster to Link1/Link2/Link3.
    Seed: Cell1→Link2, Cell2→Link3. Remaining clusters → Link1.
    """
    link_map: dict[str, set[int]] = {"Link1": set(), "Link2": set(), "Link3": set()}

    unassigned = []
    for cluster in clusters:
        assigned = False
        for cell, link in SEEDS.items():
            if cell in cluster:
                link_map[link] |= cluster
                assigned = True
                break
        if not assigned:
            unassigned.append(cluster)

    for cluster in unassigned:
        link_map["Link1"] |= cluster

    return {k: sorted(v) for k, v in link_map.items()}


def run_topology() -> dict:
    logging.info("Loading loss vectors…")
    loss_vectors: dict[int, set] = {}
    for cell in range(1, NUM_CELLS + 1):
        lv = load_loss_vector(cell)
        loss_vectors[cell] = lv
        logging.info(f"  Cell {cell:2d}: {len(lv)} loss slots")

    logging.info("Clustering cells by correlated packet loss…")
    clusters = cluster_cells(loss_vectors)
    logging.info(f"Found {len(clusters)} cluster(s): {[sorted(c) for c in clusters]}")

    link_assignment = assign_links(clusters)
    logging.info(f"Link assignment: {link_assignment}")

    # Build similarity matrix for visualization
    cells = list(range(1, NUM_CELLS + 1))
    matrix = {}
    for a in cells:
        matrix[a] = {}
        for b in cells:
            matrix[a][b] = round(jaccard(loss_vectors[a], loss_vectors[b]), 4)

    result = {
        "link_assignment": link_assignment,
        "clusters": [sorted(c) for c in clusters],
        "similarity_matrix": matrix,
    }

    out_path = os.path.join(OUT_DIR, "topology_result.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    logging.info(f"Topology result saved → {out_path}")

    return result


if __name__ == "__main__":
    run_topology()
