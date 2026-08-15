import json
import os
import threading
from datetime import datetime

_BASE = os.path.dirname(os.path.abspath(__file__))
F_STATE = os.path.join(_BASE, "data_bg_scan_state.json")

_lock = threading.Lock()

# 默认状态
_state = {
    "status": "idle",        # idle | running | done | error | cancelled
    "job_id": None,
    "job_type": None,        # "fibo" | "triple_bottom" | "universe" | "chartink"
    "job_label": "",
    "progress": 0.0,
    "current": "",
    "done_count": 0,
    "total_count": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "cancel_requested": False,
}

def _load_state():
    global _state
    try:
        if os.path.exists(F_STATE):
            with open(F_STATE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # 如果上次是 running 状态，说明实例重启了，直接重置为 error (被中断)
                    if data.get("status") == "running":
                        data["status"] = "error"
                        data["error"] = "后台扫描被系统/部署重启中断。"
                        data["finished_at"] = datetime.now().isoformat()
                    _state.update(data)
    except Exception:
        pass

def _save_state():
    try:
        with open(F_STATE, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# 初始化加载上一次状态
_load_state()

def get_status() -> dict:
    with _lock:
        return _state.copy()

def is_running() -> bool:
    with _lock:
        return _state["status"] == "running"

def request_cancel():
    with _lock:
        if _state["status"] == "running":
            _state["cancel_requested"] = True
            _state["current"] = "正在取消..."
            _save_state()

def reset_to_idle():
    with _lock:
        if _state["status"] != "running":
            _state.update({
                "status": "idle",
                "job_id": None,
                "job_type": None,
                "job_label": "",
                "progress": 0.0,
                "current": "",
                "done_count": 0,
                "total_count": 0,
                "started_at": None,
                "finished_at": None,
                "error": None,
                "cancel_requested": False,
            })
            _save_state()

def submit_job(job_type: str, label: str, params: dict, worker_fn) -> tuple[bool, str]:
    with _lock:
        if _state["status"] == "running":
            return False, "当前已有其他扫描任务正在后台运行"
        
        job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        _state.update({
            "status": "running",
            "job_id": job_id,
            "job_type": job_type,
            "job_label": label,
            "progress": 0.0,
            "current": "正在初始化...",
            "done_count": 0,
            "total_count": 0,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "error": None,
            "cancel_requested": False,
        })
        _save_state()
        
    t = threading.Thread(target=_bg_worker_wrapper, args=(job_id, worker_fn, params), daemon=True)
    try:
        t.start()
    except RuntimeError:
        # 线程数已耗尽，同步降级执行
        with _lock:
            _state["status"] = "error"
            _state["error"] = "系统线程数已耗尽，无法启动后台扫描，请稍后重试"
            _state["finished_at"] = datetime.now().isoformat()
            _save_state()
        return False, "系统线程资源不足，请稍后重试"
    return True, "扫描任务已在后台启动，您可以关闭此页面"

def _bg_worker_wrapper(job_id, worker_fn, params):
    def update_progress(done_count, total_count, current):
        with _lock:
            if _state["job_id"] != job_id:
                return
            _state["done_count"] = done_count
            _state["total_count"] = total_count
            _state["current"] = current
            if total_count > 0:
                _state["progress"] = min(float(done_count) / total_count, 1.0)
            else:
                _state["progress"] = 0.0
            _save_state()
            
    def cancel_check():
        with _lock:
            return _state["job_id"] == job_id and _state["cancel_requested"]

    try:
        worker_fn(params, update_progress, cancel_check)
        with _lock:
            if _state["job_id"] == job_id:
                if _state["cancel_requested"]:
                    _state["status"] = "cancelled"
                    _state["current"] = "已取消"
                else:
                    _state["status"] = "done"
                    _state["progress"] = 1.0
                    _state["current"] = "扫描完成"
                _state["finished_at"] = datetime.now().isoformat()
                _save_state()
    except Exception as e:
        import traceback
        err_msg = f"{str(e)}\n{traceback.format_exc()}"
        with _lock:
            if _state["job_id"] == job_id:
                _state["status"] = "error"
                _state["error"] = err_msg
                _state["current"] = "扫描出错"
                _state["finished_at"] = datetime.now().isoformat()
                _save_state()
