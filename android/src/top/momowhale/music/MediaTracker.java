package top.momowhale.music;
import android.content.ComponentName;
import android.content.Context;
import android.media.MediaMetadata;
import android.media.session.MediaController;
import android.media.session.MediaSessionManager;
import android.media.session.PlaybackState;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONObject;
public final class MediaTracker {
 public interface Observer {void onState(JSONObject value);void onPermissionMissing();}
 private final Context context;private final Observer observer;private final Handler handler=new Handler(Looper.getMainLooper());
 private final MediaSessionManager manager;private final List<MediaController> controllers=new ArrayList<>();
 private final MediaController.Callback callback=new MediaController.Callback(){@Override public void onMetadataChanged(MediaMetadata m){snapshot();}@Override public void onPlaybackStateChanged(PlaybackState s){snapshot();}@Override public void onSessionDestroyed(){refresh();}};
 private final MediaSessionManager.OnActiveSessionsChangedListener listener=items->setControllers(items);
 public MediaTracker(Context c,Observer o){context=c;observer=o;manager=(MediaSessionManager)c.getSystemService(Context.MEDIA_SESSION_SERVICE);}
 public static boolean permission(Context c){String raw=Settings.Secure.getString(c.getContentResolver(),"enabled_notification_listeners");String name=new ComponentName(c,MusicListener.class).flattenToString();if(raw==null)return false;for(String p:raw.split(":")){ComponentName n=ComponentName.unflattenFromString(p);if(n!=null&&n.equals(ComponentName.unflattenFromString(name)))return true;}return false;}
 public static boolean isKugou(String pkg){return "com.kugou.android".equals(pkg)||"com.kugou.android.lite".equals(pkg);}
 public void start(){try{manager.addOnActiveSessionsChangedListener(listener,new ComponentName(context,MusicListener.class),handler);refresh();}catch(SecurityException e){observer.onPermissionMissing();}}
 public void stop(){try{manager.removeOnActiveSessionsChangedListener(listener);}catch(Exception ignored){}for(MediaController c:controllers)c.unregisterCallback(callback);controllers.clear();}
 public void refresh(){try{setControllers(manager.getActiveSessions(new ComponentName(context,MusicListener.class)));}catch(SecurityException e){observer.onPermissionMissing();}}
 private void setControllers(List<MediaController> items){for(MediaController c:controllers)c.unregisterCallback(callback);controllers.clear();if(items!=null)for(MediaController c:items)if(isKugou(c.getPackageName())){controllers.add(c);c.registerCallback(callback,handler);}snapshot();}
 private MediaController selected(){MediaController best=null;int rank=-1;for(MediaController c:controllers){PlaybackState p=c.getPlaybackState();int s=p==null?0:p.getState();int r=s==PlaybackState.STATE_PLAYING?3:s==PlaybackState.STATE_BUFFERING?2:s==PlaybackState.STATE_PAUSED?1:0;if(r>rank){rank=r;best=c;}}return best;}
 public void snapshot(){
  try{
   MediaController c=selected();JSONObject j=new JSONObject();j.put("version",1);j.put("observedAtMs",System.currentTimeMillis());j.put("active",c!=null);
   if(c==null){j.put("state","stopped");observer.onState(j);return;}
   MediaMetadata m=c.getMetadata();PlaybackState p=c.getPlaybackState();int state=p==null?0:p.getState();
   String status=state==PlaybackState.STATE_PLAYING?"playing":state==PlaybackState.STATE_PAUSED?"paused":state==PlaybackState.STATE_BUFFERING?"buffering":state==PlaybackState.STATE_STOPPED||state==PlaybackState.STATE_NONE?"stopped":"unknown";
   j.put("package",c.getPackageName());j.put("state",status);j.put("title",value(m,MediaMetadata.METADATA_KEY_TITLE));j.put("artist",value(m,MediaMetadata.METADATA_KEY_ARTIST));j.put("album",value(m,MediaMetadata.METADATA_KEY_ALBUM));
   long duration=m!=null&&m.containsKey(MediaMetadata.METADATA_KEY_DURATION)?m.getLong(MediaMetadata.METADATA_KEY_DURATION):-1;
   long position=p==null?-1:p.getPosition();float speed=p==null?0:p.getPlaybackSpeed();if(!Float.isFinite(speed)||speed<0||speed>4)speed=0;
   if(position>=0&&state==PlaybackState.STATE_PLAYING&&p.getLastPositionUpdateTime()>0)position+=(long)(Math.max(0,SystemClock.elapsedRealtime()-p.getLastPositionUpdateTime())*speed);
   if(position>=0&&duration>0)position=Math.min(position,duration);
   j.put("positionMs",position<0?JSONObject.NULL:position);j.put("durationMs",duration<=0?JSONObject.NULL:duration);j.put("speed",speed);observer.onState(j);
  }catch(Exception e){observer.onPermissionMissing();}
 }
 private String value(MediaMetadata m,String key){String s=m==null?null:m.getString(key);if(s==null)return "";return s.length()>240?s.substring(0,240):s;}
}
