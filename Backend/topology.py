"""
topology.py  —  fixed for actual slot format
The cleaned pkt_stats CSV has integer slots (1, 2, 3…) already
because data_cleaner converts float slot_raw → int slot via round().
Loss flag = 1 when pkts_lost > 0 OR too_late > 0.
"""

import os, csv, json, logging, glob

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CLEAN_DIR  = os.path.join(BASE_DIR, "data", "cleaned")
OUT_DIR    = os.path.join(BASE_DIR, "data")
NUM_CELLS  = 24
SEEDS      = {1: "Link2", 2: "Link3"}
JACCARD_THRESHOLD = 0.15   # lower threshold — sparse loss events


def load_loss_vector(cell):
    path = os.path.join(CLEAN_DIR, f"pkt_stats_cell{cell}.csv")
    if not os.path.isfile(path):
        return set()
    loss_slots = set()
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if int(row.get("loss_flag", 0)) == 1:
                loss_slots.add(int(row["slot"]))
    return loss_slots


def jaccard(a, b):
    if not a and not b: return 0.0
    return len(a & b) / len(a | b)


def cluster_cells(loss_vectors):
    clusters = [{c} for c in loss_vectors]
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
                    jaccard(loss_vectors[a], loss_vectors[b])
                    for a in clusters[i] for b in clusters[j]
                )
                if sim >= JACCARD_THRESHOLD:
                    group |= clusters[j]
                    used.add(j)
                    merged = True
            new_clusters.append(group)
            used.add(i)
        clusters = new_clusters
    return clusters


def assign_links(clusters):
    link_map = {"Link1": set(), "Link2": set(), "Link3": set()}
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


def run_topology():
    logging.info("Loading loss vectors…")
    loss_vectors = {}
    for cell in range(1, NUM_CELLS + 1):
        lv = load_loss_vector(cell)
        loss_vectors[cell] = lv
        logging.info(f"  Cell {cell:2d}: {len(lv)} loss slots")

    # Check if any losses found at all
    total_loss = sum(len(v) for v in loss_vectors.values())
    logging.info(f"Total loss events across all cells: {total_loss}")

    if total_loss == 0:
        logging.warning("No packet loss events found — using seed-only assignment")
        link_assignment = {"Link1": list(range(3, 25)), "Link2": [1], "Link3": [2]}
        clusters = [[c] for c in range(1, 25)]
        matrix = {a: {b: 1.0 if a == b else 0.0 for b in range(1, 25)} for a in range(1, 25)}
    else:
        logging.info("Clustering cells by correlated packet loss…")
        clusters = cluster_cells(loss_vectors)
        link_assignment = assign_links(clusters)
        cells = list(range(1, NUM_CELLS + 1))
        matrix = {a: {b: round(jaccard(loss_vectors[a], loss_vectors[b]), 4)
                      for b in cells} for a in cells}

    logging.info(f"Link assignment: {link_assignment}")

    result = {
        "link_assignment": link_assignment,
        "clusters": [sorted(c) for c in clusters],
        "similarity_matrix": matrix,
    }

    out_path = os.path.join(OUT_DIR, "topology_result.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    logging.info(f"Saved → {out_path}")
    return result


if __name__ == "__main__":
    run_topology()