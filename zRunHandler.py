# 这个全是我自己写的噢
import zPerseusLogger
import zAlas , zBarkCustom , zHideAlas , zMumu , zPgrjz , zPlaywright
def handlerun(data):
    try:
        if "alas" in  data["task"]:
            if "kill" in  data["task"]:
                zAlas.alas_cleanup()
                return [True,"zAlas.alas_cleanup()"]
            elif "start" in  data["task"]:
                zAlas.alas_start()
                return [True,"zAlas.alas_start()"]
            elif "restart" in  data["task"]:
                zAlas.alas_cleanup()
                zAlas.alas_start()
                return [True,"zAlas.alas_cleanup(),zAlas.alas_start()"]
            elif "hide" in  data["task"]:
                zHideAlas.smart_hide_azurpilot()
                return [True,"zHideAlas.smart_hide_azurpilot()"]
            elif "online" in  data["task"]:
                return [True,zAlas.is_process_running()]
        elif "mumu" in  data["task"]:
            if "kill" in  data["task"]:
                zMumu.mumu_kill()
                return [True,"zMumu.mumu_kill()"]
            elif "start" in  data["task"]:
                zMumu.hidemumu()
                return [True,"zMumu.hidemumu()"]
            elif "online" in  data["task"]:
                return [True,zMumu.is_mumu_running()]
        elif "playwright" in  data["task"]:
            return [True,f"zPlaywright.main(),{zPlaywright.main()}"]
    except Exception as e:
        error_type = type(e).__name__
        error_detail = str(e)
        print(f"\n[💥 函数报错] RunHandler 执行过程中抛出异常！")
        print(f"错误类型: {error_type}")
        print(f"详细信息: {error_detail}")
        return [False,f"{error_type},{error_detail}"]
    return [True,"Unknown Task"]