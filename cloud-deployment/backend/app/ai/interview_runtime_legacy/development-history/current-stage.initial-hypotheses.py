"""Current facts cannot borrow the time frame of another part of a question."""
import json,os
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ.get('INTERVIEW_CURRENT_STAGE_RUNTIME',ROOT/'docs/prototypes/full-interview-v1/candidate30-scoped-feedback'))

def probe(text,value,question,quote=None,field='LT01-E1'):
    code=r'''
const g=require(process.argv[1]),[text,value,question,quote,fid]=JSON.parse(process.argv[2]);
const sources=[{id:'synthetic',question_id:'LT01',speaker:'narrator',text,question}];
const refs=[{source_id:'synthetic',quote:quote||text}];
const p={control:{action:'continue',evidence:[]},fields:{[fid]:{state:'known',value,evidence:refs,scope:{subject:'self',period:'now',relation_evidence:refs}}}};
process.stdout.write(JSON.stringify(g.analyze('LT01',sources,p)));
'''
    p=subprocess.run(['node','-e',code,str(RUNTIME/'engine.js'),json.dumps([text,value,question,quote,field],ensure_ascii=False)],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)['fields'][field]

class CurrentStageTests(unittest.TestCase):
    def test_recent_action_is_not_erased_by_unselected_future_evidence(self):
        text='最近我在学木工。等搬家以后，我打算每天练琴。'
        self.assertEqual(probe(text,'最近我在学木工。','您最近做什么，搬家以后打算怎样生活？')['state'],'known')
    def test_future_frame_cannot_be_hidden_by_quoting_just_the_last_clause(self):
        text='等搬家以后，我准备每天练琴。这样能慢下来。'
        r=probe(text,'这样能慢下来。','您现在喜欢什么，搬家以后打算怎样生活？','这样能慢下来。','LT01-E2')
        self.assertNotEqual(r['state'],'known')
    def test_single_current_question_does_not_override_explicit_future_prefix(self):
        text='等我搬家后，我准备每天练琴。'
        self.assertNotEqual(probe(text,'每天练琴','您现在怎么安排日常？','每天练琴')['state'],'known')
    def test_retirement_afterword_is_not_automatically_a_future_wish(self):
        self.assertEqual(probe('退休以后我每天读书。','我每天读书','您现在怎么安排日常？')['state'],'known')
    def test_mixed_question_cannot_supply_time_for_an_unmarked_short_answer(self):
        self.assertNotEqual(probe('每天练琴。','每天练琴。','您以前做什么，现在怎样生活？')['state'],'known')
    def test_current_marker_after_past_or_future_resets_the_local_frame(self):
        text='以前我想等搬家以后练琴。最近我在学木工。'
        self.assertEqual(probe(text,'最近我在学木工。','您过去与现在的日常有什么不同？')['state'],'known')
    def test_current_marker_elsewhere_does_not_promote_a_future_selected_act(self):
        text='最近我在学木工。将来我准备每天练琴。'
        self.assertNotEqual(probe(text,'我准备每天练琴','您现在怎么生活？')['state'],'known')
    def test_a_value_mixing_current_and_future_is_still_unbound(self):
        text='最近我在学木工。将来我准备每天练琴。'
        self.assertNotEqual(probe(text,text,'您现在怎样生活？')['state'],'known')
    def test_unambiguous_actual_current_question_still_supports_an_elliptic_answer(self):
        self.assertEqual(probe('每天练琴。','每天练琴。','您现在怎么安排日常？')['state'],'known')
    def test_actual_current_question_remains_valid_even_with_an_uncited_redundant_marker(self):
        self.assertEqual(probe('最近我在学木工。','学木工','您现在怎么安排日常？','学木工')['state'],'known')
    def test_uncited_current_marker_does_not_become_silent_positive_evidence(self):
        text='最近我在学木工。'
        self.assertNotEqual(probe(text,'学木工','您以前与现在都有哪些爱好？','学木工')['state'],'known')

if __name__=='__main__':unittest.main()
