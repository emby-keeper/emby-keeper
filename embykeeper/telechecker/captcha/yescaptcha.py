import time
import requests
import asyncio
from loguru import logger

""" 
YESCAPTCHA验证码Requests版本
"""


class YesCaptcha:

    def __init__(self, clientKey, websiteKey, websiteURL, task_type):
        self.clientKey = clientKey
        self.websiteKey = websiteKey
        self.websiteURL = websiteURL
        self.task_type = task_type
        self.log = logger.bind(scheme="telechecker", name="YesCaptcha",username="Nebula")

    async def create_task(self) -> str:
        """
        第一步，创建验证码任务
        :param
        :return taskId : string 创建成功的任务ID
        """
        url = "https://api.yescaptcha.com/createTask"
        data = {
            "clientKey": self.clientKey,
            "task": {
                "websiteURL": self.websiteURL,
                "websiteKey": self.websiteKey,
                "type": self.task_type
            },
            "softID": 18097,
        }
        try:
            result = requests.post(url, json=data).json()
            # print(result)
            taskId = result.get('taskId')
            if taskId:
                return taskId
        except Exception as e:
            self.log.warning(e)

    async def get_response(self, taskID):
        """
        第二步：使用taskId获取response
        :param taskID: string
        :return response: string 识别结果
        """

        # 循环请求识别结果，3秒请求一次
        times = 0
        while times < 120:
            try:
                url = "https://api.yescaptcha.com/getTaskResult"
                data = {
                    "clientKey": self.clientKey,
                    "taskId": taskID
                }
                result = requests.post(url, json=data).json()
                # print(result)
                if result.get('errorId') == 1:
                    throw = result.get('errorDescription')
                    self.log.warning('识别错误:' + throw)
                    return
                if result.get('status') == 'processing':
                    times += 1
                    time.sleep(3)
                    continue
                response = result.get('solution').get('token')
                return response
                self.log.warning('返回异常:' + result)
            except Exception as e:
                self.log.warning(e)

    async def solve(self):
        taskId = await self.create_task()
        self.log.info('创建任务:' + taskId)
        if taskId is not None:
            response = await self.get_response(taskId)
            self.log.info('识别结果:' + response)
            return response


# if __name__ == '__main__':
#     yc = YesCaptcha(clientKey, websiteKey, websiteURL, task_type)
#     asyncio.run(yc.solve())
