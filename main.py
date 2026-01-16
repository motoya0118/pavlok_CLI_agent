import os
import shlex
import subprocess
import time
from datetime import timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config

from db.engine import SessionLocal
from db.models import Schedule, now_jst


class ScheduleExecutor:
    def __init__(
        self,
        prompt_dir: Path | None = None,
        runner=None,
        now_func=now_jst,
        do_migrations: bool = False,
    ) -> None:
        self.prompt_dir = prompt_dir or (Path(__file__).resolve().parent / "prompts")
        self.runner = runner or self.run_codex
        self.now_func = now_func
        self.do_migrations = do_migrations

    @staticmethod
    def _get_int_env(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise SystemExit(f"{name} must be an integer.") from exc

    def run_migrations(self) -> None:
        config_path = Path(__file__).resolve().parent / "db" / "alembic.ini"
        config = Config(str(config_path))
        command.upgrade(config, "head")

    @staticmethod
    def render_prompt(template: str, context: dict[str, str | None]) -> str:
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(
                f"{{{{{key}}}}}", "" if value is None else str(value)
            )
        return rendered

    def build_prompt(self, schedule: Schedule) -> str:
        prompt_path = self.prompt_dir / f"{schedule.prompt_name}.md"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")
        template = prompt_path.read_text()
        context = {
            "input_value": schedule.input_value,
            "schedule_id": schedule.id,
            "state": schedule.state,
            "last_result": schedule.last_result,
            "last_error": schedule.last_error,
        }
        return self.render_prompt(template, context)

    def run_codex(self, prompt: str) -> subprocess.CompletedProcess:
        cmd = ["codex", "exec", prompt]
        self.log(f"codex exec: {self.format_command(cmd)}")
        return subprocess.run(cmd, text=True, check=False)

    @staticmethod
    def format_command(cmd: list[str], max_prompt: int = 200) -> str:
        if len(cmd) >= 3 and cmd[0] == "codex" and cmd[1] == "exec":
            prompt = cmd[2].replace("\n", " ").strip()
            if len(prompt) > max_prompt:
                prompt = f"{prompt[:max_prompt]}...({len(prompt)} chars)"
            safe_cmd = [cmd[0], cmd[1], prompt]
            return " ".join(shlex.quote(part) for part in safe_cmd)
        return " ".join(shlex.quote(part) for part in cmd)

    @staticmethod
    def log(message: str) -> None:
        print(f"[schedule_executor] {message}", flush=True)

    def ensure_initial_morning(self, session, now) -> None:
        exists = (
            session.query(Schedule)
            .filter_by(prompt_name="morning", state="pending")
            .first()
        )
        if exists is None:
            schedule = Schedule(
                prompt_name="morning",
                input_value="",
                scheduled_date=now,
                state="pending",
            )
            session.add(schedule)
            session.commit()

    @staticmethod
    def fetch_due_schedules(session, now) -> list[Schedule]:
        return (
            session.query(Schedule)
            .filter(Schedule.scheduled_date <= now)
            .filter(Schedule.state.in_(["pending", "failed"]))
            .order_by(Schedule.scheduled_date.asc())
            .all()
        )

    def execute_schedule(self, session, schedule: Schedule) -> None:
        retry_delay_min = self._get_int_env("RETRY_DELAY_MIN", default=5)
        schedule.state = "running"
        session.commit()
        self.log(
            f"schedule_id={schedule.id} state=running prompt={schedule.prompt_name}"
        )

        try:
            prompt = self.build_prompt(schedule)
            result = self.runner(prompt)
            schedule.last_result = result.stdout
            if result.returncode == 0:
                schedule.state = "done"
                schedule.last_error = None
                self.log(f"schedule_id={schedule.id} state=done")
            else:
                schedule.state = "failed"
                schedule.last_error = result.stderr or f"returncode={result.returncode}"
                schedule.scheduled_date = self.now_func() + timedelta(
                    minutes=retry_delay_min
                )
                self.log(
                    "schedule_id="
                    f"{schedule.id} state=failed retry_at={schedule.scheduled_date}"
                )
        except Exception as exc:
            schedule.state = "failed"
            schedule.last_error = str(exc)
            schedule.scheduled_date = self.now_func() + timedelta(
                minutes=retry_delay_min
            )
            self.log(
                "schedule_id="
                f"{schedule.id} state=failed error={exc} retry_at={schedule.scheduled_date}"
            )
        finally:
            session.commit()

    def run_once(self, do_migrations: bool | None = None) -> int:
        if do_migrations is None:
            do_migrations = self.do_migrations
        if do_migrations:
            self.run_migrations()

        session = SessionLocal()
        executed = 0
        try:
            now = self.now_func()
            self.ensure_initial_morning(session, now)
            due = self.fetch_due_schedules(session, now)
            if not due:
                self.log("no schedules due")
            for schedule in due:
                self.execute_schedule(session, schedule)
                executed += 1
            return executed
        finally:
            session.close()

    def run_loop(self) -> None:
        self.run_migrations()
        while True:
            self.run_once(do_migrations=False)
            time.sleep(60)


def main() -> None:
    ScheduleExecutor().run_loop()


if __name__ == "__main__":
    main()
