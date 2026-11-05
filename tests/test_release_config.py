import asyncio
import copy
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml
from fastapi import HTTPException
from typer.testing import CliRunner

from embykeeper.api import sites
from embykeeper.api import emby, subsonic
from embykeeper.api import telegram
from embykeeper.schema import EmbyAccount, SubsonicAccount, TelegramAccount
from embykeeper.telegram import registrar_main
from embykeeper.telegram.registrar import _templ_a


class WebCommandTests(unittest.TestCase):
    def test_example_password_is_rejected_before_starting_backend(self):
        from embykeeper.cli import app

        with patch.dict("os.environ", {"EK_WEBPASS": "your-password"}), patch(
            "embykeeperapi.app._ensure_bind_available"
        ) as bind, patch("embykeeperapi.app.pm.start") as start:
            result = CliRunner().invoke(app, ["web"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("your-password", result.output)
        bind.assert_not_called()
        start.assert_not_called()

    def test_other_password_starts_the_server(self):
        from embykeeper.cli import app

        with patch.dict("os.environ", {"EK_WEBPASS": "another-password"}), patch(
            "embykeeperapi.app._ensure_bind_available"
        ), patch("embykeeperapi.app.pm.start"), patch(
            "embykeeperapi.app.pm.owns_backend", return_value=False
        ), patch(
            "embykeeperapi.app.PanelServer"
        ) as server:
            result = CliRunner().invoke(app, ["web"])
        self.assertEqual(result.exit_code, 0, result.output)
        server.return_value.run.assert_called_once()

    def test_web_starts_the_panel_and_managed_backend_by_default(self):
        from embykeeper.cli import app

        with patch("embykeeperapi.app._run_server") as serve:
            result = CliRunner().invoke(app, ["web"])
        self.assertEqual(result.exit_code, 0, result.output)
        serve.assert_called_once()
        self.assertTrue(serve.call_args.kwargs["autostart"])
        self.assertFalse(serve.call_args.kwargs["reload"])

    def test_web_forwards_bind_options(self):
        from embykeeper.cli import app

        with patch("embykeeperapi.app._run_server") as serve:
            result = CliRunner().invoke(app, ["web", "--host", "127.0.0.1", "--port", "8123"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(serve.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(serve.call_args.kwargs["port"], 8123)

    def test_web_help_does_not_start_a_server(self):
        from embykeeper.cli import app

        with patch("embykeeperapi.app._run_server") as serve:
            result = CliRunner().invoke(app, ["web", "--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--port", result.output)
        serve.assert_not_called()

    def test_existing_version_option_still_works(self):
        import embykeeper
        from embykeeper.cli import app

        result = CliRunner().invoke(app, ["--version"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(embykeeper.__version__, result.output)

    def test_existing_config_and_api_options_are_preserved(self):
        from typer.main import get_command
        from embykeeper.cli import app

        command = get_command(app)
        with command.make_context("embykeeper", ["web.toml", "--api", "--api-port", "8001"]) as context:
            self.assertEqual(context.params["config_file"], "web.toml")
            self.assertTrue(context.params["api"])
            self.assertEqual(context.params["api_port"], 8001)


class WebLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_example_password_is_rejected_by_asgi_startup(self):
        from embykeeperapi.app import app, lifespan

        with patch.dict("os.environ", {"EK_WEBPASS": "your-password"}), self.assertRaisesRegex(
            ValueError, "your-password"
        ):
            async with lifespan(app):
                self.fail("the panel should not start")

    async def test_legacy_console_rejects_example_password(self):
        env = {**os.environ, "EK_WEBPASS": "your-password"}
        result = subprocess.run(
            [sys.executable, "-m", "embykeeperweb.app"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("your-password", result.stdout + result.stderr)


class WindowsPanelTests(unittest.TestCase):
    def test_local_server_creates_initial_config_without_overwriting_it(self):
        from embykeeper.windows_panel import PanelController

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "data" / "config.toml"
            with patch(
                "embykeeperapi.settings.panel_settings.resolved_backend_config_file", return_value=config
            ), patch("embykeeperapi.app._run_server") as serve:
                PanelController()._run()
                self.assertEqual(config.read_text(), "")
                self.assertEqual(serve.call_args.kwargs["host"], "127.0.0.1")
                self.assertEqual(serve.call_args.kwargs["target_host"], "127.0.0.1")
                config.write_text("existing = true\n")
                PanelController()._run()
                self.assertEqual(config.read_text(), "existing = true\n")

    def test_browser_opens_only_when_ready_and_stop_requests_shutdown(self):
        from embykeeper.windows_panel import PANEL_URL, PanelController

        controller = PanelController()
        server = SimpleNamespace(started=False, should_exit=False, force_exit=False)
        controller.set_server(server)
        with patch("embykeeper.windows_panel.webbrowser.open") as browser:
            controller.open_panel()
            browser.assert_not_called()
            server.started = True
            controller.open_panel()
            browser.assert_called_once_with(PANEL_URL)
        controller.stop()
        self.assertTrue(server.should_exit)
        self.assertFalse(controller.is_ready())

    def test_stop_before_server_creation_is_respected(self):
        from embykeeper.windows_panel import PanelController

        controller = PanelController()
        controller.stop()
        server = SimpleNamespace(started=False, should_exit=False, force_exit=False)
        controller.set_server(server)
        self.assertTrue(server.should_exit)


class DockerReleaseTests(unittest.TestCase):
    def test_release_and_editable_images_default_to_web(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "deploy" / "panel" / "Dockerfile").read_text()
        for stage in ("runtime", "editable"):
            with self.subTest(stage=stage):
                body = dockerfile.split(f" AS {stage}\n", 1)[1].split("\nFROM ", 1)[0]
                self.assertIn('CMD ["web"]', body)

    def test_both_release_workflows_build_images_with_the_panel(self):
        root = Path(__file__).resolve().parents[1]
        for filename, target in (("docker.yml", "release"), ("docker-dev.yml", "editable")):
            with self.subTest(workflow=filename):
                workflow = yaml.safe_load((root / ".github" / "workflows" / filename).read_text())
                builds = [
                    step["with"]
                    for step in workflow["jobs"]["build"]["steps"]
                    if step.get("uses", "").startswith("docker/build-push-action@")
                ]
                self.assertTrue(builds)
                self.assertEqual(workflow["env"]["REGISTRY_IMAGE"], "embykeeper/embykeeper")
                for build in builds:
                    self.assertEqual(build["file"], "./deploy/panel/Dockerfile")
                    self.assertEqual(build["target"], target)

    def test_huggingface_space_runs_the_panel_on_its_app_port(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "hf" / "Dockerfile").read_text()
        self.assertRegex(dockerfile, r"FROM embykeeper/embykeeper:v\d+\.\d+\.\d+")
        # Huggingface runs the container as UID 1000 and proxies the Space app_port.
        self.assertIn('CMD ["web", "--port", "1818"]', dockerfile)
        self.assertIn("EMBYKEEPERAPI_BASEDIR=/data", dockerfile)
        self.assertIn("chown -R 1000:1000 /data", dockerfile)
        workflow = yaml.safe_load((root / ".github" / "workflows" / "docker.yml").read_text())
        self.assertIn("sync-to-hf", workflow["jobs"])

    def test_release_draft_lists_commits_since_the_previous_tag(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / ".github" / "workflows" / "draft-release.yml").read_text())
        steps = workflow["jobs"]["draft"]["steps"]
        checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout"))
        self.assertEqual(checkout["with"]["fetch-depth"], 0)
        script = next(step["run"] for step in steps if "release-notes.md" in step.get("run", ""))
        self.assertIn("git log --no-merges --pretty=", script)
        self.assertIn("compare/${previous}...${tag}", script)
        body = (root / ".github" / "RELEASE_BODY.md").read_text()
        self.assertNotIn("v0.0.0", body)
        self.assertNotIn("8.0.1", body)

    def test_compose_and_user_guide_use_the_published_web_image_without_building(self):
        root = Path(__file__).resolve().parents[1]
        guide = (root / "docs" / "guide" / "面板模式部署.md").read_text(encoding="utf-8")
        documented = yaml.safe_load(re.search(r"```yaml\n(.*?)\n```", guide, re.S).group(1))
        supplied = yaml.safe_load((root / "deploy" / "panel" / "docker-compose.yaml").read_text())
        for name, compose in (("guide", documented), ("supplied", supplied)):
            with self.subTest(source=name):
                service = compose["services"]["panel"]
                self.assertIn("embykeeper/embykeeper:latest", service["image"])
                self.assertNotIn("command", service)
                self.assertNotIn("build", service)
        self.assertNotIn("git clone", guide)
        self.assertNotIn("--build", guide)

    def test_user_examples_use_the_placeholder_password_without_timezone(self):
        root = Path(__file__).resolve().parents[1]
        file_texts = {
            "guide": (root / "docs" / "guide" / "面板模式部署.md").read_text(encoding="utf-8"),
            "compose": (root / "deploy" / "panel" / "docker-compose.yaml").read_text(encoding="utf-8"),
            "env": (root / "deploy" / "panel" / ".env.example").read_text(encoding="utf-8"),
        }
        for name, text in file_texts.items():
            with self.subTest(source=name):
                self.assertIsNone(re.search(r"\bTZ\b", text))
        self.assertRegex(file_texts["guide"], r"""EK_WEBPASS: ['"]your-password['"]""")
        self.assertIn("EK_WEBPASS=your-password", file_texts["env"])
        self.assertIn("EK_WEBPASS='your-password'", (root / "README.md").read_text(encoding="utf-8"))


class WindowsReleaseTests(unittest.TestCase):
    def test_release_ships_only_the_online_installer(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / ".github" / "workflows" / "windows.yml").read_text())
        self.assertEqual(set(workflow["jobs"]), {"win-script", "win-validation"})
        archiving = [step for step in workflow["jobs"]["win-script"]["steps"] if "zip" in step.get("run", "")]
        self.assertTrue(archiving)
        for filename in ("Start-Embykeeper.bat", "install.ps1", "version.txt"):
            self.assertIn(filename, archiving[0]["run"])

    def test_manual_dispatch_publishes_the_installer_and_wheel_for_testing(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / ".github" / "workflows" / "windows.yml").read_text())
        artifacts = [
            step
            for job in workflow["jobs"].values()
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/upload-artifact")
        ]
        # Both the installer zip and the wheel are downloadable before a release exists.
        self.assertEqual(len(artifacts), 2)
        for step in artifacts:
            self.assertIn("workflow_dispatch", step["if"])
        self.assertIn("dist/*.whl", artifacts[1]["with"]["path"])

    def test_installer_embeds_python_and_falls_back_between_indexes(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "windows" / "installer-script" / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("$pythonVersion = '3.11.9'", script)
        self.assertIn("-embed-amd64.zip", script)
        self.assertIn("https://www.python.org/ftp/python", script)
        self.assertIn("https://registry.npmmirror.com/-/binary/python", script)
        self.assertLess(script.index("pypi.tuna.tsinghua.edu.cn"), script.index("pypi.org/simple"))
        self.assertIn("your-password", script)
        self.assertNotIn("python-3.8", script)

    def test_published_package_carries_the_panel_ui(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn("graft embykeeperapi/static", (root / "MANIFEST.in").read_text())
        self.assertIn("include-package-data = true", (root / "pyproject.toml").read_text())
        self.assertIn('pystray; sys_platform == "win32"', (root / "requirements.txt").read_text())
        pypi = yaml.safe_load((root / ".github" / "workflows" / "pypi.yml").read_text())
        build_runs = " ".join(step.get("run", "") for step in pypi["jobs"]["build"]["steps"])
        self.assertIn("pnpm run build", build_runs)
        self.assertIn("embykeeperapi/static", build_runs)

    def test_windows_launcher_requires_a_local_password(self):
        root = Path(__file__).resolve().parents[1]
        launcher = (root / "embykeeper" / "windows_panel.py").read_text(encoding="utf-8")
        self.assertIn("EK_WEBPASS", launcher)
        self.assertIn("127.0.0.1", launcher)
        self.assertIn(
            "install.ps1", (root / "windows" / "installer-script" / "Start-Embykeeper.bat").read_text()
        )


class SiteScopeTests(unittest.TestCase):
    def test_removing_last_explicit_site_keeps_empty_scope(self):
        raw = {"site": {"checkiner": ["templ_a<AuditBot>"]}}
        sites._set_site_list_entry(raw, "checkiner", "templ_a<AuditBot>", False)
        self.assertEqual(raw["site"]["checkiner"], [])

    def test_adding_to_explicit_empty_scope_does_not_enable_defaults(self):
        raw = {"site": {"checkiner": []}}
        sites._set_site_list_entry(raw, "checkiner", "templ_a<AuditBot>", True)
        self.assertEqual(raw["site"]["checkiner"], ["templ_a<AuditBot>"])

    def test_editing_keeps_explicit_and_append_forms(self):
        for entry in ("templ_a<AuditBot>", "+templ_a<AuditBot>"):
            with self.subTest(entry=entry):
                raw = {"site": {"checkiner": [entry]}}
                sites._set_site_list_entry(raw, "checkiner", "templ_a<AuditBot>", True)
                self.assertEqual(raw["site"]["checkiner"], [entry])

    def test_editing_excluded_site_keeps_exclusion(self):
        raw = {"site": {"checkiner": ["-templ_a<AuditBot>"]}}
        sites._set_site_list_entry(raw, "checkiner", "templ_a<AuditBot>", False)
        self.assertEqual(raw["site"]["checkiner"], ["-templ_a<AuditBot>"])

    def test_deletion_removes_excluded_site_reference(self):
        raw = {"site": {"checkiner": ["-templ_a<AuditBot>"]}}
        sites._set_site_list_entry(raw, "checkiner", "templ_a<AuditBot>", False, remove=True)
        self.assertNotIn("site", raw)

    def test_invalid_times_and_conflicting_schedules_are_rejected(self):
        for options in (
            {},
            {"times": ["not-a-time"]},
            {"times": ["25:10"]},
            {"times": ["09:00"], "interval_minutes": 5},
            {"interval_minutes": 0},
        ):
            with self.subTest(options=options), self.assertRaises(HTTPException):
                sites._validate_registrar_schedule(options)

    def test_supported_clock_formats_and_intervals_are_accepted(self):
        sites._validate_registrar_schedule({"times": ["09:00", "21:00", "9:00AM", "9:00 PM"]})
        sites._validate_registrar_schedule({"interval_minutes": 5})


class SiteDraftTests(unittest.IsolatedAsyncioTestCase):
    async def test_inactive_default_template_is_persisted(self):
        raw = {}
        with patch.object(sites, "_read_config_dict", side_effect=lambda: copy.deepcopy(raw)), patch.object(
            sites, "_save"
        ) as save, patch.object(sites, "_custom_sites", return_value=[]):
            result = await sites.save_custom_site(
                sites.CustomSitePayload(
                    type="checkiner",
                    template="templ_a",
                    bot="AuditBot",
                    in_site_list=False,
                ),
                True,
            )
        self.assertTrue(result["success"])
        self.assertEqual(save.call_args.args[0]["checkiner"]["templ_a<AuditBot>"], {})


class AccountMergeTests(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_edit_keeps_independent_config_and_empty_site_scope(self):
        account = TelegramAccount(
            phone="+12345678901",
            checkiner_config={"time_range": "21:00", "retries": 9},
            registrar_config={"concurrency": 2},
            site={"checkiner": []},
        )
        updated = telegram._account_from_payload(
            telegram.TelegramAccountPayload(
                phone="+12345678901",
                monitor=True,
            ),
            account,
        )
        self.assertEqual(updated.checkiner_config.time_range, "21:00")
        self.assertEqual(updated.checkiner_config.retries, 9)
        self.assertEqual(updated.registrar_config.concurrency, 2)
        self.assertEqual(updated.site.checkiner, [])

    async def test_emby_edit_keeps_device_configuration_and_scalar_duration(self):
        account = EmbyAccount(
            id="audit",
            url="https://example.invalid",
            username="audit",
            password="audit-secret",
            client="AuditClient",
            device="AuditDevice",
            time=1200,
        )
        raw = {"emby": {"account": [account.model_dump(mode="json", exclude_none=True)]}}
        with patch.object(emby, "_load_emby_accounts", return_value=(None, raw, [account])), patch.object(
            emby, "_write_config_dict"
        ) as write, patch.object(emby, "_serialize_account", return_value={}):
            result = await emby.update_emby_account(
                "audit",
                emby.EmbyAccountPayload(
                    url="https://example.invalid",
                    username="audit",
                    name="Updated",
                    password="",
                ),
                True,
            )
        self.assertTrue(result["success"])
        stored = write.call_args.args[0]["emby"]["account"][0]
        self.assertEqual(stored["client"], "AuditClient")
        self.assertEqual(stored["device"], "AuditDevice")
        self.assertEqual(stored["password"], "audit-secret")
        self.assertEqual(stored["time"], 1200)

    async def test_subsonic_edit_keeps_client_configuration_and_scalar_duration(self):
        account = SubsonicAccount(
            id="audit",
            url="https://example.invalid",
            username="audit",
            password="audit-secret",
            client="AuditClient",
            client_version="1.2",
            time=1200,
        )
        raw = {"subsonic": {"account": [account.model_dump(mode="json", exclude_none=True)]}}
        with patch.object(
            subsonic, "_load_subsonic_accounts", return_value=(None, raw, [account])
        ), patch.object(subsonic, "_write_config_dict") as write, patch.object(
            subsonic, "_serialize_account", return_value={}
        ):
            result = await subsonic.update_subsonic_account(
                "audit",
                subsonic.SubsonicAccountPayload(
                    url="https://example.invalid",
                    username="audit",
                    name="Updated",
                    password="",
                ),
                True,
            )
        self.assertTrue(result["success"])
        stored = write.call_args.args[0]["subsonic"]["account"][0]
        self.assertEqual(stored["client"], "AuditClient")
        self.assertEqual(stored["client_version"], "1.2")
        self.assertEqual(stored["password"], "audit-secret")
        self.assertEqual(stored["time"], 1200)


class ExecutionContractTests(unittest.TestCase):
    def setUp(self):
        # Preceding CLI tests call asyncio.run(), which leaves no current loop, and asyncio.Event()
        # binds to it when constructed on Python 3.8.
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def test_each_registration_time_has_an_independent_fixed_scheduler(self):
        manager = registrar_main.RegisterManager.__new__(registrar_main.RegisterManager)
        account = SimpleNamespace(phone="+12345678901")
        with patch.object(
            registrar_main, "Scheduler", side_effect=lambda **values: SimpleNamespace(**values)
        ):
            schedules = manager._schedule_site_timed(
                account,
                "templ_a<AuditBot>",
                {
                    "times": ["09:00", "21:00", "09:00"],
                },
            )
        self.assertEqual(len(schedules), 2)
        self.assertEqual({scheduler.start_time for _, scheduler in schedules}, {"09:00", "21:00"})
        self.assertTrue(all(scheduler.start_time == scheduler.end_time for _, scheduler in schedules))
        self.assertEqual(len({key for key, _ in schedules}), 2)

    def test_registration_template_keeps_factory_identity(self):
        template = _templ_a.use(bot_username="AuditBot", templ_name="templ_a<AuditBot>")
        client = SimpleNamespace(me=SimpleNamespace(full_name="Audit"))
        context = SimpleNamespace(bind_logger=lambda logger: logger)
        register = template(client, context=context, config={})
        self.assertEqual(register.bot_username, "AuditBot")
        self.assertEqual(register.templ_name, "templ_a<AuditBot>")

    def test_ocr_presets_have_numeric_runtime_values(self):
        option = next(
            option
            for option in sites._template_options("checkiner", "b")
            if option["key"] == "bot_captcha_char_range"
        )
        self.assertEqual(option["choice_values"]["NUMBER"], 0)
        self.assertEqual(option["choice_values"]["NUMBER_LLETTER"], 4)
        self.assertEqual(
            sites._validate_options("checkiner", "b", {"bot_captcha_char_range": 0}),
            {"bot_captcha_char_range": 0},
        )


if __name__ == "__main__":
    unittest.main()
