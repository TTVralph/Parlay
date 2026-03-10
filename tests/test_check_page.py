from fastapi.testclient import TestClient

from app.main import app


def test_check_page_has_loading_state_and_friendly_layout():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'Did This Parlay Cash?' in html
    assert 'Check Slip' in html
    assert 'Checking your slip...' in html
    assert 'btn.disabled=true' in html
    assert 'Paste at least one leg first, or upload a screenshot.' in html
    assert 'Paste at least one leg first.' in html
    assert '<th>Leg</th>' in html
    assert '<th>Result</th>' in html
    assert '<th>Matched event</th>' in html
    assert "id='debugOut'" in html
    assert 'OCR extracted text:' in html
    assert 'Parsed legs before grading:' in html
    assert 'No valid betting legs detected.' in html


def test_check_slip_returns_graded_legs_with_event_and_overall():
    client = TestClient(app)
    resp = client.post('/check-slip', json={'text': 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    assert body['parlay_result'] in {'lost', 'needs_review', 'still_live', 'cashed'}
    assert len(body['legs']) == 3
    assert all('matched_event' in leg for leg in body['legs'])





def test_check_page_has_copy_summary_controls_and_format():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'Copy Summary' in html
    assert 'Copy Public Link' in html
    assert 'Open Public Result' in html
    assert 'Download Share Card' in html
    assert 'buildSummary' in html
    assert 'Checked on ParlayBot' in html
    assert 'Parlay:' in html
    assert "resultEmoji={win:'✅',loss:'❌'" in html


def test_check_page_supports_screenshot_upload_flow():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "id='slipImage'" in html
    assert "accept='image/*'" in html
    assert "fetch('/ingest/screenshot/parse'" in html
    assert 'Review/edit the text, then click Check Slip.' in html


def test_check_page_shows_optional_stake_input():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "id='stakeAmount'" in html
    assert 'Stake amount (optional)' in html


def test_check_page_only_renders_manual_override_controls_when_candidates_exist():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'if(candidateGames.length>0)' in html
    assert 'wasManuallySelected:Boolean(selectedGameByLegId[legId])' in html
    assert 'Manual selection applied' in html


def test_check_page_shows_bet_date_input():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'Bet Date' in html
    assert "id='slipDate'" in html
    assert 'Optional, but strongly recommended' in html


def test_check_page_form_submit_prevents_navigation_and_submits_in_place():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "form.addEventListener('submit',async(event)=>{" in html
    assert 'event.preventDefault();' in html
    assert "await submitCheck();" in html
    assert "fetch('/check-slip'" in html


def test_check_page_reset_selection_button_is_clickable() -> None:
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "resetBtn.disabled=false" in html
    assert "resetBtn.addEventListener('click'" in html
    assert 'if(nextState.wasManuallySelected)' in html
    assert 'originalCandidateEvents' in html
    assert 'originalReviewReason' in html


def test_check_page_share_actions_have_explicit_success_and_failure_feedback():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "id='actionStatus'" in html
    assert 'Summary copied.' in html
    assert 'Public link copied.' in html
    assert 'Share card downloaded.' in html
    assert 'Copy blocked. Summary selected for manual copy.' in html
    assert 'Unable to copy automatically. Public URL:' in html
    assert 'Could not generate share card image. Please try again.' in html


def test_check_page_share_card_limits_long_slips_and_adds_footer():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'const maxLegsOnCard=8;' in html
    assert 'const hiddenCount=Math.max(0,allLegs.length-shownLegs.length);' in html
    assert "drawWrappedLine(`+${hiddenCount} more legs`" in html


def test_public_parlay_page_layout_supports_long_wrapped_leg_content():
    client = TestClient(app)
    resp = client.post('/check-slip', json={'text': '\n'.join(['Denver ML'] * 9)})
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    page = client.get(body['public_url'])
    assert page.status_code == 200
    assert 'overflow-wrap:anywhere' in page.text
    assert 'table-layout:fixed' in page.text
    assert 'Leg Results (9)' in page.text



def test_check_page_screenshot_can_be_removed_before_text_only_submit():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "id='removeScreenshotBtn'" in html
    assert "clearScreenshotSelection({keepMessage:true});" in html
    assert "if(shouldParseScreenshot){" in html
    assert "}else{" in html


def test_check_page_screenshot_can_be_removed_and_reuploaded():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "slipImage.addEventListener('change'" in html
    assert "removeScreenshotBtn.style.display=file?'inline-block':'none';" in html
    assert "removeScreenshotBtn.addEventListener('click'" in html
    assert "slipImage.value='';" in html


def test_check_page_keeps_ocr_text_in_textarea_when_screenshot_removed():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "if(parsedLegs.length){slip.value=parsedLegs.join('\\n');}" in html
    assert "else if(body.cleaned_text){slip.value=body.cleaned_text;}" in html
    assert "clearScreenshotSelection({keepMessage:true});" in html
    assert "slip.focus();" in html


def test_check_page_screenshot_second_submit_grades_text_instead_of_reparsing():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "let screenshotNeedsParse=false;" in html
    assert "screenshotNeedsParse=Boolean(file)&&nextSignature!==parsedScreenshotSignature;" in html
    assert "const shouldParseScreenshot=Boolean(file)&&screenshotNeedsParse;" in html
    assert "if(shouldParseScreenshot){" in html
    assert "}else{" in html
    assert "screenshotNeedsParse=false;" in html
    assert "parsedScreenshotSignature=screenshotSignature;" in html


def test_check_page_screenshot_remove_then_submit_uses_text_grading_path():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "clearScreenshotSelection({keepMessage:true});" in html
    assert "screenshotNeedsParse=false;" in html
    assert "parsedScreenshotSignature=null;" in html
    assert "res=await fetch('/check-slip'" in html


def test_check_page_uploading_different_screenshot_triggers_new_parse():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "function getScreenshotSignature(file){" in html
    assert "const nextSignature=getScreenshotSignature(file);" in html
    assert "screenshotNeedsParse=Boolean(file)&&nextSignature!==parsedScreenshotSignature;" in html
