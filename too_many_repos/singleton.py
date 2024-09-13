from typing_extensions import Self


class Singleton:
    def __init__(self):
        if hasattr(self.__class__, '_inst'):
            return
        setattr(self.__class__, '_inst', self)
    
    def __new__(cls) -> Self:
        if hasattr(cls, '_inst'):
            return getattr(cls, '_inst')
        inst: Self = super().__new__(cls)
        return inst
    def __copy__(self) -> Self:
        return self
    def __deepcopy__(self) -> Self:
        return self
