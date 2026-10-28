import net from 'node:net';
import {randomUUID} from 'node:crypto';
import {StringDecoder} from 'node:string_decoder';

export function exchange(socketPath, request) {
  return new Promise((resolve, reject) => {
    const conn = net.createConnection(socketPath);
    let data = '', bytes = 0, done = false;
    const decoder = new StringDecoder('utf8');
    const finish = (err, value) => {
      if (done) return;
      done = true;
      conn.destroy();
      err ? reject(new Error('room_control_unavailable')) : resolve(value);
    };
    conn.setTimeout(22000, () => finish(true));
    conn.on('error', () => finish(true));
    conn.on('connect', () => conn.write(JSON.stringify(request) + '\n'));
    conn.on('data', chunk => {
      bytes += chunk.length;
      data += decoder.write(chunk);
      if (bytes > 4096) return finish(true);
      if (data.includes('\n')) {
        try {
          const value = JSON.parse(data.split('\n')[0]);
          if (typeof value.ok !== 'boolean') return finish(true);
          finish(null, value);
        } catch { finish(true); }
      }
    });
    conn.on('end', () => finish(true));
  });
}

export async function roomAction(path, action, call = exchange) {
  if (!['status', 'pause', 'leave'].includes(action)) throw new Error('unsupported_action');
  const state = await call(path, {version: 1, action: 'status'});
  if (action === 'status' || !state.ok) return state;
  if (!Number.isSafeInteger(state.revision)) throw new Error('invalid_revision');
  // No retry of a mutation after timeout. Requery status explicitly instead.
  return call(path, {version: 1, action, request_id: randomUUID(), expected_revision: state.revision});
}
