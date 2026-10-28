package top.momowhale.music;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.UUID;
import org.json.JSONObject;

/** Explicit share and room controls; never reads the clipboard. */
public final class RoomControlActivity extends Activity {
 private TextView status;private EditText inviteInput;private String invite;private boolean busy;
 private int dp(int value){return (int)(value*getResources().getDisplayMetrics().density+.5f);}
 @Override public void onCreate(Bundle state){
  super.onCreate(state);
  ScrollView scroll=new ScrollView(this);LinearLayout content=new LinearLayout(this);
  content.setPadding(dp(24),dp(24),dp(24),dp(24));content.setOrientation(LinearLayout.VERTICAL);scroll.addView(content);setContentView(scroll);
  TextView title=new TextView(this);title.setText("小鲸鱼 · 同听房间");title.setTextSize(24);content.addView(title);
  status=new TextView(this);status.setTextSize(16);status.setPadding(0,dp(20),0,dp(12));
  status.setText("在酷狗开房，复制邀请链接，粘贴到下方并确认加入。\n点击“刷新状态”查看房间。 ");content.addView(status);
  add(content,"刷新状态",()->request("status",null));
  inviteInput=new EditText(this);inviteInput.setHint("在这里粘贴酷狗同听邀请链接");inviteInput.setMinHeight(dp(50));content.addView(inviteInput);
  add(content,"使用粘贴的邀请加入",()->{
   try{invite=SharedRoomLink.parse(inviteInput.getText().toString());inviteInput.setText("");confirmJoin();}
   catch(Exception e){notice("没有识别到邀请链接。请在酷狗的同听房间点“邀请好友”并复制链接，再粘贴到这里。");}
  });
  add(content,"加入分享到本应用的邀请",this::confirmJoin);
  add(content,"开启房间闲聊",()->new AlertDialog.Builder(this)
   .setMessage("开启后，小鲸鱼会读取这个双人房间里的新文字并回复。其他人进入时会暂停私人回复；你可以随时暂停。")
   .setPositiveButton("开启",(d,w)->request("chat",null)).setNegativeButton("取消",null).show());
  add(content,"暂停房间回复",()->request("pause",null));
  add(content,"让小鲸鱼退出同听",()->new AlertDialog.Builder(this)
   .setMessage("小鲸鱼会停止同听；你的房间和歌曲同步不受影响。")
   .setPositiveButton("退出",(d,w)->request("leave",null)).setNegativeButton("取消",null).show());
  accept(getIntent());
 }
 private void confirmJoin(){
  if(invite==null){notice("请先粘贴邀请链接，或在酷狗分享给“小鲸鱼·同听”。");return;}
  final String selected=invite;
  new AlertDialog.Builder(this).setMessage("让小鲸鱼专用号加入这个房间？会先核对房主账号。")
   .setPositiveButton("加入",(d,w)->request("join",selected)).setNegativeButton("取消",null).show();
 }
 private void add(LinearLayout parent,String text,Runnable action){
  Button button=new Button(this);button.setAllCaps(false);button.setText(text);button.setMinHeight(dp(50));
  LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.setMargins(0,dp(8),0,0);parent.addView(button,lp);button.setOnClickListener(v->action.run());
 }
 private void notice(String message){new AlertDialog.Builder(this).setMessage(message).setPositiveButton("知道了",null).show();}
 @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);accept(intent);}
 private void accept(Intent intent){
  if(intent==null||!Intent.ACTION_SEND.equals(intent.getAction())||!"text/plain".equals(intent.getType()))return;
  try{invite=SharedRoomLink.parse(intent.getStringExtra(Intent.EXTRA_TEXT));status.setText("已收到邀请。点击“加入收到的邀请”确认。");}
  catch(Exception e){invite=null;notice("没有识别到酷狗普通版的同听邀请，请重新分享完整链接。");}
  intent.removeExtra(Intent.EXTRA_TEXT);intent.setAction(null);
 }
 private void request(String action,String link){
  if(busy)return;busy=true;status.setText("正在连接房间控制…");
  new Thread(()->{
   SshUploader uploader=null;String result;
   try{
    ConnectionConfig config=SecureConfig.loadRoom(this);
    if(config==null)throw new IllegalStateException("需要先导入包含房间控制的新连接文件；原来的歌曲同步仍可使用。");
    uploader=new SshUploader(config);
    JSONObject response=uploader.room(new JSONObject().put("version",1).put("action","status"));
    if(!"status".equals(action)){
     JSONObject command=new JSONObject().put("version",1).put("action",action).put("request_id",UUID.randomUUID().toString()).put("expected_revision",response.getInt("revision"));
     if("join".equals(action))command.put("invite",link);
     response=uploader.room(command);
    }
    result=describe(response);
   }catch(IllegalStateException e){result=e.getMessage();}
   catch(Exception e){result="房间控制暂时不可用，操作结果未确认。请刷新状态，不要反复点击加入。";}
   finally{if(uploader!=null)uploader.close();}
   final String displayed=result;runOnUiThread(()->{busy=false;if(!isDestroyed())status.setText(displayed);});
  },"whale-room-control").start();
 }
 private String describe(JSONObject state){
  String value=state.optString("state"),label;
  switch(value){
   case "left":label=state.optBoolean("leave_confirmed")?"已确认退出同听":"未连接房间";break;
   case "online":label="小鲸鱼已在房间 · "+("chat".equals(state.optString("reply_mode"))?"同听并闲聊":"只同听");break;
   case "joining":label="加入指令已保存，正在核对房间；请稍后刷新";break;
   case "leaving":label="退出指令已保存，正在核对是否离开";break;
   case "leave_unconfirmed":label="已停止心跳，退出结果尚未确认";break;
   case "retrying":label="网络暂时不可用，正在核对房间状态";break;
   default:label="房间状态未知，请刷新";
  }
  String note=state.optBoolean("chat_available")?"可以选择开启或暂停房间闲聊。":"自动闲聊暂未开放。";
  String error=state.optString("error","");
  return label+"\n"+note+" 她目前没有音乐音频输入。"+(error.isEmpty()?"":"\n"+error);
 }
}
