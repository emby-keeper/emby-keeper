from pathlib import Path
import tomli as tomllib

from embykeeper.telegram.session import ClientsSession
from embykeeper.utils import AsyncTyper
from embykeeper.config import config

app = AsyncTyper()


@app.async_command()
async def main(config_file: Path, spec: str):
    await config.reload_conf(config_file)
    async with ClientsSession(config.telegram.account[:1]) as clients:
        async for _, tg in clients:
            try:
                # Try to convert spec to integer (for user_id)
                try:
                    spec = int(spec)
                except ValueError:
                    pass  # Keep as string (for username)

                results = await tg.get_users(spec)
                if results:
                    print(results)
                else:
                    print("User not found")
                break
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    app()
