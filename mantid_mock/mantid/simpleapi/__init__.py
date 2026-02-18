
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


class MockMtd:
    def doesExist(self, name):
        return False
    def getObjectNames(self):
        return []

mtd = MockMtd()

def GetIPTS(RunNumber=None, Instrument=None):
    return '/HFIR/IPTS-12345/'

def SaveNexusProcessed(InputWorkspace=None, Filename=None, Title=''):
    pass

def CreateMDWorkspace(**kwargs):
    return None

def BinMD(**kwargs):
    return None

def CreateWorkspace(**kwargs):
    return None

def DeleteWorkspace(**kwargs):
    pass

def CreateSampleWorkspace(**kwargs):
    return None

def CopyLogs(**kwargs):
    return None

def FitPeaks(**kwargs):
    return None

def RenameWorkspace(**kwargs):
    return None

def LoadEventNexus(**kwargs):
    return None

def LoadMask(**kwargs):
    return None

def RemoveLogs(**kwargs):
    pass
