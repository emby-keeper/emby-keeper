from . import BotCheckin

__ignore__ = True


class TemplateBCheckin(BotCheckin):
    bot_checkin_cmd = "/checkin"
    bot_use_captcha = False


def use(**kw):
    return type("TemplatedClass", (TemplateBCheckin,), kw)
