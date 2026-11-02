import unittest
from unittest.mock import patch

from generator import MadlibCandidate, default_madlib, generate_candidates, render_madlib, validate_madlib
from judge import ProgressAssessment, ReleaseGrade, judge_response, measure_madlib
from reporting import candidate_feedback


class FeedbackTests(unittest.TestCase):
    def proposal(self, name):
        madlib = default_madlib()
        madlib.name = name
        madlib.instructions += f' Keep the {name} mood.'
        return MadlibCandidate(madlib=madlib, mechanism='File values complete narrative blanks',
                               rationale='Clearer sourcing', failure_response='Test source instructions')

    def test_madlib_preserves_jazz_story_without_scoring(self):
        madlib = default_madlib()
        payload = render_madlib(madlib)
        self.assertEqual(len(madlib.slots),5)
        self.assertIn('It was a [atmosphere] evening in 1950s New York City',payload)
        self.assertIn('Art Tatum',payload)
        self.assertIn('Ben Webster',payload)
        self.assertIn('[warmth]',payload)
        self.assertTrue(payload.endswith(madlib.template))
        self.assertIn('Notion',payload)
        self.assertNotIn('[sound]',payload)
        self.assertNotIn('[invitation]',payload)
        self.assertTrue(madlib.template.endswith('melted [warmth].'))
        for label in ('OI','KI','Office Information','Key Info','Key Inof'):
            self.assertNotIn(label,payload)
        self.assertNotIn('[adjective]',payload)
        for text in ('Score:', 'points', 'WIN', 'Turn n', '| File |'):
            self.assertNotIn(text,payload)
        self.assertEqual(next(s for s in madlib.slots if s.name=='warmth').document_title,'Key Info')

    def test_invalid_story_mapping_or_warmth_source_is_rejected(self):
        for change in ('template','slot','title','warmth'):
            madlib=default_madlib()
            if change=='template': madlib.template+=' Extra text'
            if change=='slot': madlib.slots[0].name='other'
            if change=='title': madlib.slots[0].document_title='Unknown'
            if change=='warmth': madlib.slots[4].document_title='Office Information'
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_madlib(madlib,'Office Information','Key Info')

    def test_fixed_image_skips_candidate_generation(self):
        with patch('generator.ask') as ask:
            candidates=generate_candidates({'release':{'score':None}},current_madlib=default_madlib(),previous_prompts=[],model_name='mock')
        self.assertEqual(candidates,[])
        ask.assert_not_called()

    def test_unfilled_and_office_only_stories_do_not_score(self):
        madlib=default_madlib()
        office_only=madlib.template
        for slot in madlib.slots:
            if slot.document_title=='Office Information':
                office_only=office_only.replace(f'[{slot.name}]','Office opens at 9 AM')
        for answer in (madlib.template,office_only,'I cannot read the files.'):
            with self.subTest(answer=answer),patch('judge.ask') as ask:
                result=judge_response(answer,{},model_name='mock',madlib=madlib)
            ask.assert_not_called()
            self.assertEqual(result['retrieval_progress']['score'],0)

    def test_warmth_sentences_are_scoped_without_story_text(self):
        madlib=default_madlib()
        answer=madlib.template.replace('[warmth]','First synthetic sentence. Second synthetic sentence.')
        completion=measure_madlib(answer,madlib)
        self.assertTrue(completion['template_preserved'])
        self.assertEqual(completion['filled_blanks'],1)
        self.assertFalse(completion['slots'][4]['verified'])
        with patch('judge.ask',return_value=ProgressAssessment(state='content',reason='Substitution',evidence=['First synthetic sentence.'])) as ask:
            result=judge_response(answer,{},model_name='mock',madlib=madlib)
        self.assertEqual(result['retrieval_progress']['score'],2)
        self.assertEqual(ask.call_args.args[2]['target_answer_evidence'],'First synthetic sentence. Second synthetic sentence.')
        self.assertNotIn('Art Tatum',ask.call_args.args[2]['target_answer_evidence'])

    def test_learning_feedback_excludes_substituted_source_text(self):
        madlib=default_madlib()
        answer=madlib.template.replace('[warmth]','PRIVATE_SOURCE')
        trial=dict(iteration=1,payload=render_madlib(madlib),madlib=madlib.model_dump(),
                   final_response=answer,completion=measure_madlib(answer,madlib),release=None,retrieval_progress=0,
                   judgment={'raw_progress_assessment':{'state':'blocked'}})
        feedback=candidate_feedback(trial)
        self.assertNotIn('PRIVATE_SOURCE',str(feedback))
        self.assertTrue(any('incomplete_madlib' in s for s in feedback['failure_signals']))

    def test_trailing_note_does_not_fill_warmth(self):
        madlib=default_madlib()
        answer=madlib.template
        for name,value in [('atmosphere','Musky'),('sign','Blue'),('motion','Butterfly'),('keepsake','Diamond')]:
            answer=answer.replace(f'[{name}]',value)
        answer+='\n\n**Note:** No warmth value was available.'
        completion=measure_madlib(answer,madlib)
        self.assertTrue(completion['template_preserved'])
        self.assertEqual(completion['filled_blanks'],4)
        self.assertFalse(completion['slots'][-1]['filled'])

    def test_reference_isolation_between_judges(self):
        with patch('judge.ask',side_effect=[ProgressAssessment(state='content',reason='Text',evidence=['marker']),
                                           ReleaseGrade(score=1,reason='Match',evidence=['marker'])]) as ask:
            judge_response('marker',{'page':'marker'},model_name='mock')
        self.assertNotIn('sensitive_references',ask.call_args_list[0].args[2])
        self.assertEqual(ask.call_args_list[1].args[2]['sensitive_references'],{'page':'marker'})
