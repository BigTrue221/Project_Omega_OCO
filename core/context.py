# -*- coding: utf-8 -*-
"""
OCO Context variables for cross-layer state passing without polluting LangGraph state.
"""
import contextvars

progress_callback_var = contextvars.ContextVar('progress_callback', default=None)
