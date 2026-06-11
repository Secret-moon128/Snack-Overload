"""
topology.py
-----------
Identifies which cells share the same Ethernet link by computing
pairwise cross-correlations of their packet-loss time-series.

Key insight from problem statement (Hint 2):
  Cells sharing the same link exhibit correlated packet loss during
  congestion events.

Algorithm:
  1. Build a binary loss vector per cell (1 = slot has packet loss).
  2. Compute pairwise Pearson correlation of loss vectors.
  3. Use hierarchical / agglomerative clustering to group correlated cells.
  4. Apply seed hints (e.g., "cell1 → link2") to label clusters.
  5. Return cluster assignments + correlation matrix for visualisation.
"""

import logging
from typing import Dict, Optional, List, Any

import numpy as np
import pandas as pd
from scipy.spatial.distance import squareform
from scipy.cluster.hierarchy import linkage, fcluster

logger = logging.getLogger(__name__)

# Minimum correlation to consider two cells as sharing a link
CORR_THRESHOLD = 0.25


def _build_loss_matrix(ps_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Align all cells on a common slot index and build a loss-flag matrix.
    Rows = slots, Columns = cell_ids.
    Missing slots are filled with 0 (no loss observed → conservative).
    """
    frames = {}
    for cell_id, df in ps_data.items():
        s = df.set_index("slot_index")["loss_flag"].astype(int)
        frames[cell_id] = s

    matrix = pd.DataFrame(frames)
    matrix = matrix.fillna(0).sort_index()
    return matrix


def _correlation_matrix(loss_matrix: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation between every pair of cell loss vectors."""
    return loss_matrix.corr(method="pearson")


def _cluster_cells(
    corr: pd.DataFrame,
    n_clusters: int,
    seed_hints: Optional[Dict[str, str]],
) -> Dict[str, str]:
    """
    Agglomerative clustering on the correlation distance matrix.
    Returns {cell_id: link_label} mapping.
    """
    cell_ids = list(corr.columns)
    n = len(cell_ids)

    # Distance = 1 - |correlation|  (range 0–1)
    dist_mat = 1.0 - corr.abs().values
    np.fill_diagonal(dist_mat, 0.0)
    dist_mat = np.clip(dist_mat, 0, 1)

    # Condensed form for scipy
    condensed = squareform(dist_mat, checks=False)

    Z = linkage(condensed, method="average")
    labels = fcluster(Z, t=n_clusters, criterion="maxclust")

    assignment = {cell_ids[i]: f"cluster_{labels[i]}" for i in range(n)}

    # ── Apply seed hints to label clusters ──────────────────────────────
    if seed_hints:
        cluster_to_link: Dict[str, str] = {}
        for cell_id, link_label in seed_hints.items():
            cell_key = _normalise_cell_id(cell_id)
            for assigned_cell, cluster in assignment.items():
                if _normalise_cell_id(assigned_cell) == cell_key:
                    cluster_to_link[cluster] = link_label
                    break

        # Rename clusters that have a hint; keep cluster_N for unlabelled
        link_counter = 1
        for cluster in sorted(set(assignment.values())):
            if cluster not in cluster_to_link:
                # Pick a link label not yet used
                while f"link{link_counter}" in cluster_to_link.values():
                    link_counter += 1
                cluster_to_link[cluster] = f"link{link_counter}"
                link_counter += 1

        assignment = {
            cell: cluster_to_link.get(cluster, cluster)
            for cell, cluster in assignment.items()
        }

    return assignment


def _normalise_cell_id(cell_id: str) -> str:
    return cell_id.strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def identify_topology(
    ps_data: Dict[str, pd.DataFrame],
    seed_hints: Optional[Dict[str, str]] = None,
    n_links: int = 3,
) -> Dict[str, Any]:
    """
    Main entry point.

    Parameters
    ----------
    ps_data     : dict of {cell_id: cleaned packet_stats DataFrame}
    seed_hints  : optional dict of {cell_id: "link2"} ground-truth anchors
    n_links     : expected number of distinct links

    Returns
    -------
    {
      "assignment":      {cell_id: link_label, ...},
      "link_cells":      {link_label: [cell_id, ...], ...},
      "correlation":     {cell_id: {cell_id: float, ...}, ...},
      "loss_rate":       {cell_id: float (fraction of slots with loss)},
      "n_links":         int,
    }
    """
    if len(ps_data) < 2:
        raise ValueError("Need at least 2 cells to determine topology.")

    loss_matrix = _build_loss_matrix(ps_data)
    corr        = _correlation_matrix(loss_matrix)

    # Clamp n_clusters to number of available cells
    n_clusters = min(n_links, len(ps_data))
    assignment = _cluster_cells(corr, n_clusters, seed_hints)

    # Invert assignment → link_cells
    link_cells: Dict[str, List[str]] = {}
    for cell, link in assignment.items():
        link_cells.setdefault(link, []).append(cell)

    # Loss rate per cell (fraction of active slots with at least 1 loss)
    loss_rate = {}
    for cell_id, df in ps_data.items():
        active = df[df["lost_pkts"].notna()]
        if len(active) > 0:
            loss_rate[cell_id] = float(active["loss_flag"].mean())
        else:
            loss_rate[cell_id] = 0.0

    # Correlation dict for JSON serialisation
    corr_dict = {
        col: {row: round(float(v), 4) for row, v in corr[col].items()}
        for col in corr.columns
    }

    logger.info(f"Topology identified: {n_clusters} links, "
                f"{len(ps_data)} cells.")
    for link, cells in link_cells.items():
        logger.info(f"  {link}: {cells}")

    return {
        "assignment":  assignment,
        "link_cells":  link_cells,
        "correlation": corr_dict,
        "loss_rate":   loss_rate,
        "n_links":     len(link_cells),
    }