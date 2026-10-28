from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'room'))
from conversation import answer
from ordinary_room import RoomError

EVENT={'message_id':'42','at':1000,'text':'你好呀'}
class ConversationTests(unittest.TestCase):
    def test_paused_means_no_model_and_no_send(self):
        self.assertEqual(answer(EVENT,authorize=lambda:{'reply_mode':'paused','revision':1},
            complete=lambda _:self.fail('model'),send=lambda *_:self.fail('send'))['state'],'paused')
    def test_one_message_calls_model_once_and_sends_up_to_three_parts(self):
        calls=[];sent=[]
        result=answer(EVENT,authorize=lambda:{'reply_mode':'chat','revision':7},
            complete=lambda text:(calls.append(text) or ['一','二']),
            send=lambda *args:(sent.append(args) or {'state':'accepted'}))
        self.assertEqual(calls,['你好呀']);self.assertEqual(len(sent),2)
        self.assertEqual(result['results'],['accepted','accepted'])
    def test_pause_while_model_working_prevents_send(self):
        state={'reply_mode':'chat','revision':1}
        def model(_):state.update(reply_mode='paused',revision=2);return ['hello']
        result=answer(EVENT,authorize=lambda:dict(state),complete=model,send=lambda *_:self.fail('send'))
        self.assertEqual(result['state'],'paused')
    def test_uncertain_send_stops_remaining_parts(self):
        sent=[]
        result=answer(EVENT,authorize=lambda:{'reply_mode':'chat','revision':2},complete=lambda _:['a','b'],
            send=lambda *args:(sent.append(args) or {'state':'uncertain'}))
        self.assertEqual(len(sent),1);self.assertEqual(result['results'],['uncertain'])
    def test_invalid_event_or_model_output_fails_closed(self):
        for event, output in [(dict(EVENT,extra=1),['x']), (EVENT,[]), (EVENT,['x']*4), (EVENT,['x'*301])]:
            with self.subTest(event=event,output=output),self.assertRaises(RoomError):
                answer(event,authorize=lambda:{'reply_mode':'chat','revision':1},complete=lambda _:output,send=lambda *_:self.fail('send'))

if __name__=='__main__':unittest.main()
