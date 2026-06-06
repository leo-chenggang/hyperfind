"""
五级文件链接策略
硬链接 > 软链接 > APFS clonefile > 分块复制 > 普通复制
优先零拷贝方案，不额外占用磁盘空间。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def link_file(source: Path, dest: Path) -> str:
    """将源文件链接到目标路径，返回使用的方法名

    优先级链:
    1. hardlink  — 同一卷，零拷贝，共享 inode
    2. symlink   — 跨卷可用
    3. clonefile — macOS APFS 写时复制，近似零拷贝
    4. chunked   — 分块复制 8MB，避免大文件阻塞
    5. copy      — 普通复制（最后手段）
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    for method_name, method_func in _LINK_STRATEGIES:
        try:
            dest.unlink(missing_ok=True)
            if method_func(source, dest):
                return method_name
        except OSError:
            pass

    shutil.copy2(str(source), str(dest))
    return "copy"


def _try_hardlink(src: Path, dst: Path) -> bool:
    os.link(str(src), str(dst))
    return True


def _try_symlink(src: Path, dst: Path) -> bool:
    dst.symlink_to(src.resolve())
    return True


def _try_clonefile(src: Path, dst: Path) -> bool:
    """macOS APFS 写时复制"""
    if sys.platform != "darwin":
        return False
    subprocess.run(
        ["cp", "-c", str(src), str(dst)],
        check=True, capture_output=True, timeout=30,
    )
    return True


def _try_chunked(src: Path, dst: Path) -> bool:
    """分块复制，每块后让出 GIL"""
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            chunk = fsrc.read(CHUNK_SIZE)
            if not chunk:
                break
            fdst.write(chunk)
    return True


_LINK_STRATEGIES = [
    ("hardlink",  _try_hardlink),
    ("symlink",   _try_symlink),
    ("clonefile", _try_clonefile),
    ("chunked_copy", _try_chunked),
]


def is_same_volume(path1: Path, path2: Path) -> bool:
    """检查两个路径是否在同一存储卷上"""
    try:
        return os.stat(str(path1)).st_dev == os.stat(str(path2)).st_dev
    except OSError:
        return False
