from threading import RLock
from typing import Any, Dict, Tuple, Type

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

from weakref import WeakValueDictionary


class Singleton:
    _lock: RLock = RLock()
    __instances__: WeakValueDictionary = WeakValueDictionary()

    def __new__(cls: Type[Self], *args: Any, **kwargs: Any) -> Self:
        if cls not in cls.__instances__:
            with cls._lock:
                if cls not in cls.__instances__:
                    try:
                        instance: Self = super().__new__(cls)
                        cls.__instances__[cls] = instance
                    except:
                        if cls in cls.__instances__:
                            del cls.__instances__[cls]
                        raise
        return cls.__instances__[cls]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: Dict[int, Any]) -> Self:
        return self

    def __reduce__(self) -> Tuple[Type[Self], Tuple[()]]:
        return self.__class__, ()

    def __reduce_ex__(self, proto: int) -> Tuple[Type[Self], Tuple[()]]:
        return self.__reduce__()
