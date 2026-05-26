"""
五级文件链接策略 — 硬链接 > 软链接 > APFS clonefile > 分块复制 > 普通复制
优先使用零拷贝方案，不额外占用磁盘空间。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def link_file(source: Path, dest: Path) -> str:
    """
    将源文件链接到目标路径。返回使用的方法名。

    优先级链:
    1. hardlink  — 同一卷，零拷贝，共享 inode
    2. symlink   — 跨卷可用
    3. clonefile — macOS APFS 写时复制，近似零拷贝
    4. chunked   — 分块复制 (8MB)，避免大文件阻塞
    5. copy      — 普通复制（最后手段）
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    # 1. 硬链接 (同一卷，零拷贝)
    try:
        dest.unlink(missing_ok=True)
        os.link(str(source), str(dest))
        return "hardlink"
    except OSError:
        pass

    # 2. 软链接 (跨卷可用)
    try:
        dest.unlink(missing_ok=True)
        dest.symlink_to(source.resolve())
        return "symlink"
    except OSError:
        pass

    # 3. macOS APFS clonefile (写时复制)
    if sys.platform == "darwin":
        try:
            dest.unlink(missing_ok=True)
            subprocess.run(
                ["cp", "-c", str(source), str(dest)],
                check=True, capture_output=True, timeout=30,
            )
            return "clonefile"
        except Exception:
            pass

    # 4. 分块复制 (8MB 块)
    try:
        dest.unlink(missing_ok=True)
        _chunked_copy(source, dest)
        return "chunked_copy"
    except Exception:
        pass

    # 5. 普通复制
    shutil.copy2(str(source), str(dest))
    return "copy"


def _chunked_copy(src: Path, dst: Path, chunk_size: int = CHUNK_SIZE) -> None:
    """分块复制，每块后让出 GIL"""
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            chunk = fsrc.read(chunk_size)
            if not chunk:
                break
            fdst.write(chunk)


def is_same_volume(path1: Path, path2: Path) -> bool:
    """检查两个路径是否在同一存储卷上"""
    try:
        return os.stat(str(path1)).st_dev == os.stat(str(path2)).st_dev
    except OSError:
        return False
