"""Deterministic Stage 3B scale benchmark (opt-in, never part of CI)."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import numpy as np

from senti_next.semantic_discovery import (
    HDBSCANDiscoveryBackend,
    SemanticDiscoveryContract,
    SemanticUnitRecord,
    build_semantic_discovery,
)


@dataclass
class TimedBackend:
    delegate: HDBSCANDiscoveryBackend
    calls: int = 0
    elapsed_seconds: float = 0.0

    @property
    def identity(self):
        return self.delegate.identity

    def discover(self, vectors, **kwargs):
        started = time.perf_counter()
        self.calls += 1
        try:
            return self.delegate.discover(vectors, **kwargs)
        finally:
            self.elapsed_seconds += time.perf_counter() - started


def _rss_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD), ("page_fault_count", wintypes.DWORD),
                    ("peak_working_set", ctypes.c_size_t), ("working_set", ctypes.c_size_t),
                    ("quota_peak_paged_pool", ctypes.c_size_t), ("quota_paged_pool", ctypes.c_size_t),
                    ("quota_peak_nonpaged_pool", ctypes.c_size_t), ("quota_nonpaged_pool", ctypes.c_size_t),
                    ("pagefile_usage", ctypes.c_size_t), ("peak_pagefile_usage", ctypes.c_size_t),
                ]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            function = ctypes.windll.psapi.GetProcessMemoryInfo
            function.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
            function.restype = wintypes.BOOL
            if function(handle, ctypes.byref(counters), counters.cb):
                return int(counters.working_set)
        except Exception:
            pass
    try:
        import psutil  # optional local diagnostic only

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        return None


def _fixture(n: int, dimensions: int = 384, units_per_review: int = 1) -> list[SemanticUnitRecord]:
    rng = np.random.default_rng(20260913 + n)
    centers = np.eye(dimensions, dtype=np.float32)[:8]
    vectors = []
    for index in range(n):
        center = centers[index % len(centers)]
        vector = center + rng.normal(0.0, 0.05, size=dimensions).astype(np.float32)
        vector /= np.linalg.norm(vector)
        for unit_index in range(max(1, units_per_review)):
            unit_vector = vector if unit_index == 0 else vector + rng.normal(0.0, 0.01, size=dimensions).astype(np.float32)
            unit_vector /= np.linalg.norm(unit_vector)
            vectors.append(SemanticUnitRecord(f"r{index}:{unit_index}", f"r{index}", unit_index, unit_vector, f"hash-{index}-{unit_index}"))
    return vectors


def run(n: int, units_per_review: int = 1) -> dict[str, object]:
    units = _fixture(n, units_per_review=units_per_review)
    backend = TimedBackend(HDBSCANDiscoveryBackend())
    contract = SemanticDiscoveryContract(min_cluster_size=None, neighbor_k=5, include_unit_level_audit=False)
    rss_before = _rss_bytes()
    started = time.perf_counter()
    report = build_semantic_discovery(
        units,
        semantic_index_id=f"benchmark-{n}",
        research_run_id="benchmark",
        population_fingerprint=f"population-{n}",
        semantic_index_fingerprint=f"index-{n}",
        contract=contract,
        backend=backend,
        population_n_override=n,
    )
    elapsed = time.perf_counter() - started
    rss_after = _rss_bytes()
    return {
        "n": n,
        "units_per_review": units_per_review,
        "semantic_unit_n": len(units),
        "runtime_seconds": round(elapsed, 3),
        "hdbscan_calls": backend.calls,
        "hdbscan_cumulative_seconds": round(backend.elapsed_seconds, 3),
        "peak_rss_bytes": rss_after or rss_before,
        "dense_region_n": report["dense_region_n"],
        "rare_region_n": report["rare_region_n"],
        "outlier_review_n": report["outlier_review_n"],
        "indexed_review_accounted_n": report["indexed_review_n"],
        "status": "pass" if report["indexed_review_n"] == n else "failed_accounting",
        "hardware": platform.platform(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", nargs="+", type=int, default=[1000, 5000, 12000])
    parser.add_argument("--units-per-review", type=int, default=1)
    args = parser.parse_args()
    print(json.dumps({"benchmark": [run(value, args.units_per_review) for value in args.reviews]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
