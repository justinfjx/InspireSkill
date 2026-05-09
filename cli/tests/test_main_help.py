from click.testing import CliRunner

from inspire.cli.formatters.human_formatter import format_job_status
from inspire.cli.main import main as cli_main


def test_root_help_keeps_json_as_script_interface() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_main, ["--help"])

    assert result.exit_code == 0
    assert "Default human output is the interactive observation surface." in result.output
    assert "Use JSON only for scripts or structured automation." in result.output


def test_job_status_formatter_shows_platform_priority_fields() -> None:
    output = format_job_status(
        {
            "job_id": "job-123",
            "name": "demo",
            "status": "RUNNING",
            "running_time_ms": "1000",
            "priority": 10,
            "priority_name": "10",
            "priority_level": "HIGH",
        }
    )

    assert "Requested Priority: 10" in output
    assert "Priority Name: 10" in output
    assert "Priority Level: HIGH" in output
