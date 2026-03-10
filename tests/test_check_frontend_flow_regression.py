import re

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _check_page_script() -> str:
    response = client.get('/check')
    assert response.status_code == 200
    match = re.search(r'<script>([\s\S]*)</script>', response.text)
    assert match is not None
    return match.group(1)


def test_submit_handler_stays_async_and_prevents_refresh() -> None:
    script = _check_page_script()
    assert "form.addEventListener('submit',async(event)=>{" in script
    assert 'event.preventDefault();' in script
    assert 'await submitCheck();' in script
    assert "form id='checkForm'" in client.get('/check').text
    assert "action=" not in client.get('/check').text


def test_screenshot_parse_then_check_flow_stays_in_place() -> None:
    script = _check_page_script()
    assert "res=await fetch('/ingest/screenshot/parse'" in script
    assert "msg.textContent='Screenshot parsed. Review/edit the text, then click Check Slip.';" in script
    assert "return;" in script  # first submit exits after parsing
    assert "res=await fetch('/check-slip'" in script


def test_screenshot_remove_then_text_check_flow_is_supported() -> None:
    script = _check_page_script()
    assert "removeScreenshotBtn.addEventListener('click'" in script
    assert "clearScreenshotSelection({keepMessage:true});" in script
    assert "screenshotNeedsParse=false;" in script
    assert "parsedScreenshotSignature=null;" in script
    assert "else{" in script and "res=await fetch('/check-slip'" in script


def test_share_actions_and_summary_rendering_exist_after_grading() -> None:
    script = _check_page_script()
    assert "copyBtn.disabled=false;" in script
    assert "copyLinkBtn.disabled=!latestPublicUrl;" in script
    assert "openLinkBtn.disabled=!latestPublicUrl;" in script
    assert "downloadCardBtn.disabled=false;" in script
    assert "summaryOut.value=buildSummary(data);" in script
    assert "if(data.estimated_payout!==undefined&&data.estimated_profit!==undefined){" in script
    assert "}else if(data.payout_message){" in script


def test_manual_player_selection_ui_signals_are_rendered() -> None:
    script = _check_page_script()
    assert "Using selected player:" in script
    assert "selection_source" in script
    assert "original_typed_player_name" in script
    assert "Player selection succeeded, but this leg still needs review" in script
    assert "const canPickPlayer=!playerSelectionApplied" in script
