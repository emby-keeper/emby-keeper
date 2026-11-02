<script setup>
import {
  VTermynal,
  VtInput,
  VtProgress,
  VtText,
  VtSpinner,
} from '@lehoczky/vue-termynal';
</script>

<template>
  <v-termynal
    class="termynal"
    cursor="|"
    lazy
    forward-button
    restart-button
    :line-delay="400"
    :type-delay="40"
  >
    <vt-input><span>embykeeper</span></vt-input>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content"
        >欢迎使用 Embykeeper! 正在启动, 请稍等. 您可以通过 Ctrl+C
        以结束运行.</span
      >
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">Emby保活</span>
        <span>: 开始执行 Emby 保活.</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">Emby保活</span>
        <span>: 登录账号:</span>
        <span class="highlight"> "mike"</span>
        <span> 至服务器:</span>
        <span class="highlight"> "https://site.com:443"</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">Emby保活</span>
        <span> (</span>
        <span class="highlight">site:mike</span>
        <span>): 成功连接至服务器 (Emby 4.8.9.0).</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">Emby保活</span>
        <span> (</span>
        <span class="highlight">site:mike</span>
        <span>): 开始播放视频, 共需播放 60 秒.</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">Emby保活</span>
        <span> (</span>
        <span class="highlight">site:mike</span>
        <span>): 播放完成, 共 60 秒, 当前该视频播放 1 次.</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="success">SUCCESS</span>
      <span class="content">
        <span class="scheme">Emby保活</span>
        <span> (</span>
        <span class="highlight">site:mike</span>
        <span>): 保活成功.</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">Telegram</span>
        <span>: 登录至账号</span>
        <span class="highlight"> "+123456789"</span>
        <span>.</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">Telegram</span>
        <span>: 已连接到 Telegram, 签到器正在初始化.</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">每日签到</span>
        <span> (</span>
        <span class="highlight">mike</span>
        <span>): (卷毛鼠) 开始执行签到: 卷毛鼠 (@jmsembybot).</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">每日签到</span>
        <span> (</span>
        <span class="highlight">mike</span>
        <span>): (卷毛鼠) 签到成功:</span>
        <span class="success"> + 6 分 -> 12 分</span>
        <span>.</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="info">INFO</span>
      <span class="content">
        <span class="scheme">每日签到</span>
        <span> (</span>
        <span class="highlight">mike</span>
        <span>): (数据社工库) 今天已经签到过了.</span>
      </span>
    </vt-text>
    <vt-text class="terminal-line">
      <span class="success">SUCCESS</span>
      <span class="content">
        <span class="scheme">每日签到</span>
        <span> (</span>
        <span class="highlight">mike</span>
        <span>): 签到成功 (共2个,</span>
        <span class="success"> 1成功</span>
        <span>,</span>
        <span class="skip"> 1跳过</span>
        <span>):</span>
      </span>
    </vt-text>
  </v-termynal>
</template>

<style scoped>
.termynal {
  padding: 20px;
  padding-top: 35px;
  border-radius: 8px;
  box-shadow: 0 0 30px 12px rgba(100, 149, 237, 0.3);
  --vt-color-bg: #273346;
  --vt-color-text: #efefef;
  width: 100%;
}

.dark .termynal {
  --vt-color-bg: #1e293b;
  box-shadow: 0 0 15px 5px rgba(100, 149, 237, 0.2);
}

@media (min-width: 960px) {
  .termynal {
    padding: 45px 45px;
  }
}

.v-termynal:before {
  width: 8px;
  height: 8px;
  box-shadow:
    16px 0 #f4c025,
    32px 0 #3ec930;
}

@media (min-width: 960px) {
  .v-termynal:before {
    width: 10px;
    height: 10px;
    box-shadow:
      20px 0 #f4c025,
      40px 0 #3ec930;
  }
}

.v-termynal:after {
  content: 'Example';
  font-size: 14px;
}

@media (min-width: 960px) {
  .v-termynal:after {
    font-size: 14px;
  }
}

.v-termynal .vt__line {
  line-height: 1.5;
  font-family: ui-monospace, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', sans-serif;
  font-size: 14px;
  word-break: break-all;
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

@media (min-width: 960px) {
  .v-termynal .vt__line {
    font-size: 16px;
  }
}

.terminal-line {
  display: flex;
  align-items: flex-start;
}

.terminal-line .info,
.terminal-line .success {
  flex: 0 0 80px;
  text-align: left;
}

.terminal-line .content {
  flex: 1;
  padding-left: 10px;
  word-break: break-word;
}

.terminal-line:before {
  display: none;
}

.success {
  color: #2ecc71;
  font-weight: semibold;
}

.info {
  color: #4a90e2;
  font-weight: semibold;
}

.scheme {
  color: #9b59b6;
  font-weight: 500;
}

.highlight {
  color: #1abc9c;
}

.success {
  color: #2ecc71;
}

.skip {
  color: #f39c12;
}
</style>
