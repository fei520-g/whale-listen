import {McpServer} from '@modelcontextprotocol/sdk/server/mcp.js';
import {StdioServerTransport} from '@modelcontextprotocol/sdk/server/stdio.js';
import {roomAction} from './control-client.mjs';
const socket = process.env.WHALE_ROOM_SOCKET || '/run/whale-kugou-control/control.sock';
const server = new McpServer({name: 'whale-room', version: '0.2.0'});
for (const [name, action, description] of [
  ['get_room_status', 'status', '查看酷狗房间状态。没有音频输入，不得声称听到了声音。'],
  ['leave_room', 'leave', '仅在主人明确要求你退出酷狗同听时调用。停止心跳、暂停回复并退出自己的成员身份，不关闭房主房间。accepted 只表示指令已保存，只有 leave_confirmed=true 才可说已确认离开；否则如实说正在退出或尚未确认。'],
  ['pause_room_replies', 'pause', '主人要求暂停酷狗回复时调用。不退出房间，不影响 QQ。当前版本自动闲聊尚未开放。'],
]) {
  server.tool(name, description, {}, async () => {
    try {
      const result = await roomAction(socket, action);
      return {isError: !result.ok, content: [{type: 'text', text: JSON.stringify(result)}]};
    } catch {
      return {isError: true, content: [{type: 'text', text: JSON.stringify({ok: false,
        error: 'room_control_unavailable', confirmed: false,
        message: '房间控制暂时不可用，不能声称操作已成功。'})}]};
    }
  });
}
await server.connect(new StdioServerTransport());
