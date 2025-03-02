from ._templ_a import TemplateACheckin

__ignore__ = True


class StarcatCheckin(TemplateACheckin):
    name = "StarCat"
    bot_username = "StarCatBot"
    templ_panel_keywords = ["請在下方選擇您要使用的功能"]
    additional_auth = ["prime"]
