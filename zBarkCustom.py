from zBark import bark ,barkall

DEVICEKEYLIST = ["xxxxxx"]
ALARMSOUND = "alarm"
NORMALSOUND = "alarm"

def PerseusWarningMsg(main:str,msg:str):
    return barkall(DEVICEKEYLIST,
        title=f"WARNING:{main}",
        body=msg,
        url="http://192.168.10.3:22267",
        group="Perseus",
        sound=ALARMSOUND,
        level="timesensitive",
        )

def PerseusErrorMsg(main:str,msg:str):
    return barkall(DEVICEKEYLIST,
        title=f"ERROR:{main}",
        body=msg,
        url="http://192.168.10.3:22267",
        group="Perseus",
        sound=ALARMSOUND,
        level="timesensitive",
        )

def PerseusNotifyMsg(main:str,msg:str):
    return barkall(DEVICEKEYLIST,
        title=f"Notice:{main}",
        body=msg,
        url="http://192.168.10.3:22267",
        group="Perseus",
        sound=NORMALSOUND,
        level="passive",
        )

def CustomMsg(title:str,msg:str,group:str):
    return barkall(DEVICEKEYLIST,
        title=title,
        body=msg,
        group=group,
        sound=ALARMSOUND,
        level="passive",
        copy=msg
        )

if __name__ == "__main__":
    PerseusNotifyMsg("Tesing","test3")