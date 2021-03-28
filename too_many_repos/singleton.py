# from cyberbrain import trace
class Singleton:
    _inst = None
    # @trace
    def __init__(self):
        if self.__class__._inst:
            return
        self.__class__._inst = self
    
    # @trace
    def __new__(cls):
        if cls._inst:
            return cls._inst
        inst = super().__new__(cls)
        return inst