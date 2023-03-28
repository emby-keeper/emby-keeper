from loguru import logger


def check_config(config):
    from schema import And, Optional, Or, Regex, Schema, SchemaError, Use

    PositiveInt = lambda: And(Use(int), lambda n: n > 0)
    schema = Schema(
        {
            Optional("timeout"): PositiveInt(),
            Optional("retries"): PositiveInt(),
            Optional("concurrent"): PositiveInt(),
            Optional("random"): PositiveInt(),
            Optional("nofail"): bool,
            Optional("captcha_service"): Use(str),
            Optional("captcha_service_key"): Use(str),
            Optional("proxy"): Schema(
                {
                    Optional("hostname"): Regex(
                        r"^(?=.{1,255}$)[0-9A-Za-z](?:(?:[0-9A-Za-z]|-){0,61}[0-9A-Za-z])?(?:\.[0-9A-Za-z](?:(?:[0-9A-Za-z]|-){0,61}[0-9A-Za-z])?)*\.?$"
                    ),
                    Optional("port"): And(Use(int), lambda n: n > 1024 and n < 65536),
                    Optional("scheme"): Schema(Or("socks5", "http")),
                }
            ),
            Optional("telegram"): [
                Schema(
                    {
                        "api_id": Regex(r"^\d+$"),
                        "api_hash": Regex(r"^[a-z0-9]+$"),
                        "phone": Use(str),
                        Optional("monitor"): bool,
                        Optional("send"): bool,
                    }
                )
            ],
            Optional("emby"): [
                Schema(
                    {
                        "url": Regex(
                            r"(http|https):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])"
                        ),
                        "username": Use(str),
                        "password": Use(str),
                        Optional("time"): PositiveInt(),
                        Optional("progress"): PositiveInt(),
                    }
                )
            ],
        }
    )
    try:
        schema.validate(config)
    except SchemaError as e:
        logger.error(f"配置文件错误, 请检查配置文件:\n{e}.")
        return False
    return True


def get_faked_config():
    import uuid

    from faker import Faker
    from faker.providers import internet, profile

    fake = Faker()
    fake.add_provider(internet)
    fake.add_provider(profile)
    account = {}

    account["timeout"] = 60
    account["retries"] = 10
    account["concurrent"] = 2
    account["random"] = 15
    account["proxy"] = {
        "host": "127.0.0.1",
        "port": "1080",
        "scheme": "socks5",
    }
    account["captcha_service"] = 'disabled'
    account["captcha_service_key"] = uuid.uuid4().hex
    account["telegram"] = []
    for _ in range(2):
        account["telegram"].append(
            {
                "api_id": fake.numerify(text="########"),
                "api_hash": uuid.uuid4().hex,
                "phone": f'+861{fake.numerify(text="##########")}',
                "monitor": True,
                "send": False,
            }
        )
    account["emby"] = []
    for _ in range(2):
        account["emby"].append(
            {
                "url": fake.url(["https"]),
                "username": fake.profile()["username"],
                "password": fake.password(),
                "time": 800,
                "progress": 1000,
            }
        )
    return account


def version(value):
    if value:
        print("[orange3]{__name__.capitalize()}[/]")
