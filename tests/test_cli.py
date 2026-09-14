from paper_record.cli import main


def test_schema_command(capsys) -> None:
    assert main(["schema", "proposal"]) == 0
    assert '"operations"' in capsys.readouterr().out


def test_future_command_has_explicit_exit(capsys, tmp_path) -> None:
    assert main(["read", str(tmp_path)]) == 2
    assert "not implemented yet" in capsys.readouterr().err
