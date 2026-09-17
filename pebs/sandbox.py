from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from . import config
from .store import now_iso


class SandboxUnavailable(Exception):
    pass


DEFAULT_REQUIRED = ("filesystem", "network_off", "memory_limit")


@dataclass
class SandboxReport:
    adapter: str
    available: bool
    controls: dict[str, bool] = field(default_factory=dict)
    details: list[str] = field(default_factory=list)
    probed_at: str = ""


def _report_path() -> Path:
    return Path(config.REGISTRY_DIR) / "sandbox_report.json"


def _sandbox_cfg() -> dict[str, Any]:
    return config.SKILLS_SOURCES.get("sandbox", {})


def required_controls() -> tuple[str, ...]:
    controls = _sandbox_cfg().get("required_controls", list(DEFAULT_REQUIRED))
    return tuple(str(c) for c in controls)


class DockerSandbox:
    name = "docker"

    def _cli(self) -> str | None:
        return shutil.which("docker")

    def _run(self, args: Sequence[str], *, timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    def probe(self) -> SandboxReport:
        image = str(_sandbox_cfg().get("docker_image", "alpine:3.20"))
        timeout = int(_sandbox_cfg().get("docker_timeout_seconds", 120))
        cli = self._cli()
        if not cli:
            return SandboxReport(self.name, False, {}, ["未安装 docker CLI"], now_iso())
        info = self._run([cli, "info", "--format", "{{.ServerVersion}}"], timeout=30)
        if info.returncode != 0:
            tail = ((info.stderr or "") + (info.stdout or "")).strip()[-200:]
            return SandboxReport(self.name, False, {}, [f"Docker daemon 不可用：{tail}"], now_iso())
        base = [cli, "run", "--rm", "--network", "none", "--memory", "256m", "--pids-limit", "64"]
        controls: dict[str, bool] = {}
        details: list[str] = []
        try:
            fs = self._run(
                base + [image, "sh", "-c", "if [ -e /mnt/c ] || [ -e /host ] || [ -e /Users ]; then echo FS_LEAK; else echo FS_OK; fi"],
                timeout=timeout,
            )
            controls["filesystem"] = "FS_OK" in (fs.stdout or "")
            details.append("filesystem: " + ("容器无法访问宿主目录" if controls["filesystem"] else "检测到宿主目录可见"))
            net = self._run(
                base + [image, "sh", "-c", "if wget -T 3 -q -O /dev/null http://example.com; then echo NET_LEAK; else echo NET_OK; fi"],
                timeout=timeout,
            )
            controls["network_off"] = "NET_OK" in (net.stdout or "")
            details.append("network_off: " + ("容器无外网" if controls["network_off"] else "容器仍可联网"))
            mem = self._run(
                base + [image, "sh", "-c", "if A=$(yes | head -c 400000000 2>/dev/null); then echo MEM_LEAK; else echo MEM_LIMITED; fi"],
                timeout=timeout,
            )
            mem_output = ((mem.stdout or "") + (mem.stderr or ""))
            controls["memory_limit"] = mem.returncode != 0 or "MEM_LIMITED" in mem_output
            details.append("memory_limit: " + ("超限分配被终止" if controls["memory_limit"] else "内存限制未生效"))
            controls["timeout"] = True
        except subprocess.TimeoutExpired:
            details.append("探测超时（可能 SDK/镜像拉取缓慢）")
        except OSError as exc:
            details.append(f"探测失败：{exc}")
        available = all(controls.get(control, False) for control in required_controls())
        return SandboxReport(self.name, available, controls, details, now_iso())


class SubprocessSandbox:
    name = "subprocess_job"

    def probe(self) -> SandboxReport:
        controls: dict[str, bool] = {}
        details: list[str] = []
        windows = os.name == "nt"
        try:
            fs = subprocess.run(
                [
                    "python",
                    "-c",
                    "import pathlib,sys; sys.exit(0 if pathlib.Path(r'C:\\Windows\\win.ini').exists() else 3)",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            controls["filesystem"] = fs.returncode != 0
            details.append(
                "filesystem: " + ("子进程读不到宿主文件" if controls["filesystem"] else "子进程仍可读取宿主文件（未隔离）")
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            controls["filesystem"] = False
            details.append(f"filesystem 探测失败：{exc}")
        try:
            net = subprocess.run(
                [
                    "python",
                    "-c",
                    "import socket; socket.setdefaulttimeout(3); socket.create_connection(('example.com', 80))",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            controls["network_off"] = net.returncode != 0
            details.append(
                "network_off: " + ("子进程无网络访问" if controls["network_off"] else "子进程仍可访问网络（未隔离）")
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            controls["network_off"] = False
            details.append(f"network 探测失败：{exc}")
        controls["memory_limit"] = self._probe_memory_limit() if windows else False
        details.append(
            "memory_limit: " + ("Job Object 内存上限生效" if controls["memory_limit"] else "无法在主机上强制内存上限")
        )
        available = all(controls.get(control, False) for control in required_controls())
        return SandboxReport(self.name, available, controls, details, now_iso())

    def _probe_memory_limit(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return False

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00000100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
        info.ProcessMemoryLimit = 128 * 1024 * 1024
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(job)
            return False
        proc = subprocess.Popen(
            ["python", "-c", "b = bytearray(400 * 1024 * 1024); print('allocated')"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle)))
        timed_out = False
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
        finally:
            kernel32.CloseHandle(job)
        return (not timed_out) and proc.returncode != 0


def probe_all() -> list[SandboxReport]:
    reports = [DockerSandbox().probe(), SubprocessSandbox().probe()]
    path = _report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(report) for report in reports], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return reports


def load_report(*, refresh: bool = False) -> SandboxReport:
    path = _report_path()
    if not refresh and path.exists():
        try:
            reports = json.loads(path.read_text(encoding="utf-8"))
            if reports:
                best = next((r for r in reports if r.get("available")), reports[0])
                return SandboxReport(
                    best.get("adapter", "unknown"),
                    bool(best.get("available")),
                    best.get("controls", {}),
                    best.get("details", []),
                    best.get("probed_at", ""),
                )
        except (OSError, ValueError):
            pass
    reports = probe_all()
    best = next((r for r in reports if r.available), reports[0])
    return best


def available(*, refresh: bool = False) -> bool:
    return load_report(refresh=refresh).available


def run_sandboxed(
    command: Sequence[str],
    *,
    workdir: Path,
    timeout: int = 120,
    required: Sequence[str] | None = None,
) -> dict[str, Any]:
    report = load_report()
    need = tuple(required or required_controls())
    if not report.available:
        raise SandboxUnavailable(
            "没有通过验证的沙箱适配器（尝试过的适配器："
            + "; ".join(report.details[:2])
            + "）；候选脚本不允许在主机上执行"
        )
    missing = [control for control in need if not report.controls.get(control, False)]
    if missing:
        raise SandboxUnavailable(f"沙箱缺少必需控制：{missing}")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    if report.adapter == "docker":
        cli = shutil.which("docker")
        if not cli:
            raise SandboxUnavailable("docker CLI 消失，请重新探测")
        image = str(_sandbox_cfg().get("docker_image", "alpine:3.20"))
        cmd = [
            cli,
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            "256m",
            "--pids-limit",
            "64",
            "-v",
            f"{workdir}:/work",
            "-w",
            "/work",
            image,
            *command,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
        return {
            "adapter": "docker",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    raise SandboxUnavailable(f"未实现的沙箱适配器：{report.adapter}")
