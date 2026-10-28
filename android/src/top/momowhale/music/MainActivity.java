package top.momowhale.music;
import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;
public final class MainActivity extends Activity {
 private final Handler handler=new Handler();private TextView song,detail,status,steps,connection;private Button toggle;private boolean visible;
 private final Runnable repaint=new Runnable(){public void run(){if(visible){refresh();handler.postDelayed(this,1000);}}};
 private int dp(int n){return (int)(n*getResources().getDisplayMetrics().density+.5f);}
 private TextView text(String value,int size,int color){TextView v=new TextView(this);v.setText(value);v.setTextSize(size);v.setTextColor(color);v.setPadding(0,dp(5),0,dp(5));return v;}
 private GradientDrawable box(int color){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(18));return d;}
 private LinearLayout column(){LinearLayout c=new LinearLayout(this);c.setOrientation(LinearLayout.VERTICAL);return c;}
 private void button(LinearLayout parent,String label,View.OnClickListener action){Button b=new Button(this);b.setText(label);b.setTextColor(Color.WHITE);b.setAllCaps(false);b.setBackground(box(Color.rgb(48,101,160)));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(54));lp.setMargins(0,dp(10),0,0);parent.addView(b,lp);b.setOnClickListener(action);}
 @Override public void onCreate(Bundle b){super.onCreate(b);getWindow().setStatusBarColor(Color.rgb(235,245,253));getWindow().setNavigationBarColor(Color.rgb(235,245,253));getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
  ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setBackgroundColor(Color.rgb(235,245,253));LinearLayout root=column();root.setPadding(dp(24),dp(28),dp(24),dp(28));scroll.addView(root);setContentView(scroll);
  root.addView(text("WHALE · LISTEN TOGETHER",12,Color.rgb(87,131,172)));TextView title=text("小鲸鱼 · 同听",29,Color.rgb(26,61,106));title.setTypeface(null,Typeface.BOLD);root.addView(title);root.addView(text("把此刻的音乐，分享给她。",15,Color.rgb(93,114,139)));
  LinearLayout card=column();card.setPadding(dp(20),dp(18),dp(20),dp(18));card.setBackground(box(Color.WHITE));LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(-1,-2);cp.setMargins(0,dp(24),0,dp(12));root.addView(card,cp);
  card.addView(text("酷狗音乐 · 当前播放",12,Color.rgb(80,123,165)));song=text("等一首歌",23,Color.rgb(30,65,110));song.setTypeface(null,Typeface.BOLD);card.addView(song);detail=text("开始播放酷狗，再开启同步。",15,Color.rgb(102,121,144));card.addView(detail);status=text("尚未开始同步",14,Color.rgb(51,114,164));card.addView(status);
  connection=text("连接文件：未导入",14,Color.rgb(73,94,120));root.addView(connection);steps=text("",14,Color.rgb(73,94,120));root.addView(steps);
  button(root,"1  导入私人连接文件",v->{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.setType("*/*");i.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(i,10);});
  button(root,"2  开启通知使用权",v->startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
  toggle=new Button(this);toggle.setText("3  开始同步");toggle.setAllCaps(false);toggle.setTextColor(Color.WHITE);toggle.setBackground(box(Color.rgb(48,101,160)));LinearLayout.LayoutParams bp=new LinearLayout.LayoutParams(-1,dp(54));bp.setMargins(0,dp(10),0,dp(16));root.addView(toggle,bp);toggle.setOnClickListener(v->toggle());
  button(root,"同听房间",v->startActivity(new Intent(this,RoomControlActivity.class)));
  root.addView(text("同步提供歌名、歌手和播放进度。",13,Color.rgb(91,114,140)));
  root.addView(text("锁屏后若同步停止，请在系统电池设置中允许本应用后台运行。关闭同步后，云端旧状态最多 90 秒就会过期。",13,Color.rgb(91,114,140)));
  TextView clear=text("清除本机连接配置",13,Color.rgb(115,121,132));clear.setPadding(0,dp(20),0,dp(8));root.addView(clear);clear.setOnClickListener(v->new AlertDialog.Builder(this).setMessage("停止同步并清除这台手机保存的连接信息？").setPositiveButton("清除",(d,w)->{stopService(new Intent(this,SyncService.class));SecureConfig.clear(this);refresh();}).setNegativeButton("取消",null).show());
  TextView licenses=text("第三方许可",12,Color.rgb(115,121,132));root.addView(licenses);licenses.setOnClickListener(v->{try(InputStream in=getAssets().open("licenses/LICENSE.txt");ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] buffer=new byte[2048];int n;while((n=in.read(buffer))>0)out.write(buffer,0,n);alert(new String(out.toByteArray(),StandardCharsets.UTF_8));}catch(Exception e){alert("JSch：BSD 许可证。完整授权文件随源代码附带。");}});
 }
 private void toggle(){if(SyncService.running()){stopService(new Intent(this,SyncService.class));return;}try{if(SecureConfig.load(this)==null){alert("请先导入私人连接文件。");return;}if(!MediaTracker.permission(this)){alert("请先在通知使用权设置中开启小鲸鱼·酷狗播放状态。");return;}if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=getPackageManager().PERMISSION_GRANTED){requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},20);return;}startForegroundService(new Intent(this,SyncService.class));}catch(Exception e){alert("连接文件无法读取，请重新导入。");}}
 private void alert(String message){new AlertDialog.Builder(this).setMessage(message).setPositiveButton("知道了",null).show();}
 @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] grants){super.onRequestPermissionsResult(request,permissions,grants);if(request==20){if(grants.length>0&&grants[0]==android.content.pm.PackageManager.PERMISSION_GRANTED)toggle();else alert("可以在系统应用设置里允许通知，再开始同步。");}}
 @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request!=10||result!=RESULT_OK||data==null)return;try(InputStream in=getContentResolver().openInputStream(data.getData());ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[1024];int n;while((n=in.read(b))>0){out.write(b,0,n);if(out.size()>16384)throw new IllegalArgumentException();}stopService(new Intent(this,SyncService.class));SecureConfig.save(this,new String(out.toByteArray(),StandardCharsets.UTF_8));alert("连接信息已加密保存在本机。开启通知使用权后即可同步。");}catch(Exception e){alert("导入失败，请选择提供给你的私人连接文件。");}}
 private static String time(long ms){long seconds=Math.max(0,ms/1000);return String.format(java.util.Locale.CHINA,"%d:%02d",seconds/60,seconds%60);}
 private void refresh(){boolean configured=false;try{configured=SecureConfig.load(this)!=null;}catch(Exception ignored){}connection.setText("连接文件："+(configured?"已导入 · 本机加密保存":"未导入"));boolean permission=MediaTracker.permission(this);steps.setText("通知使用权："+(permission?"已开启":"待开启"));toggle.setText(SyncService.running()?"停止同步":"3  开始同步");status.setText(SyncService.running()?SyncService.message+(SyncService.lastSync.isEmpty()?"":" · "+SyncService.lastSync):"同步未启动");JSONObject j=SyncService.running()?SyncService.latest:null;if(j==null||!j.optBoolean("active")){song.setText("等一首歌");detail.setText("请在酷狗播放歌曲，再开始同步。");return;}song.setText(j.optString("title").isEmpty()?"酷狗未提供歌名":j.optString("title"));String state=j.optString("state"),label="playing".equals(state)?"播放中":"paused".equals(state)?"已暂停":"buffering".equals(state)?"缓冲中":"stopped".equals(state)?"已停止":"状态未知";detail.setText(j.optString("artist")+"\n"+label+"  ·  "+(j.isNull("positionMs")?"进度未提供":time(j.optLong("positionMs")))+(j.isNull("durationMs")?"":" / "+time(j.optLong("durationMs"))));}
 @Override protected void onResume(){super.onResume();visible=true;handler.post(repaint);}
 @Override protected void onPause(){super.onPause();visible=false;handler.removeCallbacks(repaint);}
}
