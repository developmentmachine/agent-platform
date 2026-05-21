"""shim → ``agent_platform.agents.stock_recap.data.sources.indices`` (W3)

Mirror 全部顶层属性到 shim 命名空间，并将 shim 上的 ``setattr`` 同步到真实模块，
以兼容旧的 ``monkeypatch.setattr(shim_module, name, val)`` 行为。W7 删除。
"""
import importlib as _il
import sys as _sys
from types import ModuleType as _MT


_new_mod = _il.import_module("agent_platform.agents.stock_recap.data.sources.indices")


def _make_shim_class(target):
    class _ShimModule(_MT):
        __target__ = target

        def __setattr__(self, name, value):  # type: ignore[override]
            _MT.__setattr__(self, name, value)
            if not name.startswith("__"):
                setattr(target, name, value)

    return _ShimModule


_self = _sys.modules[__name__]
_self.__class__ = _make_shim_class(_new_mod)
for _k, _v in vars(_new_mod).items():
    if not _k.startswith("__"):
        _MT.__setattr__(_self, _k, _v)
