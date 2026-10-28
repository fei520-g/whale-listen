import {test} from 'node:test';
import assert from 'node:assert/strict';
import {roomAction} from '../room/control-client.mjs';
test('Agent cannot join or dispatch arbitrary commands', async () => {
  await assert.rejects(roomAction('unused', 'join', () => assert.fail('must not call')));
});
test('leave reads current revision and uses one mutation', async () => {
  const calls = [];
  const result = await roomAction('private', 'leave', async (_, req) => {
    calls.push(req); return calls.length === 1 ? {ok: true, revision: 9} : {ok: true, accepted: true, leave_confirmed: false};
  });
  assert.equal(calls.length, 2);
  assert.equal(calls[1].action, 'leave');
  assert.equal(calls[1].expected_revision, 9);
  assert.equal(result.leave_confirmed, false);
});
test('timeout never retries a potentially accepted mutation', async () => {
  let count = 0;
  await assert.rejects(roomAction('private', 'pause', async () => {
    if (++count === 1) return {ok: true, revision: 4};
    throw new Error('lost response');
  }));
  assert.equal(count, 2);
});
