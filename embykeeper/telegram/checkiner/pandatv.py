from ._templ_a import TemplateACheckin


class PandaTVCheckin(TemplateACheckin):
    name = "PandaTV"
    bot_username = "PandaTV_Emby_Bot"
    checked_retries = 6
    templ_panel_keywords = "主面板"
