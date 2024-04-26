[![build status](https://img.shields.io/github/actions/workflow/status/embykeeper/embykeeper/ci.yml?branch=main)](https://github.com/embykeeper/embykeeper/commits/main) [![pypi badge](https://img.shields.io/pypi/v/embykeeper)](https://pypi.org/project/embykeeper/) [![docker](https://img.shields.io/docker/v/embykeeper/embykeeper?label=docker)](https://hub.docker.com/r/embykeeper/embykeeper) [![docker pulls](https://img.shields.io/docker/pulls/embykeeper/embykeeper?label=pulls)](https://hub.docker.com/r/embykeeper/embykeeper) [![license badge](https://img.shields.io/github/license/embykeeper/embykeeper)](https://github.com/embykeeper/embykeeper/blob/main/LICENSE) [![telegram badge](https://img.shields.io/badge/telegram-bot-blue)](https://t.me/embykeeper_bot) [![telegram badge](https://img.shields.io/badge/telegram-channel-green)](https://t.me/embykeeper) [![telegram badge](https://img.shields.io/badge/telegram-group-violet)](https://t.me/embykeeperchat)

<p align="center">
  <a href='https://github.com/embykeeper/embykeeper'>
    <img src="https://github.com/embykeeper/embykeeper/raw/main/images/logo.svg" alt="Embykeeper" />
  </a>
</p>
<p align="center">
    <b>自动签到 定时保号 按需水群</b>
</p>

---

Embykeeper 是一个在中文社群规则下用于 Emby 影视服务器的签到和保号的自动执行工具, 基于 Pyrogram 编写并具有可拓展性.

## 声明

本项目涉及的一切 Emby 服务器与 Embykeeper 开发团队无关, 在使用 Embykeeper 时造成的一切损失 (包括但不限于 Emby 或 Telegram 账号被封禁或被群封禁) 与开发团队无关. 为了您的账号安全, 推荐使用小号.

本项目设计初衷是在中文 Emby 社群规则下, 保号要求逐渐苛刻 (部分要求每月登录或每日签到), 这使得休闲时间紧张的人士难以安心使用. 本项目仅旨在帮助该类人群保号, 不鼓励持有大量 Emby 账号而不使用, 导致真正需要的人、为中文影视资源分享和翻译有贡献的人难以获得账号的行为, 开发团队也呼吁仅保留 1-2 个较全面质量较高的 Emby 服务器. 本项目仅提供工具, 具体使用形式及造成的影响和后果与开发团队无关.

本项目欢迎友善讨论与建议, 您可以通过 [Github Issue](https://github.com/embykeeper/embykeeper) 途径反馈, 并认可开发团队可以关闭与项目开发不直接相关的不友善讨论. 您也可以通过 [Telegram 讨论群](https://t.me/embykeeper_chat_bot) 获得社区帮助.

当您使用 "消息提示" 功能, 该工具时候将自动向 "[Embykeeper Auth Bot](https://t.me/embykeeper_auth_bot)" 发送关键的成功/失败日志以供从 "[Embykeeper Bot](https://t.me/embykeeper_bot)" 向您推送, 日志内容不含任何密码或密钥信息, 您认可该命令不会给您带来隐私与安全问题.

当您安装并使用该工具, 默认您已经阅读并同意上述声明, 并确认自己并非出于"集邮"目的而安装.

## 功能

- Telegram 机器人签到
  - 卷毛鼠: [频道](https://t.me/CurlyMouse) [群组](https://t.me/Curly_Mouse) [机器人](https://t.me/jmsembybot)
  - 垃圾影音: [群组](https://t.me/+3sP2A-fgeXg0ZmY1) [机器人](https://t.me/zckllflbot)
  - Pornemby: [频道](https://t.me/pornembyservice) [群组](https://t.me/Pornemby) [机器人](https://t.me/PronembyTGBot2_bot)
  - 默认禁用 (关服或无响应):
    - EmbyHub: ~~[频道](https://t.me/embyhub) [群组](https://t.me/emby_hub) [机器人](https://t.me/EdHubot)~~
    - 终点站: ~~[频道](https://t.me/embypub) [群组](https://t.me/EmbyPublic) [机器人](https://t.me/EmbyPublicBot)~~
    - 卡戎: ~~[频道](https://t.me/CharonTV) [群组](https://t.me/CharonTV_Talk) [机器人](https://t.me/CharonTV_Bot)~~
    - Peach: ~~[机器人](https://t.me/peach_emby_bot)~~
    - 魔法Emby: ~~[频道](https://t.me/Magic_EmbyChannel) [群组](https://t.me/Magicemby) [机器人](https://t.me/Magic_EmbyBot)~~
    - Temby: ~~[频道](https://t.me/tembychannel) [群组](https://t.me/tembygroup) [机器人](https://t.me/HiEmbyBot)~~
    - Misty: ~~[频道](https://t.me/FreeEmbyChannel) [群组](https://t.me/FreeEmby) [机器人](https://t.me/EmbyMistyBot)~~
    - BlueSea: ~~[群组](https://t.me/blueseachat) [机器人](https://t.me/blueseamusic_bot)~~
    - 卷毛鼠 IPTV: ~~[频道](https://t.me/CurlyMouseIPTV) [群组](https://t.me/Curly_MouseIPTV) [机器人](https://t.me/JMSIPTV_bot)~~
    - Nebula: ~~[频道](https://t.me/Nebula_Emby) [群组](https://t.me/NebulaEmbyUser) [机器人](https://t.me/Nebula_Account_bot)~~
    - Singularity: ~~[频道](https://t.me/Singularity_Emby_Channel) [群组](https://t.me/Singularity_Emby_Group) [机器人](https://t.me/Singularity_Emby_Bot)~~
    - 剧狗: ~~[频道](https://t.me/Mulgoreemby) [机器人](https://t.me/mulgorebot)~~
    - 其他非 Emby 相关:
      - 搜书神器 ([@chneez](https://github.com/embykeeper/embykeeper/pull/8) 增加): [机器人](https://t.me/sosdbot)
      - 纸片 DDoS: [频道](https://t.me/PaperBotnet) [机器人](https://t.me/zhipianbot)
      - 情报局社工库: [频道1](https://t.me/CIA_cd) [频道2](https://t.me/wanghong_sgk) [群组](https://t.me/heikeciadgk) [机器人](https://t.me/InfSGK_bot)
- Emby 保活
  - 定时模拟账号登录视频播放
  - 播放时间与进度模拟
- Telegram 自动水群 (需要 [Embykeeper 高级用户](https://t.me/embykeeper_bot?start=__prime), 默认使用内建话术列表, 易被辨别和封禁, 请谨慎使用)
  - Pornemby: [频道](https://t.me/pornembyservice) [群组](https://t.me/Pornemby) [机器人](https://t.me/PronembyTGBot2_bot) [内建话术列表](https://github.com/embykeeper/embykeeper-data/blob/main/data/pornemby-common-wl%40v1.yaml)
  - 默认禁用 (关服或无响应):
    - NakoNako 自动水群: ~~[群组](https://t.me/NakoNetwork) [机器人](https://t.me/nakonetwork_bot)~~
- Telegram 自动监控信息 (需要 [Embykeeper 高级用户](https://t.me/embykeeper_bot?start=__prime))
  - Pornemby ([定制功能](https://afdian.net/a/jackzzs)):
    - 科举考试: [活动频道](https://t.me/PornembyFun) (可选的[高准确云题库](https://afdian.net/a/jackzzs), 回答准确率 90% 以上)
    - 自动抢注: [群组](https://t.me/Pornemby)
    - 自动抢红包雨: [群组](https://t.me/Pornemby)
  - 不给看 抢邀请码: [群组](https://t.me/Ephemeralemby) [机器人](https://t.me/UnknownEmbyBot)
  - Viper 抢邀请码: [频道](https://t.me/viper_emby_channel) [群组](https://t.me/Viper_Emby_Chat) [机器人](https://t.me/viper_emby_bot)
  - Embyhub 开注自动注册: [频道](https://t.me/embyhub) [群组](https://t.me/emby_hub) [机器人](https://t.me/EdHubot)
  - 默认禁用 (关服或无响应):
    - 全局自动从众: 当在任何群组中发现 5 分钟内 5 条一样内容的消息, 会自动跟一句 (影响范围大默认禁用)
    - Polo 抢邀请码: ~~[频道](https://t.me/poloembyc) [群组](https://t.me/poloemby) [机器人](https://t.me/polo_emby_bot)~~
    - Misty 开注自动注册: ~~[频道](https://t.me/FreeEmbyChannel) [群组](https://t.me/FreeEmby) [机器人](https://t.me/EmbyMistyBot)~~
    - 剧狗 开注自动注册: ~~[频道](https://t.me/Mulgoreemby) [机器人](https://t.me/mulgorebot)~~

## 安装与使用

Embykeeper 支持 Docker 或 PyPI 安装 (Linux / Windows), 也支持云部署, 请点击下方按钮开始安装:

[![Setup Tutorial](https://github.com/embykeeper/embykeeper/raw/main/images/setup-button.svg)](https://github.com/embykeeper/embykeeper/wiki/%E5%AE%89%E8%A3%85%E6%8C%87%E5%8D%97)

若您没有服务器, 您可以通过免费的 Render 托管平台进行部署, 点击下方按钮开始部署:

[![Deploy to Render](https://github.com/embykeeper/embykeeper/raw/main/images/deploy-to-render.svg)](https://render.com/deploy?repo=https://github.com/embykeeper/embykeeper/tree/stable)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[![Tutorial](https://github.com/embykeeper/embykeeper/raw/main/images/render-tutorial.svg)](https://zetx.tech/2023/06/26/embykeeper-render-tutorial)

若您有服务器, 我们推荐使用 [Docker 部署](https://github.com/embykeeper/embykeeper/wiki/Linux-Docker-%E9%83%A8%E7%BD%B2):

```bash
docker run -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper
```

您也可以使用 [Docker Compose 部署](https://github.com/embykeeper/embykeeper/wiki/Linux-Docker-Compose-%E9%83%A8%E7%BD%B2).

除此之外, 您还可以通过 [PyPI 安装](https://github.com/embykeeper/embykeeper/wiki/Linux-%E4%BB%8E-PyPI-%E5%AE%89%E8%A3%85) 或 [源码构建](https://github.com/embykeeper/embykeeper/wiki/Linux-%E4%BB%8E%E6%BA%90%E7%A0%81%E6%9E%84%E5%BB%BA).

更多安装和配置方面的帮助请参考 [Wiki](https://github.com/embykeeper/embykeeper/wiki).

**注意**: 请尽可能使用小号运行本工具, 运行该工具的 Telegram 账号若通过接码注册, 请使用一段时间再接入本工具.

## 运行截图

![Screenshot](https://github.com/embykeeper/embykeeper/raw/main/images/screenshot.png)

## 支持 Embykeeper

##### 开发者团队

- [jackzzs](https://github.com/jackzzs)

##### 通过[爱发电](https://afdian.net/a/jackzzs)赞助

![Kitty](https://github.com/embykeeper/embykeeper/raw/main/images/kitty.gif)

## 趋势

[![Star History Chart](https://api.star-history.com/svg?repos=embykeeper/embykeeper&type=Date)](https://star-history.com/#embykeeper/embykeeper&Date)
