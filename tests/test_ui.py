"""Browser-free smoke coverage of authentication, navigation and demo analysis."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from hkrbc_agent.security import DEMO_PASSWORDS


APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HKRBC_DB_PATH", str(tmp_path / "ui.sqlite"))
    monkeypatch.setenv("HKRBC_EXTERNAL_ENABLED", "false")
    monkeypatch.delenv("HKRBC_LOCAL_MODEL", raising=False)
    for username in DEMO_PASSWORDS:
        monkeypatch.delenv(f"HKRBC_{username.upper()}_PASSWORD", raising=False)
    return AppTest.from_file(str(APP), default_timeout=15).run()


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception
    return app


def sign_in(app, username="analyst"):
    app.text_input(key="login_username").input(username)
    app.text_input(key="login_password").input(DEMO_PASSWORDS[username])
    return click(app, "Sign in")


def test_login_rejects_invalid_credentials_and_hides_workspace(app):
    assert not app.exception
    assert not any(radio.label == "Workspace" for radio in app.radio)
    app.text_input(key="login_username").input("analyst")
    app.text_input(key="login_password").input("wrong-password")
    click(app, "Sign in")
    assert any("Invalid demonstration credentials" in error.value for error in app.error)
    assert "session_token" not in app.session_state.filtered_state


def test_demo_analysis_navigation_report_and_logout_isolation(app):
    sign_in(app)
    assert app.radio(key="model_mode").options == ["Local evidence"]
    app.text_area(key="regulatory_question").input("When did HK RBC commence?")
    click(app, "Search evidence")
    assert "query_result" in app.session_state.filtered_state
    app.radio(key="page").set_value("Capital Analysis").run()
    assert not app.checkbox(key="synthetic_declaration").value
    assert next(button for button in app.button if button.label == "Run capital analysis").disabled
    click(app, "Load synthetic demo portfolios")
    assert app.checkbox(key="synthetic_declaration").value
    click(app, "Run capital analysis")
    result = app.session_state["analysis_result"]
    assert result["validation"]["passed"]
    assert abs(result["unexplained_residual"]) < 0.01
    assert len(app.metric) == 4
    click(app, "Create review report")
    assert app.session_state["saved_report"]["report_id"]
    assert "Illustrative actuarial movement report" in app.session_state["report_markdown"]
    click(app, "Generate scenarios")
    assert app.session_state["scenario_result"]["validation"]["passed"]
    app.radio(key="page").set_value("Validation Dashboard").run()
    assert not app.exception
    assert next(metric for metric in app.metric if metric.label == "Failed / review required").value == "0"
    app.radio(key="page").set_value("Governance & Audit").run()
    assert not app.exception
    assert any("administrators" in info.value for info in app.info)
    click(app, "Sign out")
    assert "analysis_result" not in app.session_state.filtered_state
    assert "query_result" not in app.session_state.filtered_state
    assert "opening_bytes" not in app.session_state.filtered_state
    sign_in(app, "reviewer")
    assert "saved_report" not in app.session_state.filtered_state
    assert "scenario_result" not in app.session_state.filtered_state


def test_unconfirming_synthetic_inputs_clears_previous_results(app):
    sign_in(app)
    app.radio(key="page").set_value("Capital Analysis").run()
    click(app, "Load synthetic demo portfolios")
    click(app, "Run capital analysis")
    assert "analysis_result" in app.session_state.filtered_state
    app.checkbox(key="synthetic_declaration").uncheck().run()
    assert not app.exception
    assert "analysis_result" not in app.session_state.filtered_state
    assert next(button for button in app.button if button.label == "Run capital analysis").disabled


def test_material_unexpected_movement_blocks_report_completion(app):
    sign_in(app)
    app.radio(key="page").set_value("Capital Analysis").run()
    click(app, "Load synthetic demo portfolios")
    app.session_state["closing_bytes"] = app.session_state["closing_bytes"].replace(
        b"SYN-EQUITY-01,equity,HKD,2026-09-30,50000000,",
        b"SYN-EQUITY-01,equity,HKD,2026-09-30,500000000,",
    )
    click(app, "Run capital analysis")
    assert app.session_state["analysis_result"]["status"] == "blocked"
    assert next(button for button in app.button if button.label == "Create review report").disabled
    app.radio(key="page").set_value("Validation Dashboard").run()
    assert not app.exception
    assert int(next(metric for metric in app.metric if metric.label == "Failed / review required").value) > 0
    assert "saved_report" not in app.session_state.filtered_state


def test_malformed_input_remains_visible_on_validation_dashboard(app):
    sign_in(app)
    app.radio(key="page").set_value("Capital Analysis").run()
    click(app, "Load synthetic demo portfolios")
    app.session_state["opening_bytes"] = (APP.parent / "data/portfolios/malformed.csv").read_bytes()
    click(app, "Run capital analysis")
    assert "analysis_result" not in app.session_state.filtered_state
    assert app.session_state["input_error"]["Result"] == "FAIL"
    app.radio(key="page").set_value("Validation Dashboard").run()
    assert not app.exception
    assert next(metric for metric in app.metric if metric.label == "Failed / review required").value == "1"


def test_reviewer_external_mode_requires_explicit_request_approval(app, tmp_path, monkeypatch):
    monkeypatch.setenv("HKRBC_EXTERNAL_ENABLED", "true")
    monkeypatch.setenv("HKRBC_DB_PATH", str(tmp_path / "external-ui.sqlite"))
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    sign_in(app, "reviewer")
    app.radio(key="model_mode").set_value("Approved external commentary").run()
    approval = next(checkbox for checkbox in app.checkbox if checkbox.label.startswith("I approve sending"))
    assert not approval.value
    app.text_area(key="regulatory_question").input("When did HK RBC commence?")
    click(app, "Search evidence")
    assert any("explicit per-request approval" in error.value for error in app.error)
    assert "query_result" not in app.session_state.filtered_state
    assert not next(checkbox for checkbox in app.checkbox if checkbox.label.startswith("I approve sending")).value
