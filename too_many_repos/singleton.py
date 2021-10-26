class Singleton:
    def __init__(self):
        if hasattr(self.__class__, '_inst'):
            return
        setattr(self.__class__, '_inst', self)
    
    def __new__(cls):
        if hasattr(cls, '_inst'):
            return getattr(cls, '_inst')
        inst = super().__new__(cls)
        return inst
