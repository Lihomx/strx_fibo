import os
import streamlit.components.v1 as _components

_COMPONENT_DIR = os.path.dirname(os.path.abspath(__file__))
_tv_click_bridge = _components.declare_component(
    "tv_click_bridge",
    path=_COMPONENT_DIR
)


def render_tv_click_bridge(key="global_tv_bridge"):
    """渲染无感又向 WebScoket 桥接组件，用于株记 TradingView 点击落盘"""
    try:
        return _tv_click_bridge(key=key, default=None)
    except Exception:
        return None
