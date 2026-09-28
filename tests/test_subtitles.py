import copy
import io
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from subtitle_document import (new_document, cue, save_project, load_project, export_text,
    import_subtitles, validate_document, History, timestamp, quality_notes)
from languages import validate_language_model
from translation import request_suggestions, validate_endpoint
import autocensor as core
from subtitle_worker import scratch_directory, caption_segments


class SubtitleTests(unittest.TestCase):
    def document(self):
        doc=new_document(language='ja');doc['cues']=[cue(1,2.5,'こんにちは','Hello.'),cue(3,4.8,'元気ですか？','How are you?')]
        return doc
    def test_project_roundtrip_keeps_both_tracks_style_and_suggestions(self):
        doc=self.document();doc['cues'][0]['suggestion']='Hi there.';doc['context']='Keep the name Mika.'
        with scratch_directory() as folder:
            path=Path(folder)/'project.juice.json';save_project(path,doc)
            self.assertEqual(load_project(path),doc)
            self.assertFalse(list(Path(folder).glob('*.tmp')))
    def test_srt_vtt_ass_unicode_roundtrip(self):
        doc=self.document()
        with scratch_directory() as folder:
            for fmt in ('srt','vtt','ass'):
                path=Path(folder)/('test.'+fmt);path.write_text(export_text(doc,fmt),encoding='utf-8')
                imported=import_subtitles(path)
                self.assertEqual([c['source'] for c in imported['cues']],[c['source'] for c in doc['cues']])
                self.assertEqual([(c['start'],c['end']) for c in imported['cues']],[(1,2.5),(3,4.8)])
    def test_timing_rounding_hours_and_invalid_bounds(self):
        self.assertEqual(timestamp(3599.9996),'01:00:00,000')
        self.assertEqual(timestamp(3599.996,True),'1:00:00.00')
        for a,b in [(2,1),(-1,1),(0,float('nan')),(0,float('inf'))]:
            doc=self.document();doc['cues'][0].update(start=a,end=b)
            with self.assertRaises(ValueError):validate_document(doc)
    def test_missing_translation_cannot_silently_export_source(self):
        doc=self.document();doc['cues'][1]['translation']=''
        with self.assertRaises(ValueError):export_text(doc,'srt','translation')
    def test_undo_redo_keeps_source_and_ids(self):
        doc=self.document();before=copy.deepcopy(doc);history=History();history.record(doc)
        doc['cues'][0]['translation']='Updated';edited=copy.deepcopy(doc)
        doc=history.undo(doc);self.assertEqual(doc,before)
        self.assertEqual(history.redo(doc),edited)
    def test_unicode_matching_keeps_accents_and_nonlatin_text(self):
        for text in ('日本語','café','Привет','العربية','한국어'):
            self.assertTrue(core.normalize_token(text))
        self.assertEqual(core.normalize_token('Ｃａｆｅ́！'),'café')
        self.assertEqual(core.normalize_token('DON’T'),'don\'t')
    def test_cjk_character_alignment_matches_phrase_but_not_across_long_pause(self):
        words=[core.Word(c,c,i*.2,i*.2+.15) for i,c in enumerate('日本語です')]
        events=core.find_events(words,['日本語'],[],dict(pre_padding=0,post_padding=0,merge_gap=0))
        self.assertEqual(len(events),1);self.assertAlmostEqual(events[0].end,.55)
        words[1].start=2;words[1].end=2.2
        self.assertEqual(core.find_events(words,['日本語'],[],{}),[])
    def test_english_substrings_do_not_match(self):
        words=[core.Word('class','class',0,1)]
        self.assertEqual(core.find_events(words,['ass'],[],{}),[])
    def test_language_model_mismatch_is_explicit(self):
        for lang in ('ja','auto'):
            with self.assertRaises(ValueError):validate_language_model(lang,'base.en')
        validate_language_model('ja','large-v3')
        with self.assertRaises(ValueError):validate_language_model('en','base.en','translate')
    def test_style_escapes_ass_commands(self):
        doc=self.document();doc['cues'][0]['source']='{\\pos(1,1)}test\nsecond'
        exported=export_text(doc,'ass');self.assertNotIn('{\\pos',exported);self.assertIn('\\Nsecond',exported)
    def test_long_captions_split_on_measured_words(self):
        words=[dict(start=i*.5,end=i*.5+.4,text=' word') for i in range(20)]
        segments=caption_segments([dict(start=0,end=10,text='long text',words=words)])
        self.assertGreater(len(segments),1)
        self.assertEqual(' '.join(s['text'] for s in segments),' '.join(['word']*20))
        for s in segments:
            self.assertIn(s['start'],[w['start'] for w in words]);self.assertIn(s['end'],[w['end'] for w in words])
    def test_bad_style_and_missing_cue_fields_rejected(self):
        doc=self.document();doc['style']['color']='red;command'
        with self.assertRaises(ValueError):validate_document(doc)
        doc=self.document();del doc['cues'][0]['end']
        with self.assertRaises(ValueError):validate_document(doc)


