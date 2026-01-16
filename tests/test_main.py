import main


def test_main_starts_executor(monkeypatch):
    calls = []

    def fake_run_loop(self):
        calls.append("called")

    monkeypatch.setattr(main.ScheduleExecutor, "run_loop", fake_run_loop)

    main.main()

    assert calls == ["called"]
