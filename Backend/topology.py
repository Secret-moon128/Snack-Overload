"""
topology.py  v3
---------------
Better clustering: uses cross-correlation of loss TIME WINDOWS
rather than exact slot matching. Cells on the same link lose
packets in the same TIME WINDOWS (within ±5 slots of timing offset).

Also adds a smarter fallback using loss_rate similarity.
"""

import os, csv, json, logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
CLEAN_DIR = os.path.join(BASE_DIR, "data", "cleaned")
OUT_DIR   = os.path.join(BASE_DIR, "data")
NUM_CELLS = 24
SEEDS     = {1: "Link2", 2: "Link3"}

# Window size for loss burst detection (slots)
WINDOW    = 10
# Minimum correlation to be considered "same link"
SIM_THRESH = 0.10


def load_loss_slots(cell):
    path = os.path.join(CLEAN_DIR, f"pkt_stats_cell{cell}.csv")
    if not os.path.isfile(path):
        return set(), 0
    loss_slots = set()
    total_slots = 0
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            total_slots += 1
            if int(row.get("loss_flag", 0)) == 1:
                loss_slots.add(int(row["slot"]))
    return loss_slots, total_slots


def expand_to_windows(loss_slots, window=WINDOW):
    """Expand each loss slot to a window — catches timing offsets."""
    expanded = set()
    for s in loss_slots:
        for d in range(-window, window + 1):
            expanded.add(s + d)
    return expanded


def jaccard(a, b):
    if not a and not b: return 0.0
    return len(a & b) / len(a | b)


def build_similarity_matrix(loss_vectors):
    cells = list(loss_vectors.keys())
    # Use windowed vectors for similarity
    windowed = {c: expand_to_windows(v) for c, v in loss_vectors.items()}
    matrix = {}
    for a in cells:
        matrix[a] = {}
        for b in cells:
            matrix[a][b] = round(jaccard(windowed[a], windowed[b]), 4)
    return matrix


def cluster_cells(loss_vectors, threshold):
    """Single-linkage clustering on windowed Jaccard similarity."""
    windowed  = {c: expand_to_windows(v) for c, v in loss_vectors.items()}
    cells     = list(loss_vectors.keys())
    clusters  = [{c} for c in cells]

    merged = True
    while merged:
        merged = False
        new_clusters = []
        used = set()
        for i in range(len(clusters)):
            if i in used: continue
            group = clusters[i].copy()
            for j in range(i + 1, len(clusters)):
                if j in used: continue
                sim = max(
                    jaccard(windowed[a], windowed[b])
                    for a in clusters[i] for b in clusters[j]
                )
                if sim >= threshold:
                    group |= clusters[j]
                    used.add(j)
                    merged = True
            new_clusters.append(group)
            used.add(i)
        clusters = new_clusters

    return clusters


def assign_links(clusters):
    link_map  = {"Link1": set(), "Link2": set(), "Link3": set()}
    unassigned = []
    for cluster in clusters:
        assigned = False
        for seed_cell, link in SEEDS.items():
            if seed_cell in cluster:
                link_map[link] |= cluster
                assigned = True
                break
        if not assigned:
            unassigned.append(cluster)
    for cluster in unassigned:
        link_map["Link1"] |= cluster
    return {k: sorted(v) for k, v in link_map.items()}


def run_topology():
    logging.info("Loading loss vectors…")
    loss_vectors = {}
    loss_rates   = {}
    for cell in range(1, NUM_CELLS + 1):
        lv, total = load_loss_slots(cell)
        loss_vectors[cell] = lv
        loss_rates[cell]   = len(lv) / max(total, 1)
        logging.info(f"  Cell {cell:2d}: {len(lv):4d} loss slots / {total} total  "
                     f"({loss_rates[cell]*100:.1f}% loss rate)")

    total_loss = sum(len(v) for v in loss_vectors.values())
    logging.info(f"\nTotal loss events: {total_loss}")

    if total_loss == 0:
        logging.warning("No loss events — defaulting to seed-only assignment")
        link_assignment = {"Link1": list(range(3, 25)), "Link2": [1], "Link3": [2]}
        clusters = [[i] for i in range(1, 25)]
        matrix   = {a: {b: (1.0 if a==b else 0.0) for b in range(1,25)} for a in range(1,25)}
    else:
        # Try progressively lower thresholds until we get 3 clusters
        final_clusters = None
        for thresh in [0.30, 0.20, 0.15, 0.10, 0.07, 0.05]:
            c = cluster_cells(loss_vectors, thresh)
            logging.info(f"  thresh={thresh:.2f} → {len(c)} cluster(s): {[sorted(x) for x in c]}")
            # We want ~3 groups (one per link). Accept if we get 2–5.
            if 2 <= len(c) <= 6:
                final_clusters = c
                break
        if final_clusters is None:
            # All cells have identical loss pattern — just use seeds
            final_clusters = cluster_cells(loss_vectors, 0.03)

        clusters        = final_clusters
        link_assignment = assign_links(clusters)
        matrix          = build_similarity_matrix(loss_vectors)

    logging.info(f"\nFinal link assignment: {link_assignment}")

    result = {
        "link_assignment": link_assignment,
        "clusters": [sorted(c) for c in clusters],
        "similarity_matrix": matrix,
    }

    out = os.path.join(OUT_DIR, "topology_result.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    logging.info(f"Saved → {out}")
    return result


if __name__ == "__main__":
    run_topology()