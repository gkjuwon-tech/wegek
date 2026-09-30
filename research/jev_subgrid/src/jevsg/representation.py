"""The representation A: per-edge crossing counts and normalised positions.

``A_e = (k_e, s_e1, ..., s_ek)`` with ``0 < s_e1 < ... < s_ek < 1`` measured from the
lower node id ``i`` to the higher node id ``j`` of the canonical edge ``(i, j)``
(proposal §2).  Only edges with ``k_e > 0`` are stored (sparse CSR).

This module also holds the representation-level operations the G1 study sweeps over:

* :func:`quantize` — positions as explicit bin choices (proposal §5.4: "위치는 명시적 구간
  선택으로 얻는다"), with strict ordering preserved so ``k`` never silently changes;
* :func:`cap_crossings` — a per-edge cap ``K`` that removes crossings in *pairs*, so the
  even-sum condition of closed surfaces survives (proposal §6: K를 둘 경우 잘린 교차 비율과
  사라진 구조를 보고);
* a compact binary format whose byte count is what we report as "the size of A"
  (header and grid identification included; proposal §7 표현 크기).
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from jevsg.grid import GRID_SCHEME_ID, TetGrid

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class EdgeCoordinates:
    """Sparse A on a :class:`~jevsg.grid.TetGrid` of resolution ``n``."""

    n: int
    edge_ids: IntArray  # (M,) strictly increasing, only edges with k > 0
    offsets: IntArray  # (M + 1,) CSR offsets into ``s``
    s: FloatArray  # (N,) positions, ascending within each edge

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_ids", np.ascontiguousarray(self.edge_ids, dtype=np.int64))
        object.__setattr__(self, "offsets", np.ascontiguousarray(self.offsets, dtype=np.int64))
        object.__setattr__(self, "s", np.ascontiguousarray(self.s, dtype=np.float64))
        if self.offsets.shape != (self.edge_ids.size + 1,):
            raise ValueError("offsets must have len(edge_ids) + 1 entries")
        if self.offsets[0] != 0 or self.offsets[-1] != self.s.size:
            raise ValueError("offsets must start at 0 and end at len(s)")

    # ----------------------------------------------------------- construction
    @staticmethod
    def empty(n: int) -> EdgeCoordinates:
        return EdgeCoordinates(n, np.zeros(0, np.int64), np.zeros(1, np.int64), np.zeros(0))

    @staticmethod
    def from_mapping(n: int, data: Mapping[int, Sequence[float]]) -> EdgeCoordinates:
        items = sorted((int(e), list(v)) for e, v in data.items() if len(v) > 0)
        ids = np.array([e for e, _ in items], dtype=np.int64)
        counts = np.array([len(v) for _, v in items], dtype=np.int64)
        offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
        s = np.array([x for _, v in items for x in v], dtype=np.float64)
        return EdgeCoordinates(n, ids, offsets, s)

    @staticmethod
    def from_hits(n: int, edge_of_hit: npt.ArrayLike, s_of_hit: npt.ArrayLike) -> EdgeCoordinates:
        """Build from an unsorted list of (edge id, position) crossings."""
        e = np.asarray(edge_of_hit, dtype=np.int64)
        s = np.asarray(s_of_hit, dtype=np.float64)
        order = np.lexsort((s, e))
        e, s = e[order], s[order]
        ids, counts = np.unique(e, return_counts=True)
        offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
        return EdgeCoordinates(n, ids, offsets, s)

    # -------------------------------------------------------------- accessors
    @property
    def counts(self) -> IntArray:
        return np.diff(self.offsets)

    @property
    def num_active_edges(self) -> int:
        return int(self.edge_ids.size)

    @property
    def num_crossings(self) -> int:
        return int(self.s.size)

    @property
    def max_k(self) -> int:
        return int(self.counts.max()) if self.edge_ids.size else 0

    def hit_edge_ids(self) -> IntArray:
        """Edge id of every crossing (parallel to ``s``)."""
        return np.repeat(self.edge_ids, self.counts)

    def local_index(self) -> IntArray:
        """0-based index of every crossing within its edge."""
        return np.arange(self.s.size, dtype=np.int64) - np.repeat(self.offsets[:-1], self.counts)

    def get(self, edge_id: int) -> FloatArray:
        pos = int(np.searchsorted(self.edge_ids, edge_id))
        if pos < self.edge_ids.size and self.edge_ids[pos] == edge_id:
            return np.asarray(self.s[self.offsets[pos] : self.offsets[pos + 1]], dtype=np.float64)
        return np.zeros(0, dtype=np.float64)

    def dense_counts(self, num_edges: int) -> IntArray:
        k = np.zeros(num_edges, dtype=np.int64)
        k[self.edge_ids] = self.counts
        return k

    def k_histogram(self) -> dict[int, int]:
        if self.edge_ids.size == 0:
            return {}
        vals, cnt = np.unique(self.counts, return_counts=True)
        return {int(v): int(c) for v, c in zip(vals, cnt, strict=True)}

    def equals(self, other: EdgeCoordinates) -> bool:
        return (
            self.n == other.n
            and np.array_equal(self.edge_ids, other.edge_ids)
            and np.array_equal(self.offsets, other.offsets)
            and np.array_equal(self.s, other.s)
        )


def flip_positions(s: npt.ArrayLike) -> FloatArray:
    """Positions of one edge read in the opposite direction (``1 - s``, re-sorted)."""
    return np.asarray(1.0 - np.asarray(s, dtype=np.float64)[::-1], dtype=np.float64)


# ------------------------------------------------------------------ validation
def validate(a: EdgeCoordinates, grid: TetGrid | None = None) -> list[str]:
    """Structural invariants of A (proposal §5.5: 자료 구조 수준에서 보장). Empty = valid."""
    problems: list[str] = []
    if grid is not None and grid.n != a.n:
        problems.append(f"resolution mismatch: A has n={a.n}, grid has n={grid.n}")
    ids = a.edge_ids
    if ids.size and np.any(np.diff(ids) <= 0):
        problems.append("edge ids are not strictly increasing")
    if ids.size and ids[0] < 0:
        problems.append("negative edge id")
    if grid is not None and ids.size and ids[-1] >= grid.num_edges:
        problems.append("edge id out of range")
    if np.any(a.counts <= 0):
        problems.append("stored edge with k <= 0")
    s = a.s
    if s.size:
        if not np.all(np.isfinite(s)):
            problems.append("non-finite position")
        if np.any(s <= 0.0) or np.any(s >= 1.0):
            problems.append("position outside the open interval (0, 1)")
        same_edge = np.diff(a.hit_edge_ids()) == 0
        if np.any(np.diff(s)[same_edge] <= 0):
            problems.append("positions are not strictly increasing within an edge")
    return problems


def check(a: EdgeCoordinates, grid: TetGrid | None = None) -> None:
    problems = validate(a, grid)
    if problems:
        raise ValueError("invalid edge coordinates: " + "; ".join(problems))


def odd_faces(a: EdgeCoordinates, grid: TetGrid) -> int:
    """Number of tet faces whose three edges carry an odd total number of crossings.

    Zero is necessary for a closed surface (the even-sum condition); a non-zero count
    means the reconstruction will contain open curves / holes near those faces.
    """
    k = a.dense_counts(grid.num_edges)
    total = k[grid.face_edge_ids].sum(axis=1)
    return int(np.count_nonzero(total % 2))


# ---------------------------------------------------------------- quantisation
@dataclass(frozen=True)
class QuantizeStats:
    bits: int
    bins: int
    crossings: int
    bumped: int  # crossings moved off their natural bin to keep strict order
    max_bump_bins: int
    max_abs_error: float  # in edge-length units
    mean_abs_error: float

    def as_dict(self) -> dict[str, float | int]:
        return dict(self.__dict__)


def _group_offsets(a: EdgeCoordinates, big: int) -> IntArray:
    return np.repeat(np.arange(a.edge_ids.size, dtype=np.int64) * big, a.counts)


def quantize_indices(a: EdgeCoordinates, bits: int) -> tuple[IntArray, QuantizeStats]:
    """Bin index ``q in [0, 2**bits)`` per crossing, strictly increasing within each edge.

    A crossing falls in bin ``floor(s * 2**bits)``.  When several crossings of one edge
    share a bin they are pushed to consecutive bins (forward pass), and pulled back if the
    push ran past the last bin (backward cap).  ``k`` is never changed; if an edge has more
    crossings than bins the call fails loudly instead of dropping structure.
    """
    if not 1 <= bits <= 30:
        raise ValueError("bits must be in [1, 30]")
    nbins = 1 << bits
    k = a.counts
    if k.size and int(k.max()) > nbins:
        raise ValueError(f"an edge has {int(k.max())} crossings but only {nbins} bins exist")
    q0 = np.clip(np.floor(a.s * nbins).astype(np.int64), 0, nbins - 1)
    if a.s.size == 0:
        return q0, QuantizeStats(bits, nbins, 0, 0, 0, 0.0, 0.0)
    loc = a.local_index()
    kk = np.repeat(k, k)
    big = nbins + 2 * int(k.max()) + 8
    grp = _group_offsets(a, big)
    fwd = np.maximum.accumulate(q0 - loc + grp) - grp + loc
    cap = nbins - kk + loc  # = nbins - 1 - (k - 1 - loc)
    q = np.minimum(fwd, cap)
    s_hat = (q.astype(np.float64) + 0.5) / nbins
    err = np.abs(s_hat - a.s)
    stats = QuantizeStats(
        bits=bits,
        bins=nbins,
        crossings=int(a.s.size),
        bumped=int(np.count_nonzero(q != q0)),
        max_bump_bins=int(np.max(np.abs(q - q0))),
        max_abs_error=float(err.max()),
        mean_abs_error=float(err.mean()),
    )
    return q, stats


def dequantize(q: npt.ArrayLike, bits: int) -> FloatArray:
    return (np.asarray(q, dtype=np.float64) + 0.5) / float(1 << bits)


def quantize(a: EdgeCoordinates, bits: int) -> tuple[EdgeCoordinates, QuantizeStats]:
    q, stats = quantize_indices(a, bits)
    return EdgeCoordinates(a.n, a.edge_ids, a.offsets, dequantize(q, bits)), stats


# ------------------------------------------------------------------- K capping
@dataclass(frozen=True)
class CapStats:
    cap: int
    edges_over_cap: int
    crossings_dropped: int
    edges_emptied: int

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


def _drop_pairs(s: list[float], target: int) -> list[float]:
    s = list(s)
    while len(s) > target:
        gaps = [s[i + 1] - s[i] for i in range(len(s) - 1)]
        i = min(range(len(gaps)), key=gaps.__getitem__)  # thinnest wall / gap first
        del s[i : i + 2]
    return s


def cap_crossings(a: EdgeCoordinates, cap: int) -> tuple[EdgeCoordinates, CapStats]:
    """Limit every edge to at most ``cap`` crossings, removing them in adjacent pairs.

    Removing pairs keeps every ``k`` parity, hence every face parity: a closed surface
    stays even-sum.  The pair removed is the closest one (the thinnest wall or gap),
    which is exactly the structure a small cap is expected to lose.  ``cap = 1`` turns
    A into the single-crossing (sign-change) representation used as ablation baseline.
    """
    if cap < 1:
        raise ValueError("cap must be >= 1")
    k = a.counts
    over = np.nonzero(k > cap)[0]
    if over.size == 0:
        return a, CapStats(cap, 0, 0, 0)
    data: dict[int, list[float]] = {}
    for row in range(a.edge_ids.size):
        data[int(a.edge_ids[row])] = a.s[a.offsets[row] : a.offsets[row + 1]].tolist()
    dropped = 0
    emptied = 0
    for idx in over.tolist():
        e = int(a.edge_ids[idx])
        kk = int(k[idx])
        target = cap if (kk - cap) % 2 == 0 else cap - 1
        data[e] = _drop_pairs(data[e], target)
        dropped += kk - target
        emptied += int(target == 0)
    out = EdgeCoordinates.from_mapping(a.n, data)
    return out, CapStats(cap, int(over.size), dropped, emptied)


# ------------------------------------------------------------- serialisation
MAGIC = b"SGEA"
FORMAT_VERSION = 1
_HEADER = struct.Struct("<4sBBHBII")


def _encode_varints(values: npt.ArrayLike) -> bytes:
    v = np.asarray(values, dtype=np.uint64)
    if v.size == 0:
        return b""
    nbytes = np.ones(v.size, dtype=np.int64)
    tmp = v >> np.uint64(7)
    while np.any(tmp):
        nbytes += (tmp > 0).astype(np.int64)
        tmp = tmp >> np.uint64(7)
    starts = np.concatenate([[0], np.cumsum(nbytes)[:-1]])
    out = np.zeros(int(nbytes.sum()), dtype=np.uint8)
    for b in range(int(nbytes.max())):
        sel = nbytes > b
        chunk = (v[sel] >> np.uint64(7 * b)) & np.uint64(0x7F)
        more = (nbytes[sel] > b + 1).astype(np.uint64) << np.uint64(7)
        out[starts[sel] + b] = (chunk | more).astype(np.uint8)
    return out.tobytes()


def _decode_varints(buf: bytes, count: int, start: int = 0) -> tuple[npt.NDArray[np.uint64], int]:
    """Decode ``count`` LEB128 varints from ``buf[start:]``; returns values and end offset."""
    if count == 0:
        return np.zeros(0, dtype=np.uint64), start
    raw = np.frombuffer(buf, dtype=np.uint8, offset=start)
    ends = np.nonzero((raw & 0x80) == 0)[0]
    if ends.size < count:
        raise ValueError("truncated varint stream")
    ends = ends[:count]
    used = int(ends[-1]) + 1
    raw = raw[:used]
    value_idx = np.concatenate([[0], np.cumsum((raw[:-1] & 0x80) == 0)])
    starts = np.concatenate([[0], ends[:-1] + 1])
    shift = (np.arange(used) - starts[value_idx]) * 7
    if np.any(shift > 63):
        raise ValueError("varint overflow")
    parts = (raw & 0x7F).astype(np.uint64) << shift.astype(np.uint64)
    vals = np.zeros(count, dtype=np.uint64)
    np.add.at(vals, value_idx, parts)
    return vals, start + used


def to_bytes(a: EdgeCoordinates, bits: int | None = None) -> bytes:
    """Serialise A.  ``bits=None`` stores float64 positions, otherwise ``bits``-bit bins.

    Layout (little endian): header ``magic, version, grid scheme, n, bits, M, N``; then
    edge-id gaps as varints (first id, then ``delta - 1``), ``k - 1`` as varints, then the
    positions.  The grid itself is identified by (scheme, n) and costs no further bytes.
    """
    if a.n >= 1 << 16:
        raise ValueError("resolution does not fit the header")
    ids = a.edge_ids
    gaps = np.concatenate([ids[:1], np.diff(ids) - 1]) if ids.size else ids
    head = _HEADER.pack(MAGIC, FORMAT_VERSION, GRID_SCHEME_ID, a.n, bits or 0, ids.size, a.s.size)
    body = _encode_varints(gaps) + _encode_varints(a.counts - 1)
    if bits is None:
        pos = a.s.astype("<f8").tobytes()
    else:
        q, _ = quantize_indices(a, bits)
        # Re-quantising already-quantised positions is the identity, so decoding gives
        # back exactly ``dequantize(q)``.
        bit_rows = ((q[:, None] >> np.arange(bits - 1, -1, -1)) & 1).astype(np.uint8)
        pos = np.packbits(bit_rows.reshape(-1)).tobytes()
    return head + body + pos


def from_bytes(buf: bytes) -> tuple[EdgeCoordinates, int | None]:
    magic, version, scheme, n, bits, m, total = _HEADER.unpack_from(buf, 0)
    if magic != MAGIC:
        raise ValueError("not an SGEA stream")
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported format version {version}")
    if scheme != GRID_SCHEME_ID:
        raise ValueError(f"unknown grid scheme {scheme}")
    off = _HEADER.size
    gaps, off = _decode_varints(buf, m, off)
    km1, off = _decode_varints(buf, m, off)
    gaps_i = gaps.astype(np.int64)
    ids = np.cumsum(gaps_i + np.concatenate([[0], np.ones(max(m - 1, 0), dtype=np.int64)]))
    counts = km1.astype(np.int64) + 1
    offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    if int(offsets[-1]) != total:
        raise ValueError("crossing count mismatch")
    if bits == 0:
        s = np.frombuffer(buf, dtype="<f8", count=total, offset=off).astype(np.float64)
        end = off + 8 * total
    else:
        nbytes = (total * bits + 7) // 8
        raw = np.frombuffer(buf, dtype=np.uint8, count=nbytes, offset=off)
        bitsarr = np.unpackbits(raw)[: total * bits].reshape(total, bits).astype(np.int64)
        q = bitsarr @ (1 << np.arange(bits - 1, -1, -1, dtype=np.int64))
        s = dequantize(q, bits)
        end = off + nbytes
    if end != len(buf):
        raise ValueError("trailing bytes in SGEA stream")
    return EdgeCoordinates(int(n), ids.astype(np.int64), offsets, s), (None if bits == 0 else bits)


@dataclass(frozen=True)
class SizeReport:
    raw_bytes: int
    zlib_bytes: int
    header_bytes: int
    edge_bytes: int
    position_bytes: int

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


def size_report(a: EdgeCoordinates, bits: int | None = None) -> SizeReport:
    buf = to_bytes(a, bits)
    pos = 8 * a.num_crossings if bits is None else (a.num_crossings * bits + 7) // 8
    return SizeReport(
        raw_bytes=len(buf),
        zlib_bytes=len(zlib.compress(buf, 9)),
        header_bytes=_HEADER.size,
        edge_bytes=len(buf) - _HEADER.size - pos,
        position_bytes=pos,
    )


def concat_positions(chunks: Iterable[FloatArray]) -> FloatArray:
    parts = list(chunks)
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float64)
