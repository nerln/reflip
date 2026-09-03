"""Tests for reflip.mac: no sysctl call is trusted, so none is made for real here.

Every kernel read (`_sysctl`, `_sysctl_int`, `_vm_pages`) is monkeypatched. The point of
this module is that it never raises even when the readings are missing, so most tests
assert a Machine came back with a sentence in `reasons` rather than an exception.
"""
from __future__ import annotations

import subprocess

from reflip import mac


# --------------------------------------------------------------------------- snapshot: fails open

def test_snapshot_never_raises_when_sysctl_binary_is_missing(monkeypatch):
    """sysctl returns nothing at all: subprocess itself fails. Bug this guards: an early
    version let subprocess.run's exception propagate out of snapshot(), which crashed the
    whole `reflip server status` call rather than degrading to "unknown"."""
    def boom(*a, **kw):
        raise FileNotFoundError("sysctl: command not found")

    monkeypatch.setattr(mac.subprocess, "run", boom)
    monkeypatch.setattr(mac, "_vm_pages", lambda: None)
    m = mac.snapshot()  # must not raise
    assert isinstance(m, mac.Machine)
    assert m.workers >= 1
    assert m.reasons, "a machine that could not be read must say so"


def test_snapshot_sysctl_returns_nothing_fails_open_with_reason(monkeypatch):
    """sysctl runs but every value comes back empty (returncode != 0, or blank stdout)."""
    def fake_run(args, capture_output, text, timeout):
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="no such variable")

    monkeypatch.setattr(mac.subprocess, "run", fake_run)
    monkeypatch.setattr(mac, "_vm_pages", lambda: None)
    m = mac.snapshot()
    assert m.total == 0
    assert m.free_for_work == 0
    assert any("not read" in r or "did not answer" in r for r in m.reasons)
    assert 1 <= m.workers <= 4


def test_snapshot_kernel_vm_call_unavailable_still_yields_a_default(monkeypatch):
    """hw.memsize answers but host_statistics64 does not (e.g. a sandboxed process)."""
    values = {"hw.memsize": 16 * 2**30, "hw.perflevel0.logicalcpu": 8,
              "kern.memorystatus_vm_pressure_level": 1}
    monkeypatch.setattr(mac, "_sysctl_int", lambda name: values.get(name))
    monkeypatch.setattr(mac, "_sysctl", lambda name: "" if name == "vm.swapusage" else None)
    monkeypatch.setattr(mac, "_vm_pages", lambda: None)
    monkeypatch.setattr(mac, "IS_MAC", True)
    m = mac.snapshot()
    assert m.total == 16 * 2**30
    assert m.free_for_work == m.total  # nothing held back: the reading was skipped
    assert any("kernel did not answer" in r for r in m.reasons)


