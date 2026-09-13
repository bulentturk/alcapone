import base64
import copy
import importlib
import json
from pathlib import Path
import sys

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parents[1] / 'src'))
p = importlib.import_module('pilot01')
g = importlib.import_module('generate_short')


def alignment_for_episode(scale=1):
    text = p.script_text(p.episode())
    return {'characters': list(text),
            'character_start_times_seconds': [i * .06 * scale for i in range(len(text))],
            'character_end_times_seconds': [(i + 1) * .06 * scale for i in range(len(text))]}


def test_new_speech_drives_scene_boundaries():
    import reva_scene as scene
    ep = p.episode()
    first = p.timing_from_alignment(alignment_for_episode(), ep)
    second = p.timing_from_alignment(alignment_for_episode(1.2), ep)
    scene.configure_timeline(first, 50)
    old_start = scene.SCENES[4][0]
    scene.configure_timeline(second, 60)
    assert scene.SCENES[4][0] == pytest.approx(old_start * 1.2)
    assert scene.SCENES[4][0] != ep['reference']['timing'][10]['start']
    assert scene.EVENTS['battery_no'] == second[9]['start']


@pytest.mark.parametrize('bad', ['text', 'missing', 'nan', 'reverse'])
def test_bad_provider_timing_stops_render(bad):
    a = alignment_for_episode()
    if bad == 'text': a['characters'][0] = 'X'
    if bad == 'missing': a['character_end_times_seconds'].pop()
    if bad == 'nan': a['character_start_times_seconds'][2] = float('nan')
    if bad == 'reverse': a['character_start_times_seconds'][3] = 0
    with pytest.raises(p.PilotError): p.timing_from_alignment(a, p.episode())


def test_wrong_reference_audio_never_uses_old_timing(tmp_path, monkeypatch):
    audio = tmp_path / 'wrong.mp3'
    audio.write_bytes(b'different recording')
    monkeypatch.setattr(p, 'verify_environment', lambda: None)
    with pytest.raises(p.PilotError, match='checksum'):
        p.prepare_speech(tmp_path / 'out', reference_audio=audio)


def test_reference_timing_cannot_overlap():
    ep = p.episode()
    cues = copy.deepcopy(ep['reference']['timing'])
    cues[1]['start'] = .1
    with pytest.raises(p.PilotError): p.validate_timing(cues, 50.81, ep)


def test_timeout_does_not_leak_key_or_repeat_call(tmp_path, monkeypatch, capsys):
    secret = 'synthetic-secret-value-for-test'
    monkeypatch.setenv('ELEVENLABS_API_KEY', secret)
    monkeypatch.setattr(p, 'verify_environment', lambda: None)
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise requests.Timeout(secret)
    monkeypatch.setattr(g.requests, 'post', fail)
    with pytest.raises(p.PilotError) as exc:
        p.prepare_speech(tmp_path)
    assert secret not in str(exc.value)
    with pytest.raises(p.PilotError, match='already attempted'):
        p.prepare_speech(tmp_path)
    assert len(calls) == 1
    assert secret not in capsys.readouterr().out
    assert secret not in (tmp_path / 'speech-attempted.json').read_text()


def test_reva_request_uses_approved_settings_and_no_redirect(tmp_path, monkeypatch):
    seen = {}
    class Response:
        status_code = 200
        def json(self):
            return {'audio_base64': base64.b64encode(b'a' * 200).decode(), 'alignment': alignment_for_episode()}
    def post(url, **kwargs):
        seen.update(kwargs)
        seen['url'] = url
        return Response()
    monkeypatch.setattr(g.requests, 'post', post)
    v = p.episode()['voice']
    g.generate_speech('synthetic-key', v['voice_id'], p.script_text(p.episode()), tmp_path / 'audio.mp3',
                      model_id=v['model_id'], voice_settings=v['voice_settings'])
    assert seen['json']['voice_settings'] == {'speed': 1, 'stability': .5, 'similarity_boost': .75, 'style': 0, 'use_speaker_boost': True}
    assert seen['json']['model_id'] == 'eleven_multilingual_v2'
    assert seen['allow_redirects'] is False
    assert seen['headers']['xi-api-key'] == 'synthetic-key'


def test_provider_error_body_is_never_read():
    class Response:
        status_code = 401
        @property
        def text(self): raise AssertionError('Do not read provider error text')
    with pytest.raises(RuntimeError, match='HTTP 401'):
        g.check_response(Response(), 'speech generation')