class FakeOpener:
    def __init__(self, transform=None, online=False):self.requests=[];self.transform=transform;self.online=online
    def open(self, request, timeout):
        self.requests.append(request)
        body=json.loads(request.data);payload=json.loads(body['messages'][1]['content'])
        rows=[dict(id=i,text='Natural translation') for i in payload['requested_ids']]
        if self.transform:rows=self.transform(rows)
        text=json.dumps({'cues':rows})
        response={'choices':[{'message':{'content':text}}]} if self.online else {'message':{'content':text}}
        return io.BytesIO(json.dumps(response).encode())


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.doc=new_document(language='ja');self.doc['cues']=[cue(i,i+.8,'原文','Existing') for i in range(30)]
        self.settings=dict(provider='local',endpoint='http://localhost:11434/api/chat',model='test-model')
    def test_context_batches_preserve_source_and_timing(self):
        before=copy.deepcopy(self.doc);opener=FakeOpener();ids=[c['id'] for c in self.doc['cues']]
        result=request_suggestions(self.doc,ids,self.settings,opener=opener)
        self.assertEqual(self.doc,before);self.assertEqual(set(result),set(ids));self.assertEqual(len(opener.requests),3)
        payload=json.loads(json.loads(opener.requests[1].data)['messages'][1]['content'])
        self.assertGreater(len(payload['context']),len(payload['requested_ids']))
    def test_malformed_duplicate_and_missing_responses_rejected(self):
        ids=[c['id'] for c in self.doc['cues'][:2]]
        for transform in (lambda rows:rows[:1],lambda rows:[rows[0],rows[0]],lambda rows:[dict(id='wrong',text='x'),rows[1]]):
            with self.assertRaises(ValueError):request_suggestions(self.doc,ids,self.settings,opener=FakeOpener(transform))
    def test_endpoint_boundary_and_key_handling(self):
        for endpoint,local in [('https://example.com/api/chat',True),('http://example.com/v1/chat/completions',False),('https://key@example.com/v1/chat/completions',False)]:
            with self.assertRaises(ValueError):validate_endpoint(endpoint,local)
        settings=dict(provider='online',endpoint='https://example.com/v1/chat/completions',model='test')
        with self.assertRaises(ValueError):request_suggestions(self.doc,[self.doc['cues'][0]['id']],settings)
        opener=FakeOpener(online=True)
        request_suggestions(self.doc,[self.doc['cues'][0]['id']],settings,'test-secret',opener=opener)
        self.assertEqual(opener.requests[0].get_header('Authorization'),'Bearer test-secret')
        self.assertNotIn(b'test-secret',opener.requests[0].data)
        self.assertNotIn('test-secret',json.dumps(settings))


if __name__=='__main__':unittest.main()