def test_snapshot_off_darwin_fails_open(monkeypatch):
    """The whole point of `not IS_MAC`: a Linux CI box must still get a usable default."""
    monkeypatch.setattr(mac, "IS_MAC", False)
    monkeypatch.setattr(mac, "_sysctl_int", lambda name: None)
    monkeypatch.setattr(mac.os, "cpu_count", lambda: 8)
    m = mac.snapshot()
    assert m.total == 0
    assert m.free_for_work == 0
    # cores is already halved once (the performance-cores estimate); workers halves it
    # again, capped at 4: cpu_count 8 -> cores 4 -> workers 2. Getting this formula wrong
    # here once made the test assert 4, not 2; snapshot() itself was correct.
    assert m.cores == 4
    assert m.workers == max(1, min(4, m.cores // 2))
    assert any("platform" in r for r in m.reasons)


# --------------------------------------------------------------------------- snapshot: normal readings

def test_snapshot_computes_free_for_work_from_pages(monkeypatch):
    total = 16 * 2**30
    values = {"hw.memsize": total, "hw.perflevel0.logicalcpu": 8,
              "kern.memorystatus_vm_pressure_level": 1}
    monkeypatch.setattr(mac, "_sysctl_int", lambda name: values.get(name))
    monkeypatch.setattr(mac, "_sysctl", lambda name: "" if name == "vm.swapusage" else None)
    # 100 wired + 50 compressor + 50 anonymous pages, PAGE bytes each: negligible against 16 GB
    monkeypatch.setattr(mac, "_vm_pages", lambda: (100, 50, 50))
    monkeypatch.setattr(mac, "IS_MAC", True)
    m = mac.snapshot()
    reserve = max(int(total * 0.15), 3 * 2**30)
    used = 200 * mac.PAGE
    assert m.free_for_work == max(0, total - reserve - used)
    assert m.workers == max(1, min(4, 8 // 2))
    assert m.reasons == []  # a healthy 16 GB machine gets no held-back sentence


def test_snapshot_memory_pressure_forces_one_worker(monkeypatch):
    total = 16 * 2**30
    values = {"hw.memsize": total, "hw.perflevel0.logicalcpu": 8,
              "kern.memorystatus_vm_pressure_level": 3}
    monkeypatch.setattr(mac, "_sysctl_int", lambda name: values.get(name))
    monkeypatch.setattr(mac, "_sysctl", lambda name: "" if name == "vm.swapusage" else None)
    monkeypatch.setattr(mac, "_vm_pages", lambda: (0, 0, 0))
    monkeypatch.setattr(mac, "IS_MAC", True)
    m = mac.snapshot()
    assert m.pressure == 3
    assert any("pressure" in r for r in m.reasons)
    assert m.workers == 1, "any reason at all drops the machine to one worker"


def test_snapshot_deep_swap_is_reported(monkeypatch):
    total = 16 * 2**30
    values = {"hw.memsize": total, "hw.perflevel0.logicalcpu": 8,
              "kern.memorystatus_vm_pressure_level": 1}
    # Real `sysctl -n vm.swapusage` shape; the parser looks for "used" in the 8 characters
    # before the number it is reading.
    swap = "total = 20480.00M  used = 10240.00M  free = 10240.00M  (encrypted)"

    def fake_sysctl(name):
        return swap if name == "vm.swapusage" else None

    monkeypatch.setattr(mac, "_sysctl_int", lambda name: values.get(name))
    monkeypatch.setattr(mac, "_sysctl", fake_sysctl)
    monkeypatch.setattr(mac, "_vm_pages", lambda: (0, 0, 0))
    monkeypatch.setattr(mac, "IS_MAC", True)
    m = mac.snapshot()
    assert m.swap_used == int(10240.00 * 2**20)
    assert any("deep in swap" in r for r in m.reasons)


def test_snapshot_low_free_memory_is_reported(monkeypatch):
    total = 4 * 2**30
    values = {"hw.memsize": total, "hw.perflevel0.logicalcpu": 4,
              "kern.memorystatus_vm_pressure_level": 1}
    monkeypatch.setattr(mac, "_sysctl_int", lambda name: values.get(name))
    monkeypatch.setattr(mac, "_sysctl", lambda name: "" if name == "vm.swapusage" else None)
    monkeypatch.setattr(mac, "_vm_pages", lambda: (0, 0, 0))  # reserve alone already eats most of it
    monkeypatch.setattr(mac, "IS_MAC", True)
    m = mac.snapshot()
    assert m.free_for_work < 2 * 2**30
    assert any("is free for new work" in r for r in m.reasons)


# --------------------------------------------------------------------------- can_load

def test_can_load_refuses_with_a_sentence(monkeypatch):
    fake = mac.Machine(total=16 * 2**30, free_for_work=2 * 2**30,
                       reasons=["The kernel says memory pressure is not normal (level 3)."])
    monkeypatch.setattr(mac, "snapshot", lambda: fake)
    monkeypatch.setattr(mac, "IS_MAC", True)
    ok, reason = mac.can_load(8 * 2**30)
    assert ok is False
    assert reason is not None and reason.strip()
    assert "8.0 GB" in reason and "2.0 GB" in reason
    assert "pressure is not normal" in reason


def test_can_load_ok_when_it_fits(monkeypatch):
    fake = mac.Machine(total=16 * 2**30, free_for_work=8 * 2**30)
    monkeypatch.setattr(mac, "snapshot", lambda: fake)
    monkeypatch.setattr(mac, "IS_MAC", True)
    ok, reason = mac.can_load(4 * 2**30)
    assert ok is True and reason is None


def test_can_load_refuses_without_a_machine_reason_falls_back(monkeypatch):
    fake = mac.Machine(total=16 * 2**30, free_for_work=1 * 2**30, reasons=[])
    monkeypatch.setattr(mac, "snapshot", lambda: fake)
    monkeypatch.setattr(mac, "IS_MAC", True)
    ok, reason = mac.can_load(9 * 2**30)
    assert ok is False
    assert "Close something and try again." in reason


def test_can_load_always_ok_off_darwin(monkeypatch):
    fake = mac.Machine(total=0, free_for_work=0)
    monkeypatch.setattr(mac, "snapshot", lambda: fake)
    monkeypatch.setattr(mac, "IS_MAC", False)
    ok, reason = mac.can_load(999 * 2**30)
    assert ok is True and reason is None
