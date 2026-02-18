
from contextlib import contextmanager

@contextmanager
def amend_config(**kwargs):
    yield


class Logger:
    def __init__(self, *args, **kwargs):
        pass
    
    def debug(self, msg):
        pass
    
    def information(self, msg):
        pass
    
    def warning(self, msg):
        pass
    
    def error(self, msg):
        pass
    
    def notice(self, msg):
        pass


class IntTimeSeriesProperty:
    pass

class Int32TimeSeriesProperty:
    pass

class Int64TimeSeriesProperty:
    pass

class Int32FilteredTimeSeriesProperty:
    pass

class Int64FilteredTimeSeriesProperty:
    pass

class FloatTimeSeriesProperty:
    pass

class FloatFilteredTimeSeriesProperty:
    pass

class BoolTimeSeriesProperty:
    pass

class StringTimeSeriesProperty:
    pass

class StringFilteredTimeSeriesProperty:
    pass
