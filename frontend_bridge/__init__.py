import os
import streamlit as st
import streamlit.components.v1 as _components
import storage

_COMPONENT_DIR = os.path.dirname(os.path.abspath(__file__))
_tv_click_bridge = _components.declare_component(
    "tv_click_bridge",
    path=_COMPONENT_DIR
)


def _render_bridge_raw(key="global_tv_bridge"):
    try:
        return _tv_click_bridge(key=key, default=None)
    except Exception:
        return None


if hasattr(st, "fragment"):
    @st.fragment
    def mount_tv_click_listener(key="global_tv_bridge"):
        """使用 st.fragment 隔离运行：点击仅在后台极速落盘，绝不引起主页面重新渲染或变灰"""
        val = _render_bridge_raw(key=key)
        if val and isinstance(val, dict):
            tk = str(val.get("ticker", "")).strip().upper()
            ts = val.get("ts", 0)
            last_ts = st.session_state.get(f"_last_ts_{key}", 0)
            if tk and ts != last_ts:
                st.session_state[f"_last_ts_{key}"] = ts
                storage.increment_link_click(tk, "tv")
else:
    def mount_tv_click_listener(key="global_tv_bridge"):
        val = _render_bridge_raw(key=key)
        if val and isinstance(val, dict):
            tk = str(val.get("ticker", "")).strip().upper()
            ts = val.get("ts", 0)
            last_ts = st.session_state.get(f"_last_ts_{key}", 0)
            if tk and ts != last_ts:
                st.session_state[f"_last_ts_{key}"] = ts
                storage.increment_link_click(tk, "tv")


def render_tv_click_bridge(key="global_tv_bridge"):
    return mount_tv_click_listener(key=key)

