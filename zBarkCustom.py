from zBark import bark ,barkall

DEVICEKEYLIST = ["xxxxx"]
ALARMSOUND = "alarm"
NORMALSOUND = "alarm"
ICON1 = "https://patchwiki.biligame.com/images/blhx/0/05/3bi61qmjssvlemdug8rag683vcj2ziy.png"
ICON2 = "https://patchwiki.biligame.com/images/blhx/0/0f/m5rycu93qc94r5lyst8862wnbvehjle.png"
ICON3 = "https://patchwiki.biligame.com/images/blhx/9/9a/onh0ri4tx1wjuhhtxegjqqcobv7wdjc.png"

def PerseusWarningMsg(main:str,msg:str):
    return barkall(DEVICEKEYLIST,
        title=f"WARNING:{main}",
        body=msg,
        group="Perseus",
        sound=ALARMSOUND,
        level="timesensitive",
        icon = ICON1
        )

def PerseusErrorMsg(main:str,msg:str):
    return barkall(DEVICEKEYLIST,
        title=f"ERROR:{main}",
        body=msg,
        group="Perseus",
        sound=ALARMSOUND,
        level="timesensitive",
        icon =  ICON3
        )

def PerseusNotifyMsg(main:str,msg:str):
    return barkall(DEVICEKEYLIST,
        title=f"Notice:{main}",
        body=msg,
        group="Perseus",
        sound=NORMALSOUND,
        level="passive",
        icon= ICON2
        )

def CustomMsg(title:str,msg:str,group:str):
    return barkall(DEVICEKEYLIST,
        title=title,
        body=msg,
        group=group,
        sound=ALARMSOUND,
        level="passive",
        copy=msg,
        icon = ICON2
        )

if __name__ == "__main__":
    PerseusNotifyMsg("Tesing","test3")
