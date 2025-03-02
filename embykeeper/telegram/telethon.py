from __future__ import annotations

import getpass
import inspect
import typing
from loguru import logger

if typing.TYPE_CHECKING:
    from telethon import TelegramClient


class TelethonUtils:
    def __init__(self, client: TelegramClient):
        self.client = client

    def start(
        self,
        phone: typing.Union[typing.Callable[[], str], str] = lambda: input(
            "Please enter your phone (or bot token): "
        ),
        password: typing.Union[typing.Callable[[], str], str] = lambda: getpass.getpass(
            "Please enter your password: "
        ),
        *,
        bot_token: str = None,
        force_sms: bool = False,
        code_callback: typing.Callable[[], typing.Union[str, int]] = None,
        first_name: str = "New User",
        last_name: str = "",
        max_attempts: int = 3,
    ):
        """This function is a modified version of telethon.client.auth.AuthMethods.start"""

        if code_callback is None:

            def code_callback():
                return input("Please enter the code you received: ")

        elif not callable(code_callback):
            raise ValueError(
                "The code_callback parameter needs to be a callable "
                "function that returns the code you received by Telegram."
            )

        if not phone and not bot_token:
            raise ValueError("No phone number or bot token provided.")

        if phone and bot_token and not callable(phone):
            raise ValueError("Both a phone and a bot token provided, " "must only provide one of either")

        coro = self._start(
            phone=phone,
            password=password,
            bot_token=bot_token,
            force_sms=force_sms,
            code_callback=code_callback,
            first_name=first_name,
            last_name=last_name,
            max_attempts=max_attempts,
        )
        return coro if self.client.loop.is_running() else self.client.loop.run_until_complete(coro)

    async def _start(
        self,
        phone,
        password,
        bot_token,
        force_sms,
        code_callback,
        first_name,
        last_name,
        max_attempts,
    ):
        """This function is a modified version of telethon.client.auth.AuthMethods._start"""

        from telethon import errors, utils

        if not self.client.is_connected():
            await self.client.connect()

        # Rather than using `is_user_authorized`, use `get_me`. While this is
        # more expensive and needs to retrieve more data from the server, it
        # enables the library to warn users trying to login to a different
        # account. See #1172.
        me = await self.client.get_me()
        if me is not None:
            # The warnings here are on a best-effort and may fail.
            if bot_token:
                # bot_token's first part has the bot ID, but it may be invalid
                # so don't try to parse as int (instead cast our ID to string).
                if bot_token[: bot_token.find(":")] != str(me.id):
                    logger.warning(
                        "该会话已经包含一个授权用户,所以没有使用提供的 bot_token 登录机器人账号(可能导致没有使用你期望的用户)"
                    )
            elif phone and not callable(phone) and utils.parse_phone(phone) != me.phone:
                logger.warning(
                    "该会话已经包含一个授权用户,所以没有使用提供的手机号登录账号 (可能导致没有使用你期望的用户)"
                )

            return self.client

        if not bot_token:
            # Turn the callable into a valid phone number (or bot token)
            while callable(phone):
                value = phone()
                if inspect.isawaitable(value):
                    value = await value

                if ":" in value:
                    # Bot tokens have 'user_id:access_hash' format
                    bot_token = value
                    break

                phone = utils.parse_phone(value) or phone

        if bot_token:
            await self.client.sign_in(bot_token=bot_token)
            return self.client

        me = None
        attempts = 0
        two_step_detected = False

        await self.client.send_code_request(phone, force_sms=force_sms)
        while attempts < max_attempts:
            try:
                value = code_callback()
                if inspect.isawaitable(value):
                    value = await value

                # Since sign-in with no code works (it sends the code)
                # we must double-check that here. Else we'll assume we
                # logged in, and it will return None as the User.
                if not value:
                    raise errors.PhoneCodeEmptyError(request=None)

                # Raises SessionPasswordNeededError if 2FA enabled
                me = await self.client.sign_in(phone, code=value)
                break
            except errors.SessionPasswordNeededError:
                two_step_detected = True
                break
            except (
                errors.PhoneCodeEmptyError,
                errors.PhoneCodeExpiredError,
                errors.PhoneCodeHashEmptyError,
                errors.PhoneCodeInvalidError,
            ):
                logger.warning("验证码错误, 请重试.")

            attempts += 1
        else:
            raise RuntimeError("{} consecutive sign-in attempts failed. Aborting".format(max_attempts))

        if two_step_detected:
            if not password:
                raise ValueError(
                    "Two-step verification is enabled for this account. "
                    "Please provide the 'password' argument to 'start()'."
                )

            if callable(password):
                for _ in range(max_attempts):
                    try:
                        value = password()
                        if inspect.isawaitable(value):
                            value = await value

                        me = await self.client.sign_in(phone=phone, password=value)
                        break
                    except errors.PasswordHashInvalidError:
                        logger.warning("两步验证密码错误, 请重试.")
                else:
                    raise errors.PasswordHashInvalidError(request=None)
            else:
                me = await self.client.sign_in(phone=phone, password=password)

        return self.client
