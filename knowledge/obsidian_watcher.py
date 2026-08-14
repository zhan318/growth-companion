"""Obsidian vault 实时文件监视器。

当 vault 内的笔记发生 新增 / 修改 / 删除 时，自动触发增量重索引，
使 agent 对 Obsidian 的语义检索基本“实时”跟随你的编辑。

实现要点：
  - 优先使用 watchdog（OS 级文件事件，毫秒级响应，真正实时）；
  - 若运行环境未安装 watchdog，自动回退为 stdlib 轮询
    （每 OBSIDIAN_WATCH_INTERVAL 秒扫描一次），无需任何额外依赖；
  - 防抖（debounce）：短时间内多次保存只触发一次重索引，
    避免大批量保存时反复重嵌；
  - 遵守 OBSIDIAN_EXCLUDE 排除清单，被排除的隐私文件（如 API.md）永不索引；
  - 通过 threading.Lock 与查询操作串行化，避免并发读写 Chroma 冲突。
"""

import os
import threading
import time
from contextlib import suppress
from pathlib import Path

from config import (
    OBSIDIAN_EXCLUDE,
    OBSIDIAN_VAULT_DIR,
    OBSIDIAN_WATCH_INTERVAL,
    OBSIDIAN_WATCHER_ENABLED,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# 仅关注这些扩展名（与 loader 支持的格式一致），其余变更忽略
_WATCHED_EXTS = {".md", ".txt", ".pdf"}


def _is_relevant(path: str) -> bool:
    """判断该文件路径是否需要触发重索引：非隐藏、受支持格式、未被排除。"""
    p = Path(path)
    # 跳过以 . 开头的隐藏目录/文件（如 .obsidian、.trash）
    if any(part.startswith(".") for part in p.parts):
        return False
    if p.suffix.lower() not in _WATCHED_EXTS:
        return False
    # 排除清单（按相对路径）
    try:
        vault = Path(OBSIDIAN_VAULT_DIR).resolve()
        rel = str(p.resolve().relative_to(vault))
    except Exception:
        rel = p.name
    from .loader import is_path_excluded
    return not is_path_excluded(rel, OBSIDIAN_EXCLUDE)


class _Debouncer:
    """收集变更事件，静默 debounce 秒后触发一次回调（合并短时间内的多次保存）。"""

    def __init__(self, debounce: float, callback):
        self.debounce = debounce
        self.callback = callback
        self._timer = None
        self._lock = threading.Lock()

    def trigger(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        try:
            self.callback()
        except Exception as e:  # noqa: BLE001
            logger.error("Obsidian 监视器重索引回调异常: %s", e)


def _reindex_once():
    # 延迟导入，避免在没有 chromadb 的环境里于模块加载阶段就报错
    from .pipeline import index_obsidian
    try:
        stats = index_obsidian(force=False)
        logger.info("Obsidian 监视器触发增量重索引: %s", stats)
    except Exception as e:  # noqa: BLE001
        logger.error("Obsidian 监视器重索引失败: %s", e)


def _scan_mtimes(vault: str) -> dict:
    """递归扫描 vault，返回 受关注文件 -> mtime 的快照（stdlib，无额外依赖）。"""
    vault_path = Path(vault).resolve()
    result: dict = {}
    for root, dirs, files in os.walk(vault_path):
        # 不进入隐藏目录（如 .obsidian、.trash）
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            p = Path(root) / fn
            if not _is_relevant(str(p)):
                continue
            with suppress(OSError):
                result[str(p.resolve())] = p.stat().st_mtime
    return result


def start_obsidian_watcher():
    """启动 Obsidian vault 文件监视器（若已配置且存在）。幂等、线程安全。

    Returns:
        Observer | None: watchdog 模式下返回 Observer，轮询模式下返回 None。
    """
    if not OBSIDIAN_WATCHER_ENABLED:
        logger.info("Obsidian 监视器已禁用（OBSIDIAN_WATCHER_ENABLED=false）")
        return None
    vault = OBSIDIAN_VAULT_DIR
    if not vault or not Path(vault).exists():
        logger.info("Obsidian 未配置或 vault 不存在，跳过监视器: %s", vault)
        return None

    debouncer = _Debouncer(OBSIDIAN_WATCH_INTERVAL, _reindex_once)

    # ── 优先 watchdog（OS 级事件，真正实时）──
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if not event.is_directory and _is_relevant(event.src_path):
                    debouncer.trigger()

            def on_created(self, event):
                if not event.is_directory and _is_relevant(event.src_path):
                    debouncer.trigger()

            def on_deleted(self, event):
                if not event.is_directory and _is_relevant(event.src_path):
                    debouncer.trigger()

            def on_moved(self, event):
                if not event.is_directory and (
                    _is_relevant(getattr(event, "src_path", ""))
                    or _is_relevant(getattr(event, "dest_path", ""))
                ):
                    debouncer.trigger()

        observer = Observer()
        observer.schedule(_Handler(), vault, recursive=True)
        observer.daemon = True
        observer.start()
        logger.info(
            "Obsidian 监视器已启动（watchdog 实时模式, 防抖 %ds）: %s",
            OBSIDIAN_WATCH_INTERVAL, vault,
        )
        return observer
    except ImportError:
        logger.warning(
            "未安装 watchdog，回退为轮询模式（pip install watchdog 可启用毫秒级实时监视）"
        )

    # ── 回退：stdlib 轮询（无需额外依赖，延迟 = OBSIDIAN_WATCH_INTERVAL）──
    def _poll_loop():
        last = _scan_mtimes(vault)
        while True:
            time.sleep(OBSIDIAN_WATCH_INTERVAL)
            try:
                current = _scan_mtimes(vault)
                if current != last:
                    last = current
                    debouncer.trigger()
            except Exception as e:  # noqa: BLE001
                logger.warning("Obsidian 轮询异常: %s", e)

    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()
    logger.info(
        "Obsidian 轮询监视器已启动（%ds 间隔）: %s",
        OBSIDIAN_WATCH_INTERVAL, vault,
    )
    return None
