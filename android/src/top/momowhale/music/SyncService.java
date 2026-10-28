package top.momowhale.music;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.JSONObject;
public final class SyncService extends Service implements MediaTracker.Observer {
 private static volatile SyncService instance;
 public static volatile String message="尚未开始同步",lastSync="";
 public static volatile JSONObject latest;
 private final Handler main=new Handler(Looper.getMainLooper());private final ExecutorService network=Executors.newSingleThreadExecutor();
 private final AtomicBoolean busy=new AtomicBoolean();private volatile JSONObject pending;private volatile boolean stopping;private SshUploader uploader;private MediaTracker tracker;
 private final Runnable heartbeat=new Runnable(){public void run(){if(!stopping){if(tracker!=null)tracker.refresh();main.postDelayed(this,20000);}}};
 public static boolean running(){return instance!=null;}
 public static void refreshIfRunning(){SyncService s=instance;if(s!=null)s.main.post(()->{if(s.tracker!=null)s.tracker.refresh();});}
 public static void permissionLost(){SyncService s=instance;if(s!=null)s.main.post(s::onPermissionMissing);}
 @Override public void onCreate(){super.onCreate();instance=this;NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);nm.createNotificationChannel(new NotificationChannel("music-sync","音乐状态同步",NotificationManager.IMPORTANCE_LOW));
  PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
  Intent stop=new Intent(this,SyncService.class).setAction("stop");PendingIntent end=PendingIntent.getService(this,1,stop,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
  Notification n=new Notification.Builder(this,"music-sync").setSmallIcon(android.R.drawable.ic_media_play).setContentTitle("小鲸鱼·同听").setContentText("正在同步酷狗播放状态，可随时停止").setContentIntent(open).addAction(new Notification.Action.Builder(null,"停止同步",end).build()).setOngoing(true).build();startForeground(17,n);
 }
 @Override public int onStartCommand(Intent intent,int flags,int id){if(intent!=null&&"stop".equals(intent.getAction())){stopSelf();return START_NOT_STICKY;}if(tracker!=null)return START_NOT_STICKY;
  try{ConnectionConfig c=SecureConfig.load(this);if(c==null)throw new IllegalStateException("请先导入连接文件");if(!MediaTracker.permission(this))throw new IllegalStateException("请先开启通知使用权");uploader=new SshUploader(c);tracker=new MediaTracker(this,this);message="正在连接小鲸鱼";tracker.start();main.postDelayed(heartbeat,20000);}catch(Exception e){message=e.getMessage();stopSelf();}return START_NOT_STICKY;
 }
 @Override public void onState(JSONObject value){latest=value;pending=value;pump();}
 private void pump(){if(stopping||pending==null||uploader==null||!busy.compareAndSet(false,true))return;JSONObject value=pending;pending=null;network.execute(()->{try{uploader.upload(value);lastSync=new java.text.SimpleDateFormat("HH:mm:ss",java.util.Locale.CHINA).format(new java.util.Date());message="已同步到小鲸鱼";}catch(Exception e){message="同步未成功，请检查网络和连接文件";}finally{busy.set(false);if(pending!=null&&!stopping)main.postDelayed(this::pump,1200);}});}
 @Override public void onPermissionMissing(){message="通知使用权已断开，请重新开启";stopSelf();}
 @Override public void onDestroy(){stopping=true;instance=null;main.removeCallbacksAndMessages(null);if(tracker!=null)tracker.stop();if(uploader!=null){network.execute(()->{try{JSONObject j=new JSONObject();j.put("version",1);j.put("observedAtMs",System.currentTimeMillis());j.put("active",false);j.put("state","stopped");uploader.upload(j);}catch(Exception ignored){}finally{uploader.close();}});}network.shutdown();stopForeground(true);super.onDestroy();}
 @Override public IBinder onBind(Intent i){return null;}
}
