"""What this Mac can spare right now, read from the kernel rather than guessed.

Two questions are asked here. How many rewrite requests may run at once (a laptop
that swaps finishes later than one that does not), and whether a model may be
loaded at all. The answers come from sysctl and host_statistics64, the same
sources rada uses, because the number that looks like free memory on a
unified-memory Mac is not the number a scheduler may spend: the compressor and
the wired pages are not going to give anything back.

Everything fails open. On an unreadable or non-Darwin machine the caller gets a
usable default and a reason saying the reading was skipped, never a refusal.
"""
from __future__ import annotations

import ctypes
import os
import platform
import subprocess
from dataclasses import dataclass, field

IS_MAC = platform.system() == "Darwin"
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096  # 16384 on Apple Silicon


def _sysctl(name: str) -> str | None:
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _sysctl_int(name: str) -> int | None:
    raw = _sysctl(name)
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


class _VMStat(ctypes.Structure):
    """host_statistics64's vm_statistics64_data_t, as far as the fields we read."""

    _fields_ = [(n, ctypes.c_uint32) for n in (
        "free_count", "active_count", "inactive_count", "wire_count", "zero_fill_count",
        "reactivations", "pageins", "pageouts", "faults", "cow_faults", "lookups", "hits",
        "purges", "purgeable_count", "speculative_count", "decompressions", "compressions",
        "swapins", "swapouts", "compressor_page_count", "throttled_count",
        "external_page_count", "internal_page_count")] + [("total_uncompressed_pages_in_compressor", ctypes.c_uint64)]


def _vm_pages() -> tuple[int, int, int] | None:
    """(wired, compressor, anonymous) pages, or None when the call is unavailable."""
    if not IS_MAC:
        return None
    try:
        libc = ctypes.CDLL("/usr/lib/libSystem.dylib", use_errno=True)
        count = ctypes.c_uint32(ctypes.sizeof(_VMStat) // ctypes.sizeof(ctypes.c_uint32))
        stat = _VMStat()
        rc = libc.host_statistics64(libc.mach_host_self(), 4,  # HOST_VM_INFO64
                                    ctypes.byref(stat), ctypes.byref(count))
        if rc != 0:
            return None
        return stat.wire_count, stat.compressor_page_count, stat.internal_page_count
    except Exception:
        return None


@dataclass
class Machine:
    """What may be spent, and why not more."""

    total: int = 0            # bytes of physical memory
    free_for_work: int = 0    # bytes a new job may claim
    pressure: int = 1         # kernel memory pressure: 1 is normal, 2 warns, 4 is the last one
    swap_used: int = 0
    cores: int = 1            # performance cores if we can tell, else half the logical ones
    workers: int = 1          # how many rewrite requests to keep in flight
    reasons: list[str] = field(default_factory=list)  # sentences, shown verbatim by the app

    def to_dict(self) -> dict:
        return {"total": self.total, "free_for_work": self.free_for_work, "pressure": self.pressure,
                "swap_used": self.swap_used, "cores": self.cores, "workers": self.workers,
                "reasons": list(self.reasons)}


def gib(n: int) -> str:
    return f"{n / 2**30:.1f} GB"


def snapshot(reserve_frac: float = 0.15, reserve_floor: int = 3 * 2**30) -> Machine:
    """Read the machine. Never raises; an unreadable field becomes a reason, not an error."""
    m = Machine()
    m.cores = max((_sysctl_int("hw.perflevel0.logicalcpu") or (os.cpu_count() or 2) // 2), 1)
    m.total = _sysctl_int("hw.memsize") or 0
    if not IS_MAC or not m.total:
        m.workers = max(1, min(4, m.cores // 2))
        m.reasons.append("Memory was not read on this platform, so nothing is being held back.")
        m.free_for_work = m.total
        return m

    pages = _vm_pages()
    if pages is None:
        m.reasons.append("The kernel did not answer the memory call, so nothing is being held back.")
        m.free_for_work = m.total
    else:
        wired, comp, anon = (p * PAGE for p in pages)
        reserve = max(int(m.total * reserve_frac), reserve_floor)
        m.free_for_work = max(0, m.total - reserve - (wired + comp + anon))

    m.pressure = _sysctl_int("kern.memorystatus_vm_pressure_level") or 1
    swap = _sysctl("vm.swapusage") or ""
    for part in swap.split():
        if part.endswith("M") and "used" in swap[: swap.index(part)][-8:]:
            try:
                m.swap_used = int(float(part[:-1]) * 2**20)
            except ValueError:
                pass
            break

    if m.pressure != 1:
        m.reasons.append(f"The kernel says memory pressure is not normal (level {m.pressure}).")
    if m.swap_used > m.total // 2:
        m.reasons.append(f"The machine is {gib(m.swap_used)} deep in swap.")
    if m.free_for_work < 2 * 2**30:
        m.reasons.append(f"Only {gib(m.free_for_work)} is free for new work.")

    # One request per two performance cores, never more than four: the model server is
    # already threaded, and past that point the requests queue inside it anyway.
    m.workers = max(1, min(4, m.cores // 2))
    if m.reasons:
        m.workers = 1
    return m


def can_load(size_bytes: int) -> tuple[bool, str | None]:
    """Whether a model of this size fits, and the sentence to show when it does not."""
    m = snapshot()
    if not IS_MAC or not m.total:
        return True, None
    if m.free_for_work >= size_bytes:
        return True, None
    return False, (f"That model needs {gib(size_bytes)} and only {gib(m.free_for_work)} is free. "
                   + (m.reasons[0] if m.reasons else "Close something and try again."))
