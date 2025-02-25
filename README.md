[![build status](https://img.shields.io/github/actions/workflow/status/emby-keeper/emby-keeper/ci.yml?branch=main)](https://github.com/emby-keeper/emby-keeper/commits/main) [![pypi badge](https://img.shields.io/pypi/v/embykeeper)](https://pypi.org/project/embykeeper/) [![docker](https://img.shields.io/docker/v/embykeeper/embykeeper?label=docker)](https://hub.docker.com/r/embykeeper/embykeeper) [![docker pulls](https://img.shields.io/docker/pulls/embykeeper/embykeeper?label=pulls)](https://hub.docker.com/r/embykeeper/embykeeper) [![license badge](https://img.shields.io/github/license/emby-keeper/emby-keeper)](https://github.com/emby-keeper/emby-keeper/blob/main/LICENSE) [![telegram badge](https://img.shields.io/badge/telegram-bot-blue)](https://t.me/embykeeper_bot) [![telegram badge](https://img.shields.io/badge/telegram-channel-green)](https://t.me/embykeeper) [![telegram badge](https://img.shields.io/badge/telegram-group-violet)](https://t.me/embykeeperchat)

<p align="center">
  <a href='https://github.com/emby-keeper/emby-keeper'>
    <img src="https://github.com/emby-keeper/emby-keeper/raw/main/images/logo.svg" alt="Embykeeper" />
  </a>
</p>
<p align="center">
    <b>自动签到 定时保号 按需水群</b>
</p>

---

## 功能

Embykeeper 是一个 Emby 影视服务器签到保号的自动执行工具, 它主要提供两大核心功能:

1. **TG 机器人签到** - 可以自动完成 50+ 站点的 Telegram 机器人每日签到, 以获取积分.

2. **Emby 保号** - 通过模拟登录和播放视频, 定期保持 Emby 账号的活跃状态, 支持任何 Emby 站点.

除此之外, Embykeeper 还提供了一些额外功能：

1. **自动抢注** - 监听邀请码发码信息和开放注册信息, 并自动抢注.

2. **群组游戏** - 自动完成群组内的抢红包和答题等游戏, 以获取积分.

3. **考核辅助** - 站点考核自动接入 GPT 和 已知题库, 提高通过率.

4. **便捷的二次开发** - 基于 Pyrogram 开发, 提供了一套便捷的框架来实现新的签到器.

项目支持 Python 运行、Docker 部署或云部署, 且完全开源, 不存储任何密钥或隐私信息, 经两年的开发已经在稳定和安全性方面有一定保证.

## 声明

本项目涉及的一切 Emby 服务器与 Embykeeper 开发团队无关, 在使用 Embykeeper 时造成的一切损失 (包括但不限于 Emby 或 Telegram 账号被封禁或被群封禁) 与开发团队无关. 为了您的账号安全, 推荐使用小号. 运行该工具的 Telegram 账号若通过接码注册, 请使用一段时间再接入本工具.

本项目设计初衷是在中文 Emby 社群规则下, 保号要求逐渐苛刻 (部分要求每月登录或每日签到), 这使得休闲时间紧张的人士难以安心使用. 本项目仅旨在帮助该类人群保号, 不鼓励持有大量 Emby 账号而不使用, 导致真正需要的人、为中文影视资源分享和翻译有贡献的人难以获得账号的行为, 开发团队也呼吁仅保留 1-2 个较全面质量较高的 Emby 服务器. 本项目仅提供工具, 具体使用形式及造成的影响和后果与开发团队无关.

Embykeeper 将自动向 Embykeeper Auth Bot ([@embykeeper_auth_bot](https://t.me/embykeeper_auth_bot))" 发送信息, 用于在线验证码解析、日志记录、用户验证等, 内容不含任何密码或密钥信息, 或其他敏感隐私信息.

当您安装并使用该工具, 默认您已经阅读并同意上述声明, 并确认自己并非出于"集邮"目的而安装.

## 安装与使用

Embykeeper 支持 Docker 或 PyPI 安装 (Linux / Windows), 也支持云部署, 请点击下方按钮开始部署:

[![Setup Tutorial](https://github.com/emby-keeper/emby-keeper/raw/main/images/setup-button.svg)](https://emby-keeper.github.io/guide/安装指南)

若您没有服务器, 您可以通过免费托管平台进行部署, 点击下方按钮开始部署:

[![Deploy to Huggingface Space](https://github.com/emby-keeper/emby-keeper/raw/main/images/deploy-to-hf.svg)](https://huggingface.co/spaces/embykeeper/ek?duplicate=true)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[![Tutorial](https://github.com/emby-keeper/emby-keeper/raw/main/images/hf-tutorial.svg)](https://blog.zetx.tech/2024/05/19/embykeeper-hf-tutorial/)

若您有服务器, 我们推荐使用 [Docker 部署](https://emby-keeper.github.io/guide/Linux-Docker-部署):

```bash
docker run -v $(pwd)/embykeeper:/app --rm -it --net=host embykeeper/embykeeper -i
```

**注意**: 由于近期 Telegram 风控等级上升, 请尽可能先使用服务器所在地区的代理在手机上先登陆一次, 再使用 Embykeeper.

您也可以使用 [Docker Compose 部署](https://emby-keeper.github.io/guide/Linux-Docker-Compose-部署).

更多安装和配置方面的帮助请参考 [**📖 教程文档**](https://emby-keeper.github.io/).

本项目欢迎友善讨论与建议, 您可以通过 [Github Issue](https://github.com/emby-keeper/emby-keeper) 途径反馈, 并认可开发团队可以关闭与项目开发不直接相关的不友善讨论. 您也可以通过 [Telegram 讨论群](https://t.me/embykeeper_chat_bot) 获得社区帮助.

## 运行截图

![Screenshot](https://github.com/emby-keeper/emby-keeper/raw/main/images/screenshot.png)

## 完整功能支持列表

- **Emby 保活**
  - 定时模拟账号登录视频播放
  - 播放时间与进度模拟
- **Telegram 机器人签到**
  <!-- #region checkiner-sites -->

  - 终点站 (`terminus`): [频道](https://t.me/embypub) [群组](https://t.me/EmbyPublic) [机器人](https://t.me/EmbyPublicBot)
  - Pornemby (`pornemby`): [频道](https://t.me/pornembyservice) [群组](https://t.me/Pornemby) [机器人](https://t.me/Porn_Emby_Bot)
  - Nebula (`nebula`): [频道](https://t.me/Nebula_Emby) [群组](https://t.me/NebulaEmbyUser) [机器人](https://t.me/Nebula_Account_bot)
  - Apop Pro (`apoppro`): [频道](https://t.me/ApopCloud_Channel) [群组](https://t.me/apopcloud) [机器人](https://t.me/apopembypro_bot)
  - 飞跃彩虹 (`feiyue`): [频道](https://t.me/fyemby) [群组](https://t.me/feiyueemby) [机器人](https://t.me/FeiyueEmby_bot)
  - PandaTV: [频道](https://t.me/PandaTV_Emby_Channel)
    - 自动签到 (`pandatv`): [机器人](https://t.me/PandaTV_Emby_Bot)
    - 每 14 天自动群里发送签到 (`pandatv_group`): [群组](https://t.me/PandaTV_Emby_Group)
  - Peach (`peach`): [机器人](https://t.me/peach_emby_bot)
  - 魔法Emby (`magic`): [频道](https://t.me/Magic_EmbyChannel) [群组](https://t.me/Magicemby) [机器人](https://t.me/Magic_EmbyBot)
  - 开心服 (`happy`): [频道](https://t.me/hhappyemby) [群组](https://t.me/Happyembyyds) [机器人](https://t.me/happy_sign_bot)
  - MICU (`micu`): [频道](http://t.me/+_PcX8rALVA80NTU1) [群组](http://t.me/+tW5vUYJROcE2ZTA1) [机器人](https://t.me/micu_user_bot)
  - 叔服Emby (`shufu`): [群组](http://t.me/+4eq37Ip8ayRhNDI9) [机器人](https://t.me/dashu660_bot)
  - 天南小筑 (`tiannan`): [频道](http://t.me/Nanflix) [群组](http://t.me/+kDBdjwtZwudhYWE1) [机器人](https://t.me/Nanflix_bot)
  - 天南小筑 US (`tiannanus`): [频道](http://t.me/Nanflix) [群组](http://t.me/+kDBdjwtZwudhYWE1) [机器人](https://t.me/US_nan_bot)
  - MJJ (`mjj`): [频道](https://t.me/YH_Emby) [群组](https://t.me/mjj_emby_Chat) [机器人](https://t.me/mjjemby_uesr_bot)
  - Pilipili (`pilipili`): [频道](https://t.me/PiliPiliTv) [群组](http://t.me/PiliPiliTv) [机器人](https://t.me/PiliPiliUltraTv_bot)
  - CC 公益 (`cc`): [频道](https://t.me/CcEmby) [群组](https://t.me/Embycc) [机器人](https://t.me/EmbyCc_bot)
  - 卡戎 (`charon`): [频道](https://t.me/CharonTV) [群组](https://t.me/CharonTV_Talk) [机器人](https://t.me/CharonTV_Bot)
  - 未响 (`future`): [频道](https://t.me/FutureEcho_Notice) [群组](https://t.me/FutureEcho_Chat) [机器人](https://t.me/lotayu_bot)
  - AWA 影视服 (`awatv`): [频道](https://t.me/awa_tv) [群组](https://t.me/awatv_chat) [机器人](https://t.me/awatv3_bot)
  - Lily (`lily`): [频道](https://t.me/lily_yaya) [群组](https://t.me/lilydeyaa) [机器人](https://t.me/lilyembybot)
  - 见手青 (`jsq`): [频道](https://t.me/jsq_channel) [群组](https://t.me/jsq_group) [机器人](https://t.me/jsq_ac_mg_bot)
  - DVFilm (`dvfilm`): [频道](https://t.me/dvfilmupdating) [机器人](https://t.me/DVfilm_user_bot)
  - 冰镇西瓜 (`watermelon`): [频道](https://t.me/WatermelonAirport) [群组](https://t.me/WatermelonAirportGroup) [机器人](https://t.me/XiguaEmbyBot)
  - Lyrebird (`lyrebird`): [频道](https://t.me/lyrebirdchannel) [群组](https://t.me/lyrebirdchat) [机器人](https://t.me/Lyrebird_bot)
  - 非越助手 (`sfcju`): [频道](https://t.me/sfcj_org) [群组](https://t.me/sfcj_chat) [机器人](https://t.me/sfcju_Bot)
  - Yomo (`yomo`): [频道](https://t.me/yomoemby_notice) [群组](https://t.me/yomoemby) [机器人](https://t.me/yomoemby_bot)
  - Raismusic (`raismusic`): [频道](https://t.me/raisemby_channel) [群组1](https://t.me/raismusic_group) [群组2](https://t.me/Raisembyg) [机器人](https://t.me/raismusicbot)
  - AIVBI (`aivbi`): [频道](https://t.me/plus_emby) [群组](https://t.me/plusemby) [机器人](https://t.me/AIVBIbot)
  - Alpha 海外服 (`alpha`): [频道](https://t.me/AlphaTVOverseaChannel) [群组](https://t.me/AlphaTVOverseaGroup) [机器人](https://t.me/AlphaTVOverseaBoss_bot)
  - 月饼 (`mooncake`): [频道](https://t.me/Mooncake_notify) [群组](https://t.me/Mooncake_Emby) [机器人](https://t.me/Moonkkbot)
  - Plumber (`plumber`): [频道](http://t.me/PlumberEmby) [群组](http://t.me/+S060mYNUi1xlODlh) [机器人](https://t.me/Plumberembybot)
  - 飞跃地平线 (`feiyuedpx`): [频道](https://t.me/dpxpindao) [群组](https://t.me/+vHiy1TBnnjNiOWU1) [机器人](https://t.me/feiyueDPX_bot)
  - Levilde Luminia (`levilde`): [频道](https://t.me/+X5jJKAnbkl8wNWNl) [群组](https://t.me/+LzAmejEBy-I4N2E1) [机器人](https://t.me/Levilde_Luminia_Bot)
  - 收束世界线 (`worldline`): [机器人](https://t.me/WorldLineEmby_bot)
  - 飞跃星空 (`feiyuemusic`): [群组](https://t.me/+FVPdVkpM8moyNjc1) [机器人](https://t.me/xingkongmusic_bot)
  - Misty (`misty`): [频道](https://t.me/FreeEmbyChannel) [群组](https://t.me/FreeEmby) [机器人](https://t.me/EmbyMistyBot)
  - 探花 (`tanhua`): [频道](https://t.me/tanhua_tv2024) [群组](https://t.me/tanhuatv2025) [机器人](https://t.me/TanhuaTvBot)
  - iKun 音乐服 (`ikunmusic`): [频道](https://t.me/Asukacute) [群组](https://t.me/ikunvv) [机器人](https://t.me/iikun_bot)
  - HKA (`hka`): [群组](https://t.me/hkaemby) [机器人](https://t.me/hkaemby_bot)
  - AuroraMedia (`aurora`): [频道](https://t.me/AuroraMedia2) [机器人](https://t.me/AuroraMedia1_bot)
  - SaturDay.Lite (`saturday`): [频道](https://t.me/saturday_lite_channel) [群组](https://t.me/SaturDay_Lite) [机器人](https://t.me/saturday_lite_bot)
  - 鹅 (`zm`): [机器人](https://t.me/ZXCHSJSHbot)
  - 起点站: [群组](https://t.me/tdckemby)
    - 新机器人 (`tdck_new`): [机器人](https://t.me/StartTdckBot)
    - 旧机器人 (`tdck`) [机器人](https://t.me/tdck_emby_create_bot)
  - 惊蛰 (`jingzhe`): [频道](https://t.me/jz_emby) [群组](https://t.me/jingzhe_EMBY) [机器人](https://t.me/JingzheProbot)

  <!-- #endregion checkiner-sites -->

  - **更多签到站**可通过[模板配置](https://emby-keeper.github.io/guide/配置文件#service-子项)或[二次开发](https://emby-keeper.github.io/guide/参与开发#每日签到站点)实现.

  - 测试中新签到器 (默认禁用, 请参考[教程文档](https://emby-keeper.github.io/guide/配置文件#service-子项)启用):
    <!-- #region checkiner-beta-sites -->

    - Temby (`temby`): [频道](https://t.me/tembychannel) [群组](https://t.me/tembygroup) [机器人](https://t.me/HiEmbyBot)
    - Temby 测试服 (`temby_beta`): [群组](https://t.me/tembybeta) [机器人](https://t.me/Temby_Bot)
    - Ciji (`ciji`): [机器人](https://t.me/MM_nastool_bot)
    - StarCat (`starcat`): [频道](https://t.me/StarCatEmby) [群组](https://t.me/StarCatEmby) [机器人](https://t.me/StarCatBot)
    - 音海拾贝 (`navidrome`): [频道](https://t.me/navidrom_notify) [群组](https://t.me/navidrom_talk) [机器人](https://t.me/navidrome_bot)
    - July (`july`): [群组](https://t.me/July_emby) [机器人](https://t.me/NASTOOL7_bot)

    <!-- #endregion checkiner-beta-sites -->
  - 关服, 无响应, 或已停用签到功能 (默认禁用, 请参考[教程文档](https://emby-keeper.github.io/guide/配置文件#service-子项)启用):
    <!-- #region checkiner-ignored-sites -->

    - 卷毛鼠 (`jms`): ~~[频道](https://t.me/CurlyMouse) [群组](https://t.me/Curly_Mouse) [机器人](https://t.me/jmsembybot)~~
    - Akuai (`akuai`): ~~[频道](https://t.me/Akuaitzpibgdao) [群组](https://t.me/ikuaiemby) [机器人](https://t.me/joulilibot)~~
    - 垃圾影音 (`ljyy`): ~~[群组](https://t.me/+3sP2A-fgeXg0ZmY1) [机器人](https://t.me/zckllflbot)~~
    - EmbyHub (`embyhub`): ~~[频道](https://t.me/embyhub) [群组](https://t.me/emby_hub) [机器人](https://t.me/EdHubot)~~
    - BlueSea (`bluesea`): ~~[群组](https://t.me/blueseachat) [机器人](https://t.me/blueseamusic_bot)~~
    - 卷毛鼠 IPTV (`jms_iptv`): ~~[频道](https://t.me/CurlyMouseIPTV) [群组](https://t.me/Curly_MouseIPTV) [机器人](https://t.me/JMSIPTV_bot)~~
    - Singularity (`singularity`): ~~[频道](https://t.me/Singularity_Emby_Channel) [群组](https://t.me/Singularity_Emby_Group) [机器人](https://t.me/Singularity_Emby_Bot)~~
    - 剧狗 (`judog`): ~~[频道](https://t.me/Mulgoreemby) [机器人](https://t.me/mulgorebot)~~
    - Heisi (`heisi`): ~~[频道](https://t.me/HeisiEm) [群组](https://t.me/HeisiYi) [机器人](https://t.me/HeisiheiBot)~~
    - 阿甘正传 (`theend`): ~~[群组](https://t.me/+5vRfDeGmOKNiMzU1) [机器人](https://t.me/theendemby_bot)~~
    - Apop 压测服 (`apop`): ~~[频道](https://t.me/ApopCloud_Channel) [群组](https://t.me/apopcloud) [机器人](https://t.me/apopcloudemby_bot)~~
    - Akile: [群组](https://t.me/akileChat)
      - 群组内签到 (`akile_group`): ~~[群组](https://t.me/akileChat) [机器人](https://t.me/akilecloud_bot)~~
      - 机器人签到 (`akile`): ~~[机器人](https://t.me/akilecloud_bot)~~
    - 尘烬 (`skysink`): ~~[频道](https://t.me/skysink) [机器人](https://t.me/kyououbot)~~
    - AWA 音乐服 (`awamusic`): ~~[频道](https://t.me/vpsliebiao) [群组](https://t.me/vpsliebiaochat) [机器人](https://t.me/awamm_bot)~~

    <!-- #endregion checkiner-ignored-sites -->
  - 其他非 Emby 相关 (默认禁用, 请参考[教程文档](https://emby-keeper.github.io/guide/配置文件#service-子项)启用):
    <!-- #region checkiner-other-sites -->

    - 搜书神器 (`sssq`): [机器人](https://t.me/sosdbot?start=fromid_6489896414)
    - 纸片 DDoS (`zhipian`): [频道](https://t.me/PaperBotnet) [机器人](https://t.me/zhipianbot?start=2zbx04e)
    - 情报局社工库 (`infsgk`): [机器人](https://t.me/qbjSGKzhuquebot?start=NjQ4OTg5NjQxNA==)
    - AI 社工库 (`aisgk`): [频道](https://t.me/AISGKChannel) [机器人](https://t.me/aishegongkubot?start=AISGK_BZ5728VM)
    - 狗狗社工库 (`dogsgk`): [频道](https://t.me/DogeSGK) [机器人](https://t.me/DogeSGK_bot?start=6489896414)
    - 花花社工库 (`huasgk`): [频道](https://t.me/sgkhua) [机器人](https://t.me/sgkvipbot?start=vip_1211595)
    - 天猫社工库 (`tianmaosgk`): [机器人](https://t.me/UISGKbot?start=7s3rgxyf)
    - 平安社工库 (`pingansgk`): [机器人](https://t.me/pingansgk_bot?start=cOfqBqegLS)
    - 小熊社工库 (`bearsgk`): [机器人](https://t.me/BearSGK_bot?start=6489896414)
    - 数据社工库 (`datasgk`): [机器人](https://t.me/datasgk_bot?start=6489896414)
    - 助手社工库 (`zhushousgk`): [机器人](https://t.me/sgk001_bot?start=NjQ4OTg5NjQxNA==)
    - 星月社工库 (`starsgk`): [机器人](https://t.me/XY_SGKBOT?start=kta1ELmKuM)
    - Bit 社工库 (`bitsgk`): [机器人](https://t.me/BitSGKBot?start=a085f7b00dcf)
    - 迷你世界社工库 (`minisgk`): [机器人](https://t.me/mnsjsgkbot?start=4146989846)
    - 冰岛社工库 (`bingdaosgk`): [机器人](https://t.me/BingDaoSGKBot?start=eM81qS9k)
    - 春江社工库 (`chunjiangsgk`): [机器人](https://t.me/ChunJiang_SGK_Bot?start=J74d1R73Z)
    - Koi 社工库 ('koisgk'): [机器人](https://t.me/KoiSGKbot?start=NI5kOPo9)
    - 清风社工库 (`qingfengsgk`): [机器人](https://t.me/Weifeng007_bot?start=iTMnapPg1Y)
    - Xray 社工库 (`xraysgk`): [机器人](https://t.me/Zonesgk_bot?start=XSZAZAXSPS)
    - Seed 社工库 (`seedsgk`): [机器人](https://t.me/SeedSGKBOT?start=38weac31b)
    - Master 社工库 (`mastersgk`): [机器人](https://t.me/BaKaMasterBot?start=dWxzgkRSBj)
    - 繁花社工库 (`fanhuasgk`): [机器人](https://t.me/FanHuaSGK_bot?start=FanHua_ALCPRMHA)
    - 度娘社工库 (`baidusgk`): [机器人](https://t.me/baidusell_bot?start=6489896414)
    - 红鼻子社工库 (`rednosesgk`): [机器人](https://t.me/freesgk123_bot?start=ZZVFMECU)
    - 银联社工库 (`unionsgk`): [机器人](https://t.me/unionpaysgkbot?start=NjQ4OTg5NjQxNA==)
    - 007 社工库 (`agentsgk`): [机器人](https://t.me/sgk007_bot?start=NjQ4OTg5NjQxNA)
    - 约翰社工库 (`johnsgk`): [机器人](https://t.me/yuehanbot?start=6489896414v4fufb)
    - 知乎社工库 (`zhihusgk`): [机器人](https://t.me/zhihu_bot?start=ZHIHU_PIIIBARB)
    - Carll 社工库 1 (`carll1sgk`): [机器人](https://t.me/Carllnet_bot?start=6489896414)
    - Carll 社工库 2 (`carll2sgk`): [机器人](https://t.me/Carllnet2_bot?start=6489896414)
    - Ingeek 社工库 (`ingeeksgk`): [机器人](https://t.me/ingeeksgkbot?start=NjQ4OTg5NjQxNA==)
    - 叮当猫社工库 (`dingdangsgk`): [机器人](https://t.me/DingDangCats_Bot?start=d9bb127efc6127d1)
    - 魔神社工库 (`moshensgk`): [机器人](https://t.me/moshensgk_bot?start=NjQ4OTg5NjQxNA==)
    - Bost 社工库 (`bostsgk`): [机器人](https://t.me/BOST_SGK_BOT?start=6489896414)
    - Oixel (`oixel`): [机器人](https://t.me/oixel_bot?start=QvSBSqCG)
    - 飞机工具箱 (`feiji`): [机器人](https://t.me/fjtool_bot?start=6489896414C44)
    - 鸟哥轰炸 (`niaoge`): [机器人](https://t.me/nb3344bot?start=6489896414)
    - Bytevirt (`bytevirt_group`): [群组](https://t.me/bytevirtchat)
    - 金鼎轰炸 (`jinding`): [机器人](https://t.me/jdHappybot?start=6489896414)
    - M78 星云 (`m78`): [机器人](https://t.me/M78CheckIn_bot)

    <!-- #endregion checkiner-other-sites -->
- **Telegram 自动监控信息**
  <!-- #region monitor-sites -->

  - Pornemby:
    - 问题回答 (`pornemby_answer`): [群组](https://t.me/Pornemby)
    - 科举考试 (`pornemby_exam`): [群组](https://t.me/Pornemby)
    - 自动抢注 (`pornemby_register`): [群组](https://t.me/Pornemby)
    - 自动抢红包雨 (`pornemby_dragon_rain`): [群组](https://t.me/Pornemby)
    - 自动翻倍 (`pornemby_double`): [群组](https://t.me/Pornemby)
    - 无 HP 自动停止自动水群 (`pornemby_nohp`): [群组](https://t.me/Pornemby)
    - 风险时期自动停止 (`pornemby_alert`): [群组](https://t.me/Pornemby)
  - 不给看 抢邀请码 (`bgk`): [群组](https://t.me/Ephemeralemby) [机器人](https://t.me/UnknownEmbyBot)
  - 叔服 抢邀请码 (`shufu`): [群组](http://t.me/+4eq37Ip8ayRhNDI9) [机器人](https://t.me/dashu660_bot)
  - Misty 开注自动注册 (`misty`): [频道](https://t.me/FreeEmbyChannel) [群组](https://t.me/FreeEmby) [机器人](https://t.me/EmbyMistyBot)

  <!-- #endregion monitor-sites -->
  - 测试中的站点 (默认禁用, 请参考[教程文档](https://emby-keeper.github.io/guide/配置文件#service-子项)启用):
    <!-- #region monitor-beta-sites -->

    - 未响 抢邀请码 (`future`): [频道](https://t.me/FutureEcho_Notice) [群组](https://t.me/FutureEcho_Chat) [机器人](https://t.me/lotayu_bot)
    - 终点站 考核辅助 (`terminus_exam`): [频道](https://t.me/embypub) [群组](https://t.me/EmbyPublic) [机器人](https://t.me/EmbyPublicBot)

    <!-- #endregion monitor-beta-sites -->
  - 关服或无响应 (默认禁用, 请参考[教程文档](https://emby-keeper.github.io/guide/配置文件#service-子项)启用):
    <!-- #region monitor-ignored-sites -->

    - 全局自动从众 (`follow`): 当在任何群组中发现 5 分钟内 5 条一样内容的消息, 会自动跟一句 (影响范围大默认禁用)
    - Polo 抢邀请码 (`polo`): ~~[频道](https://t.me/poloembyc) [群组](https://t.me/poloemby) [机器人](https://t.me/polo_emby_bot)~~
    - 剧狗 开注自动注册 (`judog`): ~~[频道](https://t.me/Mulgoreemby) [机器人](https://t.me/mulgorebot)~~
    - Embyhub 开注自动注册 (`embyhub`): ~~[频道](https://t.me/embyhub) [群组](https://t.me/emby_hub) [机器人](https://t.me/EdHubot)~~
    - Viper 抢邀请码 (`viper`): ~~[频道](https://t.me/viper_emby_channel) [群组](https://t.me/Viper_Emby_Chat) [机器人](https://t.me/viper_emby_bot)~~

    <!-- #endregion monitor-ignored-sites -->

- **Telegram 自动水群**
  <!-- #region messager-sites -->

  <!-- #endregion messager-sites -->

  - 测试中的站点 (默认禁用, 请参考[教程文档](https://emby-keeper.github.io/guide/配置文件#service-子项)启用):
    <!-- #region messager-beta-sites -->

    - Marmot (`marmot`) (周末早晚签到): [频道](https://t.me/Marmot_Emby_Channel) 群组 (非公开) [机器人](https://t.me/Marmot_Emby_Account_BOT)

    - Pornemby (`pornemby`) (打怪兽水群): [频道](https://t.me/pornembyservice) [群组](https://t.me/Pornemby) [机器人](https://t.me/PronembyTGBot2_bot)

    - Pornemby 智能化回答 (`smart_pornemby`) (打怪兽水群, AI 会考虑上下文和群组语言风格进行回答): [频道](https://t.me/pornembyservice) [群组](https://t.me/Pornemby) [机器人](https://t.me/PronembyTGBot2_bot)

    <!-- #endregion messager-beta-sites -->
  - 关服或无响应 (默认禁用, 请参考[教程文档](https://emby-keeper.github.io/guide/配置文件#service-子项)启用):
    <!-- #region messager-ignored-sites -->

    - NakoNako 自动水群 (`nakonako`): ~~[群组](https://t.me/NakoNetwork) [机器人](https://t.me/nakonetwork_bot)~~

    <!-- #endregion messager-ignored-sites -->

**注意**: 部分功能由于涉及竞争条件和付费验证码解析服务等, 仅有[高级用户](https://emby-keeper.github.io/guide/高级用户)才能使用, 您需要共享邀请码或[赞助项目](https://afdian.com/a/jackzzs)以成为永久有效期的高级用户.

## 支持 Embykeeper

##### 开发者团队

- ~~[jackzzs](https://github.com/jackzzs)~~
- [zetxtech](https://github.com/zetxtech)

##### 通过[爱发电](https://afdian.com/a/jackzzs)赞助

![Kitty](https://github.com/emby-keeper/emby-keeper/raw/main/images/kitty.gif)
