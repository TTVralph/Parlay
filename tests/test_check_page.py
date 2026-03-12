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
    assert "const canPickGame=(item.result==='review'||showGamePicker)&&candidateGames.length>0;" in html
    assert 'wasManuallySelected:Boolean(selectedGameByLegId[legId])' in html
    assert 'Possible games' in html
    assert 'Manual selection used for grading' in html
    assert 'Player selected, but not used in final grading' in html
    assert 'Game selected, but not used in final grading' in html
    assert 'selected_event_by_leg_id=selectedGameByLegId' in html


def test_check_page_shows_bet_date_input():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'Bet Date' in html
    assert "id='slipDate'" in html
    assert 'optional but strongly recommended' in html


def test_check_page_form_submit_prevents_navigation_and_submits_in_place():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "form.addEventListener('submit',async(event)=>{" in html
    assert 'event.preventDefault();' in html
    assert "await submitCheck();" in html
    assert "fetch('/check-slip'" in html


def test_check_page_reset_selection_is_available_via_auto_match_option() -> None:
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "resetGameBtn.textContent='Auto-match (clear manual selection)'" in html
    assert "resetGameBtn.addEventListener('click'" in html
    assert 'delete nextSelection[legId];' in html


def test_check_page_can_reset_player_and_game_selection_independently() -> None:
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "changePlayerBtn.textContent='Change player'" in html
    assert "resetPlayerBtn.textContent='Reset selected player'" in html
    assert "changeGameBtn.textContent='Change game'" in html
    assert "resetGameBtn.textContent='Reset selected game'" in html
    assert 'const nextSelection={...selectedPlayerByLegId};' in html
    assert 'delete nextSelection[legId];' in html
    assert 'const nextSelection={...selectedGameByLegId};' in html


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


def test_check_page_renders_compact_result_summary_chips():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "id='resultSummary'" in html
    assert "countLegResults(legs)" in html
    assert "<span class='result-chip'>${counts.total} Legs</span>" in html
    assert "<span class='result-chip'>${counts.won} Won</span>" in html
    assert "<span class='result-chip'>${counts.lost} Lost</span>" in html
    assert "<span class='result-chip'>${counts.review} Review</span>" in html


def test_check_page_renders_metadata_summary_row_when_available():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "id='metaSummary'" in html
    assert "Sport: ${sports[0]}" in html
    assert "Bet date: ${betDate}" in html
    assert "Stake: $${Number(payload.stake_amount).toFixed(2)}" in html
    assert "Est. payout: $${Number(payload.estimated_payout).toFixed(2)}" in html
    assert "if(hasStake&&payload.payout_message)" in html


def test_check_page_renders_structured_review_reason_fallback_ui():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert 'function bestReviewReason(item)' in html
    assert 'Needs manual review. We could not confidently resolve this leg.' in html
    assert "const statusBadge=reviewStatusLabel(details);" in html
    assert "suggestion.textContent=didYouMeanText;" in html
    assert 'Player selection succeeded, but another downstream grading validation still requires review.' in html
    assert 'Selected game could not be applied; choose one of the listed games.' in html
    assert '<strong>Original typed leg:</strong>' in html
    assert '<strong>Override used for grading:</strong>' in html
    assert '<strong>Override outcome:</strong>' in html
    assert '<strong>Final settlement:</strong>' in html


def test_check_page_renders_subtle_fuzzy_resolution_message_in_main_table():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "details.player_resolution_status==='fuzzy_resolved'" in html
    assert 'Resolved from likely player name match' in html


def test_check_page_shows_unresolved_typo_explanation_and_structured_details():
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert "const canPickPlayer=(item.result==='review'||showPlayerPicker)&&candidatePlayers.length>0&&String(item.sport||item.leg?.sport||'NBA')==='NBA'&&(!playerSelectionApplied||showPlayerPicker);" in html
    assert "const shouldShowPicker=(item.result==='review'||showPlayerPicker)&&candidatePlayers.length>0&&String(item.sport||item.leg?.sport||'NBA')==='NBA'&&(!playerSelectionApplied||showPlayerPicker);" in html
    assert 'Player resolution method:' in html
    assert 'Player resolution confidence:' in html
    assert 'Player resolution mode:' in html
    assert 'Canonical matched player:' in html
    assert "pickerLabel.textContent='Did you mean?';" in html


def test_check_page_renders_clickable_candidate_buttons_for_player_and_event_pickers() -> None:
    client = TestClient(app)
    page = client.get('/check')
    assert page.status_code == 200
    html = page.text
    assert '.candidate-btn' in html
    assert "pickBtn.type='button';" in html
    assert "pickBtn.className='secondary candidate-btn';" in html
    assert "payload.selected_player_by_leg_id=selectedPlayerByLegId" in html
    assert "payload.selected_event_by_leg_id=selectedGameByLegId" in html
