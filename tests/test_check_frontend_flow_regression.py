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
    assert 'setScreenshotUploadBusy(true);' in script
    assert 'setScreenshotUploadBusy(false);' in script
    assert 'resetScreenshotInputValue();' in script
    assert "Screenshot parsed. Review/edit the text, then click ${activeSlipMode===modeAnalyze?'Analyze Slip':'Check Slip'}." in script
    assert "Screenshot parsed with limited confidence. Existing text was preserved for safety." in script
    assert "return;" in script  # first submit exits after parsing
    assert "const existingSlipText=slip.value.trim();" in script
    assert "}else if(body.cleaned_text&&!existingSlipText){" in script
    assert "res=await fetch('/check-slip'" in script


def test_screenshot_remove_then_text_check_flow_is_supported() -> None:
    script = _check_page_script()
    assert "removeScreenshotBtn.addEventListener('click'" in script
    assert "clearScreenshotSelection({keepMessage:true});" in script
    assert "resetScreenshotInputValue();" in script
    assert "screenshotNeedsParse=false;" in script
    assert "parsedScreenshotSignature=null;" in script
    assert "else{" in script and "res=await fetch('/check-slip'" in script


def test_upload_input_is_clickable_after_parse_success_and_low_confidence_paths() -> None:
    script = _check_page_script()
    assert "function setScreenshotUploadBusy(isBusy){" in script
    assert 'slipImage.disabled=screenshotParseInFlight;' in script
    assert 'removeScreenshotBtn.disabled=screenshotParseInFlight;' in script
    assert "uploadWrap.classList.toggle('is-busy',screenshotParseInFlight);" in script
    assert "msg.textContent=parsedLegs.length" in script
    assert "?`Screenshot parsed. Review/edit the text, then click ${activeSlipMode===modeAnalyze?'Analyze Slip':'Check Slip'}.`" in script
    assert " :'Screenshot parsed with limited confidence. Existing text was preserved for safety.';" in script


def test_analyze_mode_uses_screenshot_parse_before_analyzer_call() -> None:
    script = _check_page_script()
    assert "const shouldParseScreenshot=Boolean(file)&&screenshotNeedsParse;" in script
    assert "if(shouldParseScreenshot){" in script
    assert "}else if(activeSlipMode===modeAnalyze){" in script
    assert "res=await fetch('/analyze-slip'" in script
    assert "res=await fetch('/check-slip'" in script
    assert "resetRenderedSlipResult();" in script
    assert 'Analyze Slip complete. Advisory only — not a guarantee.' in script


def test_upload_input_state_resets_after_screenshot_removal() -> None:
    script = _check_page_script()
    assert 'setScreenshotUploadBusy(false);' in script
    assert "removeScreenshotBtn.style.display='none';" in script
    assert "removeScreenshotBtn.addEventListener('click',()=>{" in script
    assert "msg.textContent='Screenshot removed. You can keep editing the text or upload another screenshot.';" in script


def test_uploading_new_screenshot_after_previous_parse_reuses_input_without_refresh() -> None:
    script = _check_page_script()
    assert "function resetScreenshotInputValue(){" in script
    assert "slipImage.value='';" in script
    assert "slipImage.addEventListener('change',()=>{" in script
    assert 'if(screenshotParseInFlight){return;}' in script
    assert "screenshotNeedsParse=Boolean(file)&&nextSignature!==parsedScreenshotSignature;" in script


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
    assert "Manual selection used for grading" in script
    assert "selection_source" in script
    assert "original_typed_player_name" in script
    assert "Player selected, but not used in final grading" in script
    assert "Game selected, but not used in final grading" in script
    assert "const canPickPlayer=(item.result==='review'||showPlayerPicker)&&candidatePlayers.length>0" in script
    assert "changePlayerBtn.textContent='Change player'" in script


def test_manual_event_selection_ui_is_clickable_and_reopenable() -> None:
    script = _check_page_script()
    assert "const canPickGame=(item.result==='review'||showGamePicker)&&candidateGames.length>0" in script
    assert "pickerLabel.textContent='Multiple games found. Choose the correct one.';" in script
    assert "changeGameBtn.textContent='Change game';" in script
    assert "resetGameBtn.textContent='Reset selected game';" in script
    assert "payload.selected_event_by_leg_id=selectedGameByLegId" in script


def test_manual_player_and_event_candidate_buttons_use_clickable_button_style() -> None:
    script = _check_page_script()
    assert "pickBtn.className='secondary candidate-btn';" in script
    assert "selectedPlayerByLegId={...selectedPlayerByLegId,[legId]:candidate.player_id};" in script
    assert "selectedGameByLegId={...selectedGameByLegId,[legId]:game.event_id};" in script


def test_game_time_localization_helper_uses_browser_timezone_and_utc_field() -> None:
    script = _check_page_script()
    assert "function formatLocalGameTime(utcTimestamp,timeZoneOverride){" in script
    assert "Intl.DateTimeFormat().resolvedOptions().timeZone" in script
    assert "event_start_time_utc" in script


def test_format_local_game_time_timezone_examples_via_node() -> None:
    import json
    import subprocess

    js = """
function formatLocalGameTime(utcTimestamp, timeZoneOverride) {
  const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
  if (!utcTimestamp) return null
  const date = new Date(utcTimestamp)
  if (Number.isNaN(date.getTime())) return null
  const parts = new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
    timeZone: timeZoneOverride || browserTimeZone,
  }).formatToParts(date)
  const lookup = (type) => parts.find((part) => part.type === type)?.value || ''
  const weekday = lookup('weekday')
  const month = lookup('month')
  const day = lookup('day')
  const hour = lookup('hour')
  const minute = lookup('minute')
  const dayPeriod = lookup('dayPeriod')
  const timeZoneName = lookup('timeZoneName')
  const time = [hour, minute].filter(Boolean).join(':')
  const clock = [time, dayPeriod].filter(Boolean).join(' ')
  const dateLabel = [weekday, [month, day].filter(Boolean).join(' ')].filter(Boolean).join(', ')
  return [dateLabel, clock, timeZoneName].filter(Boolean).join(' • ')
}
const ts = '2026-03-11T01:30:00Z'
const out = {
  ny: formatLocalGameTime(ts, 'America/New_York'),
  den: formatLocalGameTime(ts, 'America/Denver'),
  la: formatLocalGameTime(ts, 'America/Los_Angeles'),
}
console.log(JSON.stringify(out))
"""
    raw = subprocess.check_output(['node', '-e', js], text=True)
    data = json.loads(raw.strip())

    assert data['ny'].startswith('Tue, Mar 10 • 9:30 PM ')
    assert data['den'].startswith('Tue, Mar 10 • 7:30 PM ')
    assert data['la'].startswith('Tue, Mar 10 • 6:30 PM ')
